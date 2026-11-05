# Payments API

The target service in the Sentinel system: a small FastAPI payments API with a customer checkout page, SQLite persistence, Cashfree sandbox integration, Prometheus metrics, and an operator-controlled fault trigger.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Checkout page |
| `POST` | `/payments` | Create a payment (requires `Idempotency-Key`) |
| `GET` | `/payments/{order_id}` | Read one payment |
| `GET` | `/healthz` | Liveness/readiness |
| `GET` | `/metrics` | Prometheus exposition |
| `POST` | `/admin/chaos` | Enable the fault trigger (`X-Chaos-Token`) |
| `DELETE` | `/admin/chaos` | Disable the fault trigger (`X-Chaos-Token`) |

`POST /payments` accepts `{"amount": 10.00, "currency": "INR"}` and returns the stored payment:

```json
{ "order_id": "ORD-1042", "status": "PAID", "amount": 10.00, "currency": "INR", "provider_order_id": "cf_..." }
```

The checkout page posts `10.00 INR`: the Cashfree sandbox merchant used for local runs has INR enabled and USD disabled.

Error taxonomy:

- `422` — request validation failed.
- `502` — the payment provider returned a response we could not accept. The payment is stored with status `FAILED`.
- `500` — an unhandled defect in this service. Should never appear in a healthy deployment.

## Run it

The service is normally started by the root `docker-compose.yml`:

```powershell
docker compose up -d --build payments-api
```

Standalone, for development:

```powershell
uv venv
uv pip install -r requirements.txt
uv run uvicorn app.main:app --reload --port 8001
```

## Test it

```powershell
uv run pytest -q
```

The suite covers the happy path, upstream response-shape handling, the fault trigger lifecycle, and metric emission.

## Configuration

All configuration comes from the environment; see `../.env.example`. `CASHFREE_MODE` selects `sandbox` or `replay` (a recorded sandbox response, used when the sandbox is unavailable). `CASHFREE_MODE=replay` must be set deliberately — the service never falls back on its own.

## Fault trigger

`POST /admin/chaos` switches upstream-response handling into a degraded mode for the next N requests or until the TTL expires, whichever comes first. The flag is held in process memory and never persisted, so restarting the container always returns the service to a clean state.

## Related

The incident response story, the agent that operates this service, and the verification criteria live in [`../sre-agent/`](../sre-agent/).
