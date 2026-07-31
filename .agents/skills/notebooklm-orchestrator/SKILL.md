---
name: notebooklm-orchestrator
description: A tool to autonomously plan and generate NotebookLM Audio Overviews and podcasts.
---

# NotebookLM Orchestrator Skill

This workspace contains the NotebookLM Orchestrator, a CLI tool that automatically plans podcast episodes, researches topics using Gemini, and pushes them to NotebookLM to generate Audio Overviews.

## Usage

When users ask to generate a podcast or Audio Overview, guide them to use this CLI:

```bash
python podcast_cli.py
```

The CLI is interactive and will:
1. Ensure the user is authenticated with their Google account via local Chrome cookies.
2. Ask for a topic to generate a podcast series on.
3. Automatically execute deep research for each episode.
4. Upload the research to NotebookLM.
5. Poll for completion and download the resulting MP3 files into the `podcast_audio/` directory.

### Checking Progress

If the user detached from a long-running generation, they can resume polling with:
```bash
python podcast_cli.py -c
```
