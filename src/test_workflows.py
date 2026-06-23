"""
Interactive test runner for the Avis servicing agent.

Pick a pre-scripted scenario from the menu, run all of them, or drop into a free
chat session — all against the live API. Writes are ephemeral on the mock, so
re-running is safe.

Run from repo root:
    python src/test_workflows.py
"""
from __future__ import annotations

import os
import sys
import textwrap

from dotenv import load_dotenv
load_dotenv()

from agents import Runner  # noqa: E402
from agent import build_agent  # noqa: E402

agent = build_agent()

SEP = "─" * 70

# (name, [user turns]) — scripted scenarios.
SCENARIOS = [
    ("CANCEL — happy path (Marcus, AVS-48372915)", [
        "I'd like to cancel my rental",
        "AVS-48372915",
        "marcus.lee@example.com",
        "Yes, please go ahead and cancel",
    ]),
    ("CANCEL — wrong email ×2 → escalation (Sarah, AVS-29471835)", [
        "I need to cancel my reservation AVS-29471835",
        "wrongemail@example.com",
        "alsowrong@example.com",
    ]),
    ("UPGRADE — eligible (Marcus, AVS-48372915)", [
        "I'd like to upgrade to Avis Preferred",
        "AVS-48372915",
        "marcus.lee@example.com",
    ]),
    ("UPGRADE — NOT_ELIGIBLE (David, AVS-66002030)", [
        "Can I upgrade to Avis Preferred?",
        "AVS-66002030",
        "david.kim@example.com",
    ]),
    ("UPGRADE — ALREADY_PREFERRED (Sarah, AVS-29471835)", [
        "I want to upgrade my membership to Preferred",
        "AVS-29471835",
    ]),
]


def _show_agent(reply: str) -> None:
    print(f"\n  Agent: {textwrap.fill(reply, width=66, subsequent_indent='         ')}")


def run_scenario(name: str, turns: list[str]) -> None:
    print(f"\n{SEP}\n  SCENARIO: {name}\n{SEP}")
    history: list = []
    for user_msg in turns:
        history.append({"role": "user", "content": user_msg})
        print(f"\n  You : {user_msg}")
        result = Runner.run_sync(agent, history)
        _show_agent(result.final_output)
        history = result.to_input_list()
    print()


def free_chat() -> None:
    print(f"\n{SEP}\n  FREE CHAT — type 'back' to return to the menu\n{SEP}")
    greeting = "Hi! I can help you with your Avis reservation. What's your reservation ID?"
    _show_agent(greeting)
    history: list = [{"role": "assistant", "content": greeting}]
    while True:
        try:
            user_msg = input("\n  You : ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if user_msg.lower() in {"back", "quit", "exit"}:
            return
        if not user_msg:
            continue
        history.append({"role": "user", "content": user_msg})
        result = Runner.run_sync(agent, history)
        _show_agent(result.final_output)
        history = result.to_input_list()


def menu() -> None:
    while True:
        print(f"\n{SEP}\n  Avis agent — interactive test menu\n{SEP}")
        print("  NOTE: This is the scripted TEST runner.")
        print("  To actually run the workflows, use:  python src/agent.py")
        print(SEP)
        for i, (name, _) in enumerate(SCENARIOS, 1):
            print(f"  {i}. {name}")
        print("  a. Run ALL scripted scenarios")
        print("  c. Free chat with the agent")
        print("  q. Quit")

        try:
            choice = input("\n  Select: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if choice == "q":
            return
        elif choice == "a":
            for name, turns in SCENARIOS:
                run_scenario(name, turns)
        elif choice == "c":
            free_chat()
        elif choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS):
            name, turns = SCENARIOS[int(choice) - 1]
            run_scenario(name, turns)
        else:
            print("  Invalid choice — pick a number, 'a', 'c', or 'q'.")


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set"); sys.exit(1)
    if not os.environ.get("AVIS_API_KEY"):
        print("AVIS_API_KEY not set"); sys.exit(1)
    menu()
    print("\n  Done.")


if __name__ == "__main__":
    main()
