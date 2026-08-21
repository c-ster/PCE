"""`pce` command-line interface (PRD section 37).

Every command here does real work against the local capsule — no stubs
left. `pce --help` lists the full surface: init, source, repo, sync,
classify, assertion, index, search, memory, context, compartment, policy
explain, serve-mcp, doctor.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import click

from pce.adapters.git import GitAdapter
from pce.adapters.local_file import LocalFileAdapter
from pce.cli.home import (
    CAPSULE_SUBDIRS,
    CapsuleNotInitialized,
    capsule_home,
    db_path,
    init_capsule,
    is_initialized,
    require_initialized,
)
from pce.context.assertions import AssertionRepository, AssertionStatus, ContextAssertion
from pce.context.chunks import ChunkRepository
from pce.context.db import MIGRATIONS_DIR, connect
from pce.context.events import ContextEvent, ContextEventType, EventRepository
from pce.context.models import EpistemicRole, Sensitivity
from pce.context.registry import SourceRegistry
from pce.context.repository import SourceDocumentRepository
from pce.mcp.server import build_server as build_mcp_server
from pce.memory.observations import ContextObservation, ObservationRepository, ObservationStatus
from pce.steward.questions import QuestionRepository, QuestionStatus
from pce.steward.scan import DEFAULT_STALENESS_DAYS, run_steward_scan
from pce.policy.compartments import CompartmentRegistry
from pce.policy.engine import AccessContext, evaluate
from pce.providers.hashing_embeddings import HashingEmbeddingProvider
from pce.retrieval.indexer import build_index
from pce.router.search import route_and_search

# The only EmbeddingProvider this build ships. Query-time embedding must use
# the same provider that built the index, or similarity scores are
# meaningless — see docs/MODEL_PROVIDERS.md.
_EMBEDDING_PROVIDER = HashingEmbeddingProvider()


def _open_capsule():
    home = capsule_home()
    try:
        require_initialized(home)
    except CapsuleNotInitialized as exc:
        raise click.ClickException(str(exc)) from exc
    conn = connect(db_path(home))
    return home, conn


@click.group()
@click.version_option(package_name="personal-context-engine")
def cli() -> None:
    """Personal Context Engine — a local-first context layer for personal AI."""


@cli.command()
@click.option(
    "--compartment",
    "compartments",
    multiple=True,
    help="Create an initial compartment (repeatable).",
)
def init(compartments: tuple[str, ...]) -> None:
    """Initialize a local PCE capsule (default: ~/.pce, override with $PCE_HOME)."""
    home = capsule_home()
    already_initialized = is_initialized(home)

    init_capsule(home)

    if already_initialized:
        click.echo(f"Capsule already initialized at {home}.")
    else:
        click.echo(f"Created capsule at {home}:")
        for subdir in CAPSULE_SUBDIRS:
            click.echo(f"  {home / subdir}")

    conn = connect(db_path(home))
    if compartments:
        registry = CompartmentRegistry(conn)
        for name in compartments:
            registry.add(name)
        click.echo(f"Created compartment(s): {', '.join(compartments)}")

    click.echo()
    click.echo("Next steps:")
    click.echo("  pce source add <path>       approve a folder of Markdown/text files")
    click.echo("  pce repo add <path>         approve a local git working tree")
    click.echo("  pce compartment add <name>  define a compartment")
    click.echo("  pce index                   build the retrieval index")
    click.echo("  pce search \"...\"            search indexed context")
    click.echo("  pce context review          check for conflicts and stale facts")
    click.echo("  pce serve-mcp                connect a local model over MCP (see README.md)")
    click.echo("  pce doctor                  check the installation")
    click.echo()
    click.secho(
        "Not yet implemented in this build: a real local embedding model "
        "(retrieval uses a placeholder hashing embedding for now) and local "
        "LLM configuration. See README.md 'Status'.",
        fg="yellow",
    )


@cli.group()
def source() -> None:
    """Manage local Markdown/text file sources."""


@source.command("add")
@click.argument(
    "path", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path)
)
def source_add(path: Path) -> None:
    """Approve PATH as a source root and ingest its Markdown/text files."""
    _, conn = _open_capsule()
    resolved = path.resolve()

    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)
    registered = registry.register("local_file", str(resolved))

    adapter = LocalFileAdapter(approved_roots=[resolved])
    count = 0
    for doc in adapter.sync():
        stored = doc_repo.upsert(doc)
        registry.link_document(registered.id, stored.id)
        count += 1

    click.echo(f"Registered source {registered.id} ({resolved})")
    click.echo(f"Ingested {count} document(s).")


@source.command("list")
def source_list() -> None:
    """List registered local file sources."""
    _, conn = _open_capsule()
    registry = SourceRegistry(conn)
    sources = registry.list(kind="local_file")

    if not sources:
        click.echo("No local file sources registered. Add one with `pce source add <path>`.")
        return

    for item in sources:
        doc_count = len(registry.document_ids(item.id))
        click.echo(f"{item.id}  {item.path}  ({doc_count} documents, added {item.added_at.isoformat()})")


@source.command("inspect")
@click.argument("source_id")
def source_inspect(source_id: str) -> None:
    """Show details and ingested documents for a registered source."""
    _, conn = _open_capsule()
    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)

    item = registry.get(source_id)
    if not item:
        raise click.ClickException(f"No registered source with id {source_id}")

    click.echo(f"id:        {item.id}")
    click.echo(f"kind:      {item.kind}")
    click.echo(f"path:      {item.path}")
    click.echo(f"added_at:  {item.added_at.isoformat()}")
    click.echo()

    doc_ids = registry.document_ids(item.id)
    click.echo(f"{len(doc_ids)} document(s):")
    for doc_id in doc_ids:
        doc = doc_repo.get(doc_id)
        if doc:
            click.echo(f"  - {doc.id}  {doc.title or doc.source_ref}  [{doc.epistemic_role}, {doc.sensitivity}]")


@source.command("remove")
@click.argument("source_id")
def source_remove(source_id: str) -> None:
    """Remove a registered source and every document it ingested."""
    _, conn = _open_capsule()
    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)

    item = registry.get(source_id)
    if not item:
        raise click.ClickException(f"No registered source with id {source_id}")

    doc_ids = registry.document_ids(item.id)
    for doc_id in doc_ids:
        doc_repo.delete(doc_id)
    registry.remove(item.id)

    click.echo(f"Removed source {source_id} and {len(doc_ids)} document(s).")


@cli.command()
@click.argument("document_id")
@click.option(
    "--sensitivity", type=click.Choice([s.value for s in Sensitivity]), help="Set the document's sensitivity level."
)
@click.option(
    "--epistemic-role",
    "epistemic_role",
    type=click.Choice([r.value for r in EpistemicRole]),
    help="Set what kind of evidence this document represents (section 9) — used by the Context Router to bias ranking.",
)
@click.option(
    "--compartment",
    "compartments",
    multiple=True,
    help="Set the document's compartments (replaces any existing ones; repeatable).",
)
def classify(
    document_id: str, sensitivity: str | None, epistemic_role: str | None, compartments: tuple[str, ...]
) -> None:
    """Change a document's sensitivity, epistemic role, and/or compartments
    (PRD section 31: a state-changing action, done only on explicit
    request — never inferred)."""
    _, conn = _open_capsule()
    doc_repo = SourceDocumentRepository(conn)

    document = doc_repo.get(document_id)
    if not document:
        raise click.ClickException(f"No document with id {document_id}")

    if not sensitivity and not epistemic_role and not compartments:
        raise click.ClickException(
            "Nothing to update — pass --sensitivity, --epistemic-role, and/or --compartment."
        )

    if compartments:
        known = set(CompartmentRegistry(conn).list())
        unknown = [c for c in compartments if c not in known]
        if unknown:
            raise click.ClickException(
                f"Unknown compartment(s) {unknown}. Define them first with `pce compartment add <name>`."
            )

    updates: dict = {}
    if sensitivity:
        updates["sensitivity"] = Sensitivity(sensitivity)
    if epistemic_role:
        updates["epistemic_role"] = EpistemicRole(epistemic_role)
    if compartments:
        updates["compartments"] = list(compartments)

    updated = document.model_copy(update=updates)
    doc_repo.upsert(updated)
    click.echo(
        f"Updated {document_id}: sensitivity={updated.sensitivity}, "
        f"epistemic_role={updated.epistemic_role}, compartments={updated.compartments}"
    )


@cli.group()
def assertion() -> None:
    """Manage durable context assertions (PRD section 12-14)."""


@assertion.command("add")
@click.option("--subject", required=True)
@click.option("--predicate", required=True)
@click.option("--value", required=True)
@click.option(
    "--status", type=click.Choice([s.value for s in AssertionStatus]), default=AssertionStatus.PROPOSED.value
)
@click.option("--importance", type=float, default=0.5, show_default=True)
@click.option("--confidence", type=float, default=0.5, show_default=True)
@click.option("--source", "source_document_id", help="SourceDocument id this assertion is derived from.")
@click.option("--supersedes", help="Id of an existing assertion this one replaces.")
def assertion_add(
    subject: str,
    predicate: str,
    value: str,
    status: str,
    importance: float,
    confidence: float,
    source_document_id: str | None,
    supersedes: str | None,
) -> None:
    """Record a new assertion, optionally superseding an existing one."""
    _, conn = _open_capsule()
    repo = AssertionRepository(conn)

    if source_document_id and SourceDocumentRepository(conn).get(source_document_id) is None:
        raise click.ClickException(f"No document with id {source_document_id}")

    new_assertion = ContextAssertion(
        subject=subject,
        predicate=predicate,
        value=value,
        status=AssertionStatus(status),
        importance=importance,
        confidence=confidence,
        source=source_document_id,
    )

    if supersedes:
        if repo.get(supersedes) is None:
            raise click.ClickException(f"No assertion with id {supersedes}")
        stored = repo.supersede(supersedes, new_assertion)
        click.echo(f"Created {stored.id}, superseding {supersedes}")
    else:
        stored = repo.create(new_assertion)
        click.echo(f"Created {stored.id}")

    click.echo(f"{stored.subject} {stored.predicate} = {stored.value!r} [{stored.status}]")


@assertion.command("list")
@click.option("--subject", help="Restrict to one subject. Omit to list every current assertion.")
def assertion_list(subject: str | None) -> None:
    """List current assertions — the head of each supersession chain."""
    _, conn = _open_capsule()
    current = AssertionRepository(conn).list_current(subject=subject)

    if not current:
        click.echo("No assertions recorded yet. Add one with `pce assertion add`.")
        return

    for item in current:
        click.echo(f"{item.id}  {item.subject}  {item.predicate} = {item.value!r}  [{item.status}]")


@assertion.command("history")
@click.argument("subject")
@click.argument("predicate")
def assertion_history(subject: str, predicate: str) -> None:
    """Show the full supersession chain for one (subject, predicate), oldest first."""
    _, conn = _open_capsule()
    chain = AssertionRepository(conn).list_history(subject, predicate)

    if not chain:
        click.echo(f"No assertions for {subject} {predicate}.")
        return

    for item in chain:
        marker = "-> " if item.superseded_by is None else "   "
        click.echo(
            f"{marker}{item.valid_from.isoformat()}  {item.value!r}  [{item.status}]  id={item.id}"
        )


@assertion.command("show")
@click.argument("assertion_id")
def assertion_show(assertion_id: str) -> None:
    """Show every field of one assertion, including its supersession links."""
    _, conn = _open_capsule()
    item = AssertionRepository(conn).get(assertion_id)
    if not item:
        raise click.ClickException(f"No assertion with id {assertion_id}")

    for field_name, field_value in item.model_dump().items():
        click.echo(f"{field_name}: {field_value}")


@assertion.command("confirm")
@click.argument("assertion_id")
def assertion_confirm(assertion_id: str) -> None:
    """Record that this assertion was reconfirmed as still true, unchanged."""
    _, conn = _open_capsule()
    try:
        updated = AssertionRepository(conn).confirm(assertion_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Confirmed {updated.id} at {updated.last_confirmed_at.isoformat()}")


@assertion.command("approve")
@click.argument("assertion_id")
def assertion_approve(assertion_id: str) -> None:
    """Mark an assertion approved and record a DECISION_MADE event."""
    _, conn = _open_capsule()
    repo = AssertionRepository(conn)
    try:
        updated = repo.set_status(assertion_id, AssertionStatus.APPROVED)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    EventRepository(conn).record(
        ContextEvent(
            event_type=ContextEventType.DECISION_MADE,
            subject=updated.subject,
            assertion_id=updated.id,
            description=f"{updated.subject} {updated.predicate} approved: {updated.value!r}",
            source=updated.source,
        )
    )
    click.echo(f"Approved {updated.id}")


@assertion.command("reject")
@click.argument("assertion_id")
def assertion_reject(assertion_id: str) -> None:
    """Mark an assertion rejected and record a DECISION_REVERSED event."""
    _, conn = _open_capsule()
    repo = AssertionRepository(conn)
    try:
        updated = repo.set_status(assertion_id, AssertionStatus.REJECTED)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    EventRepository(conn).record(
        ContextEvent(
            event_type=ContextEventType.DECISION_REVERSED,
            subject=updated.subject,
            assertion_id=updated.id,
            description=f"{updated.subject} {updated.predicate} rejected: {updated.value!r}",
            source=updated.source,
        )
    )
    click.echo(f"Rejected {updated.id}")


@cli.group()
def repo() -> None:
    """Manage git repository sources."""


@repo.command("add")
@click.argument(
    "repo_path", type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path)
)
def repo_add(repo_path: Path) -> None:
    """Add a local git working tree as a source (remote URLs are not fetched — clone it yourself first)."""
    _, conn = _open_capsule()
    resolved = repo_path.resolve()

    try:
        adapter = GitAdapter(repo_path=resolved)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)
    registered = registry.register("git", str(resolved))

    count = 0
    for doc in adapter.sync():
        stored = doc_repo.upsert(doc)
        registry.link_document(registered.id, stored.id)
        count += 1

    click.echo(f"Registered git source {registered.id} ({resolved})")
    click.echo(f"Ingested {count} document(s) at HEAD.")


@repo.command("list")
def repo_list() -> None:
    """List registered git repository sources."""
    _, conn = _open_capsule()
    registry = SourceRegistry(conn)
    sources = registry.list(kind="git")

    if not sources:
        click.echo("No git sources registered. Add one with `pce repo add <path>`.")
        return

    for item in sources:
        doc_count = len(registry.document_ids(item.id))
        click.echo(f"{item.id}  {item.path}  ({doc_count} documents, added {item.added_at.isoformat()})")


@cli.command()
def sync() -> None:
    """Re-sync every registered source (local file roots and git repos)."""
    _, conn = _open_capsule()
    registry = SourceRegistry(conn)
    doc_repo = SourceDocumentRepository(conn)

    sources = registry.list()
    if not sources:
        click.echo("No registered sources. Add one with `pce source add` or `pce repo add`.")
        return

    for item in sources:
        if item.kind == "local_file":
            adapter = LocalFileAdapter(approved_roots=[Path(item.path)])
        elif item.kind == "git":
            adapter = GitAdapter(repo_path=Path(item.path))
        else:
            click.echo(f"Skipping {item.id}: unknown source kind {item.kind}")
            continue

        count = 0
        for doc in adapter.sync():
            stored = doc_repo.upsert(doc)
            registry.link_document(item.id, stored.id)
            count += 1
        click.echo(f"{item.kind}:{item.path} — synced {count} document(s)")


@cli.command()
def index() -> None:
    """Build the local retrieval index (lexical FTS5 + embeddings) for every registered source."""
    _, conn = _open_capsule()
    stats = build_index(conn, _EMBEDDING_PROVIDER)

    click.echo(f"Indexed {stats.documents_processed} document(s), {stats.chunks_created} chunk(s) created.")
    click.echo(f"Skipped {stats.documents_skipped} document(s) already up to date.")
    if stats.documents_failed:
        click.secho(f"Failed to read {stats.documents_failed} document(s):", fg="red")
        for failure in stats.failures:
            click.echo(f"  - {failure}")


@cli.command()
@click.argument("query")
@click.option("--limit", default=10, show_default=True, help="Maximum results to show.")
@click.option(
    "--compartment",
    "compartments",
    multiple=True,
    help="Restrict results to these compartments (repeatable). Omit for no compartment restriction.",
)
@click.option(
    "--include-unclassified",
    is_flag=True,
    default=False,
    help="Also include documents with UNKNOWN sensitivity (excluded by default — section 27 fails closed).",
)
def search(query: str, limit: int, compartments: tuple[str, ...], include_unclassified: bool) -> None:
    """Search indexed context (hybrid lexical + semantic, fused with RRF), policy-filtered before ranking."""
    _, conn = _open_capsule()
    chunk_repo = ChunkRepository(conn)

    if chunk_repo.count() == 0:
        raise click.ClickException("No index found. Run `pce index` first.")

    access_context = AccessContext(
        allowed_compartments=frozenset(compartments) if compartments else None,
        allow_unclassified=include_unclassified,
    )
    scope_desc = (
        f"compartments={sorted(compartments) if compartments else 'unrestricted'}, "
        f"unclassified sources {'included' if include_unclassified else 'excluded'}"
    )
    click.secho(f"Scope: {scope_desc}", fg="cyan", err=True)

    intent, results = route_and_search(conn, query, _EMBEDDING_PROVIDER, access_context, limit=limit)
    click.secho(f"Detected intent: {intent.value}", fg="cyan", err=True)
    if not results:
        click.echo("No matches.")
        return

    for rank, result in enumerate(results, start=1):
        doc = result.document
        snippet = result.text[:200].replace("\n", " ")
        click.echo(f"{rank}. [{result.score:.4f}] {doc.title or doc.source_ref}  ({doc.epistemic_role}, {doc.sensitivity})")
        click.echo(f"   source: {doc.source_ref}")
        click.echo(f"   {snippet}{'...' if len(result.text) > 200 else ''}")
        click.echo()


@cli.group()
def memory() -> None:
    """Durable memory commands (PRD sections 24-25)."""


@memory.command("propose")
@click.option("--subject", required=True)
@click.option("--description", required=True, help="The pattern or preference being proposed.")
@click.option("--confidence", type=float, default=0.5, show_default=True)
@click.option("--source", "source_document_id", help="SourceDocument id this observation is derived from.")
def memory_propose(subject: str, description: str, confidence: float, source_document_id: str | None) -> None:
    """Propose an observation. Never becomes durable on its own — accept it explicitly to save it."""
    _, conn = _open_capsule()

    if source_document_id and SourceDocumentRepository(conn).get(source_document_id) is None:
        raise click.ClickException(f"No document with id {source_document_id}")

    observation = ObservationRepository(conn).create(
        ContextObservation(subject=subject, description=description, confidence=confidence, source=source_document_id)
    )
    click.echo(f"Proposed {observation.id}")
    click.echo(f"{observation.subject}: {observation.description!r}  [{observation.status}]")


@memory.command("list")
@click.option(
    "--status",
    type=click.Choice([s.value for s in ObservationStatus]),
    default=None,
    help="Filter by status. Omit to show everything.",
)
def memory_list(status: str | None) -> None:
    """List observations."""
    _, conn = _open_capsule()
    observations = ObservationRepository(conn).list(status=ObservationStatus(status) if status else None)

    if not observations:
        click.echo("No observations recorded yet. Propose one with `pce memory propose`.")
        return

    for item in observations:
        click.echo(f"{item.id}  {item.subject}: {item.description!r}  [{item.status}]")


@memory.command("edit")
@click.argument("observation_id")
@click.argument("description")
def memory_edit(observation_id: str, description: str) -> None:
    """Edit a still-proposed observation's description before accepting or rejecting it."""
    _, conn = _open_capsule()
    try:
        updated = ObservationRepository(conn).edit(observation_id, description)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Updated {updated.id}: {updated.description!r}")


