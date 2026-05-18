import pprint


def extract_text(content) -> str:
    """Extract all text blocks from an Anthropic response content list."""
    if not isinstance(content, list):
        return ""
    texts = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts)


def normalize_messages(messages: list) -> list:
    """
    Serialize Anthropic SDK objects to plain dicts, cancel any orphaned
    tool_use blocks (tool_use with no matching tool_result), and merge
    consecutive messages from the same role.
    """
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
                clean_content.append(
                    {k: v for k, v in b.items() if k not in ("_internal", "_source", "_timestamp")}
                )
            clean["content"] = clean_content
        else:
            clean["content"] = msg.get("content", "")
        normalized.append(clean)

    # Collect all tool_use IDs that already have a matching tool_result.
    existing_results: set[str] = set()
    for msg in normalized:
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if block.get("type") == "tool_result":
                    existing_results.add(block.get("tool_use_id"))

    # Insert cancellation tool_results for any orphaned tool_use blocks.
    final_normalized = []
    for msg in normalized:
        final_normalized.append(msg)
        if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
            cancellations = [
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": "(cancelled)",
                }
                for block in msg["content"]
                if block.get("type") == "tool_use" and block.get("id") not in existing_results
            ]
            if cancellations:
                final_normalized.append({"role": "user", "content": cancellations})

    if not final_normalized:
        return final_normalized

    # Merge consecutive messages from the same role.
    merged = [final_normalized[0]]
    for msg in final_normalized[1:]:
        if msg["role"] == merged[-1]["role"]:
            prev = merged[-1]
            prev_content = (
                prev["content"]
                if isinstance(prev["content"], list)
                else [{"type": "text", "text": prev["content"]}]
            )
            curr_content = (
                msg["content"]
                if isinstance(msg["content"], list)
                else [{"type": "text", "text": msg["content"]}]
            )
            merged[-1]["content"] = prev_content + curr_content
        else:
            merged.append(msg)

    return merged


def dump_debug(state) -> None:
    """Write a pretty-printed snapshot of state.messages to debug_state.txt."""
    with open("debug_state.txt", "w") as f:
        f.write(pprint.pformat(state.messages))
