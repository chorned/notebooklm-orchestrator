"""
NotebookLM Automator

This module provides programmatic access to the NotebookLM UI via the `notebooklm-py` SDK.
It is responsible for taking a generated research markdown file and pushing it into
NotebookLM to synthesize an Audio Overview (podcast).
"""
import asyncio
import os
from notebooklm import NotebookLMClient, AudioFormat, AudioLength

async def upload_research(episode_title: str, file_path: str, podcast_prompt: str = "", profile_name: str = None) -> dict:
    """
    Uploads the generated research markdown file to a new NotebookLM project,
    and starts the generation of a podcast Audio Overview.
    
    This function leverages the `notebooklm-py` SDK. It requires that the user 
    has previously authenticated using `notebooklm login --browser-cookies chrome`.
    
    Args:
        episode_title: The title to give the new NotebookLM project.
        file_path: The absolute path to the Markdown file containing the research.
        podcast_prompt: Optional custom instructions for the podcast hosts.
        profile_name: The NotebookLM Google account profile name to use.
        
    Returns:
        A dictionary containing the 'url' to the notebook, 'notebook_id', and 'task_id'.
    """
    print(f"--- Processing: {episode_title} ---")
    
    print("Connecting to NotebookLM via notebooklm-py...")
    try:
        # Connect to NotebookLM using the authenticated session from the specified profile.
        async with NotebookLMClient.from_storage(profile=profile_name) as client:
            
            print("Creating new notebook project...")
            nb = await client.notebooks.create(episode_title)
            
            print(f"Uploading source document: {file_path}")
            # Add the markdown file as a source to the notebook and wait for processing to finish.
            await client.sources.add_file(nb.id, file_path, wait=True)
            
            print("Starting Audio Overview Generation...")
            # Start generating the podcast. We use DEEP_DIVE and LONG to get comprehensive episodes.
            instructions = podcast_prompt if podcast_prompt else None
            status = await client.artifacts.generate_audio(
                nb.id, 
                instructions=instructions,
                audio_format=AudioFormat.DEEP_DIVE,
                audio_length=AudioLength.LONG
            )
            
            # The generation process takes 10-15 minutes on Google's servers.
            # Instead of blocking, we return the task ID so the CLI can poll it asynchronously.
            print(f"Success! Project created at: https://notebook.google.com/notebook/{nb.id}")
            print(f"Audio generation started (Task ID: {status.task_id}).")
            
            return {
                "url": f"https://notebook.google.com/notebook/{nb.id}",
                "notebook_id": nb.id,
                "task_id": status.task_id
            }
            
    except Exception as e:
        print(f"Error during NotebookLM automation: {e}")
        raise e

async def automate():
    """
    Standalone helper function to automatically upload all markdown files in the 
    `research_output` directory and convert them into podcasts.
    """
    RESEARCH_DIR = os.path.join(os.getcwd(), "research_output")
    if not os.path.exists(RESEARCH_DIR):
        print(f"Directory {RESEARCH_DIR} not found.")
        return
        
    files = [f for f in os.listdir(RESEARCH_DIR) if f.endswith(".md")]
    
    for file in files:
        file_path = os.path.join(RESEARCH_DIR, file)
        episode_title = os.path.splitext(file)[0].replace("_", " ").title()
        await upload_research(episode_title, file_path)
        
if __name__ == "__main__":
    asyncio.run(automate())
