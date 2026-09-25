from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class UsageModel(APIModel):
    plan: str | None = None
    five_hour_used: int | None = Field(None, alias="fiveHourUsed", ge=0, le=100)
    five_hour_resets_at: int | None = Field(None, alias="fiveHourResetsAt")
    weekly_used: int | None = Field(None, alias="weeklyUsed", ge=0, le=100)
    weekly_resets_at: int | None = Field(None, alias="weeklyResetsAt")
    reset_credits_available: int = Field(0, alias="resetCreditsAvailable", ge=0)
    allowed: bool | None = None
    status: Literal["ready", "close", "critical", "blocked", "error", "unknown"]
    error: str | None = None


class ProviderModel(APIModel):
    id: str
    name: str
    available: bool
    error: str | None = None


class AccountModel(APIModel):
    provider: str
    id: str
    active: bool
    authenticated: bool
    duplicate: bool = False
    email: str | None = None
    usage: UsageModel | None = None


class SessionModel(APIModel):
    provider: str
    id: str
    title: str | None = None
    updated_at: int | None = Field(None, alias="updatedAt")


class RecommendationModel(APIModel):
    provider: str
    account: str
    reason: str


class StateModel(APIModel):
    providers: list[ProviderModel]
    accounts: list[AccountModel]
    sessions: list[SessionModel]
    recommendation: RecommendationModel | None = None


class CommandRequest(APIModel):
    mode: Literal["new", "resume"]
    session_id: str | None = Field(
        None, alias="sessionId", min_length=1, max_length=256
    )


class CommandResponse(APIModel):
    command: str


class ActivationResponse(APIModel):
    provider: str
    account: str
    active: bool


class OnboardRequest(APIModel):
    account: str = Field(default="", max_length=64)


class OnboardResponse(APIModel):
    provider: str
    account: str
    command: str


class RemovalResponse(APIModel):
    provider: str
    account: str
    removed: bool


class RedeemResetResponse(APIModel):
    outcome: Literal["reset", "nothingToReset", "alreadyRedeemed"]


class HealthResponse(APIModel):
    status: Literal["ok"] = "ok"
    version: str
