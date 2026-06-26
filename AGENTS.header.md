## 1. Repo identity

- **Repo:** `notebooklm-skill`
- **Purpose:** Public Claude Code **skill** for source-grounded research against Google NotebookLM notebooks — browser automation (patchright Chrome) that asks questions of uploaded sources and returns grounded answers. Entry point: `SKILL.md`; auth flow: `AUTHENTICATION.md`.
- **Owner:** @sterngold
- **Status:** active.
- **Stack:** `SKILL.md` + Python scripts (`scripts/`, runtime deps in `requirements.txt`; CI/test deps in `pyproject.toml` + `uv.lock`; `patchright install chrome` post-install). Reference docs in `references/`. Runtime still manages its own skill-local `.venv` per `SKILL.md`.

---

## 2. Build, test, lint

Unit tests cover local storage/security helpers. Full behavior verification is
still a **live skill run** (browser automation against a real NotebookLM
notebook; see `SKILL.md` for the run flow and `AUTHENTICATION.md` for first-time
auth).

```bash
# Environment (as the skill itself does it)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/patchright install chrome

# CI-equivalent local checks
uv sync --frozen --all-extras --all-groups
uv run ruff check scripts tests
uv run ruff format --check scripts tests
uv run pytest -q

# Verify this repo's AGENTS.md is in sync with its header + the shared canon
bash ~/anders-dotfiles/context-sync/assemble-agents.sh --check .   # 0 ok · 1 stale · 2 error

gitleaks detect --config .gitleaks.toml   # secret scan (also runs in CI + pre-commit)
pre-commit run --all-files                # file hygiene (after `pre-commit install`)
```

**Never commit** Google credentials, browser profiles/session state, or captured notebook content. The `.venv/` stays untracked.

**Agents:** behavior changes go through `scripts/` + `SKILL.md` together — the skill doc is the contract; scripts that drift from it break users silently.
