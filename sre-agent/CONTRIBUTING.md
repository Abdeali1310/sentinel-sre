# Contributing to Sentinel

Two halves: the target application (`payments-api/`) and the agent workspace (`sre-agent/`). The agent's docs assume no prior knowledge of either.

## Setup

Prerequisites: Docker Desktop, Python 3.13, [uv](https://docs.astral.sh/uv/), git. For the agent: Slack, Switch Console, Codex CLI.

```powershell
git clone https://github.com/Abdeali1310/sentinel-sre.git
cd sentinel-sre
Copy-Item .env.example .env
# Fill: CASHFREE_CLIENT_ID, CASHFREE_CLIENT_SECRET, CHAOS_TOKEN,
#       SLACK_WEBHOOK_URL, JIRA_EMAIL, JIRA_API_TOKEN, GITHUB_TOKEN
docker compose up -d --build
```

Verify:

```powershell
curl.exe http://localhost:8001/healthz
curl.exe http://localhost:9091/-/healthy
curl.exe http://localhost:9093/-/healthy
```

Agent setup:

```powershell
git clone https://github.com/Abdeali1310/sentinel-sre.git sre-agent/workspaces/sentinel-sre
uv pip install --python payments-api/.venv/Scripts/python.exe -r sre-agent/requirements.txt
$python = Resolve-Path payments-api/.venv/Scripts/python.exe
$server = Resolve-Path sre-agent/server.py
codex mcp add sre-tools -- $python $server
codex mcp list
```

Then add the agent from `sre-agent/agent.template.yaml` in Switch Console:

1. Templates → read `sre-agent/agent.template.yaml`. The form asks for one thing: the policy folder. Pick this checkout's `sre-agent/` directory. The file is version 2, which needs a server with agent management; a server without it takes the version-1 shape instead.
2. On the new agent, set the handle `sre-agent` (display name `Sentinel`), `codex`, `auto_approve` off, `auto_mode` on.
3. Add it to the existing private `#incidents` room with addressing `anyone`, so an alert mention wakes it.
4. Send a test mention. The agent's first call is `health_check`; if the room stays silent, the bridge or the mention is the problem, not the tools.

`scripts/deploy.ps1` is what `deploy_locally` runs. It takes no arguments and refuses a dirty or diverged checkout, so run it yourself from the repository root to prove the deploy path without the agent.

## Running tests

```powershell
cd payments-api   ; .\.venv\Scripts\python.exe -m pytest -q
cd ../sre-agent   ; ..\payments-api\.venv\Scripts\python.exe -m pytest -q
cd ../alert-relay ; ..\payments-api\.venv\Scripts\python.exe -m pytest -q
```

Both suites must pass before a pull request. CI runs the `payments-api` suite and `ruff` on every PR.

## Branch and commit conventions

- Branches: `fix/<JIRA-KEY>-<slug>` for incident fixes, `feat/<slug>` for product work, `docs/<slug>` for documentation.
- Commits: Conventional Commits — `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- Scope: one logical change per commit. No `wip`, no `fix typo` commits on top of a broken one.

## Pull requests

Every PR must:

1. Link its Jira ticket, or state that none exists.
2. Include a test for the behaviour it changes. A bug fix without a regression test is rejected.
3. Pass CI (lint, tests, image build).
4. Touch only `payments-api/` when it comes from the agent. Human PRs may touch anything.
5. Never include `.env`, tokens, or real customer data.

PRs created by the agent open with a disclaimer line and require the same review as any other. The agent cannot approve or merge.

## Changing the agent

Adding a tool:

1. Add a method to `sre-agent/sentinel/tools.py` with a typed signature and a docstring the model can read.
2. Register it in `sre-agent/server.py` and add its name to `TOOLS` in `sre-agent/cli.py`.
3. Add a test to `sre-agent/tests/`.
4. If it writes, claim the budget with `write=True`, call `_require_operator`, and update the table in `AGENTS.md`.

Changing behaviour:

- Policy that shapes reasoning belongs in `sre-agent/AGENTS.md`: `sre-agent/AGENT.md` is the text the Console injects as instructions, and it points there, so one file stays authoritative.
- Policy that constrains tools belongs in `AGENTS.md` and, when it must be enforceable, in code.
- Anything that changes the incident lifecycle updates `spec.md` and, if it is hard to reverse, gets an ADR in `sre-agent/docs/adr/`.

## Documentation hygiene

`GLOSSARY.md` is the vocabulary; use its terms in prose, commits and ticket titles. `spec.md` is the source of truth for behaviour — when code and spec disagree, fix one of them in the same PR. ADRs record decisions that are hard to reverse, surprising later, and chosen over a real alternative.

## Secrets

Never commit credentials. `.env` is ignored; `.env.example` carries placeholders only. If a token leaks into a commit, rotate it first, then rewrite history — in that order.
