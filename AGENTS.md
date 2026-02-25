# Quotes API

Python/FastAPI REST API for managing quotes, backed by MongoDB.

## Cursor Cloud specific instructions

### Architecture

Single FastAPI service (`main.py`) with MongoDB as the data store. No test framework is configured.

### Prerequisites

- **MongoDB** must be running locally on default port 27017. Start it with:
  ```
  sudo mongod --dbpath /data/db --fork --logpath /var/log/mongod.log
  ```
- A `.env` file must exist in the project root with:
  ```
  MONGO_URI=mongodb://localhost:27017
  DATABASE_NAME=quotes_db
  ```

### Running the dev server

```
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger docs available at `http://localhost:8000/docs`.

### Gotchas

- `requirements.txt` is incomplete — it's missing `motor`, `python-decouple`, and `pymongo`. The update script installs them explicitly.
- The `database/__init__.py` module pings MongoDB at import time. If MongoDB is not running, the app will crash immediately on startup.
- MongoDB 7.0 apt repo uses the `jammy` codename on Ubuntu 24.04 (Noble) since no `noble` repo exists.
- No linter or test framework is configured in the repository.
