# Sentinel — Operator Runbook

For the person in `#incidents`. The agent follows `AGENTS.md`; this document is what you do when something outside the agent misbehaves.

## Ports

| Service | Port |
|---|---|
| Checkout / API | 8001 |
| Prometheus | 9091 |
| Alertmanager | 9093 |
| Alert relay | 8085 |
| Mattermost (existing) | 8065 |

## Before a run

```powershell
docker compose ps                       # api, prometheus, alertmanager, alert-relay healthy
curl.exe http://localhost:8001/healthz
curl.exe http://localhost:8001/metrics | Select-String "payments_http_requests_total"
powershell -File scripts/reset_demo.ps1
```

- Checkout page loads and a `₹10.00` payment succeeds.
- `#incidents` is private, contains only the operator and `@sre-agent`.
- Switch Console shows the agent as online.
- Jira `KAN` transitions include `In Progress` and `Done`.

## Start and stop

```powershell
docker compose up -d --build
docker compose down            # keeps the SQLite file
docker compose down -v         # removes volumes too
docker compose logs -f payments-api
```

## Trigger the incident

```powershell
$env:CHAOS_TOKEN = (Select-String .env -Pattern '^CHAOS_TOKEN=(.*)$').Matches.Groups[1].Value
curl.exe -X POST http://localhost:8001/admin/chaos `
  -H "X-Chaos-Token: $env:CHAOS_TOKEN" `
  -H "Content-Type: application/json" `
  -d '{\"requests\":50,\"ttl_seconds\":600}'
```

Then fail three payments (three clicks, or three sequential `POST /payments`). Expected timeline:

| Elapsed | Event |
|---|---|
| 0s | first `500` |
| ~10s | 5xx share of `POST /payments` crosses 5%; the rule becomes `pending` |
| ~15s | `pending` → `firing` (the rule's `for: 5s`) |
| +2s | Alertmanager `group_wait` elapses; relay posts once to `#incidents` with `@sre-agent` |
| +30s | agent acknowledgement |

Measured on this stack: **19.2 s** from the first `500` to the relay's `POST /webhook`, at a 5xx ratio of **45.04%** (3 failures among the payment requests inside the window), and **exactly one** post — `repeat_interval: 30m` suppresses a second.

If nothing arrives by 3 minutes, see *Alert never fires*.

## Alert never fires

```powershell
curl.exe http://localhost:9091/api/v1/rules          # rule loaded?
curl.exe http://localhost:9091/api/v1/alerts         # state: pending/firing?
curl.exe http://localhost:9091/api/v1/targets        # payments-api UP?
curl.exe http://localhost:9093/-/healthy
curl.exe http://localhost:9093/api/v2/alerts
curl.exe http://localhost:8085/healthz
docker compose logs --tail=50 alert-relay
```

In order: is Prometheus scraping (`/targets` shows `payments-api` UP)? Is the rule expression returning a value (`/graph`)? Is Alertmanager receiving (`/api/v2/alerts`)? Is the relay's webhook URL correct in `.env`, and is the Mattermost webhook bound to `#incidents`?

Two traps worth checking before anything else:

- **The ratio is diluted.** The rule watches `path="/payments"` only. If you edit it to drop that matcher, Prometheus's own 5-second scrapes of `/metrics` (and the `/healthz` probes) will outnumber real traffic and hold the ratio near 1%, so the alert never fires. Three failures among a handful of payments is 40–50%; three failures among 60 scrapes is not.
- **Old failures are still in the window.** After a failed drill the 5-minute window keeps the 5xx samples alive, so the rule can sit `pending` on stale data. Clear the TSDB before re-running: `docker compose rm -sf prometheus; docker volume rm sentinel_prometheus-data; docker compose up -d prometheus`.
- **A repeat drill inside 30 minutes is silent on purpose.** `repeat_interval: 30m` means one post per incident; Alertmanager's notification log lives in its volume, so a fresh chaos burst within the window will fire again in `/api/v2/alerts` but post nothing. Recreate Alertmanager (`docker compose rm -sf alertmanager; docker volume rm sentinel_alertmanager-data; docker compose up -d alertmanager`) when you need a clean rehearsal.

