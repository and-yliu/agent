from agent import LoopState, agent_loop
from messages import extract_text
from permissionManager import PermissionManager, MODES

if __name__ == "__main__":
    print("Permission modes: default, plan, auto")
    mode_input = input("Permission (default): ").strip().lower() or "default"
    if mode_input not in MODES:
        print(f"Invalid mode: {mode_input}. Using default.")
        mode_input = "default"
    
    perms = PermissionManager(mode=mode_input)
    print(f"[Permission mode: {mode_input}]")
    
    history = []
    while True:
        try:
            query = input("\033[36mYou >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in {"q", "quit", "exit", ""}:
            break

        if query.startswith("/mode"):
            parts = query.split()
            if len(parts) == 2 and parts[1].lower() in MODES:
                perms.mode = parts[1].lower()
                print(f"[Permission mode: {perms.mode}]")
            else:
                print(f"Usage: /mode [default|plan|auto]")
            continue
        
        if query.startswith("/rules"):
            for i, rule in enumerate(perms.rules):
                print(f"    {i}: {rule}")
            continue

        history.append({"role": "user", "content": query})
        state = LoopState(messages=history)
        agent_loop(state, perms)

        final_text = extract_text(history[-1]["content"])
        if final_text:
            print(final_text)
        print()