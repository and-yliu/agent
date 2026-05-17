import subprocess
import os

from dotenv import load_dotenv
from anthropic import Anthropic
from dataclasses import dataclass
from pathlib import Path
from todoManager import TodoManager


load_dotenv()

client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
)
MODEL = os.getenv("MODEL")
WORKDIR = Path.cwd() / "workspace"
TODO = TodoManager()


SYSTEM = (
    f"""You are a AI agent at {WORKDIR}.
    Use the todo tool for multi-step work.
    Keep exactly one step in_progress when a task has multiple steps.
    Refresh the plan as work advances. Prefer tools over prose."""
)

TOOLS = [
    {
        "name": "bash",
        "description": "Execute bash commands in the current directory. Returns stdout and stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute.",
                },
            },
            "required": ["command"],
        }
    },
    {
        "name": "read",
        "description": "Read file contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "descirption": "Relative path to the WORKDIR"
                },
                "limit": {
                    "type": "integer",
                    "descirption": "Number of Lines read limit"
                }
            },
            "required": ["path"]
        },
    },
    {
        "name": "write",
        "description": "Write file contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "descirption": "Relative path to the WORKDIR"
                },
                "content": {
                    "type": "string",
                    "descirption": "New content for the file"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "edit",
        "description": "Replace exact text in file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "descirption": "Relative path to the WORKDIR"
                },
                "old_text": {
                    "type": "string"
                },
                "new_text": {
                    "type": "string"
                }
            },
            "required": ["path", "old_text", "new_text"]
        },
    },
    {
        "name": "todo",
        "description": "Rewrite the current session plan for multi-step work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                            },
                            "activeForm": {
                                "type": "string",
                                "description": "Optional present-continuous label.",
                            },
                        },
                        "required": ["content", "status"],
                    },
                },
            },
            "required": ["items"],
        },
    },
]

TOOL_HANDLERS = {
    "bash" : lambda **kwargs: run_bash(kwargs["command"]),
    "read" : lambda **kwargs: run_read(kwargs["path"], kwargs.get("limit")),
    "write": lambda **kwargs: run_write(kwargs["path"], kwargs["content"]),
    "edit": lambda **kwargs: run_edit(kwargs["path"], kwargs["old_text"],  kwargs["new_text"]),
    "todo": lambda **kwargs: TODO.update(kwargs["items"])
}

@dataclass
class LoopState:
    messages: list
    turn_count: int = 1
    transition_reason: str | None = None



def run_bash(command: str) -> str:
    print(f"\033[33m$ {command}\033[0m")
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked."

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "Error: Command timed out."
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

    output = (result.stdout + result.stderr).strip()
    return output[:8000] if output else "<no output>"

def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError("Path is outside of the work directory")
    return path

def run_read(path: str, limit:int = None) -> str:
    try:
        text = safe_path(path).read_text()
        lines = text.splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit]
        return "\n".join(lines)[:8000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        content = fp.read_text()
        if old_text not in content:
            return f"Error: Text not found in {path}"
        content = content.replace(old_text, new_text)
        fp.write_text(content)
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"
    
def extract_text(content) -> str:
    if not isinstance(content, list):
        return ""
    texts = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts)

def execute_tool_calls(response_content) -> list[dict]:
    results = []
    usedTodo = False
    for block in response_content:
        if block.type != "tool_use":
            continue

        handler = TOOL_HANDLERS[block.name]
        try:
            output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
        except Exception as exc:
            output = f"Error: {exc}"

        print(f"> {block.name}:")
        print(output[:1000])
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": output,
        })

        if block.name == "todo":
            usedTodo = True
        
    if usedTodo:
        TODO.state.rounds_since_update = 0
    else:
        TODO.note_round_without_update()
        reminder = TODO.reminder()
        if reminder:
            results.append({"type": "text", "text": reminder})

    return results

def normalize_messages(messages: list) -> list:
    normalized = []
    for msg in messages:
        clean = {"role": msg["role"]}
        if isinstance(msg.get("content"), str):
            clean["content"] = msg["content"]
        elif isinstance(msg.get("content"), list):
            clean_content = []
            for block in msg["content"]:
                if not isinstance(block, dict):
                    if hasattr(block, "model_dump"):
                        b = block.model_dump()
                    elif hasattr(block, "dict"):
                        b = block.dict()
                    else:
                        b = vars(block)
                else:
                    b = block
                clean_content.append({k: v for k, v in b.items() if k not in ("_internal", "_source", "_timestamp")})
            clean["content"] = clean_content
        else:
            clean["content"] = msg.get("content", "")
        normalized.append(clean)
    
    existing_result = set()
    for msg in normalized:
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    existing_result.add(block.get("tool_use_id"))
    
    # We must not append to the list while iterating over it in a way that messes up order.
    # It's better to create a new list and insert cancellations directly after the assistant message.
    final_normalized = []
    for msg in normalized:
        final_normalized.append(msg)
        if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
            cancellations = []
            for block in msg["content"]:
                if block.get("type") == "tool_use" and block.get("id") not in existing_result:
                    cancellations.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": "(cancelled)",
                    })
            if cancellations:
                final_normalized.append({
                    "role": "user",
                    "content": cancellations
                })
    
    if not final_normalized:
        return final_normalized

    merged = [final_normalized[0]] if final_normalized else []
    for msg in final_normalized[1:]:
        if msg["role"] == merged[-1]["role"]:
            prev = merged[-1]
            prev_content = prev["content"] if isinstance(prev["content"], list) else [{"type": "text", "text": prev["content"]}]
            curr_content = msg["content"] if isinstance(msg["content"], list) else [{"type": "text", "text": msg["content"]}]
            merged[-1]["content"] = prev_content + curr_content
        else:
            merged.append(msg)
    
    return merged


def run_loop(state: LoopState) -> bool:
    dump_debug(state)
    response = client.messages.create(
        model=MODEL,
        tools=TOOLS,
        system=SYSTEM,
        max_tokens=8000,
        messages=normalize_messages(state.messages),
    )
    state.messages.append({
        "role": "assistant",
        "content": response.content,
    })

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

def dump_debug(state: LoopState):
    import pprint
    with open("debug_state.txt", "w") as f:
        f.write(pprint.pformat(state.messages))

def agent_loop(state: LoopState) -> None:
    dump_debug(state)
    while run_loop(state):
        dump_debug(state)

if __name__ == "__main__":
    history = []
    while True:
        try:
            query = input("\033[36mYou >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in {"q", "quit", "exit", ""}:
            break
        
        history.append({"role": "user", "content": query})
        state = LoopState(messages=history)
        agent_loop(state)

        final_text = extract_text(history[-1]["content"])
        if final_text:
            print(final_text)
        print()