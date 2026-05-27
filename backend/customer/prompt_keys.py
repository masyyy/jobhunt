"""Customer-defined seed prompt keys.

Each ``PromptKey`` member identifies a seed prompt under
``backend/prompts/seeds/{key}.md`` that the chat endpoint can inject as the
first user message of a new conversation.

The frontend sends ``prompt_key`` in the ``POST /api/chat`` body on the
kickoff turn of a workshop flow. The backend validates it against
``TOOLBOX_AGENT_CONFIG[toolbox].accepted_prompt_keys`` and loads the
matching markdown file via ``PromptLoader.load_seed``.

Customer forks add entries here, mirror them in
``frontend/src/customer/promptKeys.ts``, and create the corresponding
``backend/prompts/seeds/{key}.md`` file.
``scripts/check_customer_config.py`` validates parity and file existence.
"""

from enum import StrEnum


class PromptKey(StrEnum):
    pass  # Template empty; forks add members such as WEEKLY_REVIEW
