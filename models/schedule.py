from pydantic import BaseModel, Field


class Schedule(BaseModel):
    id: str = Field(..., description="Stable schedule UUID")
    name: str
    hour: int = Field(..., ge=0, le=23)
    minute: int = Field(..., ge=0, le=59)
    timezone: str = Field(default="America/Chicago")
    pageIds: list[str] = Field(
        ...,
        description='Destinations: "x" for X/Twitter, numeric strings for Facebook page IDs',
    )
    quoteListId: str | None = Field(
        default=None,
        description="Optional quote list/filter id (e.g. hope list UUID)",
    )
    enabled: bool = True
