"""The deploy script refuses anything it cannot vouch for, before Docker runs.

Each test copies the real script into a throwaway repository and asserts the
exit code, so the refusal paths are exercised exactly as `deploy_locally` runs
them. Nothing here reaches Docker: every assertion fires before `compose up`.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy.ps1"

pytestmark = pytest.mark.skipif(
    not SCRIPT.is_file() or not shutil.which("powershell") or not shutil.which("git"),
    reason="needs PowerShell, git, and scripts/deploy.ps1",
)


def git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(path), check=True, capture_output=True, text=True)


def run_script(root: Path) -> int:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / "deploy.ps1"),
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=120,
    ).returncode


def make_checkout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir()
    shutil.copy2(SCRIPT, root / "scripts" / "deploy.ps1")
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (root / ".env.example").write_text("PLACEHOLDER=\n", encoding="utf-8")
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "test")
    git(root, "add", "-A")
    git(root, "commit", "-m", "init")


def test_refuses_a_directory_that_is_not_a_checkout(tmp_path):
    (tmp_path / "scripts").mkdir()
    shutil.copy2(SCRIPT, tmp_path / "scripts" / "deploy.ps1")

    assert run_script(tmp_path) == 1


def test_refuses_a_dirty_working_tree(tmp_path):
    make_checkout(tmp_path)
    (tmp_path / ".env.example").write_text("PLACEHOLDER=changed\n", encoding="utf-8")

    assert run_script(tmp_path) == 2


def test_refuses_a_checkout_with_no_remote(tmp_path):
    make_checkout(tmp_path)

    assert run_script(tmp_path) == 3


def test_refuses_a_local_commit_that_never_reached_origin_main(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
    )
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    make_checkout(work)
    git(work, "push", "-u", "origin", "main")

    (work / "local-only.txt").write_text("x\n", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-m", "local only")

    assert run_script(work) == 4
