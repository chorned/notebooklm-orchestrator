"""
NotebookLM UI Automator

This module uses `playwright` to automate the NotebookLM UI in headless mode.
It acts as the delivery mechanism for uploading AI-generated research into a NotebookLM project.

We use Playwright because it handles SPA (Single Page Application) navigations 
gracefully, without dropping the CDP WebSocket connection.
"""
import asyncio
import os
from playwright.async_api import async_playwright

async def upload_research(episode_title: str, file_path: str):
    """
    Uploads the generated research markdown file to a new NotebookLM project.
    
    Args:
        episode_title: The title to give the new NotebookLM project.
        file_path: The absolute path to the Markdown file to upload.
    """
    print(f"--- Processing: {episode_title} ---")
    print("Launching Playwright (Headless)...")
    import cookie_extractor
    
    print("Extracting NotebookLM session cookies...")
    if not cookie_extractor.refresh_notebooklm_cookies("storage_state.json"):
        print("Failed to extract cookies. Make sure you are logged into Google Chrome.")
        return
        
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            storage_state="storage_state.json",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        )
        
        try:
            page = await context.new_page()
            
            # 1. Start at home
            await page.goto("https://notebooklm.google.com/")
            await page.wait_for_timeout(5000)
            
            # Check if we are on the login page due to bot detection
            if "accounts.google.com" in page.url:
                print("WARNING: Google Bot Detection triggered. The headless browser was redirected to the login page.")
                print("If this persists, you may need to run fetch_cookies.py again or run the browser visibly.")
                return
            
            # 2. Click "Create new notebook"
            print("Clicking 'Create new notebook'...")
            await page.evaluate("""
                (() => {
                    const btns = Array.from(document.querySelectorAll('button, div[role="button"]'));
                    const btn = btns.find(b => (b.innerText || '').toLowerCase().includes('create new'));
                    if (btn) btn.click();
                })();
            """)
            await page.wait_for_timeout(5000)
            
            # 3. Enter Title if prompt appears
            print("Waiting for title input...")
            await page.evaluate(f"""
                (() => {{
                    const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
                    const input = inputs[0];
                    if (input) {{
                        input.value = '{episode_title}';
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                }})();
            """)
                
            await page.wait_for_timeout(1000)
            
            # 4. Upload File
            print("Uploading file...")
            # We must use Playwright's native set_input_files for file inputs
            file_input = page.locator('input[type="file"]')
            if await file_input.count() > 0:
                await file_input.first.set_input_files(file_path)
                print("File sent to upload.")
            else:
                print("Failed to find file input element.")
                    
            await page.wait_for_timeout(10000)
            
            # 5. Verification
            if "/notebook/" in page.url:
                print(f"Success! Project created at: {page.url}")
            else:
                print("Notebook creation check (URL update) did not complete.")
                
        finally:
            await browser.close()

async def automate():
    """
    Main entry point for the automation script. 
    It checks the `research_output/` directory for any Markdown files
    and attempts to upload all Markdown files found.
    """
    RESEARCH_DIR = "/Volumes/hermes/projects/podcast-bot/research_output/"
    if not os.path.exists(RESEARCH_DIR):
        print(f"Directory {RESEARCH_DIR} not found.")
        return
        
    files = [f for f in os.listdir(RESEARCH_DIR) if f.endswith(".md")]
    
    for file in files:
        file_path = os.path.join(RESEARCH_DIR, file)
        # Use the filename (without extension) as the NotebookLM episode title
        episode_title = os.path.splitext(file)[0].replace("_", " ").title()
        
        await upload_research(episode_title, file_path)
        
if __name__ == "__main__":
    asyncio.run(automate())
