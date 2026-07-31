---
name: podcast-generator
description: Generate comprehensive podcast audio overviews from a topic using Gemini and NotebookLM.
---

# NotebookLM Orchestrator

This repository is equipped with the NotebookLM Orchestrator, which automates the creation of podcast audio overviews.

## Usage

Agents can run the orchestrator either interactively or via its MCP server capabilities.

### Interactive CLI Usage
To generate a podcast via the terminal:
1. Initialize the environment: `source venv/bin/activate`
2. Run `python podcast_cli.py` to launch the interactive prompt.
3. Choose either "🪄 Generate a new Podcast Plan from a Topic" or "🚀 Execute an existing Plan (JSON)".
4. Follow the interactive prompts to construct the podcast.
5. Audio will automatically download to `podcast_audio/`. Run `python podcast_cli.py -c` to check on background tasks.

### MCP Server Usage
To empower an agent to autonomously generate podcasts, point the MCP client at the `mcp_server.py` file.
1. Ensure `python podcast_cli.py` has been run at least once to authenticate the Chrome profile.
2. Provide the agent with the `mcp_server.py` MCP tools (`generate_podcast_plan`, `execute_podcast_plan`).
