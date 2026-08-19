import pytest

from snowglobe.sql_policy import QueryPolicyRejected, SnowflakeSqlPolicy

APPROVED_VIEW = "GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW"


@pytest.fixture
def policy() -> SnowflakeSqlPolicy:
    return SnowflakeSqlPolicy.from_view_names((APPROVED_VIEW,))


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1", "SELECT 1 LIMIT 51"),
        (
            f"SELECT account_id FROM {APPROVED_VIEW} WHERE account_id > 1 ORDER BY account_id",
            f"SELECT account_id FROM {APPROVED_VIEW} "
            "WHERE account_id > 1 ORDER BY account_id LIMIT 51",
        ),
        (
            f"WITH approved AS (SELECT account_id FROM {APPROVED_VIEW}) SELECT * FROM approved",
            f"WITH approved AS (SELECT account_id FROM {APPROVED_VIEW}) "
            "SELECT * FROM approved LIMIT 51",
        ),
        (
            f"WITH first_view AS (SELECT account_id FROM {APPROVED_VIEW}), "
            "second_view AS (SELECT * FROM first_view) SELECT * FROM second_view",
            f"WITH first_view AS (SELECT account_id FROM {APPROVED_VIEW}), "
            "second_view AS (SELECT * FROM first_view) SELECT * FROM second_view LIMIT 51",
        ),
        (
            'SELECT * FROM "GOVERNED_DATABASE"."GOVERNED_SCHEMA"."APPROVED_VIEW"',
            'SELECT * FROM "GOVERNED_DATABASE"."GOVERNED_SCHEMA"."APPROVED_VIEW" LIMIT 51',
        ),
        (f"SELECT * FROM {APPROVED_VIEW} LIMIT 5", f"SELECT * FROM {APPROVED_VIEW} LIMIT 5"),
        (
            f"SELECT * FROM {APPROVED_VIEW} LIMIT 500 OFFSET 2",
            f"SELECT * FROM {APPROVED_VIEW} LIMIT 51 OFFSET 2",
        ),
        (
            f"SELECT * FROM {APPROVED_VIEW} FETCH FIRST 5 ROWS ONLY",
            f"SELECT * FROM {APPROVED_VIEW} FETCH FIRST 5 ROWS ONLY",
        ),
        (
            f"SELECT * FROM {APPROVED_VIEW} FETCH FIRST 500 ROWS ONLY",
            f"SELECT * FROM {APPROVED_VIEW} LIMIT 51",
        ),
        ("-- governed\nSELECT ';' AS marker;", "/* governed */ SELECT ';' AS marker LIMIT 51"),
    ],
)
def test_authorizes_narrow_select_and_applies_overflow_cap(
    policy: SnowflakeSqlPolicy,
    sql: str,
    expected: str,
) -> None:
    assert policy.authorize(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "/* unterminated",
        "SELECT 'unterminated",
        "SELECT 1; SELECT 2",
        "VALUES (1)",
        "SHOW TABLES",
        "DESCRIBE TABLE GOVERNED_DATABASE.GOVERNED_SCHEMA.APPROVED_VIEW",
        "EXPLAIN SELECT 1",
        "WITH x AS (SELECT 1) DELETE FROM target",
        "WITH x AS (SELECT 1) UPDATE target SET value = 1",
        "WITH x AS (SELECT 1) INSERT INTO target SELECT * FROM x",
        "WITH approved AS (SELECT * FROM approved) SELECT * FROM approved",
        "DELETE FROM target",
        "UPDATE target SET value = 1",
        "INSERT INTO target VALUES (1)",
        "MERGE INTO target USING source ON target.id = source.id WHEN MATCHED THEN DELETE",
        "CREATE TABLE target (value NUMBER)",
        "DROP TABLE target",
        "CALL procedure_name()",
        "EXECUTE IMMEDIATE 'SELECT 1'",
        "ALTER SESSION SET QUERY_TAG = 'canary'",
        "USE ROLE ACCOUNTADMIN",
        "PUT 'file:///tmp/data.csv' @stage",
        "GET @stage 'file:///tmp'",
        "REMOVE @stage/path",
        "LIST @stage",
        "COPY INTO target FROM @stage",
        "COPY INTO @stage FROM (SELECT 1)",
        "SELECT * FROM @stage/path",
        "SELECT * FROM TABLE(INFER_SCHEMA(LOCATION => '@stage'))",
        "SELECT GET_PRESIGNED_URL(@stage, 'file.csv')",
        "SELECT BUILD_SCOPED_FILE_URL(@stage, 'file.csv')",
        "SELECT SYSTEM$WAIT(1)",
        "SELECT CURRENT_ROLE()",
        "SELECT CURRENT_ACCOUNT",
        "SELECT sequence_name.NEXTVAL",
        "SELECT SAFE_UDF(1)",
        "SELECT DB.SC.SAFE_UDF(1)",
        "SELECT * FROM GOVERNED_DATABASE.GOVERNED_SCHEMA.TABLE(FLATTEN(input => value))",
        "SELECT * FROM GOVERNED_DATABASE.GOVERNED_SCHEMA.UNAPPROVED_VIEW",
        "SELECT * FROM GOVERNED_SCHEMA.APPROVED_VIEW",
        "SELECT * FROM APPROVED_VIEW",
        f"SELECT other_alias.account_id FROM {APPROVED_VIEW} AS approved_alias",
        'SELECT * FROM "governed_database"."GOVERNED_SCHEMA"."APPROVED_VIEW"',
        f"SELECT * FROM {APPROVED_VIEW} AT(TIMESTAMP => '2026-01-01')",
        f"SELECT * FROM {APPROVED_VIEW} LIMIT NULL",
        f"SELECT * FROM {APPROVED_VIEW} LIMIT $1",
        f"SELECT * FROM {APPROVED_VIEW} LIMIT 10 PERCENT",
        f"SELECT * FROM {APPROVED_VIEW} LIMIT 10 WITH TIES",
        f"SELECT * FROM (SELECT * FROM {APPROVED_VIEW} LIMIT 10 PERCENT) AS nested_view",
        f"SELECT * FROM (SELECT * FROM {APPROVED_VIEW} LIMIT NULL) AS nested_view",
        f"SELECT * FROM {APPROVED_VIEW} OFFSET $1",
        f"SELECT * FROM {APPROVED_VIEW} UNION SELECT * FROM {APPROVED_VIEW}",
    ],
)
def test_rejects_querido_and_snowflake_hostile_corpus(
    policy: SnowflakeSqlPolicy,
    sql: str,
) -> None:
    with pytest.raises(QueryPolicyRejected, match=r"^$") as caught:
        policy.authorize(sql)

    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "allowed_views",
    [
        (),
        ("APPROVED_VIEW",),
        ("SCHEMA.APPROVED_VIEW",),
        ("database.schema.lowercase_view",),
        ('"DATABASE"."SCHEMA"."VIEW"',),
        ("DATABASE.SCHEMA.VIEW;DROP_TABLE",),
    ],
)
def test_rejects_unsafe_or_ambiguous_configured_views(allowed_views: tuple[str, ...]) -> None:
    with pytest.raises(QueryPolicyRejected, match=r"^$") as caught:
        SnowflakeSqlPolicy.from_view_names(allowed_views)

    assert caught.value.__cause__ is None


def test_policy_failure_does_not_write_sql_or_parser_error(
    policy: SnowflakeSqlPolicy,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = "SQL_POLICY_CANARY"

    with pytest.raises(QueryPolicyRejected, match=r"^$"):
        policy.authorize(f"SELECT '{canary}")

    captured = capsys.readouterr()
    assert canary not in captured.out
    assert canary not in captured.err
