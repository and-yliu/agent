import re
from typing import Literal
import json
from dataclasses import dataclass, field
from fnmatch import fnmatch

MODES = ("default", "plan", "auto")
READ_ONLY_TOOLS = {"read_file", "bash_readonly", "task", "todo", "load_skill"}
WRITE_TOOLS = {"write_file", "edit_file"}


@dataclass
class PermissionRule:
    tool: str
    behavior: Literal["allow", "deny", "ask"]
    path: str | None
    content: str | None


class BashSecurityValidator:
    VALIDATORS = [
        ("shell_metachar", r"[;&|`$]"),       # shell metacharacters
        ("sudo", r"\bsudo\b"),                 # privilege escalation
        ("rm_rf", r"\brm\s+(-[a-zA-Z]*)?r"),  # recursive delete
        ("cmd_substitution", r"\$\("),          # command substitution
        ("ifs_injection", r"\bIFS\s*="),        # IFS manipulation
    ]

    def validate(self, command: str) -> list:
        """
        Check a bash command against all validators.
        Returns list of (validator_name, matched_pattern) tuples for failures.
        An empty list means the command passed all validators.
        """
        failures = []
        for name, pattern in self.VALIDATORS:
            if re.search(pattern, command):
                failures.append((name, pattern))
        return failures

    def is_safe(self, command: str) -> bool:
        """Convenience: returns True only if no validators triggered."""
        return len(self.validate(command)) == 0

    def describe_failures(self, command: str) -> str:
        """Human-readable summary of validation failures."""
        failures = self.validate(command)
        if not failures:
            return "No issues detected"
        parts = [f"{name} (pattern: {pattern})" for name, pattern in failures]
        return "Security flags: " + ", ".join(parts)

bash_validator = BashSecurityValidator()


class PermissionManager:
    def __init__(self, mode: str = "default", rules: list[PermissionRule] = None):

        if mode not in MODES:
            raise ValueError(f"Unknown mode: {mode}. Choose from {MODES}")

        self.mode = mode
        self.rules = [
            *(rules or []),
            PermissionRule(tool="load_skill", behavior="allow", path=None, content=None),
            PermissionRule(tool="todo", behavior="allow", path=None, content=None),
        ]

    def check(self, tool_name: str, tool_input: dict) -> dict:
        """
        Returns: {"behavior": "allow"|"deny"|"ask", "reason": str}
        """

        if tool_name == "bash":
            command = tool_input.get("command", "")
            failures = bash_validator.validate(command)
            if failures:
                # Severe patterns (sudo, rm_rf) get immediate deny
                severe = {"sudo", "rm_rf"}
                severe_hits = [f for f in failures if f[0] in severe]
                if severe_hits:
                    desc = bash_validator.describe_failures(command)
                    return {"behavior": "deny",
                            "reason": f"Bash validator: {desc}"}
                # Other patterns escalate to ask (user can still approve)
                desc = bash_validator.describe_failures(command)
                return {
                    "behavior": "ask",
                    "reason": f"Bash validator flagged: {desc}"
                }

        for rule in self.rules:
            if rule.behavior != "deny":
                continue
            if self._match(rule, tool_name, tool_input):
                return {
                    "behavior": "deny",
                    "reason": f"Blocked by deny rule: {rule}"
                }

        if self.mode == "plan":
            # Plan mode: deny all write operations, allow reads
            if tool_name in WRITE_TOOLS:
                return {"behavior": "deny",
                        "reason": "Plan mode: write operations are blocked"}
            return {"behavior": "allow", "reason": "Plan mode: read-only allowed"}

        if self.mode == "auto":
            # Auto mode: approve all tools without asking (bash already filtered above)
            return {"behavior": "allow", "reason": "Auto mode: tool auto-approved"}

        if tool_name in READ_ONLY_TOOLS:
            return {
                "behavior": "allow",
                "reason": "Auto mode: read-only tool auto-approved"
            }

        for rule in self.rules:
            if rule.behavior != "allow":
                continue
            if self._match(rule, tool_name, tool_input):
                return {
                    "behavior": "allow",
                    "reason": f"Matched allow rule: {rule}"
                }
        return {
            "behavior": "ask",
            "reason": f"No rule matched for {tool_name}, asking user"
        }

    def ask_user(self, tool_name: str, tool_input: dict) -> bool:
        """Interactive approval prompt. Returns True if approved."""
        preview = json.dumps(tool_input, ensure_ascii=False)
        print(f"\n  [Permission] {tool_name}: {preview}")
        try:
            answer = input("  Allow? (y/n/always): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if answer == "always":
            # Add permanent allow rule for this tool
            self.rules.append(PermissionRule(tool=tool_name, behavior="allow", path="*", content=None))
            return True
        if answer in ("y", "yes"):
            return True

        return False

    def _match(self, rule: PermissionRule, tool_name: str, tool_input: dict) -> bool:
        """Check if a rule matches the tool call."""

        # Tool name match
        if rule.tool and rule.tool != "*":
            if rule.tool != tool_name:
                return False

        # Path pattern match
        if rule.path and rule.path != "*":
            path = tool_input.get("path", "")
            if not fnmatch(path, rule.path):
                return False

        if rule.content:
            command = tool_input.get("command", "")
            if not fnmatch(command, rule.content):
                return False
        return True
