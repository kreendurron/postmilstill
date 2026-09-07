import logging
from datetime import datetime

from decouple import config
from fastapi import APIRouter, Header, HTTPException

from services.cron_runner import run_due_schedules

logger = logging.getLogger(__name__)
router = APIRouter()


def _verify_cron_secret(authorization: str | None, x_cron_secret: str | None) -> None:
    expected = config("CRON_SECRET", default="")
    if not expected:
        raise HTTPException(
            status_code=500,
            detail="CRON_SECRET is not configured on the server",
        )

    provided = None
    if authorization and authorization.startswith("Bearer "):
        provided = authorization.removeprefix("Bearer ").strip()
    elif x_cron_secret:
        provided = x_cron_secret.strip()

    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="Invalid cron credentials")


@router.post("/run", response_description="Execute due scheduled posts")
async def run_scheduled_posts(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    _verify_cron_secret(authorization, x_cron_secret)
    result = await run_due_schedules(datetime.now())
    if not result["ok"]:
        logger.error("Cron run completed with failures: %s", result)
        raise HTTPException(status_code=502, detail=result)
    return result


@router.get("/run", response_description="Execute due scheduled posts (GET for Railway cron)")
async def run_scheduled_posts_get(
    authorization: str | None = Header(default=None),
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
):
    return await run_scheduled_posts(authorization, x_cron_secret)


@router.get("/health", response_description="Cron service health")
async def cron_health():
    return {"ok": True, "service": "cron"}
