"""`pce` command-line interface (PRD section 37).

Commands backed by what's actually implemented (init, source, repo, sync,
doctor) do real work against the local capsule. Commands whose subsystem
doesn't exist yet (index, search, memory, context, policy, serve-mcp) say so
explicitly and exit non-zero, rather than pretending to work.
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
from pce.context.chunks import ChunkRepository
from pce.context.db import MIGRATIONS_DIR, connect
from pce.context.registry import SourceRegistry
from pce.context.repository import SourceDocumentRepository
from pce.policy.compartments import CompartmentRegistry
from pce.providers.hashing_embeddings import HashingEmbeddingProvider
from pce.retrieval.indexer import build_index
from pce.retrieval.search import hybrid_search

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


def _not_yet_implemented(feature: str, doc_ref: str) -> None:
    click.secho(
        f"'{feature}' is not implemented yet in this build. See {doc_ref}.",
        fg="yellow",
        err=True,
    )
    sys.exit(1)


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
    click.echo("  pce doctor                  check the installation")
    click.echo()
    click.secho(
        "Not yet implemented in this build: a real local embedding model "
        "(retrieval uses a placeholder hashing embedding for now), local "
        "LLM configuration, and MCP connection instructions. See README.md "
        "'Status'.",
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
def search(query: str, limit: int) -> None:
    """Search indexed context (hybrid lexical + semantic, fused with RRF)."""
    _, conn = _open_capsule()
    chunk_repo = ChunkRepository(conn)

    if chunk_repo.count() == 0:
        raise click.ClickException("No index found. Run `pce index` first.")

    click.secho(
        "This build does not yet enforce compartments or sensitivity — "
        "results are not policy-filtered. See docs/THREAT_MODEL.md.",
        fg="yellow",
        err=True,
    )

    results = hybrid_search(conn, query, _EMBEDDING_PROVIDER, limit=limit)
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
    """Durable memory commands."""


@memory.command("list")
def memory_list() -> None:
    _not_yet_implemented("pce memory list", "PRD section 25 (Memory Governance)")


@cli.group(name="context")
def context_group() -> None:
    """Context steward / inbox commands."""


@context_group.command("inbox")
def context_inbox() -> None:
    _not_yet_implemented("pce context inbox", "docs/CONTEXT_STEWARD.md")


@context_group.command("review")
def context_review() -> None:
    _not_yet_implemented("pce context review", "docs/CONTEXT_STEWARD.md")


@context_group.command("stats")
def context_stats() -> None:
    _not_yet_implemented("pce context stats", "docs/CONTEXT_STEWARD.md")


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
@click.argument("scenario", required=False)
def policy_explain(scenario: str | None) -> None:
    _not_yet_implemented("pce policy explain", "docs/THREAT_MODEL.md")


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

    all_ok = True
    for label, ok, detail in checks:
        symbol = "OK  " if ok else "WARN"
        click.echo(f"[{symbol}] {label} — {detail}")
        all_ok = all_ok and ok

    click.echo()
    click.secho(
        "Not yet implemented in this build: real embedding/LLM providers "
        "(retrieval uses a placeholder hashing embedding), memory, context "
        "steward, policy enforcement, and the MCP server.",
        fg="yellow",
    )

    if not all_ok:
        sys.exit(1)


@cli.command("serve-mcp")
def serve_mcp() -> None:
    """Start the local MCP server."""
    _not_yet_implemented("pce serve-mcp", "PRD section 36 (MCP Interface)")


if __name__ == "__main__":
    cli()
