from pydantic import BaseModel


class VenueSearchItemResponse(BaseModel):
    id: int
    name: str
    address_text: str | None
