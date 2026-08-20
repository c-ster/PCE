from pce.retrieval.chunking import chunk_text


def test_empty_text_yields_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_is_a_single_chunk():
    chunks = chunk_text("One paragraph.\n\nAnother paragraph.", max_chars=800)
    assert chunks == ["One paragraph.\n\nAnother paragraph."]


def test_packs_paragraphs_up_to_max_chars():
    paragraphs = [f"Paragraph {i}." * 5 for i in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, max_chars=100)

    assert len(chunks) > 1
    assert all(len(c) <= 100 or "\n\n" not in c for c in chunks)
    # Every paragraph's content survives somewhere in the output.
    joined = "\n\n".join(chunks)
    for paragraph in paragraphs:
        assert paragraph in joined


def test_hard_splits_a_single_oversized_paragraph():
    huge_paragraph = "x" * 2500
    chunks = chunk_text(huge_paragraph, max_chars=1000)
    assert len(chunks) == 3
    assert "".join(chunks) == huge_paragraph
    assert all(len(c) <= 1000 for c in chunks)
