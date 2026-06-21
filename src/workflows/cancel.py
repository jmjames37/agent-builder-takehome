"""Cancel workflow — the reference implementation other workflows mirror.

Two API calls (lookup + cancel), email-only verification, clear policy
guardrails. Status: stable.
"""
from __future__ import annotations

from agents import function_tool

from agent_common import safe_call
from avis_client import cancel_reservation

NAME = "cancel"
STATUS = "stable"
SUMMARY = "Cancel a reservation and report penalty/refund."


@function_tool
def cancel_reservation_tool(reservation_id: str, email: str, reason: str = "") -> dict:
    """Cancel a reservation after the customer has explicitly confirmed.

    `email` is the verification value the customer provided (the email on file).
    Returns the cancellation result (confirmation number, penalty, refund) on
    success, or a structured error dict on failure — notably VERIFICATION_FAILED,
    RESERVATION_NOT_ACTIVE, or RESERVATION_NOT_FOUND.
    """
    return safe_call(
        lambda: cancel_reservation(reservation_id, email, reason),
        label=f"cancel_reservation_tool({reservation_id})",
    )


TOOLS = [cancel_reservation_tool]

INSTRUCTIONS = """\
## Cancelling a reservation
1. INFORM — Before cancelling, explain the policy that applies. Ground it with
   `search_knowledge_base` and use the lookup's `timing` block:
     - more_than_48h_before_pickup: full refund of any prepaid amount.
     - within_48h_window: a penalty of roughly one day's rate may apply.
     - pickup_in_past / not active: may not be cancellable; set expectations.
   Present penalty/refund as an estimate — the final numbers come from the
   system on execution. Mention refunds take 5-10 business days to the original
   payment method, and that prepaid non-refundable rates may not be refundable.
2. CONFIRM — Ask explicitly "Do you want me to go ahead and cancel this?" and
   wait for a clear yes.
3. EXECUTE — Call `cancel_reservation_tool` with the reservation ID and the
   email the customer gave.
4. CLOSE — Share the confirmation number, penalty (if any), refund amount, and
   the 5-10 business day timeline.
Error handling: VERIFICATION_FAILED -> ask them to re-check the email; after two
failures, direct them to call Avis at 1-800-352-7900. RESERVATION_NOT_ACTIVE ->
it may already be cancelled. RESERVATION_NOT_FOUND -> re-check the ID.
"""
