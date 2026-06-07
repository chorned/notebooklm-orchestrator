# 🎙️ NotebookLM Orchestrator

An autonomous, stateful pipeline that orchestrates Gemini 3.1 Pro for deep academic research and the NotebookLM SDK for long-form audio podcast generation. Engineered for production resilience with full crash-recovery, state persistence, and rate-limit mitigation.

## 🧠 The Hermes Stack Architecture

This orchestrator is designed to operate seamlessly within the Hermes Agent ecosystem.

While the heavy lifting of long-form textbook generation is delegated to cloud models (Gemini 3.1 Pro), the overarching pipeline, decision-making, and execution routing can be managed by a local **8GB quantized Hermes model** (shoutout to Nous Research for building the self-improving agent framework that makes complex local orchestration possible).

```text
┌─────────────────────────────────────────────────────────────┐
│               NOTEBOOKLM ORCHESTRATOR                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────┐    ┌──────────────────────────────────┐  │
│  │  Interactive  │    │  Hermes (Local 8GB) or           │  │
│  │  Interview    │───▶│  Gemini 3.1 Flash-Lite           │  │
│  └───────────────┘    │  (Curriculum Design & Scoping)   │  │
│          │            └──────────────────────────────────┘  │
│          ▼                                                  │
│  ┌───────────────┐    ┌──────────────────────────────────┐  │
│  │  Gemini 3.1   │    │  PHASE 1: Research Generation    │  │
│  │  Pro Preview  │───▶│  Dense textbook chapters per     │  │
│  │               │    │  lesson (Markdown .txt files)    │  │
│  └───────────────┘    └──────────────────────────────────┘  │
│         │                                                   │
│         ▼                                                   │
│  ┌───────────────┐    ┌──────────────────────────────────┐  │
│  │  NotebookLM   │    │  PHASE 2: Audio Generation       │  │
│  │ SDK + Cookie  │───▶│  Deep Dive podcast episodes      │  │
│  │ Auth (rookiepy)│   │  (.mp3, ~100MB each)             │  │
│  └───────────────┘    └──────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  State Machine: curriculum_state.json                │   │
│  │  pending → generating → completed / failed           │   │
│  │  Enables crash recovery, resume, and CRON mode       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
