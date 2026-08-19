from pce.context.models import EpistemicRole, Sensitivity, SourceDocument, SourceStatus


def _minimal_doc(**overrides) -> SourceDocument:
    defaults = dict(
        source_type="markdown",
        source_system="local_file",
        source_ref="/approved/root/note.md",
        content_hash="deadbeef",
        parser_version="v1",
        chunking_version="v1",
    )
    defaults.update(overrides)
    return SourceDocument(**defaults)


def test_defaults_fail_closed():
    doc = _minimal_doc()
    assert doc.epistemic_role == EpistemicRole.UNKNOWN
    assert doc.sensitivity == Sensitivity.UNKNOWN
    assert doc.status == SourceStatus.ACTIVE
    assert doc.compartments == []
    assert doc.fiction is False


def test_id_and_ingested_at_are_auto_generated():
    doc_a = _minimal_doc()
    doc_b = _minimal_doc()
    assert doc_a.id != doc_b.id
    assert doc_a.ingested_at is not None


def test_fiction_role_does_not_imply_personal_view():
    doc = _minimal_doc(epistemic_role=EpistemicRole.FICTION, fiction=True)
    assert doc.epistemic_role != EpistemicRole.PERSONAL_VIEW
    assert doc.fiction is True
