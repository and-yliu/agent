CONTEXT_LIMIT = 50000
KEEP_RECENT = 3
PERSIST_THRESHOLD = 30000

def estimate_size(messages):
    return len(str(messages))

def snip_compact(messages, max_messages=50):
    if len(messages) <= max_messages:
        return messages
    
    keep_head, keep_tail = KEEP_RECENT,  max_messages - KEEP_RECENT
    snipped = len(messages) - keep_head - keep_tail

    return messages[:keep_head] + [{"role": "user", "content": f"[Context snipped: {snipped} middle messages omitted]"}] + messages[-keep_tail:]

def collect_tool_results(messages):
    blocks = []
    for mi, msg in enumerate(messages):
        if msg.get("role") != "user" or not isinstance(msg.get("content", list)):
            continue
        for bi, block in enumerate(msg["content"]):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                blocks.append((mi, bi, block))
    return blocks

def micro_compact(messages):
    tool_results = collect_tool_results(messages)
    if len(tool_results) <= KEEP_RECENT: return messages
    for _, _, block in tool_results[:-KEEP_RECENT]:
        if len(block.get("content", "")) > 120:
            block["content"] = "[Earlier tool result compacted. Re-run if needed.]"
    return messages
            