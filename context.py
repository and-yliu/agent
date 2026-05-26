class AgentContext:
    stack = ["main"]

    @classmethod
    def push(cls, agent_type: str):
        cls.stack.append(agent_type)

    @classmethod
    def pop(cls) -> str:
        if len(cls.stack) > 1:
            return cls.stack.pop()
        return cls.stack[0]

    @classmethod
    def is_subagent(cls) -> bool:
        return len(cls.stack) > 1 and cls.stack[-1] == "subagent"

    @classmethod
    def get_prefix(cls) -> str:
        """Returns a color-coded prefix for the current agent context."""
        indent = "  " * (len(cls.stack) - 1)
        if cls.is_subagent():
            # Light purple/magenta color for subagents
            return f"{indent}\033[35m[Subagent]\033[0m "
        return "\033[36m[Main]\033[0m "

    @classmethod
    def get_indent(cls) -> str:
        """Returns the space indentation level based on subagent depth."""
        return "  " * (len(cls.stack) - 1)
