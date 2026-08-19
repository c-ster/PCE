# Adapter SDK

Sources are implemented through adapters, not through the core schema. Every
adapter implements `pce.adapters.base.SourceAdapter`:

```python
class SourceAdapter:
    def discover(self): ...          # find candidate sources under approved roots
    def sync(self): ...              # discover + read + build SourceDocuments
    def enumerate_documents(self): ...# yield source refs
    def read_document(self, ref): ... # return raw content for a ref
    def get_metadata(self, ref): ...  # return adapter-specific metadata for a ref
```

Adapters must declare:

- network behavior (does it ever leave the machine?),
- permissions required,
- supported source types,
- credential requirements,
- read/write capability.

## v0.1 adapters

- **Local file** (`pce.adapters.local_file.LocalFileAdapter`) — Markdown/text
  files under explicitly approved root directories. Fully offline. Read-only.
- **Git** — planned; not yet implemented in this slice.

## Local file safety

An adapter that reads from disk must only ever read paths that resolve inside
one of its `approved_roots`. Any path outside those roots raises
`pce.adapters.errors.SourceRootViolation` rather than silently reading it.
Approved roots are explicit and user-configured — never `~/`, `~/.ssh`,
`~/Library`, or `/etc` unless the user deliberately adds them.

## Future community adapters

Obsidian, Apple Notes, Notion, Google Drive, Dropbox, Gmail, Outlook,
Goodreads, Kindle highlights, Zotero, LinkedIn export, patents, Slack,
Discord, conversation exports — each as a separate `pce-adapter-*` package,
without modifying core PCE.
