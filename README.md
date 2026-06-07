🎙️ NotebookLM OrchestratorAn autonomous, stateful pipeline that orchestrates Gemini 3.1 Pro for deep academic research and the NotebookLM SDK for long-form audio podcast generation. Engineered for production resilience with full crash-recovery, state persistence, and rate-limit mitigation.🧠 The Hermes Stack ArchitectureThis orchestrator is designed to operate seamlessly within the Hermes Agent ecosystem.While the heavy lifting of long-form textbook generation is delegated to cloud models (Gemini 3.1 Pro), the overarching pipeline, decision-making, and execution routing can be managed by a local 8GB quantized Hermes model (shoutout to Nous Research for building the self-improving agent framework that makes complex local orchestration possible).┌─────────────────────────────────────────────────────────────┐
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
✨ FeaturesAI-Driven Curriculum Design — Interactive interview to scope a personalized 10-lesson podcast series.Deep Research Generation — Gemini 3.1 Pro acts as a synthetic textbook author to generate source material.Autonomous Audio Production — The NotebookLM SDK generates long-form "Deep Dive" podcast episodes from the synthetic research.Stateful Crash Recovery — A persistent curriculum_state.json enables the pipeline to resume from any failure point.Ghost Adoption — Detects and recovers audio that Google finished generating in the background after a local crash or timeout.Stubborn Fallback Mode — A 15-minute retry loop for flaky "removed" artifact states inside NotebookLM.Rate Limit Resilience — Automatic 30-minute cooldown on 429 API responses with a clean CRON exit capability.Local Profile Auth — Uses rookiepy to securely extract your live Google session tokens directly from your local Chrome profile, bypassing the need for brittle web scrapers.🔐 Deep Dive: Cookie Authentication & PrivacyGoogle does not currently offer an official developer API or OAuth flow for NotebookLM. To automate audio generation, we must authenticate the unofficial SDK as a real human user.Why rookiepy?Alternative approaches to bypassing this limitation usually involve spinning up a headless Chromium browser via Playwright and forcing the user to manually log in, or trying to automate the login sequence. These methods are incredibly brittle, constantly break due to Google's anti-bot CAPTCHAs, and consume heavy memory resources.Instead, this orchestrator uses rookiepy. This library securely reads your active, encrypted Google session cookies directly from your machine's Chrome SQLite database, decrypting them via your OS Keychain.The Privacy GuaranteeBecause this method looks identical to how credential-stealing malware operates, we take privacy incredibly seriously:Strictly Scoped: cookie_extractor.py is hardcoded to only extract cookies for *.google.com. It ignores your banking, social media, and email cookies.Local Administrator Profile: This solution is designed to use the exact same Chrome profile as the human admin running the script. You must be actively logged into NotebookLM in your local browser.No Phoning Home: The decrypted cookies are formatted into a storage_state.json file and saved locally. They are only ever sent directly to Google's servers by the SDK.Git Ignored: The local state file containing these cookies is explicitly ignored in the .gitignore to prevent accidental public uploads.Note: On your first run, your operating system (e.g., macOS Keychain) will likely prompt you for your password or TouchID to allow rookiepy to access the Chrome database.🛠️ Swapping the LLM BackendWhile this orchestrator relies heavily on Gemini 3.1 Pro's massive context window for the deep research phase, the codebase is entirely modular thanks to LangChain.If you prefer to use Claude, OpenAI, or a local open-source model, you can update the code with minimal effort:Open podcast_worker.py.Locate the LLM initialization: llm_pro = ChatGoogleGenerativeAI(model="gemini-3.1-pro-preview").Swap it with your preferred LangChain Chat Model (e.g., ChatAnthropic, ChatOpenAI, or ChatOllama for local inference).Update your .env with the corresponding API keys.🚀 Quick StartPrerequisites: Python 3.11+, Google Chrome, a Google account logged into NotebookLM, and a Gemini API Key.# 1. Clone and enter the directory
git clone [https://github.com/chorned/notebooklm-orchestrator.git](https://github.com/chorned/notebooklm-orchestrator.git)
cd notebooklm-orchestrator

# 2. Copy the environment template and fill in your keys
cp .env.example .env
# Edit .env with your GEMINI_API_KEY

# 3. Run the bootstrapper (creates venv, installs deps, launches worker)
chmod +x launch_script.bash
./launch_script.bash
The interactive interview will guide you through creating a curriculum. After approval, the pipeline runs autonomously.⏱️ CRON ModeFor headless, scheduled execution (e.g., via crontab), run: CRON_MODE=true ./launch_script.bash.In CRON mode, the engine will auto-resume the most recently modified curriculum, process one lesson per invocation, and exit cleanly on rate limits (allowing the next cron cycle to resume).🙌 Credits & AcknowledgementsThis orchestrator stands on the shoulders of giants. Massive credit to:teng-lin/notebooklm-py: Teng Lin's phenomenal work reverse-engineering the internal NotebookLM Protobufs into a stable, typed Python SDK makes this entire project possible.Nous Research: For the inspiration behind the Hermes Agent framework, proving that local, quantized models can effectively orchestrate complex pipelines.rookiepy: For providing a lightweight, cross-platform bridge to local browser cookies.📄 LicenseMIT License