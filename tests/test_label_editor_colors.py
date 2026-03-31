from shmail.screens.label_editor import GMAIL_ALLOWED_COLOR_VALUES, SWATCHES_PER_ROW


def test_label_editor_uses_validated_gmail_custom_palette():
    """Ensure the matrix picker exposes the validated 64-color custom grid."""
    assert len(GMAIL_ALLOWED_COLOR_VALUES) == 64
    assert all(color == color.lower() for color in GMAIL_ALLOWED_COLOR_VALUES)
    assert "#285bac" in GMAIL_ALLOWED_COLOR_VALUES
    assert "#f7a7c0" in GMAIL_ALLOWED_COLOR_VALUES
    assert "#094228" not in GMAIL_ALLOWED_COLOR_VALUES


def test_label_editor_preserves_gmail_web_color_order():
    """Ensure the picker follows Gmail web's custom-grid order."""
    assert SWATCHES_PER_ROW == 8
    assert GMAIL_ALLOWED_COLOR_VALUES[:8] == [
        "#000000",
        "#434343",
        "#666666",
        "#999999",
        "#cccccc",
        "#efefef",
        "#f3f3f3",
        "#ffffff",
    ]
    assert GMAIL_ALLOWED_COLOR_VALUES[8:16] == [
        "#f6c5be",
        "#ffe6c7",
        "#fef1d1",
        "#b9e4d0",
        "#c6f3de",
        "#c9daf8",
        "#e4d7f5",
        "#fcdee8",
    ]
    assert GMAIL_ALLOWED_COLOR_VALUES[-8:] == [
        "#fb4c2f",
        "#ffad47",
        "#fad165",
        "#16a766",
        "#43d692",
        "#4a86e8",
        "#a479e2",
        "#f691b3",
    ]
