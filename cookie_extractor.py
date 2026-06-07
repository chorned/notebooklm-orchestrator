"""
cookie_extractor.py — Secure Google cookie extraction for NotebookLM authentication.

SECURITY SCOPE:
    - This module ONLY extracts cookies from Google domains.
    - No banking, email, social media, or third-party cookies are ever touched.
    - The extracted tokens are saved locally and MUST be gitignored.

HOW IT WORKS:
    1. rookiepy reads Chrome's encrypted cookie database (SQLite + OS Keychain)
    2. We filter ONLY for google.com and notebooklm.google.com domains
    3. Cookies are formatted into Playwright storageState JSON for the NotebookLM SDK
"""

import json
import logging
import rookiepy

logger = logging.getLogger(__name__)

# =====================================================================
# SECURITY: Strict domain allowlist. Only Google authentication domains.
# rookiepy will NEVER be called with any other domains.
# If you are auditing this file, this is the ONLY place cookies are read.
# =====================================================================
ALLOWED_COOKIE_DOMAINS = [
    "google.com",
    "notebooklm.google.com",
]


def refresh_notebooklm_cookies(output_path: str = "storage_state.json") -> bool:
    """
    Extracts Google-only session cookies from Chrome and saves them
    in Playwright storageState JSON format for the NotebookLM SDK.

    Args:
        output_path: Where to write the cookie JSON file.

    Returns:
        True if extraction succeeded, False otherwise.
    """
    logger.info("[Auth] Bypassing manual login by securely extracting local NotebookLM session cookies...")
    logger.info("[Auth] Target domains: %s", ", ".join(ALLOWED_COOKIE_DOMAINS))
    logger.info("[Auth] Reading Chrome cookie database via rookiepy (SQLite + OS Keychain decryption)...")

    try:
        # SECURITY: rookiepy is called with ONLY the allowed Google domains.
        # This ensures we never read cookies for banks, email providers, or any other service.
        raw_cookies = rookiepy.chrome(ALLOWED_COOKIE_DOMAINS)

        if not raw_cookies:
            logger.error("[Auth] No Google cookies found in local Chrome database. "
                         "Ensure you are logged into Google in Chrome.")
            return False

        logger.info("[Auth] Found %d raw cookies. Formatting for NotebookLM SDK...", len(raw_cookies))

        formatted_cookies = []
        for c in raw_cookies:
            # Format strictly to match Playwright storageState JSON,
            # which is what the NotebookLM Python SDK expects.
            # rookiepy returns dicts — we use .get() to safely handle missing fields.
            formatted_cookies.append({
                "name": c.get("name", ""),
                "value": c.get("value", ""),
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
                "expires": c.get("expires") if c.get("expires") is not None else -1,
                "httpOnly": c.get("http_only", False),
                "secure": c.get("secure", False),
                "sameSite": c.get("same_site", "Lax") if c.get("same_site") else "Lax"
            })

        # Write the formatted cookies to disk
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"cookies": formatted_cookies}, f, indent=4)

        logger.info("[Auth] ✅ Wrote %d Google session cookies to %s", len(formatted_cookies), output_path)
        logger.info("[Auth] ⚠️  This file contains live session tokens — ensure it is gitignored!")
        return True

    except Exception as e:
        logger.error("[Auth] ❌ Cookie extraction failed: %s", e)
        return False


if __name__ == "__main__":
    # Standalone test — configure logging since we're running directly
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    from pathlib import Path
    AUTH_PATH = Path(__file__).resolve().parent / "storage_state.json"
    refresh_notebooklm_cookies(str(AUTH_PATH))