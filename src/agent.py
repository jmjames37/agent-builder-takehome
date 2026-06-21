"""Avis servicing agent (OpenAI Agents SDK).

Assembles one agent from the workflow registry: shared tools (reservation
lookup + KB search) plus the tools and instruction fragments of every ENABLED
workflow. Cancel is enabled and validated; extend/modify/upgrade are wired in
`src/workflows/` and enabled by adding them to `workflows.ENABLED`.

Tools never raise to the model — API errors come back as structured dicts so the
agent can respond in natural language and recover.

Run an interactive session:
    python src/agent.py
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from agents import Agent, Runner  # noqa: E402

import workflows  # noqa: E402
from agent_common import SHARED_TOOLS  # noqa: E402

# ---------------------------------------------------------------------------
# Logging: stdout + agent.log in the repo root.
# ---------------------------------------------------------------------------
_LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.FileHandler(_LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("avis.agent")

BASE_INSTRUCTIONS = """\
You are an Avis Budget Group rental support agent. You help customers service an
existing reservation. You are friendly, concise, and careful — writes are
irreversible for the customer, so never guess and never skip verification or
explicit confirmation.

Always follow this shared flow, then the workflow-specific steps below:
1. IDENTIFY — Ask for the reservation ID (format like AVS-12345678) and call
   `lookup_reservation`. On RESERVATION_NOT_FOUND, ask them to re-check the ID.
   Don't reveal customer details before verification beyond confirming a
   reservation exists.
2. VERIFY — Ask for the email on file. NEVER hint at, confirm, or reveal it; the
   customer must produce it. Verification happens when you call a write tool. If
   a write returns VERIFICATION_FAILED, the email didn't match: ask them to
   double-check and re-enter it. After TWO failed verification attempts, STOP
   retrying and direct them to call Avis at 1-800-352-7900.
3. Then run the steps for the requested workflow.

Ground policy answers in `search_knowledge_base` rather than guessing. Never
invent reservation details, fees, penalties, or refund amounts — only state what
the tools return. If the customer asks for something not in your enabled
workflows, say you can't help with that yet and suggest calling Avis.

If a write fails transiently after the client's retries (NETWORK_ERROR or a
5xx-style failure), apologize and suggest trying again shortly or calling Avis
at 1-800-352-7900.

# Workflows you can handle
"""


def build_agent() -> Agent:
    instructions = BASE_INSTRUCTIONS + "\n" + workflows.collect_instructions()
    tools = SHARED_TOOLS + workflows.collect_tools()
    log.info("agent enabled workflows: %s", workflows.enabled_names())
    return Agent(name="Avis Servicing Assistant", instructions=instructions, tools=tools)


agent = build_agent()


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY in your .env first (see env.example).")
        return
    if not os.environ.get("AVIS_API_KEY"):
        print("Set AVIS_API_KEY in your .env first (see env.example).")
        return

    print("Avis Servicing Assistant. Type 'quit' to exit.\n")
    greeting = "Hi! I can help you with your Avis reservation. What's your reservation ID?"
    print(f"Agent: {greeting}")

    history: list = [{"role": "assistant", "content": greeting}]
    log.info("session start")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in {"quit", "exit"}:
            break
        if not user_input:
            continue

        log.info("user: %s", user_input)
        history.append({"role": "user", "content": user_input})
        result = Runner.run_sync(agent, history)
        reply = result.final_output
        print(f"\nAgent: {reply}")
        log.info("agent: %s", reply)
        history = result.to_input_list()

    log.info("session end")
    print("Thanks for using Avis. Goodbye!")


if __name__ == "__main__":
    main()
