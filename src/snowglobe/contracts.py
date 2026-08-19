"""Strict contracts crossing the model-facing boundary."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReceiptStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ReasonCode(StrEnum):
    NONE = "NONE"
    INVALID_REQUEST = "INVALID_REQUEST"
    POLICY_REJECTED = "POLICY_REJECTED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class QueryReceipt(BaseModel):
    """The complete model-visible query submission result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ReceiptStatus
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{20,32}$")
    reason_code: ReasonCode


class QueryLifecycleStatus(StrEnum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    NOT_FOUND = "not_found"
    SERVICE_UNAVAILABLE = "service_unavailable"


class QueryStatusReceipt(BaseModel):
    """Result-free lifecycle state for one opaque local request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{20,32}$")
    status: QueryLifecycleStatus
