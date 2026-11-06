"""R3.3: the limits are code, not prompt wording."""

import pytest

from sentinel.budget import Budget, BudgetExceeded


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_fifteen_calls_are_allowed():
    budget = Budget(clock=FakeClock())

    for call in range(1, 16):
        assert budget.claim("query_prometheus", write=False) == call

    assert budget.calls == 15


def test_reads_still_work_after_the_limit_so_the_agent_can_explain_itself():
    budget = Budget(clock=FakeClock())
    for _ in range(15):
        budget.claim("fetch_logs", write=False)

    assert budget.claim("read_file", write=False) == 16


def test_writes_are_refused_from_call_sixteen():
    budget = Budget(clock=FakeClock())
    for _ in range(15):
        budget.claim("fetch_logs", write=False)

    with pytest.raises(BudgetExceeded):
        budget.claim("publish_fix", write=True)


def test_a_write_on_the_fifteenth_call_is_still_allowed():
    budget = Budget(clock=FakeClock())
    for _ in range(14):
        budget.claim("fetch_logs", write=False)

    assert budget.claim("create_jira_ticket", write=True) == 15
    with pytest.raises(BudgetExceeded):
        budget.claim("publish_fix", write=True)


def test_wall_clock_stops_everything_after_ten_minutes():
    clock = FakeClock()
    budget = Budget(clock=clock)
    budget.claim("health_check", write=False)

    clock.now += 601

    with pytest.raises(BudgetExceeded):
        budget.claim("fetch_logs", write=False)
