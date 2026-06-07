"""
podcast_engine — Autonomous podcast generation pipeline.

Uses Gemini 3.1 Pro for deep research and NotebookLM SDK
for long-form audio generation with crash-recovery state management.
"""

from .schemas import LessonDefinition, LessonPlan
from .cookie_extractor import refresh_notebooklm_cookies
from .podcast_worker import main_workflow

__all__ = [
    "LessonDefinition",
    "LessonPlan",
    "refresh_notebooklm_cookies",
    "main_workflow",
]
