import os
from dataclasses import dataclass

from anthropic import Anthropic
from dotenv import load_dotenv

from messages import dump_debug, extract_text, normalize_messages
from todoManager import TodoManager
from tools import TOOLS, build_tool_handlers
from skill import SkillRegistry
from pathlib import Path

load_dotenv()

from tools import WORKDIR 

# ── Client & model ───────────────────────────────────────────────────────────

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = os.getenv("MODEL")
SKILLS_DIR = Path.cwd() / "skills"

# ── State ────────────────────────────────────────────────────────────────────

TODO = TodoManager()
SKILL_REGISTRY = SkillRegistry(SKILLS_DIR)

# The lambda lets us reference run_subagent before it's defined — standard
# Python forward-reference pattern; the lambda is only called at runtime.
TOOL_HANDLERS = build_tool_handlers(TODO, SKILL_REGISTRY, lambda prompt: run_subagent(prompt))

# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM = (
    f"You are an autonomous coding agent working in {WORKDIR}. "
    "For multi-step tasks, call todo first and keep exactly one item in_progress. "
    "Prefer edit over write for small changes. Read before you write. "
    "Verify work with bash or read after edits. Prefer tools over prose."
    "Use load_skill when a task needs specialized instructions before you act."
    "Skills available:"
    f"{SKILL_REGISTRY.describe_available()}"
)
SUBAGENT_SYSTEM = (
    f"You are a coding subagent working in {WORKDIR}. "
    "Complete the delegated task, verify your work, then return a concise summary."
)

# ── LoopState ────────────────────────────────────────────────────────────────


@dataclass
class LoopState:
    messages: list
    turn_count: int = 1
    transition_reason: str | None = None


# ── Tool dispatch ─────────────────────────────────────────────────────────────


def execute_tool_calls(response_content) -> list[dict]:
    results = []
    used_todo = False

    for block in response_content:
        if block.type != "tool_use":
            continue

        handler = TOOL_HANDLERS.get(block.name)
        try:
            output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
        except Exception as exc:
            output = f"Error: {exc}"

        if block.name == "task":
            desc = block.input.get("description", "subtask")
            prompt = block.input.get("prompt", "")
            print(f"> task ({desc}): {prompt[:80]}")
        else:
            print(f"> {block.name}:")
            print(output[:1000])

        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": output,
        })

        if block.name == "todo":
            used_todo = True

    if used_todo:
        TODO.state.rounds_since_update = 0
    else:
        TODO.note_round_without_update()
        reminder = TODO.reminder()
        if reminder:
            results.append({"type": "text", "text": reminder})

    return results


# ── Subagent ─────────────────────────────────────────────────────────────────


def run_subagent(prompt: str) -> str:
    subagent_tools = [t for t in TOOLS if t["name"] not in {"todo", "task"}]
    sub_messages = [{"role": "user", "content": prompt}]

    for _ in range(30):
        response = client.messages.create(
            model=MODEL,
            system=SUBAGENT_SYSTEM,
            messages=normalize_messages(sub_messages),
            tools=subagent_tools,
            max_tokens=8000,
        )
        sub_messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return extract_text(response.content) or "(no summary)"

        results = execute_tool_calls(response.content)
        sub_messages.append({"role": "user", "content": results})

    return (
        extract_text(response.content)
        + "\n(Warning: subagent stopped after reaching 30 turn limit)"
    )


# ── Agent loop ────────────────────────────────────────────────────────────────


def run_loop(state: LoopState) -> bool:
    dump_debug(state)
    response = client.messages.create(
        model=MODEL,
        tools=TOOLS,
        system=SYSTEM,
        max_tokens=8000,
        messages=normalize_messages(state.messages),
    )
    state.messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        state.transition_reason = None
        return False

    results = execute_tool_calls(response.content)
    if not results:
        state.transition_reason = None
        return False

    state.messages.append({"role": "user", "content": results})
    state.turn_count += 1
    state.transition_reason = "tool_result"
    return True


def agent_loop(state: LoopState) -> None:
    dump_debug(state)
    while run_loop(state):
        dump_debug(state)
