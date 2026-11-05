# Sentinel — Product Specification

Status: accepted for build · Owner: Abdeali · Last updated: 2026-11-05

## 1. Purpose

Sentinel closes the loop between *noticing* a production failure and *proving* it is fixed.

A human team and an AI SRE agent share one chat room. When the payments service starts failing, an alert appears in that room, the agent investigates using real tools, proposes a reviewed change, and — once a human has merged and released it — verifies recovery against metrics before closing the incident.

The product is judged on four things: that the chat bridge is load-bearing, that a stranger can clone and reproduce it, that the idea solves a real team problem, and that the story is told clearly. Every requirement below exists to serve one of those.

## 2. Actors

| Actor | Responsibility |
|---|---|
| Customer | Uses the checkout page. Sees a receipt or a generic failure message. |
| Operator | The human in `#incidents`. Passes the Merge Gate and the Deploy Gate. Can issue `stop` or `rollback`. |
| Agent (`@sre-agent`) | Triages, diagnoses, files the ticket, prepares the fix, opens the PR, deploys when told, verifies, closes. Never merges. |
| Prometheus + Alertmanager + alert-relay | Detect the symptom and deliver one alert into the room. |
| Jira (`KAN`) | System of record for the incident. |
| GitHub | System of record for the change. |

## 3. Incident lifecycle

```
DETECTED ──▶ TRIAGED ──▶ CHANGE_PROPOSED ──▶ MERGED ──▶ DEPLOYED ──▶ VERIFIED ──▶ RESOLVED
    │            │              │                          │            │
    └────────────┴──────────────┴──────────────────────────┴────────────┴──▶ ESCALATED
```

- `DETECTED` — alert post exists in the room, carrying fingerprint and metric value.
- `TRIAGED` — the agent has logs, metric data, and a stated root cause.
- `CHANGE_PROPOSED` — branch pushed, PR open, Jira comment added.
- `MERGED` — human merged. Agent does not act until told to deploy.
- `DEPLOYED` — deploy script completed and the running image is built from `origin/main`.
- `VERIFIED` — smoke payments and metrics pass the thresholds in R6.
- `RESOLVED` — Jira transitioned to Done, final message posted.
- `ESCALATED` — any unmet gate; incident stays open with an evidence summary.

Every terminal state must be announced in the room. Silence is a failure mode.

## 4. Requirements

### R1 — Target application (`payments-api/`)

- **R1.1** FastAPI service with `GET /`, `POST /payments`, `GET /payments/{order_id}`, `GET /healthz`, `GET /metrics`, `POST /admin/chaos`, `DELETE /admin/chaos`.
- **R1.2** `POST /payments` requires an `Idempotency-Key` header; repeating a key returns the original payment and never creates a second provider order.
- **R1.3** SQLite table `payments(id, order_id, idempotency_key, amount, currency, status, provider_order_id, error, created_at)` with `status ∈ {CREATED, PAID, FAILED}`; `order_id` and `idempotency_key` are both unique.
- **R1.4** Checkout page: amount fixed at `₹10.00` (`CHECKOUT_AMOUNT`/`CHECKOUT_CURRENCY` in `app/main.py`, passed to the client via `data-*` attributes), payment summary card, "Pay now" button, pending spinner, green receipt on success, red professional banner ("Something went wrong. Please try again.") on failure. No stack traces, provider names, or error codes in the UI.
- **R1.5** Error taxonomy: `422` validation, `502` unacceptable upstream response (payment stored `FAILED`), `500` only for genuine unhandled defects.
- **R1.6** `CASHFREE_MODE` selects `sandbox` or `replay`. No silent fallback: `replay` is an explicit operator choice.

### R2 — Detection

- **R2.1** Expose `payments_http_requests_total{method,path,status_code}` and `payments_request_duration_seconds` histogram.
- **R2.2** Alert `PaymentsApi5xxSpike` fires when the 5xx ratio over 5 minutes exceeds `5%` for `2m`.
- **R2.3** Alertmanager: `group_wait: 10s`, `group_interval: 1m`, `repeat_interval: 30m`, single webhook receiver.
- **R2.4** alert-relay formats the alert with severity, current value, fingerprint, runbook URL, and the literal mention `@sre-agent`, then posts to `#incidents`.
- **R2.5** The alert payload carries a stable fingerprint so duplicate alerts are recognisable.

### R3 — Agent behaviour

