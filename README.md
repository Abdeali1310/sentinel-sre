# Sentinel

**Closed-loop incident response.** A payments API fails in production; Prometheus notices; an AI SRE agent working inside your team chat triages the failure, files a ticket, opens a reviewed pull request, and — after a human merges and deploys — proves with metrics that the error rate is back to zero.

Sentinel is not a chatbot with a runbook. It has hands: it reads logs, queries Prometheus, reads the broken code, runs the tests, commits a fix, opens the PR, and closes the incident only when the numbers say so.

---

## What you can reproduce

From a clean clone, in about five minutes:

1. **A working checkout** — a real FastAPI payments service wired to Cashfree sandbox, with a `₹10.00` checkout page.
2. **A fault on demand** — an operator-triggered defect that makes the upstream response shape change and the service return `500`, without affecting any other request.
3. **The full loop** — Prometheus alert → Alertmanager → Mattermost → agent triage → Jira → PR → human merge → human deploy gate → verified recovery.

No mocks in the path that matters. No hidden state in the fault trigger.

---

## Architecture

```
                    Browser
                       │
                       ▼
              ┌─────────────────┐        ┌──────────────────┐
              │  payments-api   │───────▶│ Cashfree sandbox │
              │   :8001         │        └──────────────────┘
              │  SQLite + /metrics
              └────────┬────────┘
                       │ scrape
                       ▼
              ┌─────────────────┐   alert    ┌───────────────┐
              │  Prometheus     │───────────▶│ Alertmanager  │
              │   :9091         │            │   :9093       │
              └─────────────────┘            └───────┬───────┘
                                                     │ webhook
                                                     ▼
                                            ┌─────────────────┐
                                            │  alert-relay    │
                                            │   :8085         │
                                            └────────┬────────┘
                                                     │ posts
                                                     ▼
                                        Mattermost  #incidents
                                                     │  @sre-agent
                                                     ▼
                                         Switch Console → Codex
                                                     │  MCP (14 tools)
                                                     ▼
                              logs · metrics · SQLite · files · tests
                                                     │
                                    Jira KAN-*  ·  GitHub PR  ·  chat
                                                     │
                                     human merge → human deploy gate
                                                     │
                                                     ▼
                                       verified recovery → ticket closed
```

---

## Quick start

