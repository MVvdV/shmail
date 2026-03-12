from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Label(BaseModel):
    """Represents a Gmail label with its metadata."""

    id: str
    name: str
    type: str


class Email(BaseModel):
    """Represents a single email message with its headers and content."""

    id: str
    thread_id: str
    subject: str
    sender: str
    sender_address: Optional[str] = None
    recipient_to: Optional[str] = None
    recipient_to_addresses: Optional[str] = None
    recipient_cc: Optional[str] = None
    recipient_cc_addresses: Optional[str] = None
    recipient_bcc: Optional[str] = None
    recipient_bcc_addresses: Optional[str] = None
    snippet: str
    body: Optional[str] = None
    timestamp: datetime
    is_read: bool = False
    has_attachments: bool = False
    labels: List[Label] = Field(default_factory=list)


class Thread(BaseModel):
    """Represents a collection of related email messages."""

    id: str
    messages: List[Email] = Field(default_factory=list)

    @property
    def latest_message(self) -> Optional[Email]:
        """Returns the most recently received message in the thread."""
        if not self.messages:
            return None
        return max(self.messages, key=lambda m: m.timestamp)


class Contact(BaseModel):
    """Represents a registered contact identity."""

    email: str
    name: Optional[str] = None
    timestamp: datetime


class ParsedMessage(BaseModel):
    """Container for a parsed email and its discovered contacts."""

    email: Email
    contacts: List[Contact]


class HistoryMessage(BaseModel):
    """A minimal message representation for history synchronization."""

    id: str
    threadId: Optional[str] = None
    labelIds: List[str] = Field(default_factory=list)


class HistoryEvent(BaseModel):
    """Represents an atomic change event in the Gmail history."""

    message: HistoryMessage
    labelIds: List[str] = Field(default_factory=list)


class History(BaseModel):
    """A record of multiple synchronization events."""

    id: str
    messagesAdded: List[HistoryEvent] = Field(default_factory=list)
    labelsAdded: List[HistoryEvent] = Field(default_factory=list)
    labelsRemoved: List[HistoryEvent] = Field(default_factory=list)
    messagesDeleted: List[HistoryEvent] = Field(default_factory=list)


class GmailHistoryResponse(BaseModel):
    """Response model for the Gmail History API."""

    history: List[History] = Field(default_factory=list)
    historyId: str
    nextPageToken: Optional[str] = None
