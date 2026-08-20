"""Small Snowflake read-query policy for the local viewer."""

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import ErrorLevel, exp
from sqlglot.optimizer.scope import traverse_scope

from snowglobe.mvp_limits import MVP_MAXIMUM_VIEWPORT_ROWS

_UNQUOTED_IDENTIFIER = re.compile(r"^[A-Z_][A-Z0-9_$]*$")


class QueryPolicyRejected(Exception):
    """A deliberately detail-free policy rejection."""


@dataclass(frozen=True, slots=True)
class SnowflakeSqlPolicy:
    """Authorize one read query against configured views and impose a row cap."""

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
            if len(statements) != 1 or not isinstance(statements[0], exp.Query):
                raise QueryPolicyRejected
            statement = statements[0]
            self._validate(statement)
            _apply_row_cap(statement, self.maximum_rows + 1)
            return statement.sql(dialect="snowflake")
        except Exception:
            raise QueryPolicyRejected from None

    def _validate(self, statement: exp.Query) -> None:
        """Recursively authorize every external relation in the read-query AST."""

        scopes = traverse_scope(statement)
        if scopes is None:
            raise QueryPolicyRejected
        for scope in scopes:
            for relation, source in scope.selected_sources.values():
                if isinstance(source, exp.Table):
                    self._validate_table(source)
                elif isinstance(relation, (exp.Query, exp.Table, exp.Values)):
                    continue
                else:
                    # Table-producing functions are relation sources rather than
                    # ordinary expressions and can read data without a Table node.
                    raise QueryPolicyRejected

    def _validate_table(self, table: exp.Table) -> None:
        if not isinstance(table.this, exp.Identifier):
            raise QueryPolicyRejected
        if not table.catalog and not table.db:
            raise QueryPolicyRejected
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


def _canonical_identifier(identifier: exp.Identifier | str) -> str:
    if isinstance(identifier, str):
        return identifier.upper()
    value = identifier.this
    if not isinstance(value, str):
        raise QueryPolicyRejected
    return value if identifier.quoted else value.upper()


def _apply_row_cap(statement: exp.Query, maximum_rows: int) -> None:
    limit = statement.args.get("limit")
    if limit is None:
        statement.limit(maximum_rows, copy=False)
        return
    options = limit.args.get("limit_options")
    if options is not None and (options.args.get("percent") or options.args.get("with_ties")):
        statement.set("limit", exp.Limit(expression=exp.Literal.number(maximum_rows)))
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
