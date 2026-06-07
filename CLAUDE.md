# **🤖 AI Assistant Instructions (CLAUDE.md)**

Welcome to the notebooklm-orchestrator repository. This document outlines the architectural context, coding standards, and operational guidelines you must follow when modifying or analyzing this codebase.

## **🏗️ Project Architecture & Context**

* **Goal:** This project is a resilient, autonomous pipeline that pairs Gemini 3.1 Pro (for generating dense research/textbooks) with the unofficial NotebookLM SDK (for generating long-form audio podcasts).  
* **Core Loop:**  
  1. Interactive scoping/curriculum design.  
  2. Deep research generation (markdown text).  
  3. Audio generation via NotebookLM.  
* **State Management:** The orchestrator relies on a persistent curriculum\_state.json to track the status of each lesson (pending, generating, completed, failed). This is critical for crash recovery and resuming operations.  
* **Authentication:** The system bypasses headless browsers by using rookiepy to securely extract live Google session cookies directly from the host machine's Chrome SQLite database.  
* **Resilience:** The code must handle flaky NotebookLM artifact states (e.g., the "Stubborn Fallback Mode") and implement cooldowns for API rate limits (HTTP 429).

## **🛠️ Code Standards & Conventions**

### **Language & Typing**

* **Python:** This project targets Python 3.11+.  
* **Type Hinting:** Use strict type hints for all function signatures and complex variables. Rely on the typing module (or standard collections like list, dict in modern Python).  
* **Docstrings:** All major classes and functions must include concise docstrings explaining their purpose, arguments, and return values.

### **Modularity & Structure**

* **LangChain Integration:** The LLM backend (currently Gemini 3.1 Pro) is implemented via LangChain. Any modifications to the prompt engineering or model interaction should respect this modularity to allow easy swapping of models.  
* **Separation of Concerns:** Keep the orchestration logic (state machine, routing), research generation (LLM calls), and audio production (NotebookLM SDK interactions) cleanly separated.

### **Error Handling & Logging**

* **Graceful Failures:** Anticipate API timeouts, authentication errors, and parsing issues. Catch specific exceptions rather than using broad except Exception: blocks where possible.  
* **State Updates:** If a step fails, the failure *must* be reflected in the curriculum\_state.json so the process can be resumed or retried later. Do not leave the state machine in an inconsistent state.  
* **Logging:** Use standard logging or descriptive print statements (depending on the project's setup) to clearly indicate pipeline progress, retries, and errors.

## **🛡️ Security & Privacy Mandates**

* **Cookie Handling:** The rookiepy extraction logic is highly sensitive. **NEVER** modify cookie\_extractor.py to extract cookies from domains other than \*.google.com.  
* **No Hardcoded Credentials:** Never hardcode API keys, session tokens, or passwords in the source code. All secrets must be loaded via .env or environment variables.  
* **File Ignoring:** Ensure that any files containing decrypted cookies or local state (e.g., storage\_state.json, curriculum\_state.json) are correctly ignored in .gitignore.

## **🔄 Development Workflow**

1. **Analyze State First:** When debugging a crash or issue, first inspect the structure and contents of curriculum\_state.json to understand where the pipeline halted.  
2. **Respect CRON Mode:** Modifications to the main execution loop must remain compatible with CRON\_MODE=true (headless, single-lesson processing with clean exits on rate limits).  
3. **Test Fallbacks:** When modifying the NotebookLM interaction, consider the "Ghost Adoption" and "Stubborn Fallback" mechanisms. Ensure your changes do not break the system's ability to recover from delayed Google audio generation or "removed" artifacts.
