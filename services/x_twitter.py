import asyncio

from decouple import config
from requests_oauthlib import OAuth1Session


class XPostError(Exception):
    pass


def _x_credentials() -> dict[str, str]:
    values = {
        "X_API_KEY": config("X_API_KEY", default=""),
        "X_API_SECRET": config("X_API_SECRET", default=""),
        "X_ACCESS_TOKEN": config("X_ACCESS_TOKEN", default=""),
        "X_ACCESS_TOKEN_SECRET": config("X_ACCESS_TOKEN_SECRET", default=""),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise XPostError(
            "Missing X credentials in Railway env: " + ", ".join(missing)
        )
    return values


def _post_to_x_sync(message: str) -> dict:
    creds = _x_credentials()
    session = OAuth1Session(
        creds["X_API_KEY"],
        client_secret=creds["X_API_SECRET"],
        resource_owner_key=creds["X_ACCESS_TOKEN"],
        resource_owner_secret=creds["X_ACCESS_TOKEN_SECRET"],
    )

    response = session.post(
        "https://api.twitter.com/2/tweets",
        json={"text": message},
        timeout=30,
    )

    try:
        payload = response.json()
    except ValueError as exc:
        raise XPostError(
            f"X API returned non-JSON response (status {response.status_code})"
        ) from exc

    if response.status_code >= 400:
        detail = payload.get("detail") or payload.get("title") or response.text
        errors = payload.get("errors")
        if errors:
            detail = f"{detail}; errors={errors}"
        raise XPostError(f"X post failed: {detail}")

    tweet_id = payload.get("data", {}).get("id")
    return {"pageId": "x", "postId": tweet_id, "platform": "x"}


async def post_to_x(message: str) -> dict:
    return await asyncio.to_thread(_post_to_x_sync, message)
