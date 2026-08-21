"""Strict contracts crossing the model-facing boundary."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    governed_sql: str | None = Field(min_length=1)

    @model_validator(mode="after")
    def require_consistent_submission(self) -> "QueryReceipt":
        accepted = self.status is ReceiptStatus.ACCEPTED
        if accepted is not (self.reason_code is ReasonCode.NONE):
            raise ValueError("inconsistent submission status and reason")
        if accepted is not (self.governed_sql is not None):
            raise ValueError("inconsistent submission status and governed SQL")
        return self


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
