# Fault trigger held in process memory, never persisted

**Status:** accepted

The demonstrable failure has to be reproducible on demand without affecting normal traffic, and it has to disappear without a cleanup step. The trigger is therefore an in-memory flag: `POST /admin/chaos` (guarded by `X-Chaos-Token`) degrades upstream parsing for the next 50 requests or 10 minutes, whichever comes first; `DELETE /admin/chaos` clears it; a container restart clears it regardless. The defect itself is ordinary application code — a real unvalidated response shape — and stays in the repository. Only the *trigger* is simulated.

Using an environment variable was rejected because a stale value in `.env` or in a compose override would silently keep the service broken, and the post-deploy verification would then be measuring the trigger rather than the fix. Persisting the flag in SQLite was rejected for the same reason plus one more: the deploy step would need explicit cleanup, and a cleanup the demo can forget is a demo that lies.

## Consequences

Deployment doubles as a guaranteed clean slate, which is what makes "verified" trustworthy. The endpoint is an unauthenticated-without-token surface on a service reachable from the host, so it must stay token-guarded, bounded, and documented in the README and the runbook as a simulation tool, not a feature.
