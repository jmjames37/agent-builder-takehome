"""Shared building blocks for every servicing workflow.

Holds the cross-workflow helpers and the two tools every workflow needs
(reservation lookup + knowledge-base search), so individual workflow modules
only have to implement their own write-side tools and instructions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests
from agents import function_tool

from avis_client import get_reservation
from rag import search_knowledge_base as _search_kb

log = logging.getLogger("avis.agent")


def error_payload(exc: requests.HTTPError) -> dict:
    """Translate an HTTPError into a structured, model-friendly error dict."""
    resp = exc.response
    status = resp.status_code if resp is not None else None
    code, message = "HTTP_ERROR", str(exc)
    try:
        body = resp.json() if resp is not None else {}
        err = body.get("error", {})
        code = err.get("code", code)
        message = err.get("message", message)
    except ValueError:
        pass
    return {"error": True, "status": status, "code": code, "message": message}


def safe_call(fn, *, label: str) -> dict:
    """Run a client call and return its result, or a structured error dict.

    Tools use this so the agent always gets data to reason over and never sees a
    raised exception.
    """
    try:
        return fn()
    except requests.HTTPError as exc:
        payload = error_payload(exc)
        log.info("%s -> %s", label, payload["code"])
        return payload
    except requests.RequestException as exc:
        log.error("%s network error: %s", label, exc)
        return {"error": True, "status": None, "code": "NETWORK_ERROR", "message": str(exc)}


def is_error(result: dict) -> bool:
    return isinstance(result, dict) and result.get("error") is True


def reservation_timing(reservation: dict) -> dict:
    """Derive hours-until-pickup and the 48h window flag from reservation dates.

    Computed in code (not by the LLM) so policy timing is accurate. Useful to
    cancel (penalty window) and to extend/modify (whether the rental has started).
    Degrades gracefully if the pickup date is missing/unparseable.
    """
    pickup_raw = reservation.get("dates", {}).get("pickup_datetime")
    if not pickup_raw:
        return {"available": False}
    try:
        pickup = datetime.fromisoformat(pickup_raw)
    except ValueError:
        return {"available": False}
    now = datetime.now(timezone.utc) if pickup.tzinfo else datetime.now()
    hours = (pickup - now).total_seconds() / 3600
    return {
        "available": True,
        "pickup_datetime": pickup_raw,
        "hours_until_pickup": round(hours, 1),
        "pickup_in_past": hours < 0,
        "within_48h_window": 0 <= hours < 48,
        "more_than_48h_before_pickup": hours >= 48,
    }


# --- Shared tools ---------------------------------------------------------
@function_tool
def lookup_reservation(reservation_id: str) -> dict:
    """Look up an Avis reservation by its ID (e.g. 'AVS-29471835').

    Returns reservation details plus a derived `timing` block (hours until pickup
    and the 48-hour window) to support policy explanations. On failure returns a
    structured error dict with `code` (e.g. RESERVATION_NOT_FOUND).
    """
    result = safe_call(lambda: get_reservation(reservation_id), label=f"lookup_reservation({reservation_id})")
    if not is_error(result):
        result["timing"] = reservation_timing(result)
    return result


@function_tool
def search_knowledge_base(query: str) -> str:
    """Search the Avis help-center knowledge base for policy text.

    Use this to ground answers about penalties, fees, refunds, eligibility, and
    timing in official policy rather than guessing. Returns the top matches.
    """
    log.info("search_knowledge_base(%r)", query)
    return _search_kb(query, top_k=3)


SHARED_TOOLS = [lookup_reservation, search_knowledge_base]
