"""Extend workflow — push a rental's return date/time out.

Quote-before-charge: always show cost before collecting payment. Requires email
+ CVV + billing ZIP. Status: draft (plumbing wired and live-tested at the client
layer; conversation flow not yet validated end to end).
"""
from __future__ import annotations

from agents import function_tool

from agent_common import safe_call
from avis_client import extend_reservation, get_quote

NAME = "extend"
STATUS = "draft"
SUMMARY = "Extend a rental to a later return date/time."


@function_tool
def quote_extension(reservation_id: str, new_return_datetime: str) -> dict:
    """Price an extension to `new_return_datetime` (ISO 8601). No side effects.

    Always call this and show the customer the cost before charging.
    """
    return safe_call(
        lambda: get_quote(reservation_id, "extend", new_return_datetime),
        label=f"quote_extension({reservation_id})",
    )


@function_tool
def extend_reservation_tool(
    reservation_id: str, email: str, new_return_datetime: str, cvv: str, billing_zip: str
) -> dict:
    """Execute an extension after the customer has seen the quote and confirmed.

    `email`, `cvv`, and `billing_zip` are all required by the API. Returns a
    confirmation number and charge breakdown, or a structured error dict
    (VERIFICATION_FAILED, PAYMENT_VALIDATION_ERROR, PAYMENT_DECLINED,
    INVALID_DATE/INVALID_EXTENSION, RESERVATION_NOT_ACTIVE).
    """
    return safe_call(
        lambda: extend_reservation(reservation_id, email, new_return_datetime, cvv, billing_zip),
        label=f"extend_reservation_tool({reservation_id})",
    )


TOOLS = [quote_extension, extend_reservation_tool]

INSTRUCTIONS = """\
## Extending a reservation (draft)
1. QUOTE — Get the new return date/time, call `quote_extension`, and show the
   total cost (extension days, taxes/fees). Never charge without showing cost.
2. VERIFY + PAYMENT — Collect the email on file plus CVV and billing ZIP for the
   card on file. Late-return fees apply to standard members; Preferred members
   are exempt (check `membership_status`).
3. CONFIRM — Ask explicitly before charging; wait for a clear yes.
4. EXECUTE — Call `extend_reservation_tool`.
5. CLOSE — Share the confirmation number and the charge breakdown.
Errors: PAYMENT_VALIDATION_ERROR/PAYMENT_DECLINED -> re-collect or try another
card; INVALID_DATE/INVALID_EXTENSION -> clarify the requested time.
"""
