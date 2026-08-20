import sys
from unittest.mock import MagicMock

# Avoid requiring a live MongoDB connection during unit tests.
mock_db = MagicMock()
mock_module = MagicMock()
mock_module.quotes_collection = MagicMock()
mock_module.schedules_collection = MagicMock()
mock_module.quote_helper = lambda quote: quote

sys.modules.setdefault("database", mock_module)
