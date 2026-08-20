import logging
import random
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from database import quotes_collection, schedules_collection, quote_helper
from models.schedule import Schedule
from services.facebook import FacebookPostError, post_to_facebook
from services.post_formatter import format_quote_post
from services.x_twitter import XPostError, post_to_x

logger = logging.getLogger(__name__)

X_DESTINATION = "x"


async def _get_random_quote(quote_list_id: str | None) -> dict:
    query: dict[str, Any] = {}
    if quote_list_id:
        query["quoteListId"] = quote_list_id

    total = await quotes_collection.count_documents(query)
    if total == 0 and quote_list_id:
        total = await quotes_collection.count_documents({})
        query = {}

    if total == 0:
        raise RuntimeError("No quotes available to post")

    offset = random.randint(0, total - 1)
    docs = await quotes_collection.find(query).skip(offset).to_list(length=1)
    if not docs:
        raise RuntimeError("Failed to fetch a random quote")
    return quote_helper(docs[0])


def _schedule_is_due(schedule: Schedule, now: datetime) -> bool:
    tz = ZoneInfo(schedule.timezone)
    local_now = now.astimezone(tz)
    return local_now.hour == schedule.hour and local_now.minute == schedule.minute


async def _load_schedules() -> list[Schedule]:
    schedules: list[Schedule] = []
    async for doc in schedules_collection.find({"enabled": True}):
        schedules.append(
            Schedule(
                id=str(doc.get("id") or doc.get("_id")),
                name=doc["name"],
                hour=doc["hour"],
                minute=doc["minute"],
                timezone=doc.get("timezone", "America/Chicago"),
                pageIds=doc.get("pageIds", []),
                quoteListId=doc.get("quoteListId"),
                enabled=doc.get("enabled", True),
            )
        )
    return schedules


async def _post_to_destination(page_id: str, message: str) -> dict:
    if page_id == X_DESTINATION:
        return await post_to_x(message)
    return await post_to_facebook(page_id, message)


async def run_due_schedules(now: datetime | None = None) -> dict:
    """Run all schedules due at the current minute and fan out to each pageId."""
    now = now or datetime.now(tz=ZoneInfo("UTC"))
    schedules = await _load_schedules()
    due = [schedule for schedule in schedules if _schedule_is_due(schedule, now)]

    run_results: list[dict] = []
    had_failures = False

    for schedule in due:
        schedule_result: dict = {
            "scheduleId": schedule.id,
            "name": schedule.name,
            "pageIds": schedule.pageIds,
            "destinations": [],
        }

        try:
            quote = await _get_random_quote(schedule.quoteListId)
            message = format_quote_post(quote)
            schedule_result["quoteId"] = quote.get("id")
        except Exception as exc:
            logger.exception("Schedule %s failed before posting", schedule.id)
            schedule_result["error"] = str(exc)
            run_results.append(schedule_result)
            had_failures = True
            continue

        if not schedule.pageIds:
            schedule_result["error"] = "Schedule has no pageIds configured"
            logger.error("Schedule %s has empty pageIds", schedule.id)
            run_results.append(schedule_result)
            had_failures = True
            continue

        for page_id in schedule.pageIds:
            destination_result: dict = {"pageId": page_id, "ok": False}
            try:
                post_result = await _post_to_destination(page_id, message)
                destination_result.update({"ok": True, **post_result})
                logger.info(
                    "Posted schedule %s to %s (postId=%s)",
                    schedule.id,
                    page_id,
                    post_result.get("postId"),
                )
            except (FacebookPostError, XPostError) as exc:
                destination_result["error"] = str(exc)
                destination_result["platform"] = (
                    "x" if page_id == X_DESTINATION else "facebook"
                )
                logger.error(
                    "Failed posting schedule %s to pageId=%s: %s",
                    schedule.id,
                    page_id,
                    exc,
                )
                had_failures = True
            except Exception as exc:
                destination_result["error"] = f"Unexpected error: {exc}"
                logger.exception(
                    "Unexpected failure posting schedule %s to pageId=%s",
                    schedule.id,
                    page_id,
                )
                had_failures = True

            schedule_result["destinations"].append(destination_result)

        run_results.append(schedule_result)

    return {
        "ok": not had_failures,
        "ranAt": now.isoformat(),
        "dueScheduleCount": len(due),
        "results": run_results,
    }
