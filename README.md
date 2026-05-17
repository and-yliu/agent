# Mini CLI AI Agent

A lightweight, Python-based CLI AI agent powered by Anthropic's Claude API. It provides a conversational interface in the terminal and comes equipped with a set of tools to interact with your local filesystem, execute bash commands, and manage multi-step tasks.

## Features

- **Conversational CLI**: Interact directly with the AI agent in a continuous `s01 >>` terminal loop.
- **Anthropic Claude Integration**: Communicates seamlessly with the Anthropic API.
- **Robust Message Normalization**: Automatically merges consecutive roles and handles missing tool results (or API constraints) to prevent `BadRequestError`s during the conversational loop.
- **Built-In Tools**:
  - `bash`: Execute arbitrary bash commands (with basic safety checks against dangerous commands).
  - `read`: Read files from the current workspace.
  - `write`: Create or overwrite files.
  - `edit`: Find and replace exact text within files.
  - `todo`: A built-in multi-step task manager that helps the agent break down and track complex objectives (managed via `todoManager.py`).

## Prerequisites

- Python 3.10+
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- `python-dotenv`

## Setup

1. Clone or download this repository.
2. Install the required dependencies:
   ```bash
   pip install anthropic python-dotenv
   ```
3. Create a `.env` file in the root of the project with your Anthropic credentials and desired model:
   ```env
   ANTHROPIC_API_KEY=your_api_key_here
   MODEL=claude-3-5-sonnet-20241022
   ```
   *(Make sure to use an Anthropic model that supports tool use, such as the Claude 3 or 3.5 series).*

## Usage

Run the main script to start the agent:

```bash
python3 main.py
```

- Type your instructions or questions at the `You >>` prompt.
- The agent will decide whether to respond directly or use its tools (like writing files, checking directory contents with bash, or making a todo list for larger tasks).
- To exit the program, type `q`, `quit`, `exit`, or simply press `Ctrl+C`.

## Architecture Details

- **`main.py`**: The entry point. Handles the chat loop (`agent_loop`), tool execution mapping, Anthropics API interaction, state management (`LoopState`), and robust `normalize_messages` logic to adhere to API spec.
- **`todoManager.py`**: A specialized manager for the `todo` tool. It enforces a maximum of 12 items, tracks pending/in-progress/completed statuses, and occasionally prompts the agent with reminders to keep its plan updated if it hasn't modified it recently.

## Note on the Workspace Directory

By default, the script restricts file access (`read`, `write`, `edit`) to the `workspace/` subdirectory relative to where the script is executed. Make sure your target files reside within that directory, or adjust the `WORKDIR` variable inside `main.py` as needed.
