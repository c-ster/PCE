from pce.context.models import Sensitivity, SourceDocument
from pce.policy.engine import AccessContext, eligible_document_ids, evaluate


def _doc(**overrides) -> SourceDocument:
    defaults = dict(
        source_type="markdown",
        source_system="local_file",
        source_ref="/root/a.md",
        content_hash="hash-1",
        parser_version="v1",
        chunking_version="v1",
    )
    defaults.update(overrides)
    return SourceDocument(**defaults)


def test_unknown_sensitivity_fails_closed_by_default():
    doc = _doc()  # sensitivity defaults to UNKNOWN
    decision = evaluate(doc, AccessContext())
    assert decision.allowed is False
    assert "UNKNOWN" in decision.reason


def test_unknown_sensitivity_allowed_when_explicitly_opted_in():
    doc = _doc()
    decision = evaluate(doc, AccessContext(allow_unclassified=True))
    assert decision.allowed is True


def test_public_sensitivity_with_no_compartments_is_allowed_by_default():
    doc = _doc(sensitivity=Sensitivity.PUBLIC)
    decision = evaluate(doc, AccessContext())
    assert decision.allowed is True


def test_compartmented_document_requires_matching_scope():
    doc = _doc(sensitivity=Sensitivity.PUBLIC, compartments=["LEGAL"])

    denied = evaluate(doc, AccessContext(allowed_compartments=frozenset({"PERSONAL"})))
    assert denied.allowed is False
    assert "LEGAL" in denied.reason

    allowed = evaluate(doc, AccessContext(allowed_compartments=frozenset({"LEGAL"})))
    assert allowed.allowed is True


def test_unrestricted_scope_sees_compartmented_documents():
    doc = _doc(sensitivity=Sensitivity.PUBLIC, compartments=["LEGAL"])
    decision = evaluate(doc, AccessContext(allowed_compartments=None))
    assert decision.allowed is True


def test_uncompartmented_document_is_not_gated_by_compartment_scope():
    doc = _doc(sensitivity=Sensitivity.PUBLIC, compartments=[])
    decision = evaluate(doc, AccessContext(allowed_compartments=frozenset({"ANYTHING"})))
    assert decision.allowed is True


def test_eligible_document_ids_filters_a_mixed_list():
    visible = _doc(sensitivity=Sensitivity.PUBLIC)
    hidden_by_sensitivity = _doc(source_ref="/root/b.md", sensitivity=Sensitivity.UNKNOWN)
    hidden_by_compartment = _doc(source_ref="/root/c.md", sensitivity=Sensitivity.PUBLIC, compartments=["HEALTH"])

    ids = eligible_document_ids(
        [visible, hidden_by_sensitivity, hidden_by_compartment],
        AccessContext(allowed_compartments=frozenset({"PERSONAL"})),
    )
    assert ids == {visible.id}
