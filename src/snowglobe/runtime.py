"""Process-local state shared by the single-analyst MCP and viewer backend."""

from snowglobe.broker import InProcessBroker

broker = InProcessBroker()
