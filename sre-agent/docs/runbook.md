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

- Checkout page loads and a `$10.00` payment succeeds.
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
| ~15–30s | 5xx ratio crosses threshold |
| ~2m | alert `pending` → `firing` |
| +10s | post in `#incidents` with `@sre-agent` |
| +30s | agent acknowledgement |

If nothing arrives by 3 minutes, see *Alert never fires*.

## Alert never fires

```powershell
curl.exe http://localhost:9091/api/v1/rules          # rule loaded?
curl.exe http://localhost:9091/api/v1/alerts         # state: pending/firing?
curl.exe http://localhost:9093/-/healthy
curl.exe http://localhost:9093/api/v2/alerts
docker compose logs --tail=50 alert-relay
```

In order: is Prometheus scraping (`/targets` shows `payments-api` UP)? Is the rule expression returning a value (`/graph`)? Is Alertmanager receiving (`/api/v2/alerts`)? Is the relay's webhook URL correct in `.env`, and is the Mattermost webhook bound to `#incidents`?

## The agent is stuck or looping

1. Type `@sre-agent stop` — it must acknowledge at the next step boundary.
2. If it does not, disable the agent in Switch Console. That is the authoritative kill switch; chat instructions are advisory.
3. Inspect what it actually did: `docker compose logs --tail=100 payments-api`, `/api/v1/alerts`, and the Jira ticket comments.
4. Reset with `scripts/reset_demo.ps1` and re-run from a clean state rather than trying to repair a half-finished incident.

Hard limits are enforced in the MCP server (15 tool calls, 10 minutes) and at the provider (25 turns). Hitting them is not a failure of the agent; it is the agent reporting that the incident needs a human.

## Deploy refuses

`scripts/deploy.ps1` fails when the target checkout is not exactly `origin/main`:

```
DEPLOY REFUSED: HEAD is not origin/main (expected <sha>, found <sha>)
```

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
