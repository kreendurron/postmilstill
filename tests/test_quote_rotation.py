import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from bson.objectid import ObjectId

from services.quote_rotation import get_next_quote, record_successful_post


def _quote_doc(index: int, author: str | None = None) -> dict:
    oid = ObjectId.from_datetime(datetime(2026, 1, index + 1, tzinfo=timezone.utc))
    return {
        "_id": oid,
        "author": author or f"Author {index}",
        "quote": f"Quote text {index}",
        "source": "source",
        "link": "https://example.com",
        "quoteListId": "list-1",
    }


def _fake_find_cursor(quotes: list[dict]):
    def fake_find(_query):
        class Cursor:
            def sort(self, *_args, **_kwargs):
                return self

            def __aiter__(self):
                self._items = iter(quotes)
                return self

            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration

        return Cursor()

    return fake_find


@pytest.mark.asyncio
async def test_shared_cursor_advances_sequentially():
    quotes = [_quote_doc(i) for i in range(3)]
    now = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)
    cursor_state = {"lastIndex": -1}

    async def fake_find_one_and_update(*_args, **_kwargs):
        cursor_state["lastIndex"] += 1
        return {"lastIndex": cursor_state["lastIndex"]}

    with (
        patch("services.quote_rotation.quotes_collection") as mock_quotes,
        patch("services.quote_rotation.quote_list_cursors_collection") as mock_cursors,
        patch("services.quote_rotation.post_history_collection") as mock_history,
    ):
        mock_quotes.find = _fake_find_cursor(quotes)
        mock_cursors.update_one = AsyncMock()
        mock_cursors.find_one_and_update = fake_find_one_and_update
        mock_history.find_one = AsyncMock(return_value=None)

        first = await get_next_quote("list-1", ["109666208522653"], now=now)
        second = await get_next_quote("list-1", ["109666208522653"], now=now)

    assert first["listIndex"] == 0
    assert second["listIndex"] == 1
    assert first["id"] != second["id"]


@pytest.mark.asyncio
async def test_skips_quote_posted_within_24h():
    quotes = [_quote_doc(i) for i in range(3)]
    now = datetime(2026, 8, 20, 16, 0, tzinfo=timezone.utc)
    first_quote_id = str(quotes[0]["_id"])

    async def fake_find_one_and_update(*_args, **_kwargs):
        return {"lastIndex": 0}

    async def fake_history_find_one(filter_doc, *_args, **_kwargs):
        if filter_doc.get("quoteId") == first_quote_id:
            return {"quoteId": first_quote_id, "postedAt": now - timedelta(hours=8)}
        return None

    with (
        patch("services.quote_rotation.quotes_collection") as mock_quotes,
        patch("services.quote_rotation.quote_list_cursors_collection") as mock_cursors,
        patch("services.quote_rotation.post_history_collection") as mock_history,
    ):
        mock_quotes.find = _fake_find_cursor(quotes)
        mock_cursors.update_one = AsyncMock()
        mock_cursors.find_one_and_update = fake_find_one_and_update
        mock_history.find_one = fake_history_find_one

        selected = await get_next_quote("list-1", ["109666208522653"], now=now)

    assert selected["listIndex"] == 1
    assert selected["id"] != first_quote_id


@pytest.mark.asyncio
async def test_random_by_author_prefers_different_author():
    quotes = [
        _quote_doc(0, author="John Owen"),
        _quote_doc(1, author="John Owen"),
        _quote_doc(2, author="Tozer"),
        _quote_doc(3, author="Ravenhill"),
    ]
    now = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)
    owen_id = str(quotes[0]["_id"])

    call_count = {"n": 0}

    async def fake_history_find_one(filter_doc, *_args, **_kwargs):
        call_count["n"] += 1
        if "postedAt" in filter_doc and "$gte" in filter_doc["postedAt"]:
            return None
        if filter_doc.get("pageId"):
            return {"quoteId": owen_id, "postedAt": now - timedelta(hours=12)}
        return None

    with (
        patch("services.quote_rotation.quotes_collection") as mock_quotes,
        patch("services.quote_rotation.post_history_collection") as mock_history,
        patch("services.quote_rotation.random.choice", side_effect=["Tozer", quotes[2]]),
    ):
        mock_quotes.find = _fake_find_cursor(quotes)
        mock_history.find_one = fake_history_find_one
        mock_quotes.find_one = AsyncMock(return_value=quotes[0])

        selected = await get_next_quote(
            "list-1",
            ["109666208522653"],
            now=now,
            selection_mode="random_by_author",
        )

    assert selected["author"] == "Tozer"


@pytest.mark.asyncio
async def test_random_by_author_does_not_use_cursor():
    quotes = [_quote_doc(i) for i in range(3)]
    now = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)

    with (
        patch("services.quote_rotation.quotes_collection") as mock_quotes,
        patch("services.quote_rotation.quote_list_cursors_collection") as mock_cursors,
        patch("services.quote_rotation.post_history_collection") as mock_history,
        patch("services.quote_rotation.random.choice", side_effect=["Author 1", quotes[1]]),
    ):
        mock_quotes.find = _fake_find_cursor(quotes)
        mock_cursors.update_one = AsyncMock()
        mock_cursors.find_one_and_update = AsyncMock()
        mock_history.find_one = AsyncMock(return_value=None)

        await get_next_quote(
            "list-1",
            ["109666208522653"],
            now=now,
            selection_mode="random_by_author",
        )

    mock_cursors.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_record_successful_post_writes_history():
    mock_history = MagicMock()
    mock_history.insert_one = AsyncMock()
    now = datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc)

    with patch("services.quote_rotation.post_history_collection", mock_history):
        await record_successful_post(
            quote_list_id="list-1",
            quote_id="q1",
            page_id="109666208522653",
            schedule_id="sched-1",
            now=now,
        )

    mock_history.insert_one.assert_awaited_once()
    payload = mock_history.insert_one.await_args.args[0]
    assert payload["quoteId"] == "q1"
    assert payload["pageId"] == "109666208522653"
    assert payload["scheduleId"] == "sched-1"
