"""Modify workflow — change pickup/return time or return location.

A return-location change adds a one-way fee and depends on availability of the
vehicle class at the new location. Status: stable (validated end to end — time
change, location change with availability check + one-way fee, and
VEHICLE_UNAVAILABLE surfacing alternatives without charging).
"""
from __future__ import annotations

from agents import function_tool

from agent_common import safe_call
from avis_client import get_availability, get_quote, modify_reservation

NAME = "modify"
STATUS = "stable"
SUMMARY = "Change return time or return location on a reservation."


@function_tool
def check_availability(location: str, vehicle_type: str, start_date: str, end_date: str) -> dict:
    """Check whether a vehicle class is available at a location for a date range.

    Use before a return-location change to confirm the class is available there.
    Dates are YYYY-MM-DD. (This endpoint is the least reliable — the client
    retries transient failures; if it still fails, degrade gracefully.)
    """
    return safe_call(
        lambda: get_availability(location, vehicle_type, start_date, end_date),
        label=f"check_availability({location},{vehicle_type})",
    )


@function_tool
def quote_modification(
    reservation_id: str, new_return_datetime: str, new_return_location: str = ""
) -> dict:
    """Price a modification before committing. No side effects."""
    return safe_call(
        lambda: get_quote(reservation_id, "modify", new_return_datetime, new_return_location or None),
        label=f"quote_modification({reservation_id})",
    )


@function_tool
def modify_reservation_tool(
    reservation_id: str,
    email: str,
    cvv: str,
    billing_zip: str,
    new_return_datetime: str = "",
    new_return_location: str = "",
) -> dict:
    """Execute a modification after the customer has seen the quote and confirmed.

    Provide at least one of `new_return_datetime` / `new_return_location`. A
    location change may return VEHICLE_UNAVAILABLE with alternatives.
    """
    return safe_call(
        lambda: modify_reservation(
            reservation_id,
            email,
            cvv,
            billing_zip,
            new_return_datetime=new_return_datetime or None,
            new_return_location=new_return_location or None,
        ),
        label=f"modify_reservation_tool({reservation_id})",
    )


TOOLS = [check_availability, quote_modification, modify_reservation_tool]

INSTRUCTIONS = """\
## Modifying a reservation
1. SCOPE — Clarify what's changing (return time and/or return location).
2. AVAILABILITY — For a location change, call `check_availability` for the
   vehicle class at the new location first. If unavailable, offer the
   alternatives returned rather than promising a change you can't make.
3. QUOTE — Call `quote_modification` and show cost (incl. any one-way fee).
4. VERIFY + PAYMENT — Collect email on file, CVV, billing ZIP.
5. CONFIRM, then EXECUTE `modify_reservation_tool`, then CLOSE with the
   confirmation and charges. Handle VEHICLE_UNAVAILABLE by surfacing alternatives.
"""