A `200` from the relay's `/webhook` means Mattermost accepted the post. Alertmanager retries on any non-2xx, so a `502` in its log means the webhook URL or the room is wrong.

## The agent is stuck or looping

1. Type `@sre-agent stop` — it must acknowledge at the next step boundary.
2. If it does not, disable the agent in Switch Console. That is the authoritative kill switch; chat instructions are advisory.
3. Inspect what it actually did: `docker compose logs --tail=100 payments-api`, `/api/v1/alerts`, and the Jira ticket comments.
4. Reset with `scripts/reset_demo.ps1` and re-run from a clean state rather than trying to repair a half-finished incident.

Hard limits are enforced in the MCP server (15 tool calls, 10 minutes) and at the provider (25 turns). Hitting them is not a failure of the agent; it is the agent reporting that the incident needs a human.

## Deploy refuses

`scripts/deploy.ps1` refuses anything it cannot vouch for, before it reaches Docker. The exit code names the reason:

| Code | Message on stderr | What to do |
|---|---|---|
| 1 | `not a Sentinel checkout` | Run it from the repository root, next to `docker-compose.yml`. |
| 2 | `refusing to deploy: N uncommitted path(s)` | Commit or stash. The agent's own PR is merged, so the tree should be clean. |
| 3 | `refusing to deploy: git pull --ff-only failed` | Diverged or no upstream: `git fetch origin`, `git status`, `git log --oneline -3`. |
| 4 | `refusing to deploy: HEAD <sha> is not origin/main <sha>` | A local commit never reached GitHub. Push it through review, or reset to `origin/main`. |
| 5 | `docker compose up failed` | Read the build output. Usually a syntax error the tests did not cover. |
| 6 | `healthz did not answer within 120 s` | `docker compose ps` and `docker compose logs payments-api`. The build succeeded; the process did not. |

That is the guard working. Investigate before overriding:

```powershell
git -C . status --short
git -C . log --oneline -3
git -C . fetch origin
git -C . rev-parse HEAD; git -C . rev-parse origin/main
```

Do not edit the script to skip the assertion. If a branch must be deployed for debugging, deploy it explicitly and say so in the room — the assertion exists so that "deployed" and "merged" cannot silently diverge.

## Rollback

The agent opens a revert PR; **you** merge it; **you** tell the agent to deploy and verify. If the agent cannot open the PR, do it manually:

```powershell
git revert --no-edit <bad-sha>
git push origin HEAD:fix/rollback-<sha>
```

Then pass the deploy gate as usual. Rollback restores the previous deployed version; it does not erase history.

## Token rotation

- GitHub PAT: revoke in GitHub → Developer settings → Fine-grained tokens; create a replacement scoped to `sentinel-sre` only; update `.env`; restart the MCP server and any shell holding the old value.
- Jira API token: Atlassian account settings → Security → API tokens. Update `.env`, restart the MCP server.
- Mattermost webhook: delete and recreate in Integrations → Incoming Webhooks; update `.env`; restart `alert-relay`.
- `CHAOS_TOKEN`: edit `.env`, restart `payments-api`.

After any rotation, run the *Before a run* checklist.

## Reset

```powershell
powershell -File scripts/reset_demo.ps1
```

Does: disable chaos, truncate `payments.db`, `git fetch` + `reset --hard origin/main` (target checkout), `docker compose down`, `up -d --build`, wait for `/healthz`. Leaves Jira tickets alone — closed tickets are evidence.

## Known limitations

- The Mattermost allowlist for write actions is advisory. Switch may not expose the message author to MCP tools; see `spec.md` §7.
- The agent's shell is not sandboxed from `.env`. The token is kept out of the agent environment, but a determined prompt injection is not fully containable on one machine.
- One incident at a time. Two concurrent alerts will interleave and confuse the room.
- The fault trigger is a simulation tool. It must stay token-guarded and is not a production feature.
