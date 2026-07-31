"""
Interactive Podcast Bot CLI

This is the main orchestrator for the Podcast Bot pipeline.
It features an interactive command-line interface using `rich` and `questionary`.

Key Responsibilities:
1. Environment Setup (API keys, Chrome Profile Auth)
2. Interactive Brainstorming (Generate a podcast JSON plan using Gemini)
3. Orchestration (Run Gemini research -> NotebookLM upload -> Audio Synthesis)
4. Monitoring (Polls background audio synthesis tasks and downloads MP3s)

Usage:
    python podcast_cli.py
    python podcast_cli.py -c (to check progress of running tasks)
"""
import sys
from rich.console import Console

console = Console()

with console.status("[cyan]Initializing NotebookLM Orchestrator...[/cyan]", spinner="bouncingBar"):
    import asyncio
    import json
    import os
    import re
    import aiohttp
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    import questionary

LOGO = r"""
 [bold cyan]█▀█ █▀█ █▀▄ █▀▀ █▀█ █▀ ▀█▀[/bold cyan]
 [bold magenta]█▀▀ █▄█ █▄▀ █▄▄ █▀█ ▄█ ░█░[/bold magenta]
 
 [bold cyan]█▀▀ █▀▀ █▄░█ █▀▀ █▀█ █▀█ ▀█▀ █▀█ █▀█[/bold cyan]
 [bold magenta]█▄█ ██▄ █░▀█ ██▄ █▀▄ █▀█ ░█░ █▄█ █▀▄[/bold magenta]
 
 [bold white]NotebookLM Orchestrator[/bold white]
"""

RUNNING_TASKS_FILE = "running_tasks.json"

# =====================================================================
# State Management
# =====================================================================
# We track running NotebookLM generation tasks in a local JSON file.
# This allows the user to close the CLI and resume monitoring later
# via `python podcast_cli.py -c`.

