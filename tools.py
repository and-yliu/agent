import os
import subprocess
from pathlib import Path
from context import AgentContext

from dotenv import load_dotenv

load_dotenv()

# ── Working directory ────────────────────────────────────────────────────────
# Configurable via the WORKDIR env var; defaults to ./workspace.
WORKDIR = Path(os.getenv("WORKDIR", str(Path.cwd() / "workspace")))

# ── Tool schemas ─────────────────────────────────────────────────────────────

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
        },
    },
    {
        "name": "read",
        "description": "Read file contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the WORKDIR",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of lines read limit",
                },
            },
            "required": ["path"],
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
                    "description": "Relative path to the WORKDIR",
                },
                "content": {
                    "type": "string",
                    "description": "New content for the file",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit",
        "description": "Replace exact text in file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the WORKDIR",
                },
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
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
    {
        "name": "task",
        "description": "Run a subagent task in a clean context and return a summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Short description of the task",
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "load_skill",
        "description": "Load the full body of a named skill into the current context.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "glob", 
        "description": "Find files matching a glob pattern.",
        "input_schema": {
            "type": "object", 
            "properties": {
                "pattern": {"type": "string"}
            }, 
            "required": ["pattern"]
        }
    }
]

# ── Path sandbox ─────────────────────────────────────────────────────────────

def safe_path(p: str) -> Path:
    """Resolve a relative path inside WORKDIR; raise if it escapes the sandbox."""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError("Path is outside of the work directory")
    return path


# ── Tool implementations ─────────────────────────────────────────────────────

def run_bash(command: str) -> str:
    print(f"{AgentContext.get_indent()}\033[33m$ {command}\033[0m")
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKDIR,
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


def run_read(path: str, limit: int = None) -> str:
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
        count = content.count(old_text)
        if count > 1:
            return (
                f"Error: Found {count} occurrences of the target text in {path}. "
                "Provide a more specific old_text to uniquely identify the edit location."
            )
        content = content.replace(old_text, new_text, 1)
        fp.write_text(content)
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"

def run_glob(pattern: str) -> str:
    import glob as g
    try:
        results = []
        for match in g.glob(pattern, root_dir=WORKDIR, recursive=True):
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR):
                results.append(match)
        return "\n".join(results) if results else "(no matches)"
    except Exception as e:
        return f"Error: {e}"


# ── Handler factory ───────────────────────────────────────────────────────────

def build_tool_handlers(todo, skill_registry, run_subagent_fn: callable) -> dict:
    """
    Build the TOOL_HANDLERS dispatch dict.

    Accepts the TodoManager instance and the subagent callable explicitly
    to avoid circular imports and module-level global coupling.
    """
    return {
        "bash":  lambda **kwargs: run_bash(kwargs["command"]),
        "read":  lambda **kwargs: run_read(kwargs["path"], kwargs.get("limit")),
        "write": lambda **kwargs: run_write(kwargs["path"], kwargs["content"]),
        "edit":  lambda **kwargs: run_edit(kwargs["path"], kwargs["old_text"], kwargs["new_text"]),
        "todo":  lambda **kwargs: todo.update(kwargs["items"]),
        "task":  lambda **kwargs: run_subagent_fn(kwargs["prompt"]),
        "load_skill": lambda **kwargs: skill_registry.load_skill(kwargs["name"]),
        "glob": lambda **kwargs: run_glob(kwargs["pattern"]),
    }
