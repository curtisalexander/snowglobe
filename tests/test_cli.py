import json
from io import StringIO

from pytest import CaptureFixture, MonkeyPatch

from snowglobe import cli


def test_submit_reads_sql_from_stdin_and_prints_the_governed_sql_receipt(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    sql_canary = "PRIVATE_SQL_CANARY"
    request_id = "abcdefghijklmnopqrstuvwx"

    async def invoke(name: str, arguments: dict[str, object]) -> dict[str, object]:
        assert name == "submit_read_query"
        assert arguments == {
            "sql": sql_canary,
            "requested_ttl": 300,
        }
        return {
            "status": "accepted",
            "request_id": request_id,
            "reason_code": "NONE",
            "governed_sql": "SELECT PRIVATE_SQL_CANARY LIMIT 51",
        }

    monkeypatch.setattr(cli, "_invoke", invoke)
    monkeypatch.setattr(cli.sys, "stdin", StringIO(sql_canary))

    assert cli.main(["submit", "--ttl", "300"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "status": "accepted",
        "request_id": request_id,
        "reason_code": "NONE",
        "governed_sql": "SELECT PRIVATE_SQL_CANARY LIMIT 51",
    }
    assert captured.err == ""
    assert sql_canary in captured.out


def test_status_prints_only_closed_receipt(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    request_id = "abcdefghijklmnopqrstuvwx"

    async def invoke(name: str, arguments: dict[str, object]) -> dict[str, object]:
        assert name == "get_query_status"
        assert arguments == {"request_id": request_id}
        return {"request_id": request_id, "status": "complete"}

    monkeypatch.setattr(cli, "_invoke", invoke)

    assert cli.main(["status", request_id]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"request_id": request_id, "status": "complete"}
    assert captured.err == ""


def test_transport_failure_fails_closed(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    canary = "TRANSPORT_ERROR_CANARY"

    async def fail(_name: str, _arguments: dict[str, object]) -> dict[str, object]:
        raise RuntimeError(canary)

    monkeypatch.setattr(cli, "_invoke", fail)
    monkeypatch.setattr(cli.sys, "stdin", StringIO("PRIVATE_SQL_CANARY"))

    assert cli.main(["submit", "--ttl", "300"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["reason_code"] == "SERVICE_UNAVAILABLE"
    assert captured.err == ""
    assert canary not in captured.out


def test_invalid_submission_is_rejected_without_contacting_the_service(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    async def invoke(_name: str, _arguments: dict[str, object]) -> dict[str, object]:
        raise AssertionError("invalid input must not reach the service")

    monkeypatch.setattr(cli, "_invoke", invoke)
    monkeypatch.setattr(cli.sys, "stdin", StringIO(""))

    assert cli.main(["submit", "--ttl", "300"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["reason_code"] == "INVALID_REQUEST"


def test_status_response_must_match_the_requested_id(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    request_id = "abcdefghijklmnopqrstuvwx"

    async def invoke(_name: str, _arguments: dict[str, object]) -> dict[str, object]:
        return {"request_id": "zyxwvutsrqponmlkjihgfedc", "status": "complete"}

    monkeypatch.setattr(cli, "_invoke", invoke)

    assert cli.main(["status", request_id]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "request_id": request_id,
        "status": "service_unavailable",
    }


def test_malformed_response_with_result_data_fails_closed(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    result_canary = "PRIVATE_RESULT_CANARY"

    async def malformed(_name: str, _arguments: dict[str, object]) -> dict[str, object]:
        return {
            "status": "accepted",
            "request_id": "abcdefghijklmnopqrstuvwx",
            "reason_code": "NONE",
            "governed_sql": "SELECT 1 LIMIT 51",
            "result": result_canary,
        }

    monkeypatch.setattr(cli, "_invoke", malformed)
    monkeypatch.setattr(cli.sys, "stdin", StringIO("PRIVATE_SQL_CANARY"))

    assert cli.main(["submit", "--ttl", "300"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["reason_code"] == "SERVICE_UNAVAILABLE"
    assert captured.err == ""
    assert result_canary not in captured.out


def test_invalid_command_does_not_reflect_arguments(
    capsys: CaptureFixture[str],
) -> None:
    canary = "INVALID_COMMAND_CANARY"

    assert cli.main([canary]) == 0
    captured = capsys.readouterr()
    receipt = json.loads(captured.out)
    assert receipt["status"] == "rejected"
    assert receipt["reason_code"] == "INVALID_REQUEST"
    assert captured.err == ""
    assert canary not in captured.out


def test_invalid_status_does_not_reflect_arguments(
    capsys: CaptureFixture[str],
) -> None:
    canary = "INVALID.STATUS.CANARY"

    assert cli.main(["status", canary, "unexpected"]) == 0
    captured = capsys.readouterr()
    receipt = json.loads(captured.out)
    assert receipt["status"] == "not_found"
    assert receipt["request_id"] != canary
    assert captured.err == ""
    assert canary not in captured.out
