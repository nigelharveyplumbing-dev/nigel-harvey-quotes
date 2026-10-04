"""Versioned full-snapshot contract; only fictional simulation events accepted."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class VoiceFacts(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(default="", max_length=160)
    name_confirmed: bool = False
    callback_phone: str = Field(default="", max_length=60)
    callback_confirmed: bool = False
    address: str = Field(default="", max_length=500)
    postcode: str = Field(default="", max_length=12)
    description: str = Field(default="", max_length=4000)
    additional_details: str = Field(default="", max_length=2000)
    appointment_preference: str = Field(default="", max_length=500)
    appointment_confirmed: bool = False
    photos_useful: bool | None = None
    urgency: Literal["routine", "urgent", "gas_co", "electrical_water"] = "routine"
    urgency_reason: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=1500)


class VoiceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: Literal[1] = 1
    synthetic: Literal[True]
    provider: Literal["simulation"]
    account: Literal["synthetic-v1"]
    root_call_id: str = Field(pattern=r"^sim-[A-Za-z0-9_-]{1,80}$")
    event_id: str = Field(pattern=r"^evt-[A-Za-z0-9_-]{1,80}$")
    sequence: int = Field(ge=1, le=10000)
    leg_id: str = Field(default="", max_length=100, pattern=r"^(sim-[A-Za-z0-9_-]+)?$")
    presented_phone: str = Field(default="", max_length=60)
    started_at: datetime
    ended_at: datetime | None = None
    outcome: Literal["in_progress", "completed", "incomplete", "emergency_redirect"]
    facts: VoiceFacts
    transcript: str = Field(default="", max_length=24000)
    notice_version: Literal["synthetic-notice-v1"] = "synthetic-notice-v1"
    prompt_version: Literal["offline-policy-v1", "offline-policy-v2"] = "offline-policy-v2"
    model_version: Literal["scripted-extractor-v1"] = "scripted-extractor-v1"

    @field_validator("started_at", "ended_at")
    @classmethod
    def aware(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Call timestamps require a timezone")
        return value.astimezone(timezone.utc) if value is not None else None

    @field_validator("synthetic", mode="before")
    @classmethod
    def explicitly_synthetic(cls, value):
        if value is not True:
            raise ValueError("Synthetic must be the JSON boolean true")
        return value

    @model_validator(mode="after")
    def consistent(self):
        if self.ended_at and self.ended_at < self.started_at:
            raise ValueError("Call end precedes start")
        if (self.outcome == "in_progress") != (self.ended_at is None):
            raise ValueError("Final snapshots require an end timestamp")
        return self
