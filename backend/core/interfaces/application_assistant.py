from typing import Protocol

from backend.core.entities.job import Job
from pydantic import BaseModel


class ApplicationDraft(BaseModel):
    """A drafted application for one posting: a cover letter the applicant can
    edit and send, plus a short plain explanation of how to actually apply."""

    cover_letter: str
    how_to_apply: str


class ApplicationAssistant(Protocol):
    async def draft(self, job: Job) -> ApplicationDraft:
        """Draft a cover letter and how-to-apply note for a single posting."""
        ...
