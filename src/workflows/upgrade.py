"""Upgrade workflow — upgrade a standard customer to Avis Preferred.

Eligibility-gated: NOT_ELIGIBLE and ALREADY_PREFERRED are common, expected
outcomes the agent must explain gracefully. Needs `customer_id` from the
reservation lookup. Status: draft (client wired; conversation flow not yet
validated end to end).
"""
from __future__ import annotations

from agents import function_tool

from agent_common import safe_call
from avis_client import upgrade_customer

NAME = "upgrade"
STATUS = "draft"
SUMMARY = "Upgrade a customer to Avis Preferred membership."


@function_tool
def upgrade_customer_tool(customer_id: str, email: str) -> dict:
    """Upgrade a standard customer to Avis Preferred after they confirm.

    Get `customer_id` from the reservation lookup. `email` is the verification
    value. Returns `new_membership_status` on success, or a structured error dict
    — notably ALREADY_PREFERRED, NOT_ELIGIBLE, VERIFICATION_FAILED, or
    CUSTOMER_NOT_FOUND.
    """
    return safe_call(
        lambda: upgrade_customer(customer_id, email),
        label=f"upgrade_customer_tool({customer_id})",
    )


TOOLS = [upgrade_customer_tool]

INSTRUCTIONS = """\
## Upgrading to Avis Preferred (draft)
1. CONTEXT — Look up the reservation to get `customer_id` and current
   `membership_status`. If `membership_status` is already `avis_preferred`, tell
   them in one short sentence that they're already an Avis Preferred member and
   no upgrade is needed — do NOT ask for their email and do NOT call any tool.
2. INFORM — Explain that membership upgrades are eligibility-based (rental
   history); use `search_knowledge_base` for the benefits and eligibility policy.
   This is membership status, not a vehicle-class upgrade.
3. VERIFY + CONFIRM — Collect the email on file and confirm intent.
4. EXECUTE — Call `upgrade_customer_tool`.
5. CLOSE — On success, confirm the new Preferred status and benefits. On
   NOT_ELIGIBLE, explain kindly that continued rental activity builds
   eligibility; on ALREADY_PREFERRED, confirm they already have it. On
   CUSTOMER_NOT_FOUND, the customer record behind this reservation couldn't be
   located: ask them to re-check the reservation ID, and if it still fails after
   a fresh lookup, apologize and direct them to call Avis at 1-800-352-7900.
"""
