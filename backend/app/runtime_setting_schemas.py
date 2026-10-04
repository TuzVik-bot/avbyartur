from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, field_validator


class RuntimeSettingOut(BaseModel):
    key: str
    value: int
    revision: int
    source: Literal["environment", "override"]


class RuntimeSettingListOut(BaseModel):
    items: list[RuntimeSettingOut]


class RuntimeSettingChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: StrictInt = Field(ge=1, le=10000)
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    confirmation: Literal["UPDATE_SETTING"]
    current_password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A non-empty reason is required")
        return value


class RuntimeSettingChangeOut(BaseModel):
    setting: RuntimeSettingOut
    changed: bool
