# CLAUDE.md

## What this repo is

`mea-skills` is a personal collection of agent skills (Claude, Codex, Antigravity) plus a dependency-free Node installer that copies them into each agent's user skills directory. It is **not** an application: most of the content is `SKILL.md` prompt files, with one skill (`trivy-porter`) backed by a Python CLI.

## Layout

```
<skill-name>/SKILL.md     # a skill = any root folder containing SKILL.md (auto-discovered by the installer)
  references/, scripts/, agents/   # optional supporting files, copied along with the skill
scripts/                  # Node ESM tooling (installer, version, trivy-porter launcher)
tests/                    # node:test (*.test.mjs) and Python unittest (test_*.py)
.github/workflows/bump-version.yml
```

Skills:
- `commit-message-generator` — runs `git add -A` (unless `--only-staged`) and suggests a commit message; `no desc` gives subject only.
- `mr-synthesize` (formerly `mr-description`) — MR/PR title and description from the last N commits.
- `ut-ranger` — writes unit tests only inside test dirs (`__tests__`), never production code; `agents/openai.yaml` holds Codex UI metadata.
- `trivy-porter` — Trivy scan/remediation workflow split between a terminal CLI and an agent. It reuses `commit-message-generator` for its commit suggestions.

## Commands

Package manager is pnpm in docs, but there are **no npm dependencies**; Node >= 20 only.

```sh
pnpm run mea-skills:install      # interactive installer (scripts/install-skills.mjs)
pnpm run mea-skills:version      # prints "mea-skills vX.Y.Z"
pnpm run mea-skills:terminal-link  # link trivy-porter into ~/.local/bin (.cmd + Git Bash shim on Windows), Node-version independent
pnpm run mea-skills:terminal-unlink  # remove only the link created by terminal-link
pnpm run trivy-porter            # Node launcher -> Python CLI
pnpm test                        # node --test (installer + launcher tests)
pnpm run test:trivy-porter       # python3 -B -m unittest discover -s tests -p "test_*.py"
```

Run a single test: `node --test tests/skill-installer.test.mjs` or `python3 -B -m unittest tests.test_session_store`.

## Architecture notes

**Installer** (`scripts/`)
- `skill-installer.mjs` — core logic: `getDefaultTargets`, `resolveDestination` (expands `~`, `$HOME`, `%USERPROFILE%`, quotes; rejects cross-OS paths), `discoverSkills`, `createInstallPlan`, `applyInstallPlan`. Compares SHA-256 manifests so identical skills are skipped; updates replace the whole skill folder after preparing/verifying the copy. Ignores `.git`, `node_modules`, `__pycache__`, `.DS_Store`, `*.pyc`; symlinks inside a skill are rejected.
- `install-skills.mjs` — interactive prompt flow (target choice, path, plan review, `[Y/n]` confirm; nothing is written before confirmation). `installer-output.mjs` formats the completion summary, including the `npm link` vs `terminal-link` next steps; the installer itself never creates the CLI link.
- `terminal-link.mjs` — separate interactive command that symlinks `scripts/trivy-porter.mjs` into a user bin folder (on Windows writes a `trivy-porter.cmd` shim plus an extensionless `trivy-porter` sh shim, since Git Bash ignores PATHEXT). Every change (Windows shims, folder off `PATH`, folder creation, overwrite, `chmod +x`, final plan) is confirmed first; it never escalates privileges. It also exports the shared prompt and link-inspection helpers used by `terminal-unlink.mjs`, which removes only links mea-skills created (symlink to this repo, or shims carrying the mea-skills marker).
- Functions take injectable `platform`/`homeDirectory`/`cwd`/`env` params so tests can simulate Windows/POSIX — keep that pattern.

**trivy-porter**
- `scripts/trivy-porter.mjs` finds Python 3 (`python3`/`python`, or `py -3` on Windows) and spawns `trivy-porter/scripts/trivy_porter.py` with inherited stdio.
- Python modules in `trivy-porter/scripts/`: `trivy_porter.py` (menus, scan config/execution, sanitizing, CLI), `session_store.py` (atomic, locked JSON session storage in `.trivy-porter/`), `report_transfer.py` (sanitized report download/clean), `terminal_output.py` (handoff rendering).
- `trivy-porter/references/*.md` (interaction, session-state, git-commit) are read by the agent on demand per `SKILL.md`.
- `.trivy-porter/` at repo root is runtime state (a local session store), auto-ignored via its own mechanism — don't edit or commit it.

## Conventions

- **Language:** user-facing strings in the installer and Trivy CLI are in Indonesian (e.g. `Path instalasi tidak valid.`); `trivy-porter` and `ut-ranger` skills instruct agents to reply in Indonesian / the user's language. `README.md` and code identifiers are English. Match the language of the file you edit.
- Node code is ESM (`"type": "module"`), uses only `node:` built-ins, single quotes, semicolons, compact style — follow existing formatting.
- Commits follow Conventional Commits with scope, e.g. `feat(installer): ...`, `feat(ut-ranger): ...`, `chore(release): vX.Y.Z [skip ci]`.
- Skill `SKILL.md` files need YAML frontmatter with `name` and `description` (the description drives triggering — include the invocation phrases).

## Versioning / release

Every push to `main` triggers `.github/workflows/bump-version.yml`, which runs `npm version minor` and pushes a `chore(release): vX.Y.Z [skip ci]` commit plus annotated tag; their body lists `- <subject> (<hash>)` for each commit since the previous `v*` tag. The npm `version` lifecycle script (`scripts/sync-readme-version.mjs`) rewrites README's `Current version: **x.y.z**` line and `trivy-porter/VERSION` (read by `trivy-porter -v`, including installed copies) and stages both, so keep that exact line format. Do **not** bump `package.json` version manually.

## When adding or changing a skill

1. Create `<skill-name>/SKILL.md` (the installer picks it up automatically; no registry to update).
2. Add a row to the "Available Skills" table in `README.md`.
3. Add tests under `tests/` if there is executable code.
