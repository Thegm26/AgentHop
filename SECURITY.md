# Security policy

## Reporting a vulnerability

Please do not open a public issue for a vulnerability that could expose
credentials, session content, local files, or command execution.

Use GitHub's private vulnerability reporting feature for this repository if it is
enabled. Otherwise, contact the maintainer privately through the address listed
on their GitHub profile. Include:

- the affected version or commit;
- a concise description and impact;
- reproduction steps using redacted or synthetic data; and
- any suggested mitigation.

Never include a live `auth.json`, token, session rollout, or database. Revoke any
credential that may have been exposed during testing.

You can expect acknowledgement as soon as practical. Please allow time to verify
and prepare a fix before public disclosure. This project is maintained on a
best-effort basis and does not promise a specific response or remediation window.

## Supported versions

AgentHop is currently an MVP. Security fixes target the latest revision on the
default branch; older revisions are not maintained as separate supported release
lines.

## Scope

Relevant reports include secret disclosure, path traversal, unsafe symlink
handling, command injection, cross-origin state changes, migration corruption,
and provider impersonation. Reports about bypassing third-party service limits or
attacking provider infrastructure are outside this project's scope and should be
sent to the provider.

For deployment assumptions and defensive guidance, read
[docs/SECURITY.md](docs/SECURITY.md).
