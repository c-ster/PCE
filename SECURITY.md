# Security Policy

PCE handles personal, potentially sensitive context. If you find a security
vulnerability — including anything that could bypass compartment isolation,
sensitivity filtering, the local-file safety boundary, or that lets retrieved
content escalate into tool/model instructions — please report it privately
rather than opening a public issue.

Open a [GitHub Security Advisory](https://github.com/c-ster/PCE/security/advisories/new)
on this repository with:

- a description of the issue and its impact,
- steps to reproduce,
- affected version/commit.

We'll acknowledge reports and work with you on a fix and coordinated
disclosure timeline before any public write-up.

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the security model this
project is designed against.
