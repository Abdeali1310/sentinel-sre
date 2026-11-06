"""Read tools against a fake HTTP transport and a temporary workspace."""

from pathlib import Path

import httpx
import pytest

from sentinel.config import Settings
from sentinel.tools import ToolError, Tools

SECRET = "ghp_9f3c2b1a4d5e6f708192a3b4c5d6e7f80912"


class FakeRunner:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, argv, cwd=None, timeout=None):
        self.calls.append((list(argv), str(cwd) if cwd else None))
        return type(
            "Done",
            (),
            {"stdout": self.stdout, "stderr": self.stderr, "returncode": self.returncode},
        )()


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        api_url="http://api.test",
        prometheus_url="http://prom.test",
        alertmanager_url="http://am.test",
        repo_dir=str(tmp_path),
        workspace_dir=str(tmp_path / "workspace"),
        tests_python="python-test",
        secrets=[SECRET],
        _env_file=None,
    )


def make_tools(tmp_path: Path, handler=None, runner=None) -> Tools:
    client = httpx.Client(
        transport=httpx.MockTransport(handler or (lambda request: httpx.Response(200)))
    )
    return Tools(make_settings(tmp_path), http=client, runner=runner or FakeRunner())


def test_read_file_returns_text_inside_the_workspace(tmp_path):
    target = tmp_path / "workspace" / "payments-api" / "app" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("def handler():\n    return 1\n", encoding="utf-8")

    result = make_tools(tmp_path).read_file("payments-api/app/main.py")

    assert "def handler" in result


def test_read_file_refuses_to_escape_the_workspace(tmp_path):
    (tmp_path / "workspace").mkdir()
    (tmp_path / ".env").write_text(f"GITHUB_TOKEN={SECRET}", encoding="utf-8")

    with pytest.raises(ToolError):
        make_tools(tmp_path).read_file("../.env")


def test_read_file_refuses_an_absolute_path_outside_the_workspace(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(ToolError):
        make_tools(tmp_path).read_file(str(outside))


def test_read_file_redacts_secrets_from_source(tmp_path):
    target = tmp_path / "workspace" / "payments-api" / "app" / "leak.py"
    target.parent.mkdir(parents=True)
    target.write_text(f'TOKEN = "{SECRET}"\n', encoding="utf-8")

    assert SECRET not in make_tools(tmp_path).read_file("payments-api/app/leak.py")


def test_search_code_finds_a_pattern_and_skips_vendor_dirs(tmp_path):
    root = tmp_path / "workspace" / "payments-api"
    (root / "app").mkdir(parents=True)
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / "app" / "main.py").write_text("raw = payload['order_id']\n", encoding="utf-8")
    (root / ".venv" / "lib" / "ignored.py").write_text(
        "raw = payload['order_id']\n", encoding="utf-8"
    )

    matches = make_tools(tmp_path).search_code("order_id", glob="*.py")

    assert [m["path"] for m in matches] == ["payments-api/app/main.py"]
    assert matches[0]["line"] == 1


def test_search_code_requires_a_pattern_that_can_compile(tmp_path):
    (tmp_path / "workspace").mkdir()

    with pytest.raises(ToolError):
        make_tools(tmp_path).search_code("(", glob="*.py")


def test_fetch_logs_uses_a_fixed_argv_and_redacts(tmp_path):
    runner = FakeRunner(stdout=f"startup failed with {SECRET}\nKeyError: 'order_id'")

    output = make_tools(tmp_path, runner=runner).fetch_logs(tail=50)

    argv, cwd = runner.calls[0]
    assert argv[:5] == ["docker", "compose", "-f", "docker-compose.yml", "logs"]
    assert "--tail" in argv and "50" in argv
    assert SECRET not in output
    assert "KeyError" in output


def test_fetch_logs_bounds_the_tail(tmp_path):
    runner = FakeRunner()

    make_tools(tmp_path, runner=runner).fetch_logs(tail=100000)

    argv, _ = runner.calls[0]
    assert argv[argv.index("--tail") + 1] == "2000"


