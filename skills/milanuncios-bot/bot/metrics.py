# Milanuncios Bot - Metrics
"""
Prometheus metrics for monitoring the bot.
"""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Ads metrics
ADS_FOUND = Counter("milanuncios_ads_found_total", "Total ads found on page")

ADS_RENEWED = Counter("milanuncios_ads_renewed_total", "Total ads successfully renewed")

ADS_FAILED = Counter(
    "milanuncios_ads_failed_total",
    "Total ads that failed to renew",
    ["error_type"],  # captcha, login, not_found, timeout, other
)

ADS_SKIPPED = Counter("milanuncios_ads_skipped_total", "Total ads skipped (already renewed, not eligible, etc.)")

# Duration metrics
RENEWAL_DURATION = Histogram(
    "milanuncios_renewal_duration_seconds", "Time to renew a single ad", buckets=[1, 2, 5, 10, 20, 30, 60, 120, 300]
)

RUN_DURATION = Histogram(
    "milanuncios_run_duration_seconds", "Total run duration", buckets=[10, 30, 60, 120, 300, 600, 1200, 1800]
)

LOGIN_DURATION = Histogram(
    "milanuncios_login_duration_seconds", "Time to complete login", buckets=[1, 2, 5, 10, 15, 20, 30, 60]
)

# CAPTCHA metrics
CAPTCHA_HITS = Counter("milanuncios_captcha_hits_total", "CAPTCHA challenges detected")

# State gauge
ACTIVE_ADS = Gauge("milanuncios_active_ads", "Number of active ads in database")

# Run status
RUN_TOTAL = Counter(
    "milanuncios_runs_total",
    "Total completed runs",
    ["status"],  # success, partial, failed
)

CURRENT_ADS_RENEWING = Gauge("milanuncios_current_ads_renewing", "Number of ads currently being renewed")

# Browser metrics
BROWSER_START_DURATION = Histogram("milanuncios_browser_start_duration_seconds", "Time to start browser context")

BROWSER_ERRORS = Counter("milanuncios_browser_errors_total", "Browser errors by type", ["error_type"])


def start_metrics_server(port: int = 9090) -> None:
    """Start Prometheus metrics HTTP server."""
    start_http_server(port)


def record_ad_found() -> None:
    ADS_FOUND.inc()


def record_ad_renewed() -> None:
    ADS_RENEWED.inc()


def record_ad_failed(error_type: str = "other") -> None:
    ADS_FAILED.labels(error_type=error_type).inc()


def record_ad_skipped() -> None:
    ADS_SKIPPED.inc()


def record_renewal_duration(seconds: float) -> None:
    RENEWAL_DURATION.observe(seconds)


def record_run_duration(seconds: float) -> None:
    RUN_DURATION.observe(seconds)


def record_login_duration(seconds: float) -> None:
    LOGIN_DURATION.observe(seconds)


def record_captcha_hit() -> None:
    CAPTCHA_HITS.inc()


def set_active_ads(count: int) -> None:
    ACTIVE_ADS.set(count)


def record_run_complete(status: str) -> None:
    RUN_TOTAL.labels(status=status).inc()


def set_current_renewing(count: int) -> None:
    CURRENT_ADS_RENEWING.set(count)


def record_browser_start(seconds: float) -> None:
    BROWSER_START_DURATION.observe(seconds)


def record_browser_error(error_type: str) -> None:
    BROWSER_ERRORS.labels(error_type=error_type).inc()
