from shared.utils import chunk_string


def test_chunk_string_basic():
    assert list(chunk_string("abcdef", 2)) == ["ab", "cd", "ef"]


def test_chunk_string_single_char_chunks():
    assert list(chunk_string("abc", 1)) == ["a", "b", "c"]
