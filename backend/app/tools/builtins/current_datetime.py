"""Current date/time tool with IANA timezone support and injectable clock."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from app.tools.base import BaseTool
from app.tools.context import ToolExecutionContext
from app.tools.exceptions import ToolInvalidArgumentsError
from app.tools.schemas import ToolResultPayload


class CurrentDatetimeInput(BaseModel):
    timezone: str = Field(
        default="UTC",
        min_length=1,
        max_length=64,
        description="IANA timezone name, for example Asia/Kolkata",
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Timezone cannot be blank")
        try:
            ZoneInfo(cleaned)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid IANA timezone: {cleaned}") from exc
        return cleaned


class CurrentDatetimeOutput(BaseModel):
    iso: str
    date: str
    time: str
    timezone: str
    utc_offset: str


class CurrentDatetimeTool(BaseTool):
    name: ClassVar[str] = "current_datetime"
    description: ClassVar[str] = (
        "Return the current date and time for an IANA timezone "
        "(for example Asia/Kolkata). Defaults to UTC when omitted."
    )
    version: ClassVar[str] = "1.0.0"
    category: ClassVar[str] = "utility"
    input_model: ClassVar[type[BaseModel]] = CurrentDatetimeInput
    output_model: ClassVar[type[BaseModel] | None] = CurrentDatetimeOutput
    timeout_seconds: ClassVar[int] = 5

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        assert isinstance(arguments, CurrentDatetimeInput)
        try:
            tz = ZoneInfo(arguments.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ToolInvalidArgumentsError(f"Invalid IANA timezone: {arguments.timezone}") from exc

        now = context.clock if context.clock is not None else datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        local = now.astimezone(tz)
        offset = local.strftime("%z")
        utc_offset = f"{offset[:3]}:{offset[3:]}" if offset else "+00:00"
        payload = CurrentDatetimeOutput(
            iso=local.isoformat(),
            date=local.date().isoformat(),
            time=local.time().replace(microsecond=0).isoformat(),
            timezone=arguments.timezone,
            utc_offset=utc_offset,
        )
        return ToolResultPayload(success=True, data=payload.model_dump())
