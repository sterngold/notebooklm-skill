# GitHub Copilot instructions

Read the repository-root `AGENTS.md`, `CLAUDE.md`, `README.md`, `SKILL.md`, and
`AUTHENTICATION.md` before changing behavior. `AGENTS.md` is the repository
contract, and `SKILL.md` is the user-facing behavior contract. Resolve all
references relative to this checkout; cloud work must not depend on a user's
home directory or local Claude installation.

## Repository commands

There is no separate build artifact. Use the exact CI-equivalent commands:

```bash
uv sync --frozen --all-extras --all-groups
uv run ruff check scripts tests
uv run ruff format --check scripts tests
uv run pytest -q
```

Unit tests cover local storage and security helpers. Full behavior verification
requires a live browser session against NotebookLM and is not available in a
cloud sandbox without approved credentials and browser state. Never claim that
unit tests prove live Google/NotebookLM behavior. The required aggregate GitHub
check is `ci`; it must pass before merge.

## Working rules

- Work in an isolated task checkout: use a new worktree for local app work or
  the provider's isolated sandbox for cloud work. Use a task-named branch and
  never push code directly to `main`.
- Keep changes narrow and update `scripts/` and `SKILL.md` together whenever the
  behavior contract changes. Stage only reviewed paths, use Conventional
  Commits, and do not bypass hooks.
- Do not add a new top-level dependency or change `requirements.txt`,
  `pyproject.toml`, `uv.lock`, or another manifest/lockfile without explicit approval.
  If approved dependency work is required, use frozen lockfile
  workflows and do not enable new install lifecycle scripts implicitly.
- Never commit or upload Google credentials, cookies, browser profiles/session
  state, captured notebook content, or a local `.venv/`.
- Do not authenticate to Google or run a live NotebookLM query in cloud work.
  Stop when required live validation or local-only shared-canon context is
  unavailable; do not invent results.
- Before merge, wait for CI and resolve every review thread. Copilot review is
  a required workflow gate in this repository but remains advisory in GitHub's
  approval model; it does not replace CI or the repository owner's merge
  decision. No separate human reviewer approval is required by `AGENTS.md`.

## Review priorities

Prioritize silent failures, boundary validation, tests, security, and unresolved
review threads. Also check credential/session-state handling and agreement
between scripts and `SKILL.md`.
