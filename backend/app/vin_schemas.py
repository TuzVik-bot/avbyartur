from pydantic import BaseModel, ConfigDict


class VinCheckStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    provider: str | None
    supported_categories: list[str]
    message: str
