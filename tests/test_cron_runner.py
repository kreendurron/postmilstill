import pytest
from datetime import datetime, timezone
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

    fake_now = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)

    with (
        patch("services.cron_runner._load_schedules", AsyncMock(return_value=[schedule])),
        patch(
            "services.cron_runner.get_next_quote",
            AsyncMock(return_value={"id": "q1", "author": "A", "text": "Quote", "listIndex": 0}),
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
        patch("services.cron_runner.record_successful_post", AsyncMock()),
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

    fake_now = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)

    with (
        patch("services.cron_runner._load_schedules", AsyncMock(return_value=[schedule])),
        patch(
            "services.cron_runner.get_next_quote",
            AsyncMock(return_value={"id": "q1", "author": "A", "text": "Quote", "listIndex": 0}),
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
        patch("services.cron_runner.record_successful_post", AsyncMock()),
    ):
        result = await run_due_schedules(fake_now)

    assert result["ok"] is False
    destinations = result["results"][0]["destinations"]
    x_result = next(d for d in destinations if d["pageId"] == "x")
    fb_result = next(d for d in destinations if d["pageId"] == "109666208522653")
    assert x_result["ok"] is False
    assert "X down" in x_result["error"]
    assert fb_result["ok"] is True


@pytest.mark.asyncio
async def test_morning_and_afternoon_schedules_use_sequential_quotes():
    morning = Schedule(
        id="morning",
        name="Morning",
        hour=8,
        minute=0,
        timezone="UTC",
        pageIds=["109666208522653"],
        quoteListId="hope-list",
        enabled=True,
    )
    afternoon = Schedule(
        id="afternoon",
        name="Afternoon",
        hour=16,
        minute=0,
        timezone="UTC",
        pageIds=["109666208522653"],
        quoteListId="hope-list",
        enabled=True,
    )

    quote_sequence = iter(
        [
            {"id": "q0", "author": "Kuyper", "text": "Quote A", "listIndex": 0},
            {"id": "q1", "author": "Kuyper", "text": "Quote B", "listIndex": 1},
        ]
    )

    async def next_quote(*_args, **_kwargs):
        return next(quote_sequence)

    morning_time = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)
    afternoon_time = datetime(2026, 8, 20, 16, 0, tzinfo=timezone.utc)

    with (
        patch("services.cron_runner._load_schedules", AsyncMock(return_value=[morning])),
        patch("services.cron_runner.get_next_quote", side_effect=next_quote),
        patch("services.cron_runner.post_to_facebook", AsyncMock(return_value={"postId": "fb1"})),
        patch("services.cron_runner.record_successful_post", AsyncMock()),
    ):
        morning_result = await run_due_schedules(morning_time)

    with (
        patch("services.cron_runner._load_schedules", AsyncMock(return_value=[afternoon])),
        patch("services.cron_runner.get_next_quote", side_effect=next_quote),
        patch("services.cron_runner.post_to_facebook", AsyncMock(return_value={"postId": "fb2"})),
        patch("services.cron_runner.record_successful_post", AsyncMock()),
    ):
        afternoon_result = await run_due_schedules(afternoon_time)

    assert morning_result["results"][0]["quoteId"] == "q0"
    assert afternoon_result["results"][0]["quoteId"] == "q1"
    assert morning_result["results"][0]["quoteId"] != afternoon_result["results"][0]["quoteId"]
