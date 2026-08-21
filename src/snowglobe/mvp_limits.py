"""Fixed resource budgets for the constrained Snowflake MVP."""

from datetime import timedelta

from snowglobe.arrow_stream import ArrowAdmissionLimits

MVP_MAXIMUM_TTL = timedelta(minutes=5)
MVP_MAXIMUM_PENDING_REQUESTS = 1
MVP_MAXIMUM_REQUESTS = 100

MVP_LOGIN_TIMEOUT_SECONDS = 30
MVP_NETWORK_TIMEOUT_SECONDS = 60
MVP_SOCKET_TIMEOUT_SECONDS = 15
MVP_STATEMENT_TIMEOUT_SECONDS = 60
MVP_QUEUED_TIMEOUT_SECONDS = 15

MVP_MAXIMUM_VIEWPORT_ROWS = 50
MVP_MAXIMUM_VIEWPORT_BYTES = 256 * 1024
MVP_ARROW_LIMITS = ArrowAdmissionLimits(
    maximum_rows=MVP_MAXIMUM_VIEWPORT_ROWS,
    maximum_columns=32,
    maximum_cell_bytes=16 * 1024,
    maximum_arrow_bytes=MVP_MAXIMUM_VIEWPORT_BYTES,
    maximum_decoded_bytes=MVP_MAXIMUM_VIEWPORT_BYTES,
)
