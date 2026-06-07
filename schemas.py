"""
Pydantic schemas for the podcast_engine curriculum pipeline.

Defines the data structures for lesson plans and individual lesson
definitions, including status tracking and NotebookLM artifact references.
"""

from pydantic import BaseModel, Field


class LessonDefinition(BaseModel):
    """A single lesson within a curriculum, tracking its research and audio generation state."""

    lesson_title: str
    research_prompt: str
    podcast_prompt: str
    status: str = Field(default="pending", description="Tracks completion status of the audio.")
    research_file: str | None = Field(default=None, description="Local path to the generated Gemini research text.")
    notebook_id: str | None = Field(default=None, description="Persistent storage for the Google Notebook ID.")
    task_id: str | None = Field(default=None, description="Persistent storage for the Audio Task ID.")


class LessonPlan(BaseModel):
    """A complete curriculum series containing an ordered list of lessons."""

    series_title: str
    lessons: list[LessonDefinition]