def load_running_tasks():
    if os.path.exists(RUNNING_TASKS_FILE):
        with open(RUNNING_TASKS_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_running_tasks(tasks):
    with open(RUNNING_TASKS_FILE, "w") as f:
        json.dump(tasks, f, indent=2)

def add_running_task(notebook_id, task_id, title):
    tasks = load_running_tasks()
    tasks.append({"notebook_id": notebook_id, "task_id": task_id, "title": title})
    save_running_tasks(tasks)

def remove_running_task(task_id):
    tasks = load_running_tasks()
    tasks = [t for t in tasks if t["task_id"] != task_id]
    save_running_tasks(tasks)


# =====================================================================
# Worker Class
# =====================================================================

class LinearWorker:
    """
    A sequential worker that handles the end-to-end podcast generation pipeline.
    
    Responsibilities:
    - Calling Gemini to brainstorm curriculums.
    - Calling Gemini to do deep research.
    - Delegating the actual NotebookLM upload to `notebooklm_automator.py`.
    """
    def __init__(self, gemini_api_key, profile_name=None, research_dir="research_output"):
        self.research_dir = research_dir
        self.gemini_api_key = gemini_api_key
        self.profile_name = profile_name
        os.makedirs(self.research_dir, exist_ok=True)
        
    def sanitize_filename(self, title: str) -> str:
        """Converts a string into a safe filename."""
        clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', title)[:50]
        return clean

    async def run_deep_research(self, prompt: str, title: str, filename: str) -> str:
        """
        Calls the Gemini REST API directly to perform deep research on a topic.
        
        Saves the markdown output to `research_output/` which will later be
        uploaded as the source document for NotebookLM.
        """
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key={self.gemini_api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": f"Deep research on: {prompt}"}]}]
            }
            
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status in [503, 429]:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(5 * (attempt + 1))
                                continue
                        if resp.status != 200:
                            text = await resp.text()
                            raise Exception(f"API Error {resp.status}: {text}")
                        data = await resp.json()
                        research_content = data['candidates'][0]['content']['parts'][0]['text']
                        break
                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    raise Exception("API Request Timed Out after multiple retries.")

        # Save research permanently
        filepath = os.path.join(self.research_dir, filename + ".md")
        
        with open(filepath, 'w') as f:
            f.write(f"# Research: {title}\n\n{research_content}")
            
        return filepath

    async def run_notebooklm(self, project_name: str, research_path: str, podcast_prompt: str = "") -> dict:
        """Invokes the NotebookLM UI Automator script to upload the research and start synthesis."""
        sys.path.append(os.path.abspath('venv/lib/python3.11/site-packages'))
        
        # Import dynamically to ensure it runs inside the correct venv context
        import notebooklm_automator
        return await notebooklm_automator.upload_research(
            episode_title=project_name,
            file_path=research_path,
            podcast_prompt=podcast_prompt,
            profile_name=self.profile_name
        )

    async def ask_clarifying_questions(self, topic: str) -> list[str]:
        """Uses Gemini to brainstorm follow-up questions to refine the user's podcast topic."""
        async with aiohttp.ClientSession() as session:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_api_key}"
            headers = {"Content-Type": "application/json"}
            system_prompt = (
                f"The user wants to create a podcast about: '{topic}'. "
                "Generate exactly 3 concise, thought-provoking clarifying questions to help narrow down the focus, target audience, or specific angle for the podcast. "
                "Return a raw JSON array of strings (no markdown fences)."
            )
            payload = {
                "contents": [{"parts": [{"text": system_prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }
            try:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    content = data['candidates'][0]['content']['parts'][0]['text']
                    return json.loads(content)
            except Exception:
                return []

    async def generate_plan(self, topic: str, context: str = "", previous_plan: dict = None, feedback: str = "") -> dict:
        """
        Uses Gemini to dynamically brainstorm a podcast curriculum and returns it as structured JSON.
        This JSON file is used as the blueprint for the entire pipeline.
        """
        async with aiohttp.ClientSession() as session:
            # We can use a faster model for the quick JSON generation
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_api_key}"
            headers = {"Content-Type": "application/json"}
            
            system_prompt = (
                f"Create a 1-5 episode podcast lesson plan for the topic: '{topic}'.\n"
                "Assume each lesson takes about 45 minutes to record.\n"
            )
            
            if context:
                system_prompt += f"Additional Context from the user:\n{context}\n\n"
                
            if previous_plan and feedback:
                system_prompt += (
                    f"The user provided feedback on a previous iteration of the plan.\n"
                    f"Previous Plan: {json.dumps(previous_plan)}\n"
                    f"User Feedback: {feedback}\n"
                    f"Please revise the plan heavily based on this feedback.\n"
                )

            system_prompt += (
                "Return a raw JSON object with this exact structure (no markdown fences): "
                "{\"topic\": \"...\", \"episodes\": [{\"title\": \"...\", \"researchPrompt\": \"...\", \"podcastPrompt\": \"...\"}]}\n\n"
                "CRITICAL: The 'podcastPrompt' is a custom instruction for the podcast hosts. "
                "It should explicitly tell the hosts to reference previous episodes if applicable "
                "(e.g. 'Welcome back! In our last episode, we talked about X. Today we are exploring Y'). "
                "Assume the listener listens to them in order."
            )
            
            payload = {
                "contents": [{"parts": [{"text": system_prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"}
            }
            
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"API Error {resp.status}: {text}")
                data = await resp.json()
                content = data['candidates'][0]['content']['parts'][0]['text']
                
                # Parse JSON
                return json.loads(content)


# =====================================================================
# Main Application Flow
# =====================================================================

async def main():
    console.print(Panel.fit(LOGO, border_style="cyan"))
    
    # 1. Setup API Key
    try:
        from dotenv import load_dotenv, set_key
        load_dotenv()
    except ImportError:
        pass # In case dotenv isn't available

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[yellow]GEMINI_API_KEY is not set in your environment.[/yellow]")
        api_key = await questionary.password("Please enter your Gemini API Key (input is hidden):").ask_async()
        if not api_key:
            console.print("[red]API Key is required. Exiting.[/red]")
            return
        os.environ["GEMINI_API_KEY"] = api_key
        
        try:
            set_key(".env", "GEMINI_API_KEY", api_key)
            console.print("[green]Saved API Key to .env file.[/green]")
        except ImportError:
            pass
        
    worker = LinearWorker(gemini_api_key=api_key)
    
    # 2. Run Diagnostics Automatically
    with console.status("[cyan]Running startup diagnostics & auth checks...[/cyan]", spinner="dots"):
        try:
            await worker.ask_clarifying_questions("test")
            console.print("[green]✓ Gemini API is reachable and authenticated.[/green]")
        except Exception as e:
            console.print(f"[red]❌ Gemini API Error: {e}[/red]")
            console.print("[yellow]Please check your GEMINI_API_KEY and run again.[/yellow]")
            return
            
    # Auth setup using --all-accounts to bind to specific Chrome profile
    # This invokes the notebooklm-py SDK's native browser cookie extractor.
    import subprocess
    import json
    
    console.print("[cyan]Extracting Google accounts from local Chrome...[/cyan]")
    result = subprocess.run(
        [sys.executable, "-m", "notebooklm", "login", "--browser-cookies", "chrome", "--all-accounts"],
        capture_output=True, text=True
    )
    
    # Parse output to find available Chrome profiles
    import re
    accounts = []
    for line in result.stdout.splitlines():
        # Looks for lines like: ✓ k-horned  →  k.horned@gmail.com
        m = re.search(r"✓\s+(?P<profile>\S+)\s+→\s+(?P<email>\S+)", line)
        if m:
            accounts.append(m.groupdict())
            
    if not accounts:
        console.print("[red]❌ No signed-in Google accounts found in Chrome. Please open Chrome, visit notebook.google.com, and log in.[/red]")
        return
        
    config = {}
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
        except:
            pass
            
    selected_profile = config.get("selected_profile")
    
    # Check if selected_profile is still valid
    if selected_profile and any(a["profile"] == selected_profile for a in accounts):
        console.print(f"[green]✓ NotebookLM is authenticated using saved account profile: {selected_profile}[/green]")
        worker.profile_name = selected_profile
    else:
        if len(accounts) == 1:
            selected_profile = accounts[0]["profile"]
            email = accounts[0]["email"]
            console.print(f"[green]✓ Automatically selected single NotebookLM account: {email}[/green]")
        else:
            choices = [f"{a['email']} (Profile: {a['profile']})" for a in accounts]
            choice = await questionary.select(
                "Multiple Google accounts found. Which account should be used for NotebookLM?",
                choices=choices
            ).ask_async()
            if not choice:
                return
            # Extract profile name
            selected_profile = choice.split("(Profile: ")[1].rstrip(")")
            console.print(f"[green]✓ Selected NotebookLM account: {choice.split(' ')[0]}[/green]")
            
        config["selected_profile"] = selected_profile
        with open("config.json", "w") as f:
            json.dump(config, f)
        worker.profile_name = selected_profile
    console.print("\n")
    
    while True:
        # 3. Main Menu
        choice = await questionary.select(
            "What would you like to do?",
            choices=[
                "🪄  Generate a new Podcast Plan from a Topic",
                "🚀  Execute an existing Plan (JSON)",
                "❌  Exit"
            ]
        ).ask_async()
        
        if not choice or choice.startswith("❌"):
            console.print("[green]Goodbye![/green]")
            break
            
        elif choice.startswith("🪄"):
            topic = await questionary.text("Enter the overarching topic for the podcast (e.g., 'Quantum Physics'):").ask_async()
            if not topic:
                continue
                
            with console.status("[cyan]Analyzing topic and brainstorming clarifying questions...[/cyan]"):
                questions = await worker.ask_clarifying_questions(topic)
                
            answers = []
            if questions:
                console.print("\n[yellow]Gemini has a few follow-up questions to help tailor the podcast.[/yellow] (Press Enter to skip any question)")
                for q in questions[:3]:
                    ans = await questionary.text(f"❓ {q}").ask_async()
                    if ans and ans.strip():
                        answers.append(f"Q: {q}\nA: {ans}")
                        
            context_str = "\n".join(answers)
            current_plan = None
            feedback = ""
            
            while True:
                with console.status(f"[cyan]Drafting podcast curriculum for '{topic}'...[/cyan]", spinner="dots"):
                    try:
                        plan = await worker.generate_plan(topic, context=context_str, previous_plan=current_plan, feedback=feedback)
                        current_plan = plan
                        feedback = "" # reset feedback after successful generation
                    except Exception as e:
                        console.print(f"[red]Failed to generate plan: {e}[/red]")
                        break
                        
                console.print(f"\n[bold green]Generated Plan for: {plan.get('topic')}[/bold green]")
                
                # Make the table more readable
                table = Table(show_header=True, header_style="bold magenta", show_lines=True)
                table.add_column("Episode", style="dim", ratio=1)
                table.add_column("Title", style="cyan", ratio=2)
                table.add_column("Research Prompt", style="white", ratio=4)
                
                episodes = plan.get('episodes', [])
                for idx, ep in enumerate(episodes):
                    table.add_row(f"Ep {idx+1}", ep.get('title', ''), ep.get('researchPrompt', ''))
                    
                console.print(table)
                console.print("\n")
                
                action = await questionary.select(
                    "What would you like to do with this plan?",
                    choices=[
                        "🚀  Accept and Execute",
                        "✍️   Provide Feedback and Regenerate",
                        "❌  Cancel"
                    ]
                ).ask_async()
                
                if action and action.startswith("🚀"):
                    plan_file = f"{worker.sanitize_filename(plan.get('topic', 'plan')).replace(' ', '_')}.json"
                    with open(plan_file, 'w') as f:
                        json.dump(plan, f, indent=2)
                    console.print(f"[green]Saved plan to {plan_file}[/green]")
                    await execute_plan(worker, plan)
                    break
                elif action and action.startswith("✍️"):
                    feedback = await questionary.text("What should be changed? (e.g., 'Make it more technical', 'Combine ep 1 & 2'):").ask_async()
                    if not feedback:
                        console.print("[yellow]No feedback provided, regenerating...[/yellow]")
                else:
                    console.print("[yellow]Plan discarded.[/yellow]\n")
                    break
                
        elif choice.startswith("🚀"):
            json_files = [f for f in os.listdir('.') if f.endswith('.json') and f not in ('config.json', 'running_tasks.json', 'package.json', 'package-lock.json')]
            if not json_files:
                console.print("[yellow]No JSON plan files found in the current directory.[/yellow]")
                continue
                
            plan_file = await questionary.select("Select a plan to execute:", choices=json_files).ask_async()
            if plan_file:
                try:
                    with open(plan_file, 'r') as f:
                        plan = json.load(f)
                    await execute_plan(worker, plan)
                except Exception as e:
                    console.print(f"[red]Error loading plan: {e}[/red]")
                    


# =====================================================================
# Background Task Polling
# =====================================================================

async def poll_running_tasks(table: Table, live: Live, profile_name: str = None):
    """
    Background loop that continuously checks the NotebookLM API for the status
    of our running audio generation tasks. 
    Downloads the audio to `podcast_audio/` once generation is complete.
    """
    from notebooklm import NotebookLMClient
    try:
        async with NotebookLMClient.from_storage(profile=profile_name) as client:
            while True:
                tasks = load_running_tasks()
                
                # We yield a new table entirely to correctly update the Rich Live display
                new_table = Table(title="[bold cyan]Audio Generation Status[/bold cyan] (Can take up to 1hr per lesson) ⏳", show_header=True, header_style="bold magenta")
                new_table.add_column("Episode", style="cyan")
                new_table.add_column("Status", style="yellow")
                new_table.add_column("URL", style="blue")
                
                if not tasks:
                    new_table.add_row("No active tasks.", "-", "-")
                
                for t in tasks:
                    status = await client.artifacts.poll_status(t["notebook_id"], t["task_id"])
                    
                    status_text = "Pending"
                    if status.is_in_progress:
                        status_text = "In Progress"
                    elif status.is_complete:
                        status_text = "[green]Complete[/green]"
                        
                        # Automatically download the generated mp3
                        os.makedirs("podcast_audio", exist_ok=True)
                        import re
                        safe_title = re.sub(r'[^a-zA-Z0-9_\- ]', '', t["title"]).strip().replace(" ", "_")
                        output_path = f"podcast_audio/{safe_title}.mp3"
                        
                        try:
                            await client.artifacts.download_audio(t["notebook_id"], output_path)
                            status_text = f"[green]Saved to {output_path}[/green]"
                        except Exception as e:
                            status_text = f"[red]Complete, but download failed: {e}[/red]"
                            
                    elif status.is_failed:
                        status_text = f"[red]Failed: {status.error}[/red]"
                    elif status.is_removed:
                        status_text = "[red]Removed[/red]"
                    elif status.is_not_found:
                        status_text = "[yellow]Initializing / Not Found[/yellow]"
                        
                    url = f"https://notebook.google.com/notebook/{t['notebook_id']}"
                    new_table.add_row(t["title"], status_text, url)
                    
                    if status.is_complete or status.is_failed or status.is_removed:
                        remove_running_task(t["task_id"])
                        
                live.update(new_table)
                await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        from rich.console import Console
        Console().print(f"[red]Poller Error: {e}[/red]")


async def execute_plan(worker: LinearWorker, plan: dict):
    """
    Executes a podcast plan by orchestrating research generation and NotebookLM uploading
    for each episode sequentially. Spawns a background poller to monitor progress.
    """
    topic = plan.get('topic', 'Unknown Topic')
    episodes = plan.get('episodes', [])
    
    console.print(f"\n[bold blue]Starting Podcast Generation for: {topic}[/bold blue]")
    
    table = Table(title="Audio Generation Status", show_header=True, header_style="bold magenta")
    table.add_column("Episode", style="cyan")
    table.add_column("Status", style="yellow")
    table.add_column("URL", style="blue")
    
    with Live(table, console=console, refresh_per_second=2) as live:
        poller_task = asyncio.create_task(poll_running_tasks(table, live, worker.profile_name))
        
        for idx, ep in enumerate(episodes):
            ep_num = idx + 1
            title = ep['title']
            
            project_name = f"[Ep {ep_num}] {topic} - {title}"
            base_filename = worker.sanitize_filename(project_name).replace(" ", "_")
            
            console.print(f"\n[bold yellow]--- {project_name} ---[/bold yellow]")
            
            try:
                # 1. Generate Research
                with console.status("[cyan]Deep Researching via Gemini...[/cyan]", spinner="bouncingBar"):
                    research_path = await worker.run_deep_research(ep['researchPrompt'], project_name, base_filename)
                console.print(f"[green]✓[/green] Research saved to: {research_path}")
                
                # 2. Upload to NotebookLM
                with console.status("[cyan]Uploading to NotebookLM...[/cyan]", spinner="bouncingBar"):
                    audio_data = await worker.run_notebooklm(
                        project_name=project_name,
                        research_path=research_path,
                        podcast_prompt=ep.get('podcastPrompt', '')
                    )
                
                # 3. Track state
                add_running_task(audio_data["notebook_id"], audio_data["task_id"], project_name)
                
                console.print(f"[bold green]✓ Successfully submitted episode {ep_num}![/bold green] Output: {audio_data['url']}")
                
            except asyncio.CancelledError:
                poller_task.cancel()
                raise
            except Exception as e:
                err_msg = str(e) if str(e) else repr(e)
                console.print(f"[bold red]Error executing episode {ep_num}:[/bold red] {err_msg}")
        
        # After loop, ask to detach or wait
        live.stop()
        
        choice = await questionary.select(
            "\nAll episodes submitted! (Generation can take up to 1hr per lesson)",
            choices=[
                "⏳  Keep monitoring here (Auto-downloads when done)",
                "🏃  Detach (Exit now, run '-c' later to resume monitoring/downloading)",
                "❌  Clear Tasks & Quit"
            ]
        ).ask_async()
        
        if choice and choice.startswith("🏃"):
            console.print("[green]Detached! Run `python podcast_cli.py -c` to check progress later.[/green]")
            poller_task.cancel()
            sys.exit(0)
            
        elif choice and choice.startswith("❌"):
            console.print("[yellow]Clearing running tasks and exiting.[/yellow]")
            save_running_tasks([])
            poller_task.cancel()
            sys.exit(0)
            
        elif choice and choice.startswith("⏳"):
            console.print("[cyan]Resuming live tracking... (Press Ctrl+C to detach)[/cyan]")
            try:
                with Live(table, console=console, refresh_per_second=2) as live2:
                    while True:
                        tasks = load_running_tasks()
                        if not tasks:
                            console.print("[bold green]All audio generations are complete![/bold green]")
                            break
                        await asyncio.sleep(2)
            except KeyboardInterrupt:
                console.print("\n[green]Detached! Run `python podcast_cli.py -c` to check progress later.[/green]")
                sys.exit(0)
            finally:
                poller_task.cancel()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NotebookLM Podcast Orchestrator")
    parser.add_argument("-c", "--check", action="store_true", help="Check progress of detached audio generation tasks.")
    args = parser.parse_args()
    
    # Run the detached tracking mode
    if args.check:
        async def check_progress():
            tasks = load_running_tasks()
            if not tasks:
                console.print("[bold green]No active audio generations found![/bold green]")
                return
                
            console.print("[cyan]Resuming live tracking... (Press Ctrl+C to detach)[/cyan]")
            table = Table(title="Audio Generation Status", show_header=True, header_style="bold magenta")
            table.add_column("Episode", style="cyan")
            table.add_column("Status", style="yellow")
            table.add_column("URL", style="blue")
            
            with Live(table, console=console, refresh_per_second=2) as live:
                profile_name = None
                if os.path.exists("config.json"):
                    try:
                        with open("config.json", "r") as f:
                            config = json.load(f)
                        profile_name = config.get("selected_profile")
                    except:
                        pass
                
                poller_task = asyncio.create_task(poll_running_tasks(table, live, profile_name))
                try:
                    while True:
                        current_tasks = load_running_tasks()
                        if not current_tasks:
                            console.print("\n[bold green]All audio generations are complete![/bold green]")
                            break
                        await asyncio.sleep(2)
                except KeyboardInterrupt:
                    console.print("\n[green]Detached![/green]")
                finally:
                    poller_task.cancel()
                    
        asyncio.run(check_progress())
    else:
        # Run the standard main UI
        asyncio.run(main())
