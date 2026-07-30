"""
Fetch Cookies Utility

This script uses `nodriver` to launch Chrome using a shared persistent profile
and navigate to NotebookLM to extract session cookies. 

It is useful for bypassing bot-protection on Google domains. Once cookies are 
extracted, they can be passed to headless HTTP clients (e.g. `requests` or `aiohttp`) 
to interact with internal NotebookLM APIs directly without browser overhead.
"""
import asyncio
import nodriver as uc
import os

async def main():
    print("Launching nodriver to fetch cookies...")
    
    # We use a local chrome_profile directory to persist login sessions.
    # This ensures that subsequent runs (or other scripts using this profile)
    # share the same authenticated session.
    profile_dir = os.path.abspath("chrome_profile")
    
    browser = await uc.start(
        browser_executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        user_data_dir=profile_dir,
        headless=True
    )
    
    try:
        # Navigate to a Google property to ensure cookies are loaded from the profile
        page = await browser.get("https://notebooklm.google.com/")
        await asyncio.sleep(3)
        
        # Get cookies from the active session
        print("Extracting cookies...")
        cookies = await browser.cookies.get_all()
        
        if not cookies:
            print("No cookies found. You might need to log in first. Run with headless=False to authenticate.")
        else:
            print(f"Successfully extracted {len(cookies)} cookies.")
            # Print a summary of domains to verify we have Google auth cookies
            domains = set()
            for c in cookies:
                domain = c.domain if hasattr(c, 'domain') else c.get('domain', 'unknown')
                domains.add(domain)
            print(f"Cookies found for domains: {', '.join(domains)}")
                    
        print("\nCookie fetch functionality test complete.")
    finally:
        # Stop the browser to free up the profile lock
        browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
