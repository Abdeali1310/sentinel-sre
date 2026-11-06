"""The one error type a tool may raise: readable, safe to show the operator."""


class ToolError(RuntimeError):
    """A tool failed in a way the agent can report, with a readable reason."""
