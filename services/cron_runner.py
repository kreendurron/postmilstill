import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from database import schedules_collection
from models.schedule import Schedule
from services.facebook import FacebookPostError, post_to_facebook
from services.post_formatter import format_quote_post
from services.quote_rotation import choose_quote_id, record_successful_post
from services.x_twitter import XPostError, post_to_x

logger = logging.getLogger(__name__)

X_DESTINATION = "x"


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
                orderType=doc.get("orderType", "sequential"),
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
            quote = await choose_quote_id(
                schedule.quoteListId,
                schedule.pageIds,
                order_type=schedule.orderType,
                now=now,
            )
            message = format_quote_post(quote)
            schedule_result["quoteId"] = quote.get("id")
            schedule_result["listIndex"] = quote.get("listIndex")
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
                await record_successful_post(
                    quote_list_id=schedule.quoteListId,
                    quote_id=quote["id"],
                    page_id=page_id,
                    schedule_id=schedule.id,
                    now=now,
                )
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
