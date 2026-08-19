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
