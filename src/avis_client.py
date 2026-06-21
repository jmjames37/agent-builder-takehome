"""Avis reservation-servicing API client.

Thin, fully-typed wrappers over every endpoint the servicing workflows need —
reads (`get_reservation`, `get_availability`, `get_quote`) and writes
(`cancel`, `extend`, `modify`, `upgrade`). All calls share one transport layer:

  - bounded exponential backoff + jitter on transient failures (5xx, timeouts,
    connection errors), max 3 attempts; 4xx are never retried;
  - a fresh UUID ``Idempotency-Key`` on every write so a retry can't
    double-execute;
  - structured logging on every request/response.

This is the shared foundation for all workflows. Each workflow module composes
these calls into a conversation; the plumbing lives here once.

Run directly to smoke-test connectivity (needs AVIS_API_KEY in .env):
    python src/avis_client.py
"""
from __future__ import annotations

import logging
import os
import random
import time
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

AVIS_API_URL = os.environ["AVIS_API_URL"].rstrip("/")
AVIS_API_KEY = os.environ.get("AVIS_API_KEY", "")

# Per-request timeout (connect, read). Writes can be slow, so the read budget is
# generous; the retry loop covers anything slower than this.
TIMEOUT = (5, 20)
MAX_ATTEMPTS = 3

log = logging.getLogger("avis.client")


def _headers(extra: dict | None = None) -> dict:
    headers = {"X-API-Key": AVIS_API_KEY}
    if extra:
        headers.update(extra)
    return headers


def _retryable(exc: Exception) -> bool:
    """Retry transient failures only: timeouts, connection errors, and 5xx.

    4xx are deterministic (bad input, failed verification, wrong state) and must
    NOT be retried — they would fail identically and waste the customer's time.
    """
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code >= 500
    return False


def _retry(fn, *, label: str, max_attempts: int = MAX_ATTEMPTS):
    """Call ``fn`` with exponential backoff + jitter on transient failures.

    Backoff is ~0.5s, 1s, 2s with up to 50% jitter so concurrent retries don't
    synchronize. Non-retryable errors raise immediately.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - re-raised below if not retryable
            if not _retryable(exc) or attempt == max_attempts:
                log.error("%s failed on attempt %d/%d: %s", label, attempt, max_attempts, exc)
                raise
            backoff = 0.5 * (2 ** (attempt - 1))
            delay = backoff * (1 + random.random() * 0.5)
            log.warning(
                "%s transient error on attempt %d/%d (%s); retrying in %.2fs",
                label, attempt, max_attempts, exc, delay,
            )
            time.sleep(delay)


def _get(path: str, *, params: dict | None = None, label: str) -> dict:
    def _do():
        log.info("GET %s params=%s", path, params or {})
        resp = requests.get(
            f"{AVIS_API_URL}{path}", headers=_headers(), params=params, timeout=TIMEOUT,
        )
        log.info("GET %s -> %d", path, resp.status_code)
        resp.raise_for_status()
        return resp.json()

    return _retry(_do, label=label)


def _post(path: str, *, body: dict, label: str, idempotent: bool = False) -> dict:
    """POST helper. Writes pass ``idempotent=True`` to attach an Idempotency-Key.

    Read-only POSTs (e.g. /quote) skip the key since they have no side effects.
    """
    headers = {"Content-Type": "application/json"}
    key = None
    if idempotent:
        key = str(uuid.uuid4())
        headers["Idempotency-Key"] = key

    def _do():
        log.info("POST %s%s", path, f" (idempotency_key={key})" if key else "")
        resp = requests.post(
            f"{AVIS_API_URL}{path}", headers=_headers(headers), json=body, timeout=TIMEOUT,
        )
        log.info("POST %s -> %d%s", path, resp.status_code, f" (idempotency_key={key})" if key else "")
        resp.raise_for_status()
        return resp.json()

    return _retry(_do, label=label)


# --- Reads ----------------------------------------------------------------
def get_reservation(reservation_id: str) -> dict:
    """Look up a reservation by id. Raises requests.HTTPError on a non-2xx response."""
    return _get(f"/reservations/{reservation_id}", label=f"get_reservation({reservation_id})")


def get_availability(location: str, vehicle_type: str, start_date: str, end_date: str) -> dict:
    """Check vehicle availability at a location for a date range (YYYY-MM-DD)."""
    return _get(
        "/availability",
        params={
            "location": location,
            "vehicle_type": vehicle_type,
            "start_date": start_date,
            "end_date": end_date,
        },
        label=f"get_availability({location},{vehicle_type})",
    )


def get_quote(
    reservation_id: str,
    change_type: str,
    new_return_datetime: str,
    new_return_location: str | None = None,
) -> dict:
    """Price a proposed extend/modify change. No side effects."""
    body: dict = {"change_type": change_type, "new_return_datetime": new_return_datetime}
    if new_return_location:
        body["new_return_location"] = new_return_location
    return _post(
        f"/reservations/{reservation_id}/quote",
        body=body,
        label=f"get_quote({reservation_id},{change_type})",
    )


# --- Writes (require email verification) ----------------------------------
def cancel_reservation(reservation_id: str, email: str, reason: str = "") -> dict:
    """Cancel a reservation. ``email`` is the verification value the customer provides."""
    body: dict = {"email": email}
    if reason:
        body["reason"] = reason
    return _post(
        f"/reservations/{reservation_id}/cancel",
        body=body,
        label=f"cancel_reservation({reservation_id})",
        idempotent=True,
    )


def extend_reservation(
    reservation_id: str,
    email: str,
    new_return_datetime: str,
    cvv: str,
    billing_zip: str,
    use_card_on_file: bool = True,
) -> dict:
    """Extend a rental to a new return date/time. Requires email + payment details."""
    body = {
        "new_return_datetime": new_return_datetime,
        "email": email,
        "payment": {"use_card_on_file": use_card_on_file, "cvv": cvv, "billing_zip": billing_zip},
    }
    return _post(
        f"/reservations/{reservation_id}/extend",
        body=body,
        label=f"extend_reservation({reservation_id})",
        idempotent=True,
    )


def modify_reservation(
    reservation_id: str,
    email: str,
    cvv: str,
    billing_zip: str,
    new_pickup_datetime: str | None = None,
    new_return_datetime: str | None = None,
    new_return_location: str | None = None,
    use_card_on_file: bool = True,
) -> dict:
    """Change pickup/return time or return location. Requires email + payment details."""
    body: dict = {
        "email": email,
        "payment": {"use_card_on_file": use_card_on_file, "cvv": cvv, "billing_zip": billing_zip},
    }
    if new_pickup_datetime:
        body["new_pickup_datetime"] = new_pickup_datetime
    if new_return_datetime:
        body["new_return_datetime"] = new_return_datetime
    if new_return_location:
        body["new_return_location"] = new_return_location
    return _post(
        f"/reservations/{reservation_id}/modify",
        body=body,
        label=f"modify_reservation({reservation_id})",
        idempotent=True,
    )


def upgrade_customer(customer_id: str, email: str) -> dict:
    """Upgrade a standard customer to Avis Preferred (eligibility-gated)."""
    return _post(
        f"/customers/{customer_id}/upgrade",
        body={"email": email},
        label=f"upgrade_customer({customer_id})",
        idempotent=True,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    reservation = get_reservation("AVS-29471835")
    print("Connected. Sample reservation:")
    print(f"  {reservation['customer_name']} — {reservation['vehicle']['description']}")
    print(f"  pickup {reservation['dates']['pickup_datetime']} at {reservation['pickup_location']['code']}")
