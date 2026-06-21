"""Workflow registry.

Each workflow module exposes a uniform interface — NAME, STATUS, SUMMARY, TOOLS,
INSTRUCTIONS — so the agent assembles its tools and instructions by iterating
this list. Adding a workflow is: write the module, import it here.

`STATUS` is "stable" (validated end to end) or "draft" (plumbing in place,
conversation not yet validated). Flip `ENABLED` to control what the live agent
exposes.
"""
from __future__ import annotations

from . import cancel, extend, modify, upgrade

# All available workflows, in the order their instructions are presented.
REGISTRY = [cancel, extend, modify, upgrade]

# Workflows the running agent actually exposes. Cancel is validated; extend is
# enabled here for live validation alongside it.
ENABLED = [cancel, extend]


def collect_tools(workflows=None):
    workflows = workflows if workflows is not None else ENABLED
    tools = []
    for wf in workflows:
        tools.extend(wf.TOOLS)
    return tools


def collect_instructions(workflows=None):
    workflows = workflows if workflows is not None else ENABLED
    return "\n\n".join(wf.INSTRUCTIONS for wf in workflows)


def enabled_names(workflows=None):
    workflows = workflows if workflows is not None else ENABLED
    return [wf.NAME for wf in workflows]
