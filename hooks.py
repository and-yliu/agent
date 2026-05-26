import sys
from pathlib import Path
from tools import WORKDIR
from context import AgentContext

HOOKS = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": []
}

def register_hook(event: str, callback):
    if event not in HOOKS:
        raise ValueError(f"Unknown hook event: {event}")
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:  # Block this tool call or halt action
            return result
    return None

# --- Custom Hook Implementations ---

DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if="]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]

def permission_hook(block):
    """PreToolUse: check permission logic."""
    if block.name == "bash":
        command = block.input.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                print(f"\n{AgentContext.get_prefix()}\033[31m⛔ Blocked: '{pattern}'\033[0m")
                return "Permission denied by deny list"
        for kw in DESTRUCTIVE:
            if kw in command:
                print(f"\n{AgentContext.get_prefix()}\033[33m⚠  Potentially destructive command: '{command}'\033[0m")
                print(f"{AgentContext.get_indent()}   Tool: {block.name}({block.input})")
                try:
                    choice = input(f"{AgentContext.get_indent()}   Allow? [y/N] ").strip().lower()
                    if choice not in ("y", "yes"):
                        return "Permission denied by user"
                except (EOFError, KeyboardInterrupt):
                    return "Permission denied by user"

    if block.name in ("write", "edit", "write_file", "edit_file"):
        path = block.input.get("path", "")
        try:
            resolved_path = (WORKDIR / path).resolve()
            if not resolved_path.is_relative_to(WORKDIR):
                print(f"\n{AgentContext.get_prefix()}\033[33m⚠  Writing outside workspace: {path}\033[0m")
                print(f"{AgentContext.get_indent()}   Tool: {block.name}({block.input})")
                choice = input(f"{AgentContext.get_indent()}   Allow? [y/N] ").strip().lower()
                if choice not in ("y", "yes"):
                    return "Permission denied by user"
        except (EOFError, KeyboardInterrupt):
            return "Permission denied by user"
    return None

def log_hook(block):
    """PreToolUse: log every tool call."""
    args_preview = str(list(block.input.values())[:2])[:60]
    print(f"{AgentContext.get_prefix()}\033[90m[HOOK] {block.name}({args_preview})\033[0m")
    return None

def large_output_hook(block, output):
    """PostToolUse: warn on large output."""
    if len(str(output)) > 10000:
        print(f"{AgentContext.get_prefix()}\033[33m[HOOK] ⚠ Large output from {block.name}: {len(str(output))} chars\033[0m")
    return None

def context_inject_hook(query: str):
    """UserPromptSubmit: log user input before it reaches the LLM."""
    print(f"{AgentContext.get_prefix()}\033[90m[HOOK] UserPromptSubmit: working in {WORKDIR}\033[0m")
    return None

def summary_hook(messages: list):
    """Stop: print summary when loop is about to exit."""
    tool_count = 0
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tool_count += 1
    print(f"{AgentContext.get_prefix()}\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None

# Register hooks
register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)
