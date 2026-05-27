"""LLM-backed application assistant.

A structured PydanticAI call that drafts a cover letter and a short how-to-apply
note for one posting, grounded in the applicant profile and the job details.

Tone matters here: the output is meant to be sent as-is (after light editing),
so the instructions push hard against the usual tells of machine-written text.
No em dashes anywhere.
"""

from __future__ import annotations

import logging

from pydantic_ai import Agent

from backend.core.agents.model_config import MODEL_APPLICATION, get_model
from backend.core.entities.job import Job
from backend.core.interfaces.application_assistant import ApplicationDraft
from backend.core.jobs.profile import APPLICANT_PROFILE

logger = logging.getLogger(__name__)

_INSTRUCTIONS = f"""\
You help one specific job applicant write applications for Finnish job postings.

Applicant profile:
{APPLICANT_PROFILE}

You produce two things:
1. cover_letter: a short cover letter (about 150 to 220 words) written in the
   first person as the applicant, ready for her to read, lightly edit, and
   send. Write it in the language of the job posting (Finnish if the posting is
   in Finnish, otherwise English). Her Finnish is about B1, so when writing in
   Finnish keep it simple, clear, and natural rather than ornate, and it is
   fine for the letter to mention that she is improving her Finnish and is
   fluent in English and Spanish.
2. how_to_apply: short, concrete steps telling her exactly how to apply for
   this specific posting. Read the posting description carefully and surface any
   explicit application instructions it gives. Employers often state specific
   requirements, and you MUST include every one you find, for example:
   - a required email subject line or reference code (quote it exactly),
   - which email address or contact person to send to,
   - documents to attach (CV, portfolio, certificates, work samples),
   - an application deadline or "apply as soon as possible" note,
   - a specific application portal, form, or link to use,
   - any questions the applicant must answer or info she must include.
   Quote required exact strings (subject lines, reference codes) verbatim and
   make clear they must be used as written. If the posting gives no explicit
   instructions, give the normal sensible steps for this kind of job and say so
   plainly. ALWAYS write how_to_apply in English, even when the cover letter is
   in Finnish; keep quoted details (email, subject line, contact name, deadline)
   verbatim, but the surrounding instructions must be in English.

Hard rules for the cover letter:
- Never use em dashes or en dashes. Use commas, periods, or simple sentences.
- Sound like a real, warm, slightly informal young person, not a template.
  Avoid corporate filler and cliches ("I am writing to express my interest",
  "I am a highly motivated team player", "fast-paced environment", "passionate
  about", "leverage my skills", "synergy", "I believe I would be a great fit").
- Be concrete and specific to this job and her real experience (bookstore sales
  at Suomalainen Kirjakauppa, crafts and graphic design). Do not invent
  qualifications she does not have.
- Keep sentences varied and natural. Do not start three sentences in a row the
  same way. No bullet lists inside the cover letter.
- Honest and grounded. It is fine to be enthusiastic without overselling.
"""


def _format_job(job: Job) -> str:
    lines = [f"Title: {job.title}"]
    if job.employer:
        lines.append(f"Employer: {job.employer}")
    if job.location:
        lines.append(f"Location: {job.location}")
    lines.append(f"Posting URL: {job.url}")
    if job.description:
        lines.append(f"Description:\n{job.description}")
    else:
        lines.append("Description: (not available; only the title and employer are known)")
    return "\n".join(lines)


class LlmApplicationAssistant:
    def __init__(self) -> None:
        self._agent: Agent[None, ApplicationDraft] = Agent(
            get_model(MODEL_APPLICATION),
            instructions=_INSTRUCTIONS,
            output_type=ApplicationDraft,
        )

    async def draft(self, job: Job) -> ApplicationDraft:
        result = await self._agent.run(_format_job(job))
        draft = result.output
        # Belt-and-suspenders: strip any dashes the model slipped in anyway.
        return ApplicationDraft(
            cover_letter=_strip_dashes(draft.cover_letter),
            how_to_apply=draft.how_to_apply,
        )


def _strip_dashes(text: str) -> str:
    return text.replace(" — ", ", ").replace(" – ", ", ").replace("—", ", ").replace("–", ", ")
