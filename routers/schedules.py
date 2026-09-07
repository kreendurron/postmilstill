from fastapi import APIRouter, HTTPException

from database import schedules_collection
from models.schedule import Schedule

router = APIRouter()


@router.get("/", response_description="List configured schedules")
async def list_schedules():
    schedules: list[dict] = []
    async for doc in schedules_collection.find():
        schedules.append(
            {
                "id": doc.get("id") or str(doc.get("_id")),
                "name": doc.get("name"),
                "hour": doc.get("hour"),
                "minute": doc.get("minute"),
                "timezone": doc.get("timezone", "America/Chicago"),
                "pageIds": doc.get("pageIds", []),
                "quoteListId": doc.get("quoteListId"),
                "selectionMode": doc.get("selectionMode", "sequential"),
                "enabled": doc.get("enabled", True),
            }
        )
    return schedules


@router.put("/{schedule_id}", response_description="Upsert a schedule")
async def upsert_schedule(schedule_id: str, schedule: Schedule):
    if schedule.id != schedule_id:
        raise HTTPException(status_code=400, detail="Schedule id in path and body must match")

    payload = schedule.model_dump()
    await schedules_collection.update_one(
        {"id": schedule_id},
        {"$set": payload},
        upsert=True,
    )
    return payload
