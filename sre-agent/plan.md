# Sentinel — Build Plan

Companion to `spec.md`. Each milestone ends in something demonstrable, so a slip shows up early rather than at the recording.

## Timeline

| Date | Milestones | Notes |
|---|---|---|
| Nov 5 (evening) | M1, M2 | Target app runs; failure reproduces |
| Nov 6 (morning) | M3 | Alert lands in Mattermost |
| Nov 6 (afternoon) | M4, M5 | Tools work from the CLI; agent opens a PR |
| Nov 7 (morning) | M6 | Full loop through Switch |
| Nov 7 (afternoon) | M7 | Rollback, reset, docs, recording |
| Nov 7, 23:59 IST | Submission | Hard deadline |

## M1 — Target application (≈3h)

Build: FastAPI skeleton, settings, SQLite layer, `POST /payments` with idempotency, `GET /payments/{order_id}`, `/healthz`, `/metrics`, checkout page + CSS + JS, Dockerfile.

Acceptance: `docker compose up` → checkout page charges `$10.00` against Cashfree sandbox → green receipt → row in SQLite → counter visible at `/metrics`.

Risk: Cashfree sandbox quirks. Fallback: capture one real sandbox response into `replay` mode, decide deliberately, never silently.

## M2 — The defect and the trigger (≈2h)

Build: upstream response parsing that assumes `snake_case`; chaos endpoint (token, 50-request budget, 10-minute TTL, in-memory); regression test asserting camelCase input yields `502` + `FAILED`, not `500`.

Acceptance: chaos on → checkout returns `500`; chaos off or restart → `200`; `pytest -q` green.

Note: the defect is real and stays in the codebase's history. The trigger is the simulation, not the bug.

## M3 — Detection (≈2h)

Build: Prometheus config and rules, Alertmanager config with grouping, `alert-relay` (FastAPI + Mattermost webhook), compose wiring on ports `9091`, `9093`, `8085`.

Acceptance: enable chaos, fail 3 payments, alert appears in `#incidents` within 30s with severity, value, fingerprint, runbook link and `@sre-agent`; `repeat_interval` prevents a second post within 30 minutes.

## M4 — MCP tool server (≈3h)

Build: `mcp/server.py` (FastMCP), `config.py` (dotenv + startup validation), `budget.py` (15-call cap, write lockout), `redact.py`; tools `health_check`, `fetch_logs`, `query_prometheus`, `read_file`, `search_code`, `get_payment`, `run_tests`.

Acceptance: every tool runs from the CLI harness against the live stack; redaction covered by a test; budget test proves write tools are refused at call 16.

## M5 — Change and record-keeping tools (≈3h)

Build: `create_jira_ticket`, `update_jira_ticket`, `publish_fix` (Git Data API, path allowlist), `post_mattermost`, `get_ci_status`, `rollback`.

Acceptance: agent creates a `Bug`/`P1` incident in `KAN`; `publish_fix` opens a PR touching only `payments-api/`; an attempt to include `.github/workflows/ci.yml` is refused by a test; CI runs on the PR.

## M6 — Switch integration (≈3h, highest risk)

Build: `agent.template.yaml` (persona, provider `codex`, `directory`, `addressing: anyone`); `AGENTS.md`; room bound to Mattermost; `codex mcp add sre-tools`; milestone messages; deploy instruction handling.

Acceptance: alert mention wakes the agent; four milestone messages appear; `@sre-agent deploy` triggers `scripts/deploy.ps1`; verification numbers are quoted; Jira reaches `Done`.

Risk: Switch/Mattermost provisioning details. Mitigation: start this milestone the moment M4 is green, not after M5 is polished.

## M7 — Hardening, docs, recording (≈4h)

Build: `rollback` rehearsed end to end; `scripts/reset_demo.ps1`; README verification on a clean clone; ADRs; runbook; demo script; video.

Acceptance: the ten acceptance criteria in `spec.md` §6 pass, twice in a row, without manual fixing between runs.

## Dependency order

```
M1 ──▶ M2 ──▶ M3
        │
        └──▶ M4 ──▶ M5 ──▶ M6 ──▶ M7
```

M3 and M4 may run in parallel once M2 is green: detection needs no agent, and the agent's read tools need no alert.

## Risks

| Risk | Likelihood | Effect | Mitigation |
|---|---|---|---|
| Switch cannot deliver alert messages to the agent automatically | Medium | Beat 3 becomes manual | Verify during M4; fallback is a human mention, documented in README |
| Jira custom fields block ticket creation | Low | M5 stalled | Check the create screen before writing the tool |
| Cashfree sandbox latency or outage | Medium | Recording stalls | Pre-warm; `CASHFREE_MODE=replay` decided before recording |
| Codex free-tier turn limit truncates a run | Medium | Agent stops mid-incident | 15-call budget, one incident at a time, short prompts |
| Alert latency exceeds 2 minutes | Medium | Awkward pause on camera | Tighten `for:` to `1m` for recording only, note it |
| Deploy rebuild takes longer than the verification window | Low | Premature "resolved" | Wait for container health before the first smoke payment |

## Definition of done

The ten acceptance criteria in `spec.md` §6, plus:

- The three ADRs and the runbook describe what is actually built, not what was planned.
- `scripts/reset_demo.ps1` has been run at least three times without manual repair.
- The recorded run has no terminal fumbling: commands are pasted, not typed live.
- README's quick start has been followed on a clean clone by someone other than the author, or by the author in a fresh directory.

## Verification commands

```powershell
docker compose up -d --build
docker compose ps
curl.exe http://localhost:8001/healthz
curl.exe http://localhost:9091/-/healthy
curl.exe http://localhost:9093/-/healthy
uv run --project sre-agent/mcp pytest -q sre-agent/mcp/tests
docker compose exec payments-api pytest -q
```
