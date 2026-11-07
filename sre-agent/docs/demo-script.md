# Demo script — Sentinel

Target length **3:00**. One take after two clean rehearsals. Screen 1920×1080, browser at 100%, notifications off, terminal font 16pt.

## Pre-flight (T−30 minutes)

- [ ] `powershell -File scripts/reset_demo.ps1` — ends green
- [ ] Happy-path payment succeeds; receipt shows `₹10.00 paid`
- [ ] Chaos disabled (`DELETE /admin/chaos` returns `{"active": false}`)
- [ ] `@sre-agent` online in Switch Console
- [ ] `#incidents` private, only you and the agent
- [ ] Jira ticket from the last rehearsal left in place (proves history); new one will be created
- [ ] `CASHFREE_MODE` decided: `sandbox` if healthy, `replay` if the sandbox is slow — decide now, not on camera
- [ ] Prometheus `/alerts` shows no firing alert; `http://localhost:8085/healthz` returns `{"status":"ok"}`
- [ ] Prometheus `/rules` shows `PaymentsApi5xxSpike` at `health=ok` (not `err`)
- [ ] Terminal opened at repo root with `$env:CHAOS_TOKEN` already exported
- [ ] Screen recorder test-clipped and audio checked

## Beats

| Time | On screen | Action | Voiceover |
|---|---|---|---|
| 0:00 | Checkout page | Click **Pay now**, show spinner, green receipt `ORD-… paid` | "This is a ₹10 checkout against Cashfree sandbox. Normal traffic, normal day." |
| 0:20 | Terminal | Paste chaos `curl` → "fault trigger enabled for 50 requests" | "An operator enables a known-bad upstream condition: the provider starts returning `orderId` instead of `order_id`." |
| 0:28 | Checkout | Pay again → red banner "Something went wrong. Please try again." | "The customer sees a failure. The stack trace stays in the logs, where it belongs." |
| 0:40 | Prometheus → Slack | Cut to `#incidents`; the alert lands ~20 s after the first failure | "Prometheus sees the 5xx ratio cross five percent. Alertmanager forwards it, the relay posts it, and it mentions the agent." |
| 1:05 | Slack | Agent milestone 1: symptom, the measured 5xx ratio, failing order id | "No prompt. The alert woke the agent. It states the symptom with a number before touching anything." |
| 1:12 | Slack | Milestone 2 — root cause: unvalidated upstream response shape, with a log line as evidence | "Four tool calls: logs, metric, the failed payment, the code. It names the root cause and shows the evidence." |
| 1:35 | Slack + Jira | Ticket `KAN-…` created; milestone 3 — PR link | "The ticket is diagnostic, not a copy of the alert. Then a branch, a regression test, and a pull request." |
| 1:50 | GitHub PR | Scroll the diff: model validation where the dict index used to be; test file added | "The fix is a real change with a test that fails on the old code. The agent cannot merge this — that is my job." |
| 2:00 | GitHub + Slack | Click **Merge**; type in chat: `@sre-agent the PR is merged. Deploy and verify.` | "I merge, then I pass the deploy gate myself." |
| 2:10 | Slack | `deploy_locally` output: the built commit sha, then `healthz ok after Ns` | "The agent deploys the merged commit locally, and the rebuilt container clears the fault state — a clean slate to measure against." |
| 2:20 | Slack | Milestone 4 — measured before → after error ratio, "10/10 smoke payments passed" + Jira `Done` | "It checks metrics and smoke payments, not the PR status. Then it closes the ticket and reports the number that matters." |
| 2:35 | Architecture slide | Static image of the loop | "Alert, diagnose, fix, review, deploy, verify. The agent does the work; the human keeps the keys." |

## Exact chat messages

### What the human types

Chaos (terminal, not chat):

```powershell
curl.exe -X POST http://localhost:8001/admin/chaos `
  -H "X-Chaos-Token: $env:CHAOS_TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"requests":50,"ttl_seconds":600}'
```

The only chat instruction in the whole run — the deploy gate:

```
@sre-agent the PR is merged. Deploy and verify.
```

If the agent goes silent for more than 60 seconds, a legitimate operator action:

```
@sre-agent status
```

### What the agent posts (expected)

These are the four milestone messages, top-level, no per-tool narration. The exact wording will vary with the numbers the run produces; the shape below is what the procedure in `AGENTS.md` produces.

**Milestone 1 — Acknowledge (after `health_check` + triage):**

```
@operator Payments API is failing. 5xx ratio on POST /payments is 45% over the last 5 minutes (threshold 5%). Failing order: ORD-142857. health_check: payments-api ok, Prometheus ok, Alertmanager ok.
```

**Milestone 2 — Root cause (after logs, metrics, get_payment, read_file):**

```
Root cause: POST /payments trusts the upstream response shape instead of validating it. With the chaos trigger active, Cashfree returns `orderId`; the code reads `raw["order_id"]`, that key is missing, and the payment is stored FAILED with error `upstream_contract`.

Evidence: `payments-api/app/main.py:107` reads `raw["order_id"]` with no validation; `payments-api/app/chaos.py` renames those keys to camelCase for the next 50 requests.
```

**Milestone 3 — Change (after create_jira_ticket + publish_fix + update_jira_ticket):**

```
Jira ticket KAN-9 created (Task, P1). Pull request #3 opens the fix:
  branch  fix/KAN-9-upstream-response-shape
  title   validate upstream response shape before indexing it
  https://github.com/Abdeali1310/sentinel-sre/pull/3

