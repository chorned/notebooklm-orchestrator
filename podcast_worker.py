import os
import sys
import json
import logging
import asyncio
import aiohttp
from pathlib import Path
from dotenv import load_dotenv

# LangChain
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage

# NotebookLM SDK
from notebooklm import NotebookLMClient, AudioFormat, AudioLength

# Local Modules
from cookie_extractor import refresh_notebooklm_cookies
from schemas import LessonDefinition, LessonPlan

# =====================================================================
# CONFIGURATION & INITIALIZATION
# =====================================================================
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
AUTH_PATH = Path(os.environ.get("NOTEBOOKLM_STORAGE_PATH", str(BASE_DIR / "storage_state.json")))

# Persistent local base directory for isolated project folders
OUTPUT_BASE_DIR = BASE_DIR / "output"
OUTPUT_BASE_DIR.mkdir(parents=True, exist_ok=True)

# RATE LIMIT & PACING CONFIGURATION
CRON_MODE = os.environ.get("CRON_MODE", "False").lower() in ("true", "1", "yes")
INTER_LESSON_DELAY_SECONDS = 900 # Hardcoded to 15 minutes between lessons
RATE_LIMIT_COOLDOWN_SECONDS = 1800 # 30 minutes to aggressively snipe rolling Token Bucket refills

# =====================================================================
# SCHEMAS & STATE MANAGEMENT
# =====================================================================
# Schemas imported from schemas.py

def save_curriculum_state(plan: LessonPlan, state_path: Path):
    """Saves the current progress of the curriculum to the specific project directory."""
    state_path.write_text(plan.model_dump_json(indent=4), encoding="utf-8")
    logger.info(f"💾 Curriculum state saved to disk at {state_path}")

def get_latest_state_file():
    """Finds the most recently modified state file for CRON mode auto-resume."""
    state_files = list(OUTPUT_BASE_DIR.rglob("curriculum_state.json"))
    if not state_files:
        return None
    return max(state_files, key=lambda p: p.stat().st_mtime)

def ensure_valid_auth_file(path: Path):
    """Failsafe to ensure file structure is correct on initial load."""
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            repaired_data = {"cookies": data}
            path.write_text(json.dumps(repaired_data, indent=4), encoding="utf-8")
    except json.JSONDecodeError:
        pass

