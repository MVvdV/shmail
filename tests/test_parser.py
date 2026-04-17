import base64
import json
from datetime import timezone

import pytest

from shmail.services.parser import MessageParser


@pytest.fixture
def raw_gmail_message():
    """
    A sample raw email structure as returned by the Gmail API.
    """
    mime_content = (
        "From: Alice <alice@example.com>\r\n"
        "To: Bob <bob@example.com>, Charlie <charlie@example.com>\r\n"
        "Cc: Dana <dana@example.com>\r\n"
        "Subject: Hello World\r\n"
        "Date: Mon, 16 Feb 2026 10:00:00 +0000\r\n"
        'Content-Type: multipart/mixed; boundary="boundary"\r\n'
        "\r\n"
        "--boundary\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n'
        "\r\n"
        "This is the body.\r\n"
        "--boundary\r\n"
        "Content-Type: application/pdf\r\n"
        'Content-Disposition: attachment; filename="test.pdf"\r\n'
        "\r\n"
        "dummy-pdf-content\r\n"
        "--boundary--"
    )

    raw_b64 = base64.urlsafe_b64encode(mime_content.encode()).decode()

    return {
        "id": "msg123",
        "threadId": "thread123",
        "raw": raw_b64,
        "snippet": "This is the body.",
        "internalDate": "1739699800000",
    }


def test_parse_gmail_response_basic(raw_gmail_message):
    """
    Verify the high-level parse_gmail_response result.
    """
    result = MessageParser.parse_gmail_response(
        message_id="msg123",
        thread_id="thread123",
        message_data=raw_gmail_message,
        label_ids=["INBOX", "UNREAD"],
    )
    message = result.message
    assert message.id == "msg123"
    assert message.thread_id == "thread123"
    assert message.subject == "Hello World"
    assert message.sender == "Alice"
    assert message.sender_address == "alice@example.com"
    assert (
        message.recipient_to == "Bob <bob@example.com>, Charlie <charlie@example.com>"
    )
    assert message.recipient_cc == "Dana <dana@example.com>"
    assert message.body == "This is the body."
    assert message.body_links is not None
    assert message.body_links == "[]"
    assert message.body_source == "plain"
    assert message.body_content_type == "text/plain"
    assert message.body_charset == "utf-8"
    assert message.body_link_count == 0
    assert message.body_conversion_warnings == "[]"
    assert message.is_read is False
    assert message.has_attachments is True
    assert len(message.attachments) == 1
    assert message.attachments[0].id == "msg123:1"
    assert message.attachments[0].filename == "test.pdf"
    assert message.attachments[0].mime_type == "application/pdf"
    assert len(message.labels) == 2
    assert message.labels[0].id == "INBOX"
    assert result.parse_metadata is not None
    assert result.parse_metadata.body_source == "plain"


def test_extract_contacts_logic(raw_gmail_message):
    """
    Verify that all unique contacts are extracted.
    """
    result = MessageParser.parse_gmail_response(
        message_id="msg123",
        thread_id="thread123",
        message_data=raw_gmail_message,
        label_ids=["INBOX", "UNREAD"],
    )
    assert len(result.contacts) == 4

    contact_emails = [c.email for c in result.contacts]
    assert "alice@example.com" in contact_emails
    assert "bob@example.com" in contact_emails
    assert "charlie@example.com" in contact_emails
    assert "dana@example.com" in contact_emails

    alice = next(c for c in result.contacts if c.email == "alice@example.com")
    assert alice.name == "Alice"
    assert alice.timestamp.tzinfo == timezone.utc


def test_decode_attachment_payload_returns_binary_and_name(raw_gmail_message):
    """Ensure attachment downloads can rehydrate one raw MIME part."""
    payload, filename = MessageParser.decode_attachment_payload(
        raw_gmail_message["raw"], 1
    )

    assert filename == "test.pdf"
    assert payload == b"dummy-pdf-content"


