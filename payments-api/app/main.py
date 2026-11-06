import logging
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from . import chaos, db
from .cashfree import CashfreeClient, UpstreamError
from .config import Settings
from .metrics import DURATION, REQUESTS

logger = logging.getLogger("payments")

APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

CHECKOUT_AMOUNT = 10.00
CHECKOUT_CURRENCY = "INR"

router = APIRouter()


# --------------------------------------------------------------------- schemas


class PaymentCreate(BaseModel):
    amount: float = Field(gt=0, le=100_000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class PaymentOut(BaseModel):
    order_id: str
    status: str
    amount: float
    currency: str
    provider_order_id: str | None = None
    error: str | None = None


class ChaosRequest(BaseModel):
    requests: int = Field(default=50, ge=1, le=1000)
    ttl_seconds: int = Field(default=600, ge=1, le=3600)


# ---------------------------------------------------------------- dependencies


def get_client(request: Request) -> CashfreeClient:
    return CashfreeClient(request.app.state.settings)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


# -------------------------------------------------------------------- handlers


@router.get("/", response_class=HTMLResponse)
def checkout_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        request,
        "checkout.html",
        {
            "amount": f"{CHECKOUT_AMOUNT:.2f}",
            "currency": CHECKOUT_CURRENCY,
            "symbol": "\u20b9",
        },
    )


@router.get("/healthz")
def healthz(request: Request) -> dict:
    with db.connect(_settings(request).database_url) as connection:
        connection.execute("SELECT 1")
    return {"status": "ok", "database": "ok"}


@router.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.post("/payments", response_model=PaymentOut)
async def create_payment(
    request: Request,
    body: PaymentCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1),
    provider: CashfreeClient = Depends(get_client),
):
    settings = _settings(request)

    existing = db.get_by_idempotency(settings.database_url, idempotency_key)
    if existing is not None:
        return _to_payment_out(existing)

    order_id = _new_order_id()
    db.insert_payment(
        settings.database_url,
        order_id=order_id,
        idempotency_key=idempotency_key,
        amount=body.amount,
        currency=body.currency,
    )

    payload = {
        "order_id": order_id,
        "order_amount": body.amount,
        "order_currency": body.currency,
    }

    try:
        raw = await provider.create_order(payload)
    except UpstreamError as exc:
        logger.warning("provider_unavailable order_id=%s reason=%s", order_id, exc)
        db.mark_failed(settings.database_url, order_id, "upstream_unavailable")
        return _upstream_failure(order_id, "upstream_unavailable")

    try:
        confirmed_order_id = raw["order_id"]
        provider_order_id = raw["cf_order_id"]
    except KeyError as exc:
        # The provider's payload is untrusted input. A missing field is a 502
        # ("upstream said something we cannot accept"), never an unhandled 500.
        logger.warning("provider_contract order_id=%s missing=%s", order_id, exc)
        db.mark_failed(settings.database_url, order_id, "upstream_contract")
        return _upstream_failure(order_id, "upstream_contract")

    db.mark_paid(settings.database_url, order_id, provider_order_id)
    return PaymentOut(
        order_id=confirmed_order_id,
        status="PAID",
        amount=body.amount,
        currency=body.currency,
        provider_order_id=provider_order_id,
    )


@router.get("/payments/{order_id}", response_model=PaymentOut)
def get_payment(request: Request, order_id: str):
    row = db.get_by_order_id(_settings(request).database_url, order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Payment not found.")
    return _to_payment_out(row)


@router.post("/admin/chaos")
def enable_chaos(
    request: Request,
    body: ChaosRequest,
    x_chaos_token: str = Header(default="", alias="X-Chaos-Token"),
) -> dict:
    _require_chaos_token(_settings(request), x_chaos_token)
    return chaos.enable(body.requests, body.ttl_seconds)


@router.delete("/admin/chaos")
def disable_chaos(
    request: Request,
    x_chaos_token: str = Header(default="", alias="X-Chaos-Token"),
) -> dict:
    _require_chaos_token(_settings(request), x_chaos_token)
    return chaos.disable()


# --------------------------------------------------------------------- helpers


def _new_order_id() -> str:
    return f"ORD-{secrets.randbelow(900_000) + 100_000}"


def _to_payment_out(row: dict) -> PaymentOut:
    return PaymentOut(
        order_id=row["order_id"],
        status=row["status"],
        amount=row["amount"],
        currency=row["currency"],
        provider_order_id=row["provider_order_id"],
        error=row["error"],
    )


def _upstream_failure(order_id: str, error: str) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": error,
            "message": "The payment provider returned an unexpected response.",
            "order_id": order_id,
        },
    )


def _require_chaos_token(settings: Settings, supplied: str) -> None:
    expected = settings.chaos_token
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid chaos token.")


def _record(request: Request, status_code: int, started: float) -> None:
    route = request.scope.get("route")
    path = getattr(route, "path", None) or "<unmatched>"
    REQUESTS.labels(request.method, path, str(status_code)).inc()
    DURATION.labels(request.method, path).observe(time.perf_counter() - started)


# ----------------------------------------------------------------- app factory


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Sentinel Payments API", version="1.0.0")
    app.state.settings = settings
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    db.init_db(settings.database_url)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def record_request(request: Request, call_next):
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Count the failure before Starlette turns it into a bare 500, so the
            # 5xx ratio reflects reality.
            _record(request, 500, started)
            raise
        _record(request, response.status_code, started)
        return response

    app.include_router(router)
    return app


app = create_app(Settings())
