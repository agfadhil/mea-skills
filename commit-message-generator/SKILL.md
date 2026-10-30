---
name: commit-message-generator
description: >-
  Stages all repository changes and suggests a commit message following the
  project's commit rules, including a bullet-point body by default. Use
  --only-staged to inspect the existing staged diff without changing the index,
  and no desc to generate only a one-line commit subject.
  Triggered by /commit, /commit-message-generator, or an explicit request to use
  this skill to suggest a commit message.
---

# Git Commit Generator

## Overview

When the user types `/commit` or `/commit-message-generator`, this skill:

1. **Detects** the repository root and applicable commit message rules.
2. **Stages all changes** from the repository root by default, or preserves the
   existing index when `--only-staged` is supplied.
3. **Inspects** every staged file and their diff.
4. **Generates** a single, compliant commit message with a subject and concise
   bullet-point body by default — ready to paste.

The output MUST be **ONLY a single markdown code block** (` ``` `). Do not include any tool execution logs, conversational filler, or text outside the code block.

Without parameters, include a brief description in bullet points in the commit
body. When the invocation includes `no desc` (e.g., `/commit no desc`), output
only the one-line commit subject, with no body or footer.

`--only-staged` controls staging independently of `no desc`; accept either
order when both are supplied. For example,
`/commit-message-generator --only-staged no desc` suggests only a one-line
subject using the existing staged changes. Never run `git commit` or push as
part of either mode.

---

## Default Commit Message Format

Use the **Conventional Commits** format as the default baseline:

```
<type>(<optional-scope>): <description>

- Brief description of the changes

[optional footer(s)]
```

> [!IMPORTANT]
> These are **defaults only**. Always detect and apply the project's own rules
> first (see Step 0 in the Workflow below). Project-specific config overrides
> every default listed here.

### Type (default set)

Choose **exactly one** type that best matches the staged changes:

| Type       | When to use                                                    |
| ---------- | -------------------------------------------------------------- |
| `feat`     | A new feature or user-visible capability                       |
| `fix`      | A bug fix                                                      |
| `docs`     | Documentation-only changes (README, comments, `.md` files)     |
| `style`    | Formatting, whitespace, semicolons — no logic change           |
| `refactor` | Code restructure without behaviour change and without new feat |
| `test`     | Adding or updating tests                                       |
| `chore`    | Maintenance: config, deps, tooling, CI, build scripts          |
| `perf`     | Performance improvement                                        |
| `ci`       | CI/CD pipeline changes                                         |
| `build`    | Build system or external dependency changes                    |
| `revert`   | Reverts a previous commit                                      |

If the project restricts types to a specific list, use only types from that list.

### Scope (optional by default)

A short noun in **lowercase** identifying the area of change.
Derive the scope from the route/page name, component folder, service name, or
tooling name. Omit when changes span many unrelated areas.

If the project enforces a fixed list of scopes, use only scopes from that list.

### Description (required)

- **Imperative, present tense**: "add", "fix", "remove" — not "added" or "fixes"
- **Lowercase first letter**
- **No trailing period**
- **≤ 72 characters** for the entire header line

### Body (included by default)

Include a concise bullet-point description of the actual staged changes, even
when the subject alone would explain them. Add the reason when it helps.
Separate the body from the subject with a blank line and wrap at 72 characters.
Omit the body entirely only when the invocation includes `no desc`.

### Footer (optional)

Use `BREAKING CHANGE: <description>` for breaking changes.
Use `Closes #<issue>` or `Fixes #<issue>` to reference issues.
The `no desc` mode emits only the subject, so omit footers in that mode.

---

## Workflow

### Step 0 — Detect project commit rules

Before analysing any diff, discover what commit message rules this project
enforces. Check the following locations **in order**, stopping at the first hit:

**a) commitlint configuration**

Look for any of these files in the repository root:

- `commitlint.config.js` / `commitlint.config.cjs` / `commitlint.config.mjs`
- `commitlint.config.ts`
- `.commitlintrc` / `.commitlintrc.json` / `.commitlintrc.yaml` / `.commitlintrc.yml`
- `commitlint` key inside `package.json`

Read the file and note:

- Which **preset/extends** is used (e.g., `@commitlint/config-conventional`,
  `@commitlint/config-angular`, a custom config, etc.).
- Any **rules overrides** — custom type enums, scope enums, max header length,
  case rules, etc.
- The associated **git hook** (usually `.husky/commit-msg` or
  `.git/hooks/commit-msg`) to confirm the hook is active.

**b) AGENTS.md / CONTRIBUTING.md / README.md**

If no commitlint config exists, scan `AGENTS.md`, `CONTRIBUTING.md`, and
`README.md` (in that order) for a section describing commit message conventions.
Extract any documented format, type list, or examples.

**c) Infer from recent commit history**

If no documentation is found, run:

```
git log --oneline -20
```

Look for a consistent pattern in recent commit messages (Conventional Commits,
Angular style, Gitmoji, plain prose, etc.) and follow that pattern.

**d) Default fallback**

If nothing can be detected, apply the **Default Commit Message Format** defined
in this skill (Conventional Commits baseline).

After detection, hold the resolved rules in mind for Steps 4–6. If the project
uses a non-Conventional-Commits format, adapt all subsequent steps accordingly.

---

### Step 1 — Detect the git repository root

Run:

```
git rev-parse --show-toplevel
```

If this fails, stop and tell the user: "No git repository found. Please run
`/commit` from inside a git project directory."

### Step 2 — Prepare the index and check for staged files

Unless the invocation includes `--only-staged`, run this command using the
resolved repository root as the working directory:

```sh
git add -A
```

