from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

"""DOMAIN MODELS"""


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


"""GMAIL HISTORY API MODELS for DTO's"""


class HistoryMessage(BaseModel):
    """A minimal message object returned within history events."""

    id: str
    threadId: Optional[str] = None
    # Labels inside here are for 'messagesAdded'
    labelIds: List[str] = Field(default_factory=list)


class HistoryEvent(BaseModel):
    """Represents a single change event (message added, label changed, etc)."""

    message: HistoryMessage
    # Labels inside here are for 'labelsAdded' / 'labelsRemoved'
    labelIds: List[str] = Field(default_factory=list)


class History(BaseModel):
    """A record of multiple events associated with a specific history ID."""

    id: str
    messagesAdded: List[HistoryEvent] = Field(default_factory=list)
    labelsAdded: List[HistoryEvent] = Field(default_factory=list)
    labelsRemoved: List[HistoryEvent] = Field(default_factory=list)
    messagesDeleted: List[HistoryEvent] = Field(default_factory=list)


class GmailHistoryResponse(BaseModel):
    history: List[History] = Field(default_factory=list)
    historyId: str
    nextPageToken: Optional[str] = None
