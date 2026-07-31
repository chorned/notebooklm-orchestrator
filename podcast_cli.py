"""
Interactive Podcast Bot CLI

This is the main orchestrator for the Podcast Bot pipeline.
It features an interactive command-line interface using `rich` and `questionary`.

Usage:
    python podcast_cli.py
"""
import asyncio
import json
import os
import re
import aiohttp
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import questionary

console = Console()

LOGO = r"""
 [bold cyan]█▀█ █▀█ █▀▄ █▀▀ █▀▀ █▄░█ █ █░█ █▀[/bold cyan]
 [bold magenta]█▀▀ █▄█ █▄▀ █▄█ ██▄ █░▀█ █ █▄█ ▄█[/bold magenta]
 
 [bold white]PodGenius Orchestrator[/bold white]
"""

class LinearWorker:
    """
    A sequential worker that handles one episode at a time.
    It manages the transition from a research prompt to a saved markdown file,
    and then invokes the NotebookLM automator.
    """
    def __init__(self, gemini_api_key, research_dir="research_output"):
        self.research_dir = research_dir
        self.gemini_api_key = gemini_api_key
        os.makedirs(self.research_dir, exist_ok=True)
        
    def sanitize_filename(self, title: str) -> str:
        """Converts an episode title into a safe file path string."""
        clean = re.sub(r'[^a-zA-Z0-9_\-]', '_', title)[:50]
        return f"{clean}.md"

    async def run_deep_research(self, prompt: str, title: str) -> str:
        """Calls the Gemini REST API directly to perform deep research."""
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
        filename = self.sanitize_filename(title)
        filepath = os.path.join(self.research_dir, filename)
        
        with open(filepath, 'w') as f:
            f.write(f"# Research: {title}\n\n{research_content}")
            
        return filepath

    async def run_notebooklm(self, project_name: str, research_path: str, podcast_prompt: str) -> str:
        """Invokes the NotebookLM UI Automator script."""
        sys.path.append(os.path.abspath('venv/lib/python3.11/site-packages'))
        # Import dynamically to ensure it runs inside the correct venv context
        import notebooklm_automator
        await notebooklm_automator.upload_research(project_name, research_path)
        return research_path

    async def ask_clarifying_questions(self, topic: str) -> list[str]:
        """Uses Gemini to brainstorm follow-up questions before creating a plan."""
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
        """Uses Gemini to dynamically brainstorm a podcast curriculum as JSON."""
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
                "{\"topic\": \"...\", \"episodes\": [{\"title\": \"...\", \"researchPrompt\": \"...\"}]}"
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

async def main():
    console.print(Panel.fit(LOGO, border_style="cyan"))
    
    # 1. Setup API Key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[yellow]GEMINI_API_KEY is not set in your environment.[/yellow]")
        api_key = await questionary.password("Please enter your Gemini API Key (input is hidden):").ask_async()
        if not api_key:
            console.print("[red]API Key is required. Exiting.[/red]")
            return
        os.environ["GEMINI_API_KEY"] = api_key
        
    worker = LinearWorker(gemini_api_key=api_key)
    
    while True:
        # 2. Main Menu
        choice = await questionary.select(
            "What would you like to do?",
            choices=[
                "🪄  Generate a new Podcast Plan from a Topic",
                "🚀  Execute an existing Plan (JSON)",
                "🍪  Fetch Google Cookies for NotebookLM",
                "❌  Exit"
            ]
        ).ask_async()
        
        if not choice or choice.startswith("❌"):
            console.print("[green]Goodbye![/green]")
            break
            
        elif choice.startswith("🍪"):
            console.print("[cyan]Extracting Google Cookies from local Chrome...[/cyan]")
            import cookie_extractor
            success = cookie_extractor.refresh_notebooklm_cookies("storage_state.json")
            if success:
                console.print("[green]✓ Successfully extracted and saved NotebookLM cookies![/green]")
            else:
                console.print("[red]❌ Failed to extract cookies. Make sure you are logged into Google Chrome.[/red]")
            console.print("\n")
            
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
                
                # Make the table more readable with show_lines=True and ratios
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
                    plan_file = worker.sanitize_filename(plan.get('topic', 'plan')).replace(".md", ".json")
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
            json_files = [f for f in os.listdir('.') if f.endswith('.json')]
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
                    

async def execute_plan(worker: LinearWorker, plan: dict):
    topic = plan.get('topic', 'Unknown Topic')
    episodes = plan.get('episodes', [])
    
    console.print(f"\n[bold blue]Starting Podcast Generation for: {topic}[/bold blue]")
    
    for idx, ep in enumerate(episodes):
        ep_num = idx + 1
        title = ep['title']
        
        console.print(f"\n[bold yellow]--- Episode {ep_num}/{len(episodes)}: {title} ---[/bold yellow]")
        
        try:
            with console.status("[cyan]Deep Researching via Gemini...[/cyan]", spinner="bouncingBar"):
                research_path = await worker.run_deep_research(ep['researchPrompt'], title)
            console.print(f"[green]✓[/green] Research saved to: {research_path}")
            
            with console.status("[cyan]Uploading to NotebookLM (Browser launching...)[/cyan]", spinner="bouncingBar"):
                audio_path = await worker.run_notebooklm(
                    project_name=f"{topic} - {title}",
                    research_path=research_path,
                    podcast_prompt=ep.get('podcastPrompt', '')
                )
            
            console.print(f"[bold green]✓ Successfully processed episode {ep_num}![/bold green] Output: {audio_path}")
            
        except asyncio.CancelledError:
            raise
        except Exception as e:
            err_msg = str(e) if str(e) else repr(e)
            console.print(f"[bold red]Error executing episode {ep_num}:[/bold red] {err_msg}")

if __name__ == "__main__":
    asyncio.run(main())
