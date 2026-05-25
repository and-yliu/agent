from agent import LoopState, agent_loop
from messages import extract_text
from hooks import trigger_hooks

if __name__ == "__main__":
    print("[Starting Autonomous Coding Agent]")
    
    history = []
    while True:
        try:
            query = input("\033[36mYou >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in {"q", "quit", "exit", ""}:
            break

        # Trigger prompt submit hook
        trigger_hooks("UserPromptSubmit", query)

        history.append({"role": "user", "content": query})
        state = LoopState(messages=history)
        agent_loop(state)

        final_text = extract_text(history[-1]["content"])
        if final_text:
            print(final_text)
        print()