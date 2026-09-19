# Contributing to AgentHop

Thanks for helping improve AgentHop. This is security-sensitive local tooling, so
small, reviewable changes with focused tests are preferred.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest

cd frontend
npm install
npm run dev
```

For the integrated development UI, start the backend with
`agenthop --reload --port 8000`; Vite proxies `/api` to that port. The standalone
CLI default is `127.0.0.1:8765`.

The frontend currently supports Node 18.19+, with Node 20+ recommended. Run both
`npm audit --omit=dev` and the full `npm audit`; see [docs/SECURITY.md](docs/SECURITY.md)
for the documented development-only audit exception. Do not apply a forced major
upgrade without updating the supported runtime and verifying tests and builds.

Use the repository's `Makefile` and package scripts when they provide a more
specific command. The backend and frontend should be developed against temporary
profile roots; never use real credentials in fixtures.

## Pull requests

- Keep the change scoped and explain its user-visible effect.
- Add focused tests for behavior changes and migration edge cases.
- Run the narrowest relevant tests, then the full available suite.
- Update documentation when commands, API models, security boundaries, or state
  layouts change.
- Do not include generated build output, local databases, sessions, logs, or
  credentials.
- Call out compatibility assumptions and any undocumented provider surface.

## Provider adapters

Read [docs/PROVIDER_ADAPTERS.md](docs/PROVIDER_ADAPTERS.md) before proposing an
integration. A proposal should first describe the provider's credential boundary,
continuity state, supported local interface, migration behavior, and recovery
plan.

Provider adapters must degrade safely when optional capabilities are unavailable.
Do not interpret missing usage data as unlimited capacity, and do not determine
authentication only by reading secret files.

## Testing expectations

Use temporary directories and mocked provider processes. Important cases include:

- valid and invalid profile identifiers;
- missing executables and timeouts;
- file and credential-store authentication;
- empty and populated state roots;
- repeat migrations;
- identical and conflicting files;
- unexpected symlinks;
- locked or incompatible SQLite databases; and
- API responses and logs that must not contain secrets.

Frontend changes should include the relevant component tests and a production
build. Backend changes should include unit/API tests and lint/type checks provided
by the project configuration.

## Security reports

Do not open a public issue for a suspected vulnerability or include live secrets
in any report. Follow [SECURITY.md](SECURITY.md).

By contributing, you agree that your contribution is licensed under the MIT
License.
