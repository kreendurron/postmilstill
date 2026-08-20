import httpx
from decouple import config


class FacebookPostError(Exception):
    pass


def _get_page_access_token() -> str:
    token = config("FACEBOOK_PAGE_ACCESS_TOKEN", default="") or config(
        "FB_PAGE_ACCESS_TOKEN", default=""
    )
    if not token:
        raise FacebookPostError(
            "Missing Facebook page access token. Set FACEBOOK_PAGE_ACCESS_TOKEN or "
            "FB_PAGE_ACCESS_TOKEN in Railway."
        )
    return token


async def post_to_facebook(page_id: str, message: str) -> dict:
    token = _get_page_access_token()
    url = f"https://graph.facebook.com/v21.0/{page_id}/feed"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            data={"message": message, "access_token": token},
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise FacebookPostError(
            f"Facebook API returned non-JSON response (status {response.status_code})"
        ) from exc

    if response.status_code >= 400 or "error" in payload:
        error = payload.get("error", {})
        message_text = error.get("message", response.text)
        raise FacebookPostError(
            f"Facebook post failed for page {page_id}: {message_text}"
        )

    return {"pageId": page_id, "postId": payload.get("id"), "platform": "facebook"}
