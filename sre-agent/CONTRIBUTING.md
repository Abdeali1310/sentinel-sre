# Contributing to Sentinel

Two halves: the target application (`payments-api/`) and the agent workspace (`sre-agent/`). The agent's docs assume no prior knowledge of either.

## Setup

Prerequisites: Docker Desktop, Python 3.13, [uv](https://docs.astral.sh/uv/), git. For the agent: Mattermost, Switch Console, Codex CLI.

```powershell
git clone https://github.com/Abdeali1310/sentinel-sre.git
cd sentinel-sre
Copy-Item .env.example .env
# Fill: CASHFREE_CLIENT_ID, CASHFREE_CLIENT_SECRET, CHAOS_TOKEN,
#       MATTERMOST_WEBHOOK_URL, JIRA_EMAIL, JIRA_API_TOKEN, GITHUB_TOKEN
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
powershell -File scripts/setup_workspace.ps1     # clone of this repo into sre-agent/workspaces/
codex mcp add sre-tools -- uv run --project sre-agent/mcp python -m mcp.server
codex mcp list
```

Then import `sre-agent/agent.template.yaml` in Switch Console and connect the Mattermost bridge.

## Running tests

```powershell
docker compose exec payments-api pytest -q
uv run --project sre-agent/mcp pytest -q
```

Both suites must pass before a pull request. CI runs them on every PR.

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

1. Add a module under `sre-agent/mcp/tools/` with a typed signature and a docstring the model can read.
2. Register it in `sre-agent/mcp/server.py`.
3. Add a test to `sre-agent/mcp/tests/`.
4. If it writes, update the budget classification in `budget.py` and the table in `AGENTS.md`.

Changing behaviour:

- Policy that shapes reasoning belongs in `sre-agent/prompts/sre-agent.md`.
- Policy that constrains tools belongs in `AGENTS.md` and, when it must be enforceable, in code.
- Anything that changes the incident lifecycle updates `spec.md` and, if it is hard to reverse, gets an ADR in `sre-agent/docs/adr/`.

## Documentation hygiene

`GLOSSARY.md` is the vocabulary; use its terms in prose, commits and ticket titles. `spec.md` is the source of truth for behaviour — when code and spec disagree, fix one of them in the same PR. ADRs record decisions that are hard to reverse, surprising later, and chosen over a real alternative.

## Secrets

Never commit credentials. `.env` is ignored; `.env.example` carries placeholders only. If a token leaks into a commit, rotate it first, then rewrite history — in that order.
