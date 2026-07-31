# NotebookLM Podcast Orchestrator

This is an autonomous orchestrator that automatically plans and generates NotebookLM Audio Overviews (podcasts) using Gemini and the NotebookLM Python SDK.

## Features
- **Deep Research**: Leverages Gemini Pro to automatically generate in-depth research documents based on your topics.
- **Automated Audio Generation**: Pushes research directly to NotebookLM and starts synthesis using the `notebooklm-py` SDK.
- **Background Tracking**: Start a generation, detach your terminal, and resume tracking later.
- **Automatic MP3 Downloads**: Automatically downloads generated audio directly to `podcast_audio/`.
- **Agent/MCP Ready**: Exposes an MCP (Model Context Protocol) server so AI agents can autonomously generate podcasts.

## Prerequisites
1. **Google Chrome**: You must have Google Chrome installed and be logged into `notebooklm.google.com`. The bot uses your local Chrome cookies to authenticate.
2. **Gemini API Key**: You need a Gemini API Key to run the research phases.

## Setup
```bash
# Create a virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Interactive CLI Usage
Run the interactive orchestrator:
```bash
python podcast_cli.py
```
From the interactive menu, you can generate a new Podcast Plan from a topic or execute an existing JSON plan. 

If you start a generation and want to close the terminal, you can! The generation happens in the cloud. You can reconnect and check on the status later by running:
```bash
python podcast_cli.py -c
```

## Autonomous Agent (MCP) Usage
You can run the MCP server to expose the podcast generation capabilities to an AI agent:
```bash
python mcp_server.py
```
Agents will be able to use the `generate_podcast_plan` and `execute_podcast_plan` tools to run the pipeline autonomously.
