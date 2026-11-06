# Demo script

Target length **2:45**. One take after two clean rehearsals. Screen 1920×1080, browser at 100%, notifications off, terminal font 16pt.

## Pre-flight (T−30 minutes)

- [ ] `powershell -File scripts/reset_demo.ps1` — ends green
- [ ] Happy-path payment succeeds; receipt visible
- [ ] Chaos disabled (`DELETE /admin/chaos` returns `{"active": false}`)
- [ ] `@sre-agent` online in Switch Console
- [ ] `#incidents` private, only you and the agent
- [ ] Jira ticket from the last rehearsal left in place (proves history); new one will be created
- [ ] `CASHFREE_MODE` decided: `sandbox` if healthy, `replay` if the sandbox is slow — decide now, not on camera
- [ ] Prometheus at `/alerts` shows no firing alert; `http://localhost:8085/healthz` returns `{"status":"ok"}`
- [ ] Prometheus `/rules` shows `PaymentsApi5xxSpike` at `health=ok` (not `err`)
- [ ] Terminal opened at repo root with `$env:CHAOS_TOKEN` already exported
- [ ] Screen recorder test-clipped and audio checked

## Beats

| Time | On screen | Action | Voiceover |
|---|---|---|---|
| 0:00 | Checkout page | Click **Pay now**, show spinner, green receipt `ORD-… paid` | "This is a ₹10 checkout against Cashfree sandbox. Normal traffic, normal day." |
| 0:20 | Terminal | Paste chaos `curl` → "fault trigger enabled for 50 requests" | "An operator enables a known-bad upstream condition: the provider starts returning `orderId` instead of `order_id`." |
| 0:28 | Checkout | Pay again → red banner "Something went wrong" | "The customer sees a failure. The stack trace stays in the logs, where it belongs." |
| 0:40 | Prometheus → Mattermost | Cut to `#incidents`; the alert lands ~20 s after the first failure | "Prometheus sees the 5xx ratio cross five percent. Alertmanager forwards it, the relay posts it, and it mentions the agent." |
| 1:05 | Mattermost | Agent milestone 1: symptom, the measured 5xx ratio, failing order id | "No prompt. The alert woke the agent. It states the symptom with a number before touching anything." |
| 1:12 | Mattermost | Milestone 2 — root cause: unvalidated upstream response shape, with a log line as evidence | "Four tool calls: logs, metric, the failed payment, the code. It names the root cause and shows the evidence." |
| 1:35 | Mattermost + Jira | Ticket `KAN-…` created; milestone 3 — PR link | "The ticket is diagnostic, not a copy of the alert. Then a branch, a regression test, and a pull request." |
| 1:50 | GitHub PR | Scroll the diff: model validation where the dict index used to be; test file added | "The fix is a real change with a test that fails on the old code. The agent cannot merge this — that is my job." |
| 2:00 | GitHub + Mattermost | Click **Merge**; type in chat: `@sre-agent the PR is merged. Deploy and verify.` | "I merge, then I pass the deploy gate myself." |
| 2:10 | Mattermost | `deploy_locally` output: the built commit sha, then `healthz ok after Ns` | "The agent deploys the merged commit locally, and the rebuilt container clears the fault state — a clean slate to measure against." |
| 2:20 | Mattermost | Milestone 4 — measured before → after error ratio, "10/10 smoke payments passed" + Jira `Done` | "It checks metrics and smoke payments, not the PR status. Then it closes the ticket and reports the number that matters." |
| 2:35 | Architecture slide | Static image of the loop | "Alert, diagnose, fix, review, deploy, verify. The agent does the work; the human keeps the keys." |

## Exact lines to type

Chaos:

```powershell
curl.exe -X POST http://localhost:8001/admin/chaos -H "X-Chaos-Token: $env:CHAOS_TOKEN" -H "Content-Type: application/json" -d '{\"requests\":50,\"ttl_seconds\":600}'
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

## Editing notes

- The alert lands ~20 s after the first failure, so no latency trim is needed; keep the timestamp visible.
- Insert a 3-second title card at 0:00: "Sentinel — closed-loop incident response".
- No background music over voiceover. No captions needed if the room text is legible.
- End card: repository URL, and one line naming Switch as the chat bridge.

## What must not appear

The event name, organiser names, "judges", "submission", or any date-specific hackathon language. This is a product walkthrough.
