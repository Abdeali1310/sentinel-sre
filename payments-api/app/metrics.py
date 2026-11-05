from prometheus_client import Counter, Histogram

REQUESTS = Counter(
    "payments_http_requests_total",
    "HTTP requests handled, by route and status.",
    ["method", "path", "status_code"],
)

DURATION = Histogram(
    "payments_request_duration_seconds",
    "Request duration in seconds, by route.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
