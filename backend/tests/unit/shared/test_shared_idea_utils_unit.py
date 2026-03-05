from shared.idea_utils import get_idea_text


def test_get_idea_text_none_or_non_str():
    assert get_idea_text(None) == ""
    assert get_idea_text(123) == ""


def test_get_idea_text_strips():
    assert get_idea_text("  hello \n") == "hello"
