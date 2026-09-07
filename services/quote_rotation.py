import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo import ReturnDocument

from database import (
    post_history_collection,
    quote_list_cursors_collection,
    quote_helper,
    quotes_collection,
)
from models.schedule import OrderType

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


async def choose_next_quote_id(
    quotes: list[dict],
    list_key: str,
    page_ids: list[str],
    now: datetime,
) -> tuple[dict, int]:
    """Sequential cursor through list position order with 24h same-page dedupe."""
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


async def _choose_random_quote_id(
    quotes: list[dict],
    page_ids: list[str],
    now: datetime,
) -> tuple[dict, int]:
    """Uniform random among quotes not posted to these pages within 24h."""
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

    selected = random.choice(eligible)
    chosen_index = quotes.index(selected)
    logger.info(
        "Random pick: author=%s index=%s quoteId=%s",
        selected.get("author", "Unknown"),
        chosen_index,
        str(selected["_id"]),
    )
    return selected, chosen_index


async def choose_quote_id(
    quote_list_id: str | None,
    page_ids: list[str],
    order_type: OrderType = "sequential",
    now: datetime | None = None,
) -> dict:
    """Pick the next quote honoring schedule.orderType and 24h same-page dedupe."""
    now = now or datetime.now(tz=timezone.utc)
    list_key = quote_list_id or "__all__"
    quotes = await _load_quote_list(quote_list_id)

    if not quotes:
        raise RuntimeError("No quotes available to post")

    if order_type == "random":
        selected, chosen_index = await _choose_random_quote_id(quotes, page_ids, now)
    elif order_type == "sequential":
        selected, chosen_index = await choose_next_quote_id(
            quotes, list_key, page_ids, now
        )
    else:
        exhaustive: OrderType = order_type
        raise ValueError(f"Unsupported orderType: {exhaustive}")

    result = quote_helper(selected)
    result["listIndex"] = chosen_index
    result["quoteListId"] = list_key
    return result


async def get_next_quote(
    quote_list_id: str | None,
    page_ids: list[str],
    now: datetime | None = None,
    order_type: OrderType = "sequential",
) -> dict:
    """Backward-compatible alias for choose_quote_id."""
    return await choose_quote_id(quote_list_id, page_ids, order_type, now)


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