@memory.command("accept")
@click.argument("observation_id")
@click.option("--predicate", default="observation", show_default=True)
@click.option("--value", help="Override the assertion's value. Defaults to the observation's description.")
def memory_accept(observation_id: str, predicate: str, value: str | None) -> None:
    """"Save": promote this observation into a durable ContextAssertion."""
    _, conn = _open_capsule()
    try:
        observation, assertion = ObservationRepository(conn).accept(observation_id, predicate=predicate, value=value)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Accepted {observation.id} -> assertion {assertion.id}")
    click.echo(f"{assertion.subject} {assertion.predicate} = {assertion.value!r}")


@memory.command("reject")
@click.argument("observation_id")
def memory_reject(observation_id: str) -> None:
    """"Don't save": reject this observation. No assertion is created."""
    _, conn = _open_capsule()
    try:
        updated = ObservationRepository(conn).reject(observation_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Rejected {updated.id}")


@cli.group(name="context")
def context_group() -> None:
    """Context Steward / Inbox commands (PRD sections 17-22)."""


def _print_inbox(questions: list) -> None:
    if not questions:
        click.echo("Context Inbox · 0 — nothing waiting on you.")
        return

    click.echo(f"Context Inbox · {len(questions)}")
    for i, q in enumerate(questions, start=1):
        click.echo(f"{i}. [{q.urgency}] {q.description}")
        if q.suggested_answer:
            click.echo(f"   Suggested: {q.suggested_answer}")
        click.echo(f"   id: {q.id}")


@context_group.command("inbox")
@click.option("--include-deferred", is_flag=True, default=False, help="Also show deferred (not just open) questions.")
def context_inbox(include_deferred: bool) -> None:
    """List unresolved context questions. Does not scan for new ones — see `pce context review`."""
    _, conn = _open_capsule()
    statuses = (QuestionStatus.OPEN, QuestionStatus.DEFERRED) if include_deferred else (QuestionStatus.OPEN,)
    _print_inbox(QuestionRepository(conn).list(statuses=statuses))


@context_group.command("review")
@click.option(
    "--staleness-days", type=int, default=DEFAULT_STALENESS_DAYS, show_default=True,
    help="How long a current assertion can go unconfirmed before it's flagged stale.",
)
def context_review(staleness_days: int) -> None:
    """Scan for conflicts, staleness, and unreviewed observations, then show the inbox."""
    _, conn = _open_capsule()
    new_questions = run_steward_scan(conn, max_age_days=staleness_days)
    if new_questions:
        click.secho(f"Found {len(new_questions)} new item(s).", fg="cyan", err=True)
    _print_inbox(QuestionRepository(conn).list(statuses=(QuestionStatus.OPEN,)))


@context_group.command("stats")
def context_stats() -> None:
    """Show counts of context questions by status."""
    _, conn = _open_capsule()
    stats = QuestionRepository(conn).stats()
    for status, count in stats.items():
        click.echo(f"{status}: {count}")


@context_group.command("answer")
@click.argument("question_id")
@click.option("--note", required=True, help="What you decided.")
@click.option(
    "--reconfirm",
    is_flag=True,
    default=False,
    help="For a staleness question: also mark the related assertion reconfirmed today.",
)
def context_answer(question_id: str, note: str, reconfirm: bool) -> None:
    """Resolve a question with a decision."""
    _, conn = _open_capsule()
    question_repo = QuestionRepository(conn)

    question = question_repo.get(question_id)
    if not question:
        raise click.ClickException(f"No question with id {question_id}")

    if reconfirm:
        assertion_repo = AssertionRepository(conn)
        for assertion_id in question.related_assertion_ids:
            assertion_repo.confirm(assertion_id)

    updated = question_repo.answer(question_id, note)
    click.echo(f"Answered {updated.id}: {updated.resolution_note}")


@context_group.command("defer")
@click.argument("question_id")
def context_defer(question_id: str) -> None:
    """Postpone a question — still pending, just out of the default inbox view."""
    _, conn = _open_capsule()
    try:
        updated = QuestionRepository(conn).defer(question_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Deferred {updated.id}")


@context_group.command("dismiss")
@click.argument("question_id")
def context_dismiss(question_id: str) -> None:
    """Dismiss a question — not worth resolving, no action taken."""
    _, conn = _open_capsule()
    try:
        updated = QuestionRepository(conn).dismiss(question_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Dismissed {updated.id}")


@cli.group()
def compartment() -> None:
    """Manage compartments (PRD section 28)."""


@compartment.command("list")
def compartment_list() -> None:
    """List defined compartments."""
    _, conn = _open_capsule()
    registry = CompartmentRegistry(conn)
    names = registry.list()

    if not names:
        click.echo("No compartments defined yet. Add one with `pce compartment add <name>`.")
        return

    for name in names:
        click.echo(name)


@compartment.command("add")
@click.argument("name")
def compartment_add(name: str) -> None:
    """Define a new compartment."""
    _, conn = _open_capsule()
    registry = CompartmentRegistry(conn)
    registry.add(name)
    click.echo(f"Added compartment '{name}'.")


@cli.group()
def policy() -> None:
    """Explain policy decisions (PRD section 26/29)."""


@policy.command("explain")
@click.argument("document_id")
@click.option(
    "--compartment",
    "compartments",
    multiple=True,
    help="Compartment scope to evaluate against (repeatable). Omit for no compartment restriction.",
)
@click.option(
    "--include-unclassified",
    is_flag=True,
    default=False,
    help="Evaluate as if UNKNOWN-sensitivity sources were allowed.",
)
def policy_explain(document_id: str, compartments: tuple[str, ...], include_unclassified: bool) -> None:
    """Explain whether DOCUMENT_ID would be visible under a given access scope, and why."""
    _, conn = _open_capsule()
    document = SourceDocumentRepository(conn).get(document_id)
    if not document:
        raise click.ClickException(f"No document with id {document_id}")

    context = AccessContext(
        allowed_compartments=frozenset(compartments) if compartments else None,
        allow_unclassified=include_unclassified,
    )
    decision = evaluate(document, context)

    click.echo(f"document:     {document.title or document.source_ref}")
    click.echo(f"sensitivity:  {document.sensitivity}")
    click.echo(f"compartments: {document.compartments or '(none)'}")
    click.echo()
    click.echo(
        "requested scope: compartments="
        f"{sorted(compartments) if compartments else 'unrestricted'}, "
        f"unclassified={'allowed' if include_unclassified else 'excluded'}"
    )
    click.echo()
    click.secho(
        f"decision: {'ALLOWED' if decision.allowed else 'DENIED'}",
        fg="green" if decision.allowed else "red",
    )
    click.echo(f"reason:   {decision.reason}")

    if not decision.allowed:
        sys.exit(1)


@cli.command()
def doctor() -> None:
    """Check that the local PCE installation is healthy."""
    checks: list[tuple[str, bool, str]] = []

    py_ok = sys.version_info >= (3, 12)
    checks.append(("Python >= 3.12", py_ok, sys.version.split()[0]))

    git_path = shutil.which("git")
    checks.append(("git executable on PATH", git_path is not None, git_path or "not found"))

    home = capsule_home()
    home_ok = is_initialized(home)
    checks.append((f"capsule initialized at {home}", home_ok, "ok" if home_ok else "run `pce init`"))

    if home_ok:
        missing_subdirs = [d for d in CAPSULE_SUBDIRS if not (home / d).is_dir()]
        checks.append(
            (
                "capsule directory layout",
                not missing_subdirs,
                "ok" if not missing_subdirs else f"missing: {missing_subdirs}",
            )
        )

        conn = connect(db_path(home))
        applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
        available = {p.name for p in MIGRATIONS_DIR.glob("*.sql")}
        pending = sorted(available - applied)
        checks.append(
            ("database migrations up to date", not pending, "ok" if not pending else f"pending: {pending}")
        )

        registry = SourceRegistry(conn)
        checks.append(("registered sources", True, f"{len(registry.list())} registered"))

        chunk_repo = ChunkRepository(conn)
        checks.append(("retrieval index", True, f"{chunk_repo.count()} chunk(s) indexed (run `pce index` to build/refresh)"))

        assertion_count = len(AssertionRepository(conn).list_current())
        checks.append(("context assertions", True, f"{assertion_count} current assertion(s)"))

        open_questions = len(QuestionRepository(conn).list(statuses=(QuestionStatus.OPEN,)))
        checks.append(("context inbox", True, f"{open_questions} open question(s) (run `pce context review` to scan)"))

    all_ok = True
    for label, ok, detail in checks:
        symbol = "OK  " if ok else "WARN"
        click.echo(f"[{symbol}] {label} — {detail}")
        all_ok = all_ok and ok

    click.echo()
    click.secho(
        "Still placeholder rather than real: the embedding model (retrieval "
        "works, just not with true semantic understanding) and local LLM "
        "configuration. Everything else in `pce --help` does real work — "
        "see README.md 'Status'.",
        fg="yellow",
    )

    if not all_ok:
        sys.exit(1)


@cli.command("serve-mcp")
@click.option(
    "--compartment",
    "compartments",
    multiple=True,
    help=(
        "Fixed compartment scope for this server (repeatable). This is set once at "
        "startup by you, not something the connecting model can change — omit for no "
        "compartment restriction."
    ),
)
@click.option(
    "--include-unclassified",
    is_flag=True,
    default=False,
    help="Also allow documents with UNKNOWN sensitivity for this server's lifetime.",
)
def serve_mcp(compartments: tuple[str, ...], include_unclassified: bool) -> None:
    """Start the local MCP server (stdio transport) with a fixed access scope."""
    _, conn = _open_capsule()
    access_context = AccessContext(
        allowed_compartments=frozenset(compartments) if compartments else None,
        allow_unclassified=include_unclassified,
    )

    # stdout is the MCP protocol channel once server.run() starts — every
    # diagnostic here must go to stderr.
    click.secho(
        "Starting MCP server (stdio). Scope: compartments="
        f"{sorted(compartments) if compartments else 'unrestricted'}, "
        f"unclassified {'included' if include_unclassified else 'excluded'}.",
        fg="cyan",
        err=True,
    )

    server = build_mcp_server(conn, _EMBEDDING_PROVIDER, access_context)
    server.run()


if __name__ == "__main__":
    cli()
