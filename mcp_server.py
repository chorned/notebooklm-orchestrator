"""
NotebookLM Orchestrator MCP Server

This module provides a Model Context Protocol (MCP) server that exposes the Podcast Bot's 
capabilities to AI agents. Agents can use these tools to autonomously generate podcast
lesson plans and execute them without human intervention.
"""
import asyncio
import json
import os
from mcp.server.fastmcp import FastMCP
from podcast_cli import LinearWorker, execute_plan, add_running_task

# Initialize the FastMCP server
mcp = FastMCP("NotebookLM Orchestrator")

def _get_worker() -> LinearWorker:
    """
    Helper function to initialize the LinearWorker with the Gemini API key 
    and the selected NotebookLM profile from config.json.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")
        
    config = {}
    if os.path.exists("config.json"):
        with open("config.json", "r") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                pass
                
    profile_name = config.get("selected_profile")
    if not profile_name:
        raise ValueError("No selected_profile found in config.json. Please run `python podcast_cli.py` first to authenticate.")
        
    return LinearWorker(gemini_api_key=api_key, profile_name=profile_name)


@mcp.tool()
async def generate_podcast_plan(topic: str) -> str:
    """
    Generates a structured lesson plan for a podcast based on a topic.
    Returns the JSON plan and saves it to a file.
    
    Args:
        topic: The topic of the podcast series.
    """
    try:
        worker = _get_worker()
    except Exception as e:
        return f"Error: {e}"
        
    try:
        # Generate the plan directly from the topic (skips interactive questions)
        plan = await worker.generate_plan(topic)
        
        # Save the plan to a local JSON file
        plan_file = worker.sanitize_filename(plan.get('topic', 'plan')).replace(".md", ".json")
        with open(plan_file, 'w') as f:
            json.dump(plan, f, indent=2)
            
        return f"Plan generated and saved to {plan_file}. Contents: {json.dumps(plan, indent=2)}"
    except Exception as e:
        return f"Error generating plan: {e}"


@mcp.tool()
async def execute_podcast_plan(plan_file: str) -> str:
    """
    Executes a saved JSON podcast plan and generates audio overviews for each episode.
    
    Args:
        plan_file: The path to the JSON plan file to execute.
    """
    try:
        worker = _get_worker()
    except Exception as e:
        return f"Error: {e}"
        
    if not os.path.exists(plan_file):
        return f"Error: Plan file '{plan_file}' not found."
        
    try:
        with open(plan_file, 'r') as f:
            plan = json.load(f)
            
        # Execute the plan (this will handle research generation and uploading to NotebookLM)
        await execute_plan(worker, plan)
        return "Podcast plan execution completed. Audio is being generated in the background on NotebookLM."
    except Exception as e:
        return f"Error executing plan: {str(e)}"


@mcp.tool()
async def generate_podcast_from_json(topic: str, episodes_json_str: str) -> str:
    """
    Generates a podcast series for a given topic immediately without saving a plan file.
    
    Args:
        topic: The topic of the podcast.
        episodes_json_str: A JSON string containing a list of episode dictionaries. 
                           Each dictionary should have 'title', 'researchPrompt', and optional 'podcastPrompt'.
    """
    try:
        episodes = json.loads(episodes_json_str)
    except json.JSONDecodeError:
        return "Error: episodes_json_str is not valid JSON."
        
    try:
        worker = _get_worker()
    except Exception as e:
        return f"Error: {e}"
        
    results = []
    for idx, ep in enumerate(episodes):
        ep_num = idx + 1
        title = ep['title']
        project_name = f"[Ep {ep_num}] {topic} - {title}"
        base_filename = worker.sanitize_filename(project_name).replace(" ", "_")
        
        try:
            # 1. Generate the research markdown
            research_path = await worker.run_deep_research(ep['researchPrompt'], project_name, base_filename)
            
            # 2. Upload the research to NotebookLM and start the audio generation task
            audio_data = await worker.run_notebooklm(
                project_name=project_name,
                research_path=research_path,
                podcast_prompt=ep.get('podcastPrompt', '')
            )
            
            # 3. Track the task locally so `podcast_cli.py -c` can monitor it later
            add_running_task(audio_data["notebook_id"], audio_data["task_id"], project_name)
            
            results.append(f"Started generation for '{project_name}' (URL: {audio_data['url']})")
        except Exception as e:
            results.append(f"Failed to start '{project_name}': {e}")
            
    return "\n".join(results) + "\n\nUse `python podcast_cli.py -c` to check progress."


if __name__ == "__main__":
    # Start the MCP server loop
    mcp.run()