Diff summary: model-validate the upstream dict in `payments-api/app/main.py` and add a regression test in `payments-api/tests/test_upstream_contract.py` that asserts a camelCase response returns 502 + FAILED, not 500. Tests pass before the PR is opened. I cannot merge this — the operator must.
```

**Milestone 4 — Resolved (after deploy_locally + smoke payments + metrics poll + update_jira_ticket):**

```
Incident KAN-9 resolved.

Before → after: 5xx ratio 45.0% → 0.0% over the last 5 minutes.
Smoke: 10/10 payments returned 200.
PR #3 merged and deployed (commit 58315a1).
Jira KAN-9 transitioned to Done.
https://github.com/Abdeali1310/sentinel-sre/pull/3
```

### What the agent never says

- No per-tool narration ("I'm now running fetch_logs…").
- No emoji, no exclamation marks, no "I've gone ahead and".
- No merge, no force-push, no deploy without the explicit instruction above.
- No invented numbers — every figure comes from `query_prometheus` or the smoke loop.

## Exact lines to type

Chaos:

```powershell
curl.exe -X POST http://localhost:8001/admin/chaos -H "X-Chaos-Token: $env:CHAOS_TOKEN" -H "Content-Type: application/json" -d '{"requests":50,"ttl_seconds":600}'
```

Deploy gate (the only agent instruction in the whole run):

```
@sre-agent the PR is merged. Deploy and verify.
```

## Contingencies

| Problem | Recovery on camera |
|---|---|
| Alert late (>60 s) | Cut to Prometheus graph showing the ratio rising, say "alert is firing", continue. Do not sit in silence. |
| Alert never fires | The rule is scoped to `path="/payments"`; if the ratio sits near 1% something is diluting it. Stale 5xx samples from a previous drill also keep it `pending` — clear the TSDB and re-run. |
| Agent silent >60s | Type `@sre-agent status` — a legitimate operator action, not a hack. |
| PR creation fails | Show the tool error in chat, then `scripts/` fallback: `git` commit + PR by hand, and say the automation step failed. Honesty reads better than a hidden retry. |
| Deploy rebuild slow | Cut the wait; the verification numbers are the point, not the build. |
| Verification fails | Do **not** hide it. Show the escalation message and the open ticket — that is the closed loop working, not failing. |
| Cashfree slow at 0:00 | Use the pre-recorded happy path clip captured in pre-flight. |

## Switch Console — import and bind the agent

These are the UI steps to get `@sre-agent` into `#incidents`. The template is version 2; the Console builds one form from `params:` and the policy folder you point it at.

### 1. Import the template

1. Open Switch Console → **Templates**.
2. Choose **Import from file** and select `sre-agent/agent.template.yaml` from this checkout.
3. The form asks for one field: **Sentinel policy folder** (the `params.workspace` directory). Set it to this checkout's `sre-agent/` directory — the one containing `AGENT.md` and `AGENTS.md`.
4. Submit the form. Switch creates the agent resource `sre-agent` using the provider `codex`, the directory you gave it, and the instructions from `AGENT.md`.

### 2. Set the handle and policy flags

On the new agent's page:

1. **Handle**: `sre-agent`
2. **Display name**: `Sentinel`
3. **Provider**: `codex` (already set by the template)
4. **Auto-approve**: **off** — `deploy_locally` rebuilds the whole stack, so every write stays behind an operator instruction.
5. **Auto-mode**: **on** — this is what lets an alert mention wake the agent without a direct reply.
6. **Addressing**: `anyone` — the alert relay mentions `@sre-agent`; with `addressing: anyone` the agent wakes on that mention even though it was not spoken to directly.

### 3. Bind the room

1. Add the agent to the existing private **#incidents** channel.
2. Confirm it is bound: the agent shows as online in Switch Console and present in `#incidents`.

### 4. Smoke test the binding

Send a test mention in `#incidents`:

```
@sre-agent ping
```

Expected: the agent's first tool call is `health_check`. It replies with the three dependencies (payments-api, Prometheus, Alertmanager) and their status. If the room stays silent for more than a minute, the problem is the room binding or the mention delivery — not the tools. Disable the agent in Switch Console to confirm the kill switch works, then re-enable.

### 5. One thing the template cannot do

The template creates the agent and points it at the policy folder. Two things are Console-UI-only and must be done after import:

- Setting the handle to `sre-agent` (the template names the resource, not the handle).
- Binding the agent to the existing `#incidents` room.

There is no Switch control-API route that writes an agent definition; the control API on port 49721 authenticates with `x-switch-control-token` and exposes `/agents` reads plus session create/delete only.

## Editing notes

- The alert lands ~20 s after the first failure, so no latency trim is needed; keep the timestamp visible.
- Insert a 3-second title card at 0:00: "Sentinel — closed-loop incident response".
- No background music over voiceover. No captions needed if the room text is legible.
- End card: repository URL, and one line naming Switch as the chat bridge.

## What must not appear

The event name, organiser names, "judges", "submission", or any date-specific hackathon language. This is a product walkthrough.
