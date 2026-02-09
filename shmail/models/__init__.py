from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Label(BaseModel):
    id: str
    name: str
    type: str


class Email(BaseModel):
    id: str
    thread_id: str
    subject: str
    sender: str
    snippet: str
    body: Optional[str] = None
    timestamp: datetime
    is_read: bool = False
    has_attachments: bool = False
    labels: List[Label] = Field(default_factory=list)


class Thread(BaseModel):
    id: str
    messages: List[Email] = Field(default_factory=list)

    @property
    def latest_message(self) -> Optional[Email]:
        if not self.messages:
            return None
        return max(self.messages, key=lambda m: m.timestamp)
