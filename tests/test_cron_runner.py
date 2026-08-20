import pytest
from unittest.mock import AsyncMock, patch

from models.schedule import Schedule
from services.cron_runner import run_due_schedules
from services.x_twitter import XPostError


@pytest.mark.asyncio
async def test_fan_out_calls_x_and_facebook():
    schedule = Schedule(
        id="test-schedule",
        name="Test",
        hour=8,
        minute=0,
        timezone="UTC",
        pageIds=["x", "109666208522653"],
        enabled=True,
    )

    fake_now = __import__("datetime").datetime(
        2026, 8, 20, 8, 0, tzinfo=__import__("datetime").timezone.utc
    )

    with (
        patch("services.cron_runner._load_schedules", AsyncMock(return_value=[schedule])),
        patch(
            "services.cron_runner._get_random_quote",
            AsyncMock(return_value={"id": "q1", "author": "A", "text": "Quote"}),
        ),
        patch(
            "services.cron_runner.post_to_x",
            AsyncMock(return_value={"pageId": "x", "postId": "tw1", "platform": "x"}),
        ) as mock_x,
        patch(
            "services.cron_runner.post_to_facebook",
            AsyncMock(
                return_value={
                    "pageId": "109666208522653",
                    "postId": "fb1",
                    "platform": "facebook",
                }
            ),
        ) as mock_fb,
    ):
        result = await run_due_schedules(fake_now)

    assert result["dueScheduleCount"] == 1
    assert result["ok"] is True
    mock_x.assert_awaited_once()
    mock_fb.assert_awaited_once_with("109666208522653", mock_x.await_args.args[0])


@pytest.mark.asyncio
async def test_x_failure_is_reported_and_not_swallowed():
    schedule = Schedule(
        id="test-schedule",
        name="Test",
        hour=8,
        minute=0,
        timezone="UTC",
        pageIds=["x", "109666208522653"],
        enabled=True,
    )

    fake_now = __import__("datetime").datetime(
        2026, 8, 20, 8, 0, tzinfo=__import__("datetime").timezone.utc
    )

    with (
        patch("services.cron_runner._load_schedules", AsyncMock(return_value=[schedule])),
        patch(
            "services.cron_runner._get_random_quote",
            AsyncMock(return_value={"id": "q1", "author": "A", "text": "Quote"}),
        ),
        patch(
            "services.cron_runner.post_to_x",
            AsyncMock(side_effect=XPostError("X down")),
        ),
        patch(
            "services.cron_runner.post_to_facebook",
            AsyncMock(
                return_value={
                    "pageId": "109666208522653",
                    "postId": "fb1",
                    "platform": "facebook",
                }
            ),
        ),
    ):
        result = await run_due_schedules(fake_now)

    assert result["ok"] is False
    destinations = result["results"][0]["destinations"]
    x_result = next(d for d in destinations if d["pageId"] == "x")
    fb_result = next(d for d in destinations if d["pageId"] == "109666208522653")
    assert x_result["ok"] is False
    assert "X down" in x_result["error"]
    assert fb_result["ok"] is True