def test_timestamp_normalization():
    """
    Verify that offset-aware and naive dates are handled correctly.
    """
    data = {
        "raw": base64.urlsafe_b64encode(
            b"Date: Mon, 16 Feb 2026 10:00:00 -0500\r\n\r\n"
        ).decode(),
        "internalDate": "0",
    }
    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.timestamp.hour == 15
    assert result.message.timestamp.tzinfo == timezone.utc

    data = {
        "raw": base64.urlsafe_b64encode(b"Date: 16 Feb 2026 10:00:00\r\n\r\n").decode(),
        "internalDate": "0",
    }
    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.timestamp.hour == 10
    assert result.message.timestamp.tzinfo == timezone.utc

    data = {
        "raw": base64.urlsafe_b64encode(b"Date: Invalid Date\r\n\r\n").decode(),
        "internalDate": "1739700000000",
    }
    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.timestamp.hour == 10
    assert result.message.timestamp.tzinfo == timezone.utc


def test_plain_text_linkify_trailing_punctuation():
    """Ensure plain text linkification excludes trailing punctuation."""
    source = "Open https://example.com, mail admin@example.com."
    rendered = MessageParser._to_markdown(source, is_html=False)
    links = MessageParser._extract_links_from_markdown(rendered)
    assert links[0]["label"] == "https://example.com"
    assert links[0]["href"] == "https://example.com"
    assert links[1]["label"] == "admin@example.com"
    assert links[1]["href"] == "mailto:admin@example.com"


