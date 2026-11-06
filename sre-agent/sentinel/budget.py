"""R3.3: 15 tool calls and 10 minutes, enforced where the model cannot argue."""

import time


class BudgetExceeded(RuntimeError):
    """The agent has spent its allowance for this incident."""


class Budget:
    def __init__(self, max_calls: int = 15, max_seconds: float = 600, clock=time.monotonic):
        self.max_calls = max_calls
        self.max_seconds = max_seconds
        self._clock = clock
        self._started = clock()
        self.calls = 0

    @property
    def elapsed(self) -> float:
        return self._clock() - self._started

    def claim(self, tool: str, *, write: bool) -> int:
        if self.elapsed > self.max_seconds:
            raise BudgetExceeded(
                f"wall clock limit reached ({self.max_seconds:.0f}s); {tool} refused"
            )
        if write and self.calls >= self.max_calls:
            raise BudgetExceeded(
                f"tool call limit reached ({self.max_calls}); {tool} is a write and is refused"
            )
        self.calls += 1
        return self.calls