- **R3.1** Defined by `sre-agent/agent.template.yaml`; `addressing: anyone`, private room, agent display name `Sentinel`, handle `@sre-agent`.
- **R3.2** The first tool call of every incident is `health_check()`. On failure the agent posts the failed dependency and stops.
- **R3.3** Limits, enforced in code and not only in the prompt: **15 tool calls**, **10 minutes wall clock**, **25 provider turns**. After 15 calls, write tools are refused; read tools remain available so the agent can explain itself.
- **R3.4** Four milestone messages, top-level, no per-tool narration: acknowledge, root cause, PR opened, resolved.
- **R3.5** Before creating a ticket, the agent searches Jira for an open incident with the same fingerprint. Duplicates are commented on, not recreated.
- **R3.6** The agent honours operator `stop` and `rollback` instructions at the next step boundary.

### R4 — Change

- **R4.1** Branch name `fix/<JIRA-KEY>-<slug>`. Commits are created through the GitHub Git Data API by `publish_fix`; the agent never runs `git push`.
- **R4.2** `publish_fix` refuses any path outside `payments-api/app/` and `payments-api/tests/`.
- **R4.3** PR body opens with `_Automated remediation by Sentinel (@sre-agent) — human review required._` and links the Jira ticket.
- **R4.4** The agent never merges, never force-pushes, never deletes branches.

### R5 — Deployment

- **R5.1** Deployment is human-gated: the operator types an instruction in the room.
- **R5.2** `deploy_locally` runs a fixed script with no arguments: `git -C <target-checkout> pull --ff-only`, assert `HEAD == origin/main`, then `docker compose up -d --build`.
- **R5.3** If the assertion fails (diverged checkout, dirty tree), the deploy refuses and the agent reports why.

### R6 — Verification and closure

- **R6.1** Post-deploy: 10 smoke payments, one every 3 seconds.
- **R6.2** Resolution requires 5-minute error ratio `< 1%` **and** all 10 smoke payments returning `200`, polled up to 10 times at 15-second intervals.
- **R6.3** On failure: exactly one rollback attempt (revert PR; human merges), then escalation with a comment describing what was tried. The ticket stays open.
- **R6.4** Closure: comment with before/after error rate and PR link, then transition via `JIRA_TRANSITION_DONE`.
- **R6.5** The final chat message quotes real numbers ("error rate 18.2% → 0%").

### R7 — Security and operability

- **R7.1** All credentials in a root `.env`, untracked; placeholders in `.env.example`.
- **R7.2** Logs are redacted for `api key / token / password / secret / bearer / client_secret` before reaching the agent; output capped at 20 KB.
- **R7.3** `read_file` is jailed to the agent workspace.
- **R7.4** Tools accept no model-supplied shell command; `deploy_locally` and `fetch_logs` use fixed argument vectors.
- **R7.5** Write actions check the requesting Mattermost username against an advisory allowlist and log the decision.
- **R7.6** The fault trigger requires `X-Chaos-Token`, is rate-bounded (50 requests / 10 minutes), and lives only in process memory.

## 5. Non-goals

- Multiple services, languages, or clusters. One API, one stack, one machine.
- Kubernetes, service mesh, or cloud deployment.
- Automatic merge, automatic deploy without a human instruction, or self-service rollback without a human merge.
- Refunds, Cashfree webhooks, customer lists, authentication for shoppers, multi-tenancy.
- An incident dashboard or a second UI. The room, the ticket, and the PR are the UI.
- Historical analytics, alert tuning UI, or on-call scheduling.

## 6. Acceptance criteria

1. Fresh clone + `docker compose up -d --build` yields a working checkout page.
2. One chaos call reproduces the failure; a restart clears it.
3. Alert reaches `#incidents` with `@sre-agent` within 30 seconds of the first 500s.
4. Agent completes triage → Jira → PR within 15 tool calls.
5. Merge + deploy instruction produces `0%` 5xx and a `Done` ticket.
6. Rollback path rehearsed successfully once.
7. `scripts/reset_demo.ps1` returns any state to green.
8. No secrets in git history; `.env` untracked.
9. README lets a stranger run it in five minutes.
10. No build-time or UI references to the event this was built for.

## 7. Open questions

| Question | Impact if wrong | Resolution path |
|---|---|---|
| Does Switch deliver the chat author's identity to MCP tools? | Soft allowlist becomes advisory only | Inspect room payload during first integration |
| Does `addressing: anyone` wake the agent on an alert mention it did not receive directly? | Alert → agent handoff may need a human nudge | Test with a real alert before recording |
| Are `KAN` transitions named `In Progress` / `Done`? | Tool call fails at closure | Check Jira workflow before M4 |
| Is the Cashfree sandbox stable during recording? | Demo stalls | Pre-warm, keep `CASHFREE_MODE=replay` ready |
