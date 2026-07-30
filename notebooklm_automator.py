"""
NotebookLM UI Automator

This module uses `nodriver` (a stealth Chrome driver framework) to automate the NotebookLM UI.
It acts as the delivery mechanism for uploading AI-generated research into a NotebookLM project.

WARNING (Architectural Note on SPAs and nodriver): 
NotebookLM uses a Single Page Application (SPA) architecture that heavily manipulates the DOM.
Specifically, when clicking "Create new notebook", NotebookLM triggers a navigation event
that forces the Chrome DevTools Protocol (CDP) WebSocket to disconnect.

Currently, `nodriver` struggles to automatically re-attach to the new CDP target after this 
navigation (resulting in `websockets.exceptions.ConnectionClosedError`). 
This script includes a fallback try-catch block attempting to re-fetch the active tab, 
but if issues persist, future maintainers should consider a "Split Engine" approach:
1. Use `nodriver` to launch Chrome on a debug port (`--remote-debugging-port=9222`).
2. Use a distinct CDP library (like Playwright over CDP, or `browser-use`) to attach to 
   the port and perform the DOM clicks, as they handle target reconnections better.
"""
import asyncio
import nodriver as uc
import os

async def upload_research(episode_title: str, file_path: str):
    """
    Automates the process of creating a new NotebookLM project and uploading a research document.
    
    Args:
        episode_title: The title to give the new NotebookLM project.
        file_path: The absolute path to the Markdown file to upload.
    """
    print("Launching nodriver...")
    browser = await uc.start(
        browser_executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        user_data_dir=os.path.abspath("chrome_profile"),
        headless=False # Visible for debugging and manual auth if needed
    )
    
    try:
        print(f"--- Processing: {episode_title} ---")
        
        # 1. Start at home
        page = await browser.get("https://notebooklm.google.com/")
        await asyncio.sleep(5)
        
        # 2. Click "Create new notebook"
        # We use a precise querySelector block to bypass shadow dom complexity
        print("Clicking 'Create new notebook'...")
        await page.evaluate("""
            const btns = Array.from(document.querySelectorAll('button'));
            const btn = btns.find(b => (b.innerText || '').toLowerCase().includes('create new'));
            if (btn) btn.click();
        """)
        await asyncio.sleep(5)
        
        # Re-fetch the page object in case the navigation closed the previous websocket target
        page = browser.main_tab
        
        # 3. Enter Title if prompt appears
        print("Waiting for title input...")
        await asyncio.sleep(2)
        try:
            # We use Javascript evaluation directly to dispatch input events,
            # which is faster and more reliable than raw CDP keystrokes in React apps.
            await page.evaluate(f"""
                const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
                const input = inputs[0];
                if (input) {{
                    input.value = '{episode_title}';
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)
        except Exception as e:
            # Catch the CDP ConnectionClosedError and attempt to salvage the session
            print(f"Connection dropped (SPA Navigation), reconnecting to tab: {{e}}")
            page = browser.tabs[0]
            await asyncio.sleep(2)
            await page.evaluate(f"""
                const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
                const input = inputs[0];
                if (input) {{
                    input.value = '{episode_title}';
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)
            
        await asyncio.sleep(1)
        
        # 4. Upload File
        print("Uploading file...")
        # Evaluate doesn't work for file uploads due to security restrictions.
        # We must use native CDP/nodriver methods to send the file path to the input element.
        try:
            upload_el = await page.select('input[type="file"]')
            if upload_el:
                await upload_el.send_keys(file_path)
                print("File sent to upload.")
        except Exception as e:
            print(f"Failed to find upload element: {{e}}")
            
        await asyncio.sleep(10)
        
        # 5. Verification
        if "/notebook/" in page.url:
            print(f"Success! Project created at: {{page.url}}")
        else:
            print("Notebook creation check (URL update) did not complete.")
    finally:
        browser.stop()

async def automate():
    """
    Local testing function that scans the research_output directory 
    and attempts to upload all Markdown files found.
    """
    RESEARCH_DIR = "/Volumes/hermes/projects/podcast-bot/research_output/"
    files = [f for f in os.listdir(RESEARCH_DIR) if f.endswith(".md")]
    
    for file in files:
        file_path = os.path.join(RESEARCH_DIR, file)
        episode_title = file.replace(".md", "")
        await upload_research(episode_title, file_path)

if __name__ == "__main__":
    asyncio.run(automate())
