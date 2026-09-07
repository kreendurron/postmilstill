"""Seed known production schedules with X + Facebook destinations."""

import asyncio

from database import schedules_collection
from models.schedule import Schedule

POSTMILSTILL_FB_PAGE = "109666208522653"
HOPE_LIST_ID = "54bdceca-a370-421b-87ab-7abd43ddf27d"

DEFAULT_SCHEDULES = [
    Schedule(
        id="6ff0af0d-7a2d-461e-a95a-0b16f3f56c26",
        name="Morning quote",
        hour=8,
        minute=0,
        timezone="America/Chicago",
        pageIds=["x", POSTMILSTILL_FB_PAGE],
        quoteListId=HOPE_LIST_ID,
        enabled=True,
    ),
    Schedule(
        id="18ab11ec-f65d-4432-a2a8-11ba8f9ab6ab",
        name="Afternoon quote",
        hour=16,
        minute=0,
        timezone="America/Chicago",
        pageIds=["x", POSTMILSTILL_FB_PAGE],
        quoteListId=HOPE_LIST_ID,
        enabled=True,
    ),
]


async def seed() -> None:
    for schedule in DEFAULT_SCHEDULES:
        await schedules_collection.update_one(
            {"id": schedule.id},
            {"$set": schedule.model_dump()},
            upsert=True,
        )
        print(f"Seeded schedule {schedule.id} pageIds={schedule.pageIds}")


if __name__ == "__main__":
    asyncio.run(seed())