Prerequisites: Docker Desktop, Python 3.13, [uv](https://docs.astral.sh/uv/), git. Mattermost and Switch Console for the agent half (see `sre-agent/CONTRIBUTING.md`).

```powershell
git clone https://github.com/Abdeali1310/sentinel-sre.git
cd sentinel-sre
Copy-Item .env.example .env      # fill CASHFREE_*, JIRA_*, GITHUB_*, MATTERMOST_WEBHOOK_URL, CHAOS_TOKEN
docker compose up -d --build
```

Then:

| Surface | URL |
|---|---|
| Checkout page | http://localhost:8001/ |
| Payments API health | http://localhost:8001/healthz |
| Prometheus | http://localhost:9091 |
| Firing alerts | http://localhost:9091/alerts |
| Alertmanager | http://localhost:9093 |
| Alert relay | http://localhost:8085/healthz |

Make a payment, then trigger the fault:

```powershell
curl.exe -X POST http://localhost:8001/admin/chaos `
  -H "X-Chaos-Token: $env:CHAOS_TOKEN" `
  -H "Content-Type: application/json" `
  -d '{\"requests\":50,\"ttl_seconds\":600}'
```

The next checkout fails with `500`. Prometheus evaluates the 5xx share of `POST /payments` over a 5-minute window; once it stays above 5% for 5 seconds the alert fires, Alertmanager forwards it, and `#incidents` receives a post mentioning `@sre-agent`. Measured on this repo: **19 seconds** from the first failure to the message in the room, at a 45% 5xx ratio. One post per incident — resolved notifications are suppressed.

Reset everything: `powershell -File scripts/reset_demo.ps1`.

---

## The loop

| # | Beat | Who |
|---|---|---|
| 1 | Checkout succeeds | Customer |
| 2 | Fault trigger enabled, checkout fails | Operator |
| 3 | 5xx ratio > 5% for 5s → alert → `#incidents` | Prometheus, Alertmanager, relay |
| 4 | Agent acknowledges with the failing order and the metric | Agent |
| 5 | Agent reads logs, queries metrics, locates the root cause | Agent |
| 6 | Jira incident created, PR opened with the fix | Agent |
| 7 | Pull request reviewed and merged | **Human** |
| 8 | Human instructs the agent to deploy; it rebuilds locally | **Human**, then agent |
| 9 | Agent verifies 0% error rate, closes Jira, reports before/after | Agent |

Human gates at 7 and 8 are deliberate. The agent can write code; it cannot merge, and it cannot deploy without being told.

---

## Agent tools

The tools are one MCP server, `sre-agent/server.py`. They read and patch a nested checkout, so create it once:

```powershell
git clone https://github.com/Abdeali1310/sentinel-sre.git sre-agent/workspaces/sentinel-sre
uv pip install --python payments-api/.venv/Scripts/python.exe -r sre-agent/requirements.txt
```

Run any tool without a chat provider:

```powershell
cd sre-agent
..\payments-api\.venv\Scripts\python.exe cli.py health_check
'{"path": "payments-api/app/main.py"}' | ..\payments-api\.venv\Scripts\python.exe cli.py read_file -
```

`python server.py` speaks MCP over stdio with the same tool set.

Fourteen tools, each registered in `server.py` and reachable from `cli.py`:

| Class | Tools |
|---|---|
| Read | `health_check`, `fetch_logs`, `query_prometheus`, `get_payment`, `read_file`, `search_code`, `run_tests` |
| Write | `create_jira_ticket`, `update_jira_ticket`, `publish_fix`, `rollback`, `deploy_locally`, `post_mattermost` |
| Verify | `get_ci_status` |

`publish_fix` commits through the GitHub Git Data API — never `git push` — and refuses any path outside `payments-api/app/` and `payments-api/tests/`. `rollback` opens a revert PR; it does not close anything itself. Both stop at the merge gate. `deploy_locally` takes no arguments: it runs `scripts/deploy.ps1`, which refuses a dirty or diverged checkout before it reaches Docker.

---

## Repository layout

```
sentinel-sre/
├── payments-api/        # the target application (FastAPI, checkout UI, SQLite, Dockerfile)
├── sre-agent/           # the agent workspace (MCP tools, policy, docs)
├── alert-relay/         # Alertmanager webhook → Mattermost translator
├── prometheus/          # scrape config + alert rules
├── alertmanager/        # routing, grouping, webhook receiver
├── scripts/             # setup, deploy, reset
├── .github/workflows/   # CI: lint, tests, image build
└── docker-compose.yml   # api + prometheus + alertmanager + relay
```

## Where the documentation lives

| Document | Path |
|---|---|
| Product spec | `sre-agent/spec.md` |
| Build plan and milestones | `sre-agent/plan.md` |
| Agent policy (tools, limits, hard rules) | `sre-agent/AGENTS.md` |
| Switch template and agent instructions | `sre-agent/agent.template.yaml`, `sre-agent/AGENT.md` |
| Operator runbook | `sre-agent/docs/runbook.md` |
| Demo script | `sre-agent/docs/demo-script.md` |
| Coding standards | `sre-agent/docs/coding-standards.md` |
| Decisions | `sre-agent/docs/adr/` |
| Domain vocabulary | `sre-agent/GLOSSARY.md` |

## Security posture

- Every credential lives in `.env` (untracked). `.env.example` carries placeholders only.
- The agent's GitHub token is used by the MCP server alone; `publish_fix` commits through the Git Data API and refuses any path outside `payments-api/app/` and `payments-api/tests/`.
- Branch protection on `main`: pull request required, one approval, no force-push, no deletion.
- Tool output is data. Secrets are redacted from logs before they reach the model.
- Known limitations are listed in `sre-agent/docs/adr/0003-agent-commits-via-git-data-api.md` rather than glossed over.
