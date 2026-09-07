import logging

from fastapi import FastAPI

from routers import router
from routers.cron import router as cron_router
from routers.schedules import router as schedules_router

logging.basicConfig(level=logging.INFO)

app = FastAPI()

app.include_router(router, prefix="/quotes", tags=["Quotes"])
app.include_router(cron_router, prefix="/cron", tags=["Cron"])
app.include_router(schedules_router, prefix="/schedules", tags=["Schedules"])


@app.get("/")
def read_root():
    return {"message": "Welcome to the Quotes API!"}
