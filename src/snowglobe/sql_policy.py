"""Fail-closed Snowflake AST policy for the constrained MVP."""

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.optimizer.scope import Scope, traverse_scope

from snowglobe.mvp_limits import MVP_MAXIMUM_VIEWPORT_ROWS

_UNQUOTED_IDENTIFIER = re.compile(r"^[A-Z_][A-Z0-9_$]*$")
_SAFE_NODES = (
    exp.Select,
    exp.With,
    exp.CTE,
    exp.Subquery,
    exp.TableAlias,
    exp.From,
    exp.Table,
    exp.Join,
    exp.Column,
    exp.Identifier,
    exp.Star,
    exp.Alias,
    exp.Literal,
    exp.Boolean,
    exp.Null,
    exp.Where,
    exp.Group,
    exp.Having,
    exp.Qualify,
    exp.Order,
    exp.Ordered,
    exp.Limit,
    exp.Fetch,
    exp.LimitOptions,
    exp.Offset,
    exp.Distinct,
    exp.And,
    exp.Or,
    exp.Not,
    exp.Paren,
    exp.EQ,
    exp.NEQ,
    exp.GT,
    exp.GTE,
    exp.LT,
    exp.LTE,
    exp.Is,
    exp.In,
    exp.Between,
    exp.Like,
    exp.ILike,
    exp.Add,
    exp.Sub,
    exp.Mul,
    exp.Div,
    exp.Mod,
    exp.Neg,
    exp.Case,
    exp.If,
)


class QueryPolicyRejected(Exception):
    """A deliberately detail-free policy rejection."""


@dataclass(frozen=True, slots=True)
class SnowflakeSqlPolicy:
    """Authorize one narrow SELECT and impose the server-owned overflow cap."""

    allowed_views: frozenset[tuple[str, str, str]]
    maximum_rows: int = MVP_MAXIMUM_VIEWPORT_ROWS

    @classmethod
    def from_view_names(
        cls,
        allowed_views: tuple[str, ...],
        *,
        maximum_rows: int = MVP_MAXIMUM_VIEWPORT_ROWS,
    ) -> "SnowflakeSqlPolicy":
        try:
            views = frozenset(_configured_view(name) for name in allowed_views)
            if not views or maximum_rows <= 0:
                raise QueryPolicyRejected
        except Exception:
            raise QueryPolicyRejected from None
        return cls(allowed_views=views, maximum_rows=maximum_rows)

    def authorize(self, sql: str) -> str:
        """Return policy-generated Snowflake SQL or reject without detail."""

        try:
            statements = sqlglot.parse(sql, read="snowflake", error_level=ErrorLevel.RAISE)
            if len(statements) != 1 or not isinstance(statements[0], exp.Select):
                raise QueryPolicyRejected
            statement = statements[0]
            self._validate(statement)
            _apply_row_cap(statement, self.maximum_rows + 1)
            governed_sql = statement.sql(dialect="snowflake")

            round_trip = sqlglot.parse(
                governed_sql,
                read="snowflake",
                error_level=ErrorLevel.RAISE,
            )
            if len(round_trip) != 1 or not isinstance(round_trip[0], exp.Select):
                raise QueryPolicyRejected
            self._validate(round_trip[0])
            return governed_sql
        except Exception:
            raise QueryPolicyRejected from None

    def _validate(self, statement: exp.Select) -> None:
        cte_references = _cte_reference_ids(statement)
        for node in statement.walk():
            if isinstance(node, exp.Func):
                # The MVP function allowlist is intentionally empty. Functions can
                # add external, metadata, staged-file, or side-effectful behavior.
                raise QueryPolicyRejected
            if isinstance(node, exp.Table):
                self._validate_table(node, cte_references)
            elif not isinstance(node, _SAFE_NODES):
                raise QueryPolicyRejected
            if isinstance(node, (exp.Limit, exp.Fetch)):
                _validate_limit(node)
            elif isinstance(node, exp.Offset):
                _nonnegative_integer(node.expression)
        _validate_columns(statement)

    def _validate_table(self, table: exp.Table, cte_references: set[int]) -> None:
        if not isinstance(table.this, exp.Identifier):
            raise QueryPolicyRejected
        if not table.catalog and not table.db:
            if id(table) not in cte_references:
                raise QueryPolicyRejected
            return
        if not isinstance(table.args.get("catalog"), exp.Identifier) or not isinstance(
            table.args.get("db"), exp.Identifier
        ):
            raise QueryPolicyRejected
        view = (
            _canonical_identifier(table.args["catalog"]),
            _canonical_identifier(table.args["db"]),
            _canonical_identifier(table.this),
        )
        if view not in self.allowed_views:
            raise QueryPolicyRejected


def _configured_view(name: str) -> tuple[str, str, str]:
    parts = name.split(".")
    if len(parts) != 3 or any(_UNQUOTED_IDENTIFIER.fullmatch(part) is None for part in parts):
        raise QueryPolicyRejected
    return parts[0], parts[1], parts[2]


def _cte_reference_ids(statement: exp.Select) -> set[int]:
    references: set[int] = set()
    for scope in traverse_scope(statement):
        for table in scope.tables:
            source = scope.sources.get(table.alias_or_name)
            if isinstance(source, Scope):
                references.add(id(table))
    return references


def _validate_columns(statement: exp.Select) -> None:
    for scope in traverse_scope(statement):
        source_names = {name.upper() for name in scope.sources}
        for column in scope.columns:
            if not scope.sources or column.catalog or column.db:
                raise QueryPolicyRejected
            table = column.args.get("table")
            if table is not None:
                if not isinstance(table, exp.Identifier):
                    raise QueryPolicyRejected
                if _canonical_identifier(table) not in source_names:
                    raise QueryPolicyRejected


def _canonical_identifier(identifier: exp.Identifier | str) -> str:
    if isinstance(identifier, str):
        return identifier.upper()
    value = identifier.this
    if not isinstance(value, str):
        raise QueryPolicyRejected
    return value if identifier.quoted else value.upper()


def _validate_limit(limit: exp.Limit | exp.Fetch) -> None:
    if isinstance(limit, exp.Limit):
        options = limit.args.get("limit_options")
        if options is not None and (options.args.get("percent") or options.args.get("with_ties")):
            raise QueryPolicyRejected
        _nonnegative_integer(limit.expression)
        return
    if isinstance(limit, exp.Fetch):
        options = limit.args.get("limit_options")
        if options is None or options.args.get("percent") or options.args.get("with_ties"):
            raise QueryPolicyRejected
        _nonnegative_integer(limit.args.get("count"))
        return
    raise QueryPolicyRejected


def _apply_row_cap(statement: exp.Select, maximum_rows: int) -> None:
    limit = statement.args.get("limit")
    if limit is None:
        statement.limit(maximum_rows, copy=False)
        return
    expression = limit.expression if isinstance(limit, exp.Limit) else limit.args.get("count")
    if _nonnegative_integer(expression) > maximum_rows:
        statement.set("limit", exp.Limit(expression=exp.Literal.number(maximum_rows)))


def _nonnegative_integer(expression: exp.Expression | None) -> int:
    if not isinstance(expression, exp.Literal) or not expression.is_int:
        raise QueryPolicyRejected
    value = int(expression.this)
    if value < 0:
        raise QueryPolicyRejected
    return value
