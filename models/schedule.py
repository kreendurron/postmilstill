from typing import Literal

from pydantic import BaseModel, Field

QuoteSelectionMode = Literal["sequential", "random_by_author"]


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
    selectionMode: QuoteSelectionMode = Field(
        default="sequential",
        description=(
            "How to pick the next quote: sequential cursor through the list, "
            "or random_by_author (uniform author, then random quote)"
        ),
    )
    enabled: bool = True
