import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from bson.errors import InvalidId
from bson.objectid import ObjectId
from pymongo import ReturnDocument

from database import (
    post_history_collection,
    quote_list_cursors_collection,
    quote_helper,
    quotes_collection,
)
from models.schedule import QuoteSelectionMode

logger = logging.getLogger(__name__)

RECENT_POST_WINDOW = timedelta(hours=24)


async def _load_quote_list(quote_list_id: str | None) -> list[dict]:
    query: dict[str, Any] = {}
    if quote_list_id:
        query["quoteListId"] = quote_list_id

    quotes: list[dict] = []
    async for doc in quotes_collection.find(query).sort("_id", 1):
        quotes.append(doc)

    if not quotes and quote_list_id:
        async for doc in quotes_collection.find({}).sort("_id", 1):
            quotes.append(doc)

    return quotes


async def _was_posted_recently(
    quote_id: str, page_ids: list[str], now: datetime
) -> bool:
    cutoff = now - RECENT_POST_WINDOW
    existing = await post_history_collection.find_one(
        {
            "quoteId": quote_id,
            "pageId": {"$in": page_ids},
            "postedAt": {"$gte": cutoff},
        }
    )
    return existing is not None


async def _get_last_posted_author(page_ids: list[str]) -> str | None:
    last_post = await post_history_collection.find_one(
        {"pageId": {"$in": page_ids}},
        sort=[("postedAt", -1)],
    )
    if not last_post:
        return None

    quote_id = last_post.get("quoteId")
    if not quote_id:
        return None

    try:
        quote_doc = await quotes_collection.find_one({"_id": ObjectId(quote_id)})
    except InvalidId:
        return None

    if not quote_doc:
        return None

    return quote_doc.get("author", "Unknown")


async def _reserve_next_index(quote_list_id: str, list_size: int, now: datetime) -> int:
    await quote_list_cursors_collection.update_one(
        {"quoteListId": quote_list_id},
        {"$setOnInsert": {"quoteListId": quote_list_id, "lastIndex": -1}},
        upsert=True,
    )
    doc = await quote_list_cursors_collection.find_one_and_update(
        {"quoteListId": quote_list_id},
        {
            "$inc": {"lastIndex": 1},
            "$set": {"updatedAt": now},
        },
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise RuntimeError(f"Failed to advance cursor for quote list {quote_list_id}")
    return int(doc["lastIndex"]) % list_size


async def _set_cursor_index(quote_list_id: str, index: int, now: datetime) -> None:
    await quote_list_cursors_collection.update_one(
        {"quoteListId": quote_list_id},
        {"$set": {"lastIndex": index, "updatedAt": now}},
        upsert=True,
    )


async def _pick_sequential(
    quotes: list[dict],
    list_key: str,
    page_ids: list[str],
    now: datetime,
) -> tuple[dict, int]:
    start_index = await _reserve_next_index(list_key, len(quotes), now)
    chosen_index = start_index

    for offset in range(len(quotes)):
        candidate_index = (start_index + offset) % len(quotes)
        candidate = quotes[candidate_index]
        candidate_id = str(candidate["_id"])

        if not await _was_posted_recently(candidate_id, page_ids, now):
            chosen_index = candidate_index
            break

        logger.info(
            "Skipping quote %s at index %s — posted to %s within last 24h",
            candidate_id,
            candidate_index,
            page_ids,
        )
    else:
        logger.warning(
            "All quotes in list %s were posted within 24h; reusing index %s",
            list_key,
            start_index,
        )
        chosen_index = start_index

    if chosen_index != start_index:
        await _set_cursor_index(list_key, chosen_index, now)

    return quotes[chosen_index], chosen_index


async def _pick_random_by_author(
    quotes: list[dict],
    page_ids: list[str],
    now: datetime,
) -> tuple[dict, int]:
    eligible: list[dict] = []
    for quote in quotes:
        quote_id = str(quote["_id"])
        if not await _was_posted_recently(quote_id, page_ids, now):
            eligible.append(quote)

    if not eligible:
        logger.warning(
            "All quotes were posted within 24h for pages %s; choosing from full list",
            page_ids,
        )
        eligible = quotes

    by_author: dict[str, list[dict]] = {}
    for quote in eligible:
        author = quote.get("author", "Unknown")
        by_author.setdefault(author, []).append(quote)

    last_author = await _get_last_posted_author(page_ids)
    authors = list(by_author.keys())
    if last_author and len(authors) > 1:
        different_authors = [author for author in authors if author != last_author]
        chosen_author = random.choice(different_authors or authors)
    else:
        chosen_author = random.choice(authors)

    selected = random.choice(by_author[chosen_author])
    chosen_index = quotes.index(selected)
    logger.info(
        "Random-by-author pick: author=%s index=%s quoteId=%s",
        chosen_author,
        chosen_index,
        str(selected["_id"]),
    )
    return selected, chosen_index


async def get_next_quote(
    quote_list_id: str | None,
    page_ids: list[str],
    now: datetime | None = None,
    selection_mode: QuoteSelectionMode = "sequential",
) -> dict:
    """Pick the next quote using the configured selection mode and 24h page dedup."""
    now = now or datetime.now(tz=timezone.utc)
    list_key = quote_list_id or "__all__"
    quotes = await _load_quote_list(quote_list_id)

    if not quotes:
        raise RuntimeError("No quotes available to post")

    if selection_mode == "random_by_author":
        selected, chosen_index = await _pick_random_by_author(quotes, page_ids, now)
    elif selection_mode == "sequential":
        selected, chosen_index = await _pick_sequential(quotes, list_key, page_ids, now)
    else:
        exhaustive: QuoteSelectionMode = selection_mode
        raise ValueError(f"Unsupported selection mode: {exhaustive}")

    result = quote_helper(selected)
    result["listIndex"] = chosen_index
    result["quoteListId"] = list_key
    return result


async def record_successful_post(
    *,
    quote_list_id: str | None,
    quote_id: str,
    page_id: str,
    schedule_id: str,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(tz=timezone.utc)
    await post_history_collection.insert_one(
        {
            "quoteListId": quote_list_id or "__all__",
            "quoteId": quote_id,
            "pageId": page_id,
            "scheduleId": schedule_id,
            "postedAt": now,
        }
    )
