import sys
from unittest.mock import AsyncMock, MagicMock

# Avoid requiring a live MongoDB connection during unit tests.
mock_module = MagicMock()
mock_module.quotes_collection = MagicMock()
mock_module.schedules_collection = MagicMock()
mock_module.quote_list_cursors_collection = MagicMock()
mock_module.post_history_collection = MagicMock()
mock_module.post_history_collection.insert_one = AsyncMock()
mock_module.quote_helper = lambda quote: {
    "id": str(quote.get("_id", quote.get("id", "unknown"))),
    "author": quote.get("author", "Unknown"),
    "text": quote.get("quote", quote.get("text", "")),
    "source": quote.get("source", "unknown"),
    "link": quote.get("link", ""),
}

sys.modules.setdefault("database", mock_module)
