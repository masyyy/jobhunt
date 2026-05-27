from datetime import datetime

from pydantic import BaseModel


class ConversationResponse(BaseModel):
    conversation_id: str


class ConversationListItem(BaseModel):
    conversation_id: str
    title: str
    updated_at: datetime