def test_extract_body_prefers_html_when_available():
    """Ensure HTML body is preferred over plain text in multipart content."""
    mime_content = (
        'Content-Type: multipart/alternative; boundary="b"\r\n'
        "\r\n"
        "--b\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n'
        "\r\n"
        "Plain body\r\n"
        "--b\r\n"
        'Content-Type: text/html; charset="utf-8"\r\n'
        "\r\n"
        "<p>HTML <a href='https://example.com'>link</a></p>\r\n"
        "--b--"
    )
    data = {
        "raw": base64.urlsafe_b64encode(mime_content.encode()).decode(),
        "internalDate": "1739700000000",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.body_source == "html"
    assert result.message.body_content_type == "text/html"
    assert result.message.body_link_count >= 1
    assert result.message.body is not None
    assert "[link](https://example.com)" in result.message.body
    assert result.message.body_links is not None


def test_html_disallowed_link_scheme_remains_visible_but_non_executable():
    """Ensure non-allowlisted hrefs remain visible but are flagged non-executable."""
    mime_content = (
        'Content-Type: text/html; charset="utf-8"\r\n'
        "\r\n"
        "<p>Click <a href='javascript:alert(1)'>here</a></p>"
    )
    data = {
        "raw": base64.urlsafe_b64encode(mime_content.encode()).decode(),
        "internalDate": "1739700000000",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.body_links is not None
    links = json.loads(result.message.body_links)
    assert links
    assert links[0]["href"] == "javascript:alert(1)"
    assert links[0]["executable"] is False


def test_invalid_internal_date_falls_back_without_crash():
    """Ensure malformed internalDate does not crash parsing."""
    data = {
        "raw": base64.urlsafe_b64encode(b"Date: Invalid Date\r\n\r\n").decode(),
        "internalDate": "not-a-number",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.timestamp.tzinfo == timezone.utc


def test_extract_contacts_deduplicates_addresses_across_headers():
    """Ensure duplicate addresses are emitted only once."""
    mime_content = (
        "From: Alice <alice@example.com>\r\n"
        "To: Alice <alice@example.com>, Bob <bob@example.com>\r\n"
        "Cc: bob@example.com\r\n"
        "Date: Mon, 16 Feb 2026 10:00:00 +0000\r\n"
        "\r\n"
        "Body"
    )
    data = {
        "raw": base64.urlsafe_b64encode(mime_content.encode()).decode(),
        "internalDate": "1739700000000",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    emails = sorted(contact.email for contact in result.contacts)
    assert emails == ["alice@example.com", "bob@example.com"]


def test_html_uppercase_scheme_is_marked_executable():
    """Ensure allowlist checks are case-insensitive."""
    mime_content = (
        'Content-Type: text/html; charset="utf-8"\r\n'
        "\r\n"
        "<p><a href='HTTPS://example.com'>Example</a></p>"
    )
    data = {
        "raw": base64.urlsafe_b64encode(mime_content.encode()).decode(),
        "internalDate": "1739700000000",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    links = json.loads(result.message.body_links or "[]")
    assert links
    assert links[0]["executable"] is True


def test_plain_text_artifact_rows_are_removed_without_losing_content():
    """Ensure plain text is preserved while spacing is normalized."""
    source = (
        "Status update\n"
        "| | |\n"
        "| --- | --- |\n"
        "+----------+\n"
        "Proceed to https://example.com\n"
    )
    normalized = MessageParser._to_markdown(source, is_html=False)
    assert "| --- | --- |" in normalized
    assert "+----------+" in normalized
    assert "Status update" in normalized
    assert "https://example.com" in normalized


def test_cleanup_markdown_artifacts_collapses_blank_lines_and_border_noise():
    """Ensure markdown cleanup keeps readable spacing."""
    noisy = "Header\n\n\n| | |\n──────\nBody\n\n\nFooter\n"
    cleaned = MessageParser._cleanup_markdown_artifacts(noisy, is_html=False)
    assert cleaned == "Header\n\n| | |\n──────\nBody\n\nFooter"


def test_html_cleanup_removes_layout_indentation_that_triggers_code_blocks():
    """Ensure HTML conversion output does not accidentally create code blocks."""
    source = "                 Indented line\n\n  Normal\n"
    cleaned = MessageParser._cleanup_markdown_artifacts(source, is_html=True)
    assert cleaned == "Indented line\n\nNormal"


def test_html_fallback_metadata_and_links_stay_consistent():
    """Ensure HTML fallback keeps metadata and link count aligned with persisted links."""
    mime_content = (
        'Content-Type: multipart/alternative; boundary="b"\r\n'
        "\r\n"
        "--b\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n'
        "\r\n"
        "Plain fallback https://example.com\r\n"
        "--b\r\n"
        'Content-Type: text/html; charset="utf-8"\r\n'
        "\r\n"
        "<html><body>   </body></html>\r\n"
        "--b--"
    )
    data = {
        "raw": base64.urlsafe_b64encode(mime_content.encode()).decode(),
        "internalDate": "1739700000000",
    }

    result = MessageParser.parse_gmail_response("id", "tid", data, [])
    assert result.message.body_source == "plain"
    warnings = json.loads(result.message.body_conversion_warnings or "[]")
    assert warnings
    links = json.loads(result.message.body_links or "[]")
    assert result.message.body_link_count == len(links)
    assert links[0]["href"] == "https://example.com"


def test_markdown_link_extraction_preserves_duplicate_hrefs_in_order():
    """Ensure canonical links mirror markdown interactive token order."""
    body = "[One](https://example.com) [Two](https://example.com)"
    links = MessageParser._extract_links_from_markdown(body)
    assert len(links) == 2
    assert links[0]["label"] == "One"
    assert links[1]["label"] == "Two"
    assert links[0]["href"] == "https://example.com"
    assert links[1]["href"] == "https://example.com"


def test_markdown_link_extraction_sets_kind_for_placeholder_and_mailto():
    """Ensure link kind metadata is populated for lightweight styling hints."""
    body = "[Logo](#) and mail [support](mailto:support@example.com)"
    links = MessageParser._extract_links_from_markdown(body)
    assert links[0]["kind"] == "placeholder"
    assert links[1]["kind"] == "mailto"


def test_markdown_link_extraction_omits_scroll_metadata():
    """Ensure canonical link payload does not include viewer scroll metadata."""
    body = "Intro\n[One](https://example.com)\n[Two](https://example.org)"
    links = MessageParser._extract_links_from_markdown(body)
    assert len(links) == 2
    assert "line_start" not in links[0]
    assert "line_start" not in links[1]


def test_create_markdown_parser_injects_active_link_marker_before_selected_link():
    """Ensure parser factory can inject markers inside the selected link."""
    parser = MessageParser.create_markdown_parser(
        active_link_index=1,
        active_marker_prefix="【↗ ",
        active_marker_suffix=" 】",
    )
    tokens = parser.parse("[One](https://a) [Two](https://b) [Three](https://c)")

    inline_children = []
    for token in tokens:
        inline_children.extend(token.children or [])

    link_positions = [
        index
        for index, child in enumerate(inline_children)
        if child.type == "link_open"
    ]
    assert len(link_positions) == 3
    second_open = link_positions[1]
    assert inline_children[second_open + 1].type == "text"
    assert inline_children[second_open + 1].content == "【↗ "

    second_close = next(
        i
        for i in range(second_open + 1, len(inline_children))
        if inline_children[i].type == "link_close"
    )
    assert inline_children[second_close - 1].type == "text"
    assert inline_children[second_close - 1].content == " 】"


def test_create_markdown_parser_breaks_option_preserves_single_newline_breaks():
    """Ensure compose preview parser can render hard line breaks on single newlines."""
    parser = MessageParser.create_markdown_parser(breaks=True)
    html = parser.render("Line one\nLine two")
    assert "<br" in html


def test_html_quotes_preserve_nested_depth_and_signature_inside_quote():
    """Ensure wrapper + single blockquote normalizes to one quote level."""
    source = (
        "<div>Hello</div>"
        "<div class='gmail_quote'>"
        "<div>On Tue wrote:</div>"
        "<blockquote><div>Earlier line</div><div class='gmail_signature'>-- <br/>Sig</div></blockquote>"
        "</div>"
    )
    rendered = MessageParser._to_markdown(source, is_html=True)
    assert "> On Tue wrote:" in rendered
    assert "> Earlier line" in rendered
    assert "> ---" in rendered
    assert "> Sig" in rendered


def test_html_nested_blockquote_depth_is_preserved():
    """Ensure true nested blockquote structure still increases quote depth."""
    source = (
        "<div class='gmail_quote'>"
        "<blockquote><blockquote><div>Deep line</div></blockquote></blockquote>"
        "</div>"
    )
    rendered = MessageParser._to_markdown(source, is_html=True)
    assert "> > Deep line" in rendered


def test_html_overlapping_quote_wrappers_do_not_stack_depth():
    """Ensure overlapping wrapper classes don't inflate quote depth."""
    source = (
        "<div class='gmail_quote'><div class='yahoo_quoted'>"
        "<blockquote><div>Quoted line</div></blockquote>"
        "</div></div>"
    )
    rendered = MessageParser._to_markdown(source, is_html=True)
    assert "> Quoted line" in rendered
    assert "> > >" not in rendered


def test_html_dynamic_quote_wrapper_detection_handles_unknown_quote_class():
    """Ensure unknown quote-like classes still map to quote wrappers."""
    source = "<div class='acme_quote_wrapper'><div>Vendor quote line</div></div>"
    rendered = MessageParser._to_markdown(source, is_html=True)
    assert "> Vendor quote line" in rendered


def test_html_top_level_signature_inserts_separator():
    """Ensure top-level signatures are separated with horizontal rule."""
    source = (
        "<div>Body line</div>"
        "<div class='gmail_signature'>-- <br/>Sig Name<br/>Role</div>"
    )
    rendered = MessageParser._to_markdown(source, is_html=True)
    assert "Body line" in rendered
    assert "\n---\n" in rendered
    assert "Sig Name" in rendered


def test_html_inline_emphasis_and_code_are_preserved_when_safe():
    """Ensure safe inline emphasis tags map to markdown markers."""
    source = "<p><strong>Bold</strong> and <em>em</em> and <code>x=1</code></p>"
    rendered = MessageParser._to_markdown(source, is_html=True)
    assert "**Bold**" in rendered
    assert "*em*" in rendered
    assert "`x=1`" in rendered


def test_html_pre_blocks_convert_to_fenced_code_blocks():
    """Ensure multiline preformatted HTML sections map to fenced markdown blocks."""
    source = "<pre>line1\nline2</pre>"
    rendered = MessageParser._to_markdown(source, is_html=True)
    assert rendered.startswith("```")
    assert "line1" in rendered
    assert "line2" in rendered
    assert rendered.endswith("```")
