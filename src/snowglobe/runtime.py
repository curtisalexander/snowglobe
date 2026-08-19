"""Process-local state shared by the single-analyst MCP and viewer backend."""

from snowglobe.broker import InProcessBroker
from snowglobe.mvp_limits import MVP_MAXIMUM_PENDING_REQUESTS, MVP_MAXIMUM_TTL

broker = InProcessBroker(
    maximum_ttl=MVP_MAXIMUM_TTL,
    maximum_pending_requests=MVP_MAXIMUM_PENDING_REQUESTS,
)