def test_query_prometheus_returns_the_series(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "result": [
                        {"metric": {"path": "/payments"}, "value": [1, "0.42"]},
                    ]
                },
            },
        )

    result = make_tools(tmp_path, handler=handler).query_prometheus(
        "sum(rate(payments_http_requests_total[5m]))"
    )

    assert "prom.test/api/v1/query" in seen["url"]
    assert result["result"][0]["value"] == [1, "0.42"]


def test_query_prometheus_reports_a_query_error_instead_of_inventing_data(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"status": "error", "error": "bad query"})

    with pytest.raises(ToolError, match="bad query"):
        make_tools(tmp_path, handler=handler).query_prometheus("nonsense(")


def test_get_payment_returns_the_row(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/payments/ORD-1001"
        return httpx.Response(200, json={"order_id": "ORD-1001", "status": "FAILED"})

    payment = make_tools(tmp_path, handler=handler).get_payment("ORD-1001")

    assert payment["status"] == "FAILED"


def test_get_payment_turns_a_404_into_a_readable_error(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "payment not found"})

    with pytest.raises(ToolError, match="not found"):
        make_tools(tmp_path, handler=handler).get_payment("ORD-9999")


def test_health_check_reports_each_dependency(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.test":
            return httpx.Response(200, json={"status": "ok", "database": "ok"})
        if request.url.host == "prom.test":
            return httpx.Response(200, text="Prometheus is Ready.")
        return httpx.Response(503, text="nope")

    report = make_tools(tmp_path, handler=handler).health_check()

    assert report["ok"] is False
    assert report["dependencies"]["payments-api"]["ok"] is True
    assert report["dependencies"]["prometheus"]["ok"] is True
    assert report["dependencies"]["alertmanager"]["ok"] is False
    assert report["dependencies"]["alertmanager"]["detail"]


def test_run_tests_uses_the_project_venv_and_reports_the_summary(tmp_path):
    runner = FakeRunner(stdout="25 passed, 2 xfailed in 1.02s\n", returncode=0)

    result = make_tools(tmp_path, runner=runner).run_tests()

    argv, cwd = runner.calls[0]
    assert argv[0] == "python-test"
    assert argv[1:] == ["-m", "pytest", "-q"]
    assert cwd == str(tmp_path / "payments-api")
    assert result["ok"] is True
    assert "25 passed" in result["output"]


def test_run_tests_reports_failure_with_the_output(tmp_path):
    runner = FakeRunner(stdout="1 failed, 25 passed\nE KeyError\n", returncode=1)

    result = make_tools(tmp_path, runner=runner).run_tests()

    assert result["ok"] is False
    assert "1 failed" in result["output"]


def test_deploy_locally_runs_the_fixed_script_with_no_model_arguments(tmp_path):
    script = tmp_path / "scripts" / "deploy.ps1"
    script.parent.mkdir()
    script.write_text("# deploy\n", encoding="utf-8")
    runner = FakeRunner(stdout="deployed abc123, healthz ok after 8s\n")

    result = make_tools(tmp_path, runner=runner).deploy_locally(requested_by="Abdeali")

    argv, cwd = runner.calls[0]
    assert argv[0] == "powershell"
    assert argv[-2:] == ["-File", str(script)]
    assert cwd == str(tmp_path)
    assert result == {
        "ok": True,
        "exit_code": 0,
        "output": "deployed abc123, healthz ok after 8s",
    }


def test_deploy_locally_reports_a_refusal_instead_of_raising(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "deploy.ps1").write_text("# deploy\n", encoding="utf-8")
    runner = FakeRunner(stderr="refusing to deploy: 3 uncommitted path(s)\n", returncode=2)

    result = make_tools(tmp_path, runner=runner).deploy_locally()

    assert result["ok"] is False
    assert result["exit_code"] == 2
    assert "uncommitted" in result["output"]


def test_deploy_locally_refuses_when_the_script_is_missing(tmp_path):
    with pytest.raises(ToolError, match="deploy.ps1"):
        make_tools(tmp_path).deploy_locally()
