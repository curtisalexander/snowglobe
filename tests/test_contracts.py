import pytest
from pydantic import ValidationError

from snowglobe.contracts import QueryReceipt, QueryStatusReceipt


def test_receipt_rejects_additional_fields() -> None:
    with pytest.raises(ValidationError):
        QueryReceipt.model_validate(
            {
                "status": "accepted",
                "request_id": "01JABCDEFGHJKMNPQRSTVWXYZ",
                "reason_code": "NONE",
                "governed_sql": "SELECT 1 LIMIT 51",
                "row_count": 42,
            }
        )


def test_status_receipt_rejects_result_metadata() -> None:
    with pytest.raises(ValidationError):
        QueryStatusReceipt.model_validate(
            {
                "request_id": "01JABCDEFGHJKMNPQRSTVWXYZ",
                "status": "complete",
                "row_count": 42,
            }
        )


@pytest.mark.parametrize(
    "receipt",
    [
        {
            "status": "accepted",
            "request_id": "01JABCDEFGHJKMNPQRSTVWXYZ",
            "reason_code": "SERVICE_UNAVAILABLE",
            "governed_sql": "SELECT 1 LIMIT 51",
        },
        {
            "status": "rejected",
            "request_id": "01JABCDEFGHJKMNPQRSTVWXYZ",
            "reason_code": "NONE",
            "governed_sql": None,
        },
        {
            "status": "accepted",
            "request_id": "01JABCDEFGHJKMNPQRSTVWXYZ",
            "reason_code": "NONE",
            "governed_sql": None,
        },
        {
            "status": "rejected",
            "request_id": "01JABCDEFGHJKMNPQRSTVWXYZ",
            "reason_code": "POLICY_REJECTED",
            "governed_sql": "SELECT 1 LIMIT 51",
        },
    ],
)
def test_receipt_rejects_inconsistent_fields(receipt: dict[str, str | None]) -> None:
    with pytest.raises(ValidationError):
        QueryReceipt.model_validate(receipt)
