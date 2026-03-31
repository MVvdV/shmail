from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class Label(BaseModel):
    """Represents a Gmail label with its metadata."""

    id: str
    name: str
    type: str
    label_list_visibility: Optional[str] = None
    message_list_visibility: Optional[str] = None
    background_color: Optional[str] = None
    text_color: Optional[str] = None


class Message(BaseModel):
    """Represents a single message with its headers and content."""

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
    body_links: Optional[str] = None
    body_source: Optional[str] = None
    body_content_type: Optional[str] = None
    body_charset: Optional[str] = None
    body_link_count: int = 0
    body_conversion_warnings: Optional[str] = None
    timestamp: datetime
    is_read: bool = False
    has_attachments: bool = False
    labels: List[Label] = Field(default_factory=list)


class Thread(BaseModel):
    """Represents a collection of related messages."""

    id: str
    messages: List[Message] = Field(default_factory=list)

    @property
    def latest_message(self) -> Optional[Message]:
        """Returns the most recently received message in the thread."""
        if not self.messages:
            return None
        return max(self.messages, key=lambda m: m.timestamp)


class Contact(BaseModel):
    """Represents a registered contact identity."""

    email: str
    name: Optional[str] = None
    timestamp: datetime


class ParseMetadata(BaseModel):
    """Captures body extraction metadata for diagnostics and testing."""

    body_source: str
    selected_content_type: Optional[str] = None
    selected_charset: Optional[str] = None
    link_count: int = 0
    conversion_warnings: List[str] = Field(default_factory=list)


class ParsedMessage(BaseModel):
    """Container for a parsed message and its discovered contacts."""

    message: Message
    contacts: List[Contact]
    parse_metadata: Optional[ParseMetadata] = None


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


class MessageDraft(BaseModel):
    """Represents a locally persisted draft message under composition."""

    id: str
    mode: str = "new"
    to_addresses: str = ""
    cc_addresses: str = ""
    bcc_addresses: str = ""
    subject: str = ""
    body: str = ""
    source_message_id: Optional[str] = None
    source_thread_id: Optional[str] = None
    state: str = "editing"
    queued_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class MutationRecord(BaseModel):
    """Represents one provider-agnostic local mutation intent."""

    id: str
    account_id: str
    provider_key: str
    target_kind: str
    target_id: str
    action_type: str
    payload_json: str = "{}"
    state: str = "pending_local"
    error_message: Optional[str] = None
    retry_count: int = 0
    last_attempt_at: Optional[datetime] = None
    next_attempt_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