# =====================================================================
# MAIN ORCHESTRATOR
# =====================================================================
async def main_workflow():
    llm_flash = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", temperature=0.7)
    llm_pro = ChatGoogleGenerativeAI(model="gemini-3.1-pro-preview", temperature=0.7)
    
    print("\n" + "="*60)
    print("🎙️ WELCOME TO PROJECT HERMES")
    if CRON_MODE:
        print("🤖 RUNNING IN CRON (SINGLE-SHOT) MODE")
    print("="*60 + "\n")

    lesson_plan = None
    project_dir = None
    state_file_path = None

    # --- STATE DISCOVERY & ISOLATION ---
    existing_states = list(OUTPUT_BASE_DIR.rglob("curriculum_state.json"))
    
    if CRON_MODE and existing_states:
        state_file_path = get_latest_state_file()
        if state_file_path:
            project_dir = state_file_path.parent
            print(f"🤖 Auto-resuming latest curriculum in CRON_MODE: {project_dir.name}")
    elif existing_states and not CRON_MODE:
        print("📁 Existing Curriculums Found:")
        for idx, path in enumerate(existing_states, 1):
            dir_name = path.parent.name
            print(f"  {idx}. {dir_name}")
        print(f"  {len(existing_states) + 1}. Start a NEW curriculum")
        
        choice = input("\nSelect an option to resume, or start fresh: ")
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(existing_states):
                state_file_path = existing_states[choice_idx]
                project_dir = state_file_path.parent
                print(f"Resuming workflow for: {project_dir.name}")
        except ValueError:
            pass # Invalid input, will fall through to new curriculum

    # Load existing state if selected
    if state_file_path:
        try:
            lesson_plan = LessonPlan.model_validate_json(state_file_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load state: {e}. Starting fresh.")
            lesson_plan = None
            state_file_path = None
            project_dir = None

    # --- NEW CURRICULUM GENERATION ---
    if not lesson_plan:
        if CRON_MODE:
            logger.error("No curriculum state found, but running in CRON_MODE. Exiting.")
            sys.exit(1)

        sys_prompt = (
            "You are an expert curriculum designer and podcast producer. "
            "The user will provide a topic they want to learn about. "
            "Your task is to conduct a thorough interview to understand their goals, current knowledge level, "
            "and specific angles of interest to create a highly tailored, deeply researched podcast curriculum (up to 10 lessons). "
            "RULES: "
            "1. You MUST ask at least 3-4 thoughtful, probing questions to do proper research on what the user wants. "
            "2. Ask ONLY one question at a time. Wait for the user's response. "
            "3. Do NOT generate the curriculum during this phase. "
            "4. ONLY after you have gathered sufficient, deep context from the user, reply with exactly the word: READY"
        )
        messages = [SystemMessage(content=sys_prompt)]
        messages.append(HumanMessage(content=input("What do you want to learn about?\n> ")))
        print("\n[AI is thinking...]")
        
        while True:
            response = llm_flash.invoke(messages)
            ai_text = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in response.content).strip() if isinstance(response.content, list) else str(response.content).strip()
            
            if "READY" in ai_text.upper():
                print("\n[AI has enough information. Structuring Lesson Plan...]")
                break
                
            print(f"\nAI Curriculum Designer: {ai_text}")
            messages.extend([AIMessage(content=ai_text), HumanMessage(content=input("> "))])

        messages.append(HumanMessage(content=(
            "Based on our detailed interview, perform a deep dive synthesis on the topic. "
            "Then, generate the comprehensive lesson plan (up to 10 lessons). "
            "Make the research prompts highly detailed, academic, and exhaustive so that a secondary AI "
            "can use them to write dense textbook chapters."
        )))
        
        print("\n[AI is performing deep research and structuring the JSON curriculum... This may take a minute.]")
        lesson_plan = llm_pro.with_structured_output(LessonPlan).invoke(messages)
        
        print(f"\n--- Proposed Plan: {lesson_plan.series_title} ---")
        for i, l in enumerate(lesson_plan.lessons):
            print(f"\n{i+1}. {l.lesson_title}\n   ➤ Research Prompt: {l.research_prompt}\n   ➤ Podcast Prompt:  {l.podcast_prompt}")
        
        if input("\nDo you approve this lesson plan and want to start research/generation? (y/n): ").lower() != 'y':
            print("Workflow aborted by user.")
            return
            
        # Create Isolated Directory
        safe_series_name = "".join(c if c.isalnum() else "_" for c in lesson_plan.series_title)
        project_dir = OUTPUT_BASE_DIR / safe_series_name
        project_dir.mkdir(parents=True, exist_ok=True)
        state_file_path = project_dir / "curriculum_state.json"
        
        save_curriculum_state(lesson_plan, state_file_path)

    # =====================================================================
    # PHASE 1: RESEARCH GENERATION LOOP (GEMINI 3.1 PRO)
    # =====================================================================
    print("\n" + "="*60)
    print("📚 PHASE 1: GENERATING TEXTBOOK RESEARCH MATERIALS")
    print("="*60 + "\n")
    
    for index, lesson in enumerate(lesson_plan.lessons, 1):
        safe_lesson_title = "".join(c if c.isalnum() else "_" for c in lesson.lesson_title)
        research_path = project_dir / f"Research_{index}_{safe_lesson_title}.txt"
        
        # Skip generation if the text file already exists and is reasonably sized
        if research_path.exists() and research_path.stat().st_size > 500:
            if not lesson.research_file:
                lesson.research_file = str(research_path)
                save_curriculum_state(lesson_plan, state_file_path)
            continue
            
        logger.info(f"Generating intensive research for Lesson {index}: {lesson.lesson_title}")
        research_response = llm_pro.invoke([
            SystemMessage(content="You are an expert textbook author. Write an exhaustive, dense chapter based on the user's prompt. Provide deep academic context, factual timelines, and critical analysis to serve as source material for a long-form podcast. Use clear Markdown formatting."),
            HumanMessage(content=lesson.research_prompt)
        ])
        textbook_content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in research_response.content) if isinstance(research_response.content, list) else str(research_response.content)
        
        research_path.write_text(textbook_content, encoding="utf-8")
            
        lesson.research_file = str(research_path)
        save_curriculum_state(lesson_plan, state_file_path)
        logger.info(f"✅ Saved research to {research_path}")

    logger.info("🎉 All Gemini research complete. Proceeding to Audio Generation.")

    # =====================================================================
    # PHASE 2: AUDIO GENERATION LOOP (NOTEBOOKLM SDK)
    # =====================================================================
    print("\n" + "="*60)
    print("🎙️ PHASE 2: GENERATING DEEP DIVE PODCASTS")
    print("="*60 + "\n")
    
    for index, lesson in enumerate(lesson_plan.lessons, 1):
        if lesson.status == "completed":
            logger.info(f"⏭️ Skipping Lesson {index}/{len(lesson_plan.lessons)}: '{lesson.lesson_title}' (Already Completed)")
            continue

        notebook_title = f"Ep {index}: {lesson.lesson_title}"[:50]
        safe_lesson_title = "".join(c if c.isalnum() else "_" for c in lesson.lesson_title)
        local_audio_path = project_dir / f"Episode_{index}_{safe_lesson_title}.mp3"
        
        # Resiliency Check
        if local_audio_path.exists() and local_audio_path.stat().st_size > 1024 * 1024: 
            logger.info(f"✅ RECOVERY: Found fully downloaded audio for Episode {index} at {local_audio_path}!")
            lesson.status = "completed"
            save_curriculum_state(lesson_plan, state_file_path)
            continue

        # 👻 GHOST ADOPTION CHECK
        if lesson.notebook_id:
            logger.info(f"🕵️ Ghost Adoption Check: Notebook {lesson.notebook_id} exists. Checking if Google finished it in the background...")
            try:
                ensure_valid_auth_file(AUTH_PATH)
                async with NotebookLMClient.from_storage(str(AUTH_PATH)) as client:
                    ghost_downloaded = False
                    try:
                        await client.artifacts.download_audio(lesson.notebook_id, str(local_audio_path))
                        ghost_downloaded = True
                    except Exception:
                        try:
                            # Fallback: Try with the specific task_id if it exists
                            if lesson.task_id:
                                await client.artifacts.download_audio(lesson.notebook_id, str(local_audio_path), artifact_id=lesson.task_id)
                                ghost_downloaded = True
                        except Exception:
                            pass

                    if ghost_downloaded and local_audio_path.exists() and local_audio_path.stat().st_size > 500 * 1024:
                        logger.info(f"🎉 GHOST ADOPTION SUCCESSFUL! Downloaded previously abandoned audio to {local_audio_path}")
                        lesson.status = "completed"
                        save_curriculum_state(lesson_plan, state_file_path)

                        # Clean up the ghost notebook to save quota
                        try:
                            await client.notebooks.delete(lesson.notebook_id)
                            logger.info("🗑️ Cleaned up Ghost Notebook to save quota.")
                        except Exception as e:
                            logger.warning(f"Could not delete Ghost Notebook: {e}")

                        continue # Move to next lesson immediately
                    else:
                        logger.info("No completed background audio found. Proceeding with standard generation pipeline.")
                        if local_audio_path.exists(): local_audio_path.unlink()
            except Exception as e:
                logger.debug(f"Ghost check failed: {e}")

        logger.info(f"Uploading pre-generated research for Lesson {index}/{len(lesson_plan.lessons)}: {lesson.lesson_title}")
        
        generation_successful = False
        current_notebook_id = lesson.notebook_id
        current_task_id = lesson.task_id

        while True:
            try:
                ensure_valid_auth_file(AUTH_PATH)
                async with NotebookLMClient.from_storage(str(AUTH_PATH)) as client:
                    
                    # 1. NOTEBOOK CREATION & SOURCE UPLOAD
                    if not current_notebook_id:
                        logger.info(f"Creating NotebookLM Project: {notebook_title}")
                        notebook = await client.notebooks.create(title=notebook_title)
                        current_notebook_id = notebook.id
                        
                        lesson.notebook_id = current_notebook_id
                        save_curriculum_state(lesson_plan, state_file_path)
                        
                        logger.info("Uploading local research file to NotebookLM...")
                        await client.sources.add_file(current_notebook_id, lesson.research_file)

                        logger.info("⏳ Waiting 30 seconds for Google to index the document...")
                        await asyncio.sleep(30)

                    # 2. AUDIO GENERATION
                    if not current_task_id:
                        for attempt in range(3):
                            try:
                                logger.info(f"Audio Generation Attempt {attempt + 1}/3...")
                                status = await client.artifacts.generate_audio(
                                    current_notebook_id, 
                                    source_ids=None, 
                                    instructions=lesson.podcast_prompt,
                                    audio_format=AudioFormat.DEEP_DIVE, 
                                    audio_length=AudioLength.LONG, 
                                    language="en"
                                )
                                
                                if not status or not getattr(status, 'task_id', None):
                                    raise Exception("RateLimitError swallowed by SDK: empty task_id returned. API rejected.")
                                    
                                current_task_id = status.task_id
                                
                                lesson.task_id = current_task_id
                                save_curriculum_state(lesson_plan, state_file_path)
                                break
                            except Exception as gen_err:
                                err_str = str(gen_err).lower()
                                if "ratelimit" in err_str or "rate limit" in err_str or "429" in err_str or "empty task_id" in err_str:
                                    raise Exception(f"RateLimitError encountered: {gen_err}")
                                elif "unavailable" in err_str and attempt < 2:
                                    logger.warning(f"Backend indexing delayed. Retrying in 30s... ({gen_err})")
                                    await asyncio.sleep(30)
                                else:
                                    raise Exception(f"Audio generation initiation failed: {gen_err}")
                    else:
                        logger.info("🔄 Existing task found! Resuming wait for Google backend...")
                    
                    logger.info(f"Audio generation queued (Task ID: {current_task_id}). Waiting for completion...")
                    final = await client.artifacts.wait_for_completion(
                        current_notebook_id, current_task_id, timeout=7500, initial_interval=60
                    )
                    
                    # 3. DOWNLOAD & FALLBACK HANDLING
                    if final.is_complete:
                        logger.info(f"Generation successful! Downloading MP3 to {local_audio_path}...")
                        await client.artifacts.download_audio(current_notebook_id, str(local_audio_path), artifact_id=current_task_id)
                        lesson.status = "completed"
                        generation_successful = True
                    else:
                        if final.status == "removed":
                            logger.warning("SDK reported artifact 'removed'. Entering stubborn fallback mode...")
                            
                            download_success = False
                            for attempt in range(15): 
                                await asyncio.sleep(60) 
                                try:
                                    logger.info(f"Fallback Download Attempt {attempt+1}/15...")
                                    try:
                                        await client.artifacts.download_audio(current_notebook_id, str(local_audio_path))
                                    except TypeError:
                                        await client.artifacts.download_audio(current_notebook_id, str(local_audio_path), artifact_id=current_task_id)
                                        
                                    if local_audio_path.exists() and local_audio_path.stat().st_size > 500 * 1024:
                                        logger.info(f"🎉 Fallback successful! Audio downloaded to {local_audio_path}")

                                        lesson.status = "completed"
                                        generation_successful = True
                                        download_success = True
                                        break
                                    else:
                                        logger.warning("Downloaded file too small. Backend finalizing...")
                                        if local_audio_path.exists(): local_audio_path.unlink()
                                        
                                except Exception as e:
                                    logger.warning(f"Audio not ready yet (Attempt {attempt+1}): {str(e)[:250]}")
                                    
                            if not download_success:
                                logger.error("Fallback timed out after 15 minutes. Initiating Infinite Retry Reset...")
                                if current_notebook_id:
                                    try: 
                                        await client.notebooks.delete(current_notebook_id)
                                        logger.info("🗑️ Deleted broken notebook safely from active session.")
                                    except Exception as del_err:
                                        logger.warning(f"⚠️ Failed to delete notebook (Google is likely locking it): {del_err}")
                                lesson.notebook_id = None
                                lesson.task_id = None
                                current_notebook_id = None
                                current_task_id = None
                                save_curriculum_state(lesson_plan, state_file_path)
                                continue
                        else:
                            logger.error(f"Audio generation failed ({final.status}). Initiating Infinite Retry Reset...")
                            if current_notebook_id:
                                try: 
                                    await client.notebooks.delete(current_notebook_id)
                                    logger.info("🗑️ Deleted broken notebook safely from active session.")
                                except Exception as del_err:
                                    logger.warning(f"⚠️ Failed to delete notebook (Google is likely locking it): {del_err}")
                                lesson.notebook_id = None
                                lesson.task_id = None
                                current_notebook_id = None
                                current_task_id = None
                                save_curriculum_state(lesson_plan, state_file_path)
                                continue
                        
                    save_curriculum_state(lesson_plan, state_file_path)
                    
                    # Clean up the successful notebook while the session is still active!
                    if current_notebook_id:
                        try:
                            await client.notebooks.delete(current_notebook_id)
                            logger.info("🗑️ Cleaned up completed NotebookLM project to save quota.")
                        except Exception as e:
                            logger.warning(f"Failed to delete completed notebook: {e}")
                            
                    break # Break retry loop, move to next lesson pacing logic
                    
            except Exception as e:
                error_msg = str(e)
                if "RateLimitError" in error_msg or "rate limit" in error_msg.lower() or "429" in error_msg:
                    logger.error(f"🚨 RATE LIMIT DETECTED: {error_msg}")
                    if CRON_MODE:
                        logger.warning("Cron mode active. Exiting cleanly to allow natural limit reset.")
                        sys.exit(0)
                    else:
                        logger.warning(f"Sleeping for {RATE_LIMIT_COOLDOWN_SECONDS // 60} minutes to allow limits to cool...")
                        await asyncio.sleep(RATE_LIMIT_COOLDOWN_SECONDS)
                        continue 
                
                elif "Authentication expired" in error_msg or "accounts.google.com" in error_msg or "Storage file not found" in error_msg:
                    logger.warning("🚨 Authentication expired. Triggering cookie extraction...")
                    if refresh_notebooklm_cookies(str(AUTH_PATH)):
                        logger.info("✅ Cookie extraction successful! Resuming...")
                        continue
                    else:
                        logger.error("🛑 Extraction failed. Exiting cleanly.")
                        sys.exit(1)
                else:
                    logger.error(f"NotebookLM failed for this lesson: {error_msg}")
                    logger.info("Initiating Infinite Retry Reset...")
                    
                    # BUG FIX: The previous 'async with' session is closed here. 
                    # We MUST open a temporary client to safely assassinate the orphaned notebook!
                    if current_notebook_id:
                        try:
                            logger.info("Opening temporary client to clean up orphaned notebook...")
                            async with NotebookLMClient.from_storage(str(AUTH_PATH)) as temp_client:
                                await temp_client.notebooks.delete(current_notebook_id)
                                logger.info("🗑️ Orphaned notebook deleted successfully.")
                        except Exception as cleanup_err:
                            logger.warning(f"Could not delete orphaned notebook (API might be down): {cleanup_err}")
                            
                    lesson.notebook_id = None
                    lesson.task_id = None
                    current_notebook_id = None
                    current_task_id = None
                    save_curriculum_state(lesson_plan, state_file_path)
                    continue

        # Post-Lesson Pacing
        pending_left = sum(1 for l in lesson_plan.lessons if l.status != "completed")
        
        if CRON_MODE:
            logger.info("⏱️ CRON_MODE is enabled. Completed one cycle. Shutting down.")
            return
            
        if generation_successful and pending_left > 0:
            logger.info(f"⏳ Pacing mechanism activated to avoid rate limits.")
            logger.info(f"Sleeping for {INTER_LESSON_DELAY_SECONDS // 60} minutes before starting the next episode...")
            await asyncio.sleep(INTER_LESSON_DELAY_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(main_workflow())
    except KeyboardInterrupt:
        print("\n\n🛑 Workflow manually aborted by user (Ctrl+C). Exiting cleanly.")
        sys.exit(130)