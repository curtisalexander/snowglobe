import pytest
from pydantic import ValidationError

from snowglobe.contracts import QueryReceipt


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