This stages added, modified, and deleted files across the entire repository,
including untracked files and changes outside the invocation's subdirectory.
Partially staged files become fully staged with their current working-tree
contents. Respect normal Git ignore rules; do not force-add ignored files.
The default invocation authorizes this staging step without a separate prompt.
If staging fails, stop and report the failure instead of suggesting a message
from an incomplete or outdated index.

With `--only-staged`, skip staging entirely. Do not add, reset, unstage, or
otherwise change the index or working files. Analyze only the existing staged
snapshot, excluding unstaged edits and untracked files.

Then, in either mode, run from the repository root:

```
git diff --staged --name-only
```

If the output is empty, stop without inventing a commit message:

- Default mode: "No changes found to stage or describe."
- `--only-staged`: "No staged files found. Stage your changes with
  `git add <files>` or run without `--only-staged`."

### Step 3 — Collect the staged diff

Run from the repository root:

```
git diff --staged
```

Read the full unified diff output. This is the primary input for analysis.

Also collect the list of staged files and their change status:

```
git diff --staged --name-status
```

### Step 4 — Analyse the changes

Reason over the staged diff:

1. **Identify what changed** — new files, deleted files, modified files,
   renamed files. Group them by subsystem/area.
2. **Determine the type** — use the type table above. If in doubt between
   `feat` and `refactor`, ask: does this add a capability the user didn't have
   before? If yes → `feat`. If it only reorganises → `refactor`.
3. **Determine the scope** — look at directory paths and file names. Map them
   to the scope guidance above. If all staged files live under one route or
   component folder, use that as the scope.
4. **Write the description** — one tight imperative phrase. Focus on the
   _effect_ on the system, not the mechanical change.
5. **Write the body** — summarize the staged changes in concise bullet points
   by default. Skip the body only when the invocation includes `no desc`.

### Step 5 — Apply project-specific scope conventions

If a fixed scope list was found in Step 0, use only scopes from that list.

Otherwise, derive the scope from directory structure. Common heuristics:

| Path pattern                                | Suggested scope                    |
| ------------------------------------------- | ---------------------------------- |
| Auth/login route folder                     | `auth`                             |
| A specific route or page folder             | route name in kebab-case           |
| A specific component folder                 | component name in kebab-case       |
| `src/services/` or API utilities            | `api` or service name              |
| Test files (`*.test.*`, `*.spec.*`)         | name of the component being tested |
| Config files (`.eslintrc`, `jest.config.*`) | tool name (e.g., `eslint`, `jest`) |
| Git hook files (`.husky/`)                  | `husky` or hook name               |
| `package.json`, lockfiles                   | `deps`                             |
| Documentation files (`*.md`, `docs/`)       | `docs` (or omit scope)             |
| Theme / global CSS files                    | `theme`                            |

Always prefer the narrowest accurate scope. Omit scope when changes span
multiple unrelated areas.

### Step 6 — Output the commit message

Print the commit message wrapped **only** inside a single markdown code block (` ``` `).
**CRITICAL: Do NOT output any conversational filler (e.g., "Here is the commit message"), tool execution logs, or thought processes outside the code block.** The final output must strictly be the code block.

By default, the commit message must include a subject, a blank line, and a
concise bullet-point body. If `no desc` is supplied, include only the subject.

Keep the code block copy-clean so the copy button never adds a trailing
newline: put the closing fence on the line directly after the last content
line (the subject in `no desc` mode, otherwise the last bullet). Never leave a
blank line, whitespace-only line, or trailing spaces before the closing fence.

Example valid outputs for `/commit no desc`:

```
feat(dropdown): add keyboard navigation support
```

```
fix(pin-input): prevent focus loss on mobile backspace
```

```
refactor(auth): extract login form into reusable LoginForm component
```

```
chore(deps): update @legion-ui-kit to v3.2.1
```

```
docs: add architecture decision for vertical slice routing
```

Example valid output for `/commit`:

```text
test(update-stock-merchant): improve unit tests for page and actions

- Add unit test coverage for UpdateStockMerchant page
- Mock API responses for success and error scenarios
- Verify form validation behaves correctly
```

---

## Common Mistakes to Avoid

1. **Wrong tense** — always use the imperative ("add", not "added" or "adds").
2. **Period at the end** — do NOT end the description with `.`
3. **Uppercase first letter in description** — keep it lowercase after the
   colon and space.
4. **Header too long** — if `type(scope): description` exceeds 72 characters,
   shorten the description; do NOT remove the scope to save space unless the
   scope genuinely does not apply.
5. **Mixing multiple unrelated changes into one message** — if the staged diff
   covers truly unrelated areas (e.g., a bug fix AND a feature), describe the
   most significant change and mention the secondary in the body. Never generate
   multiple commit messages for a single `/commit` invocation.
6. **Using `fix` for refactors** — restructuring code that works correctly is
   `refactor`, not `fix`.
7. **Ignoring the staging mode** — default mode stages all repository changes;
   `--only-staged` must leave the index unchanged. Do not limit default staging
   to the current directory or include unstaged content in an only-staged message.
8. **Omitting the default description** — include a bullet-point body without
   requiring an extra parameter. Use only the subject when `no desc` is supplied.
9. **Trailing blank line inside the code block** — the copied message must end
   on its last content line; a blank line before the closing fence pastes as an
   extra newline.

---

## Quick Reference

```text
# Trigger
/commit [--only-staged] [no desc]

# What happens
1. Resolve the repository root and detect its commit rules
2. git add -A                     → stage all, unless --only-staged
3. git diff --staged --name-only   → list staged files
4. git diff --staged               → full diff for analysis
5. Infer: type, scope, description
6. Output: ONLY one code block with the subject and bullet-point body by default;
   use only the one-line subject when no desc is supplied
```
