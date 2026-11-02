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

Look for a commitlint config in the repository root (use the same lookup order
as commitlint itself and stop at the first hit):

1. `package.json` with a top-level `commitlint` key
2. `.commitlintrc`, `.commitlintrc.json`, `.commitlintrc.yaml`,
   `.commitlintrc.yml`
3. `.commitlintrc.js`, `.commitlintrc.cjs`, `.commitlintrc.mjs`,
   `.commitlintrc.ts`, `.commitlintrc.cts`
4. `commitlint.config.js`, `commitlint.config.cjs`, `commitlint.config.mjs`,
   `commitlint.config.ts`, `commitlint.config.cts`

If the invocation directory is a subfolder with its own config (monorepo
package), that nearer config wins over the root one.

Resolve the **effective** rules, not just the file's own overrides:

- Read the config file. Never assume its contents from the filename.
- Follow `extends` (e.g., `@commitlint/config-conventional`,
  `@commitlint/config-angular`, a shared or relative config). Read the preset
  from `node_modules/` when it is installed; the file's own `rules` override
  the preset's.
- If a local commitlint binary exists (`node_modules/.bin/commitlint`), prefer
  `npx --no-install commitlint --print-config` to get the fully resolved rules.
  Never let this trigger a network install; fall back to reading files if it
  fails or is unavailable.
- Note `parserPreset` (a custom `headerPattern` changes the required header
  shape, e.g. a ticket id prefix) and `ignores`/`defaultIgnores`.
- Note the associated **git hook** (usually `.husky/commit-msg` or
  `.git/hooks/commit-msg`) to confirm commitlint is actually enforced.

Rules have the form `[level, applicable, value]`. Level `2` (error) is mandatory;
level `1` (warning) should be followed whenever possible; level `0` is disabled
and must be ignored. `applicable` is `always` or `never` (rule negated). Map the
common rules onto the message like this:

| Rule(s)                                                     | Applies to                                      |
| ----------------------------------------------------------- | ----------------------------------------------- |
| `type-enum`, `type-case`, `type-empty`                      | choose only listed types; casing; type required |
| `scope-enum`, `scope-case`, `scope-empty`                   | choose only listed scopes; casing; scope needed |
| `subject-case`, `subject-empty`, `subject-full-stop`        | description casing, required, trailing period   |
| `subject-min-length`, `subject-max-length`                  | description length                              |
| `header-max-length`, `header-min-length`, `header-case`     | whole first line                                |
| `body-leading-blank`, `body-empty`, `body-min-length`       | blank line after header; body required/length   |
| `body-max-length`, `body-max-line-length`, `body-case`      | body size, line wrapping, casing                |
| `footer-leading-blank`, `footer-empty`, `footer-max-*`      | footer separation, presence, length             |
| `references-empty`, `signed-off-by`, `trailer-exists`       | issue refs / `Signed-off-by:` / required trailer |

A `subject-case` of `never` with a list means every listed case is forbidden
(e.g. `never: [sentence-case, start-case, pascal-case, upper-case]` still
allows lowercase). Compute the allowed set; do not just guess.

**These rules take precedence over every default in this skill** (the 72
character limits, the lowercase description, the type table, bullet wrapping,
and so on). Where the config is silent on something, fall back to the default.

- Never invent values required by a rule. For `references-empty: never`, take
  the issue/ticket id from the branch name (`git branch --show-current`) or
  recent commits; if none can be found, omit it rather than fabricate one.
- In `no desc` mode, still output only the subject even if a body rule such as
  `body-empty: never` exists, because the explicit invocation wins.

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
Detection is silent: never mention the config or rules in the final output.

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

If a local commitlint binary exists, validate the drafted message before
printing it, without touching the index or creating a commit:

```sh
printf '%s' "<message>" | npx --no-install commitlint
```

(Use `--config <file>` only if the config is not discoverable from the
repository root.) If it reports errors, fix the message and re-validate; stop
after a few attempts and output the best compliant draft. Skip this check
silently when commitlint is not installed locally. Validation output must never
appear in the final reply.

#### Copy-clean output (strict)

The user clicks the code block's copy button and pastes straight into a commit
message input. The pasted text must end exactly on the last character of the
message, with the cursor sitting right after it, not on a new line. Build the
final block like this:

1. Open the fence (` ```text `) and put the subject on the very next line. No
   blank line or space before the subject.
2. The last content line is the final bullet (or the subject in `no desc`
   mode). Its last character is the last character of the message: no trailing
   period added for style, no trailing spaces, no tab.
3. Put the closing fence on the line **directly after** that last content line.
   There must be no blank line, whitespace-only line, or extra newline between
   them.
4. No trailing spaces on any line of the message.
5. Do not put anything after the closing fence (no sign-off, no explanation, no
   second code block).

Correct (the closing fence touches the last line):

````text
```text
fix(auth): prevent token refresh loop

- Stop retrying refresh when the server returns 401
```
````

Wrong (a blank line before the closing fence pastes as a trailing newline):

````text
```text
fix(auth): prevent token refresh loop

- Stop retrying refresh when the server returns 401

```
````

Re-check this shape just before printing; if the draft violates any point, fix
it first.

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
9. **Trailing newline in the copied text** — the copied message must end on
   its last character. A blank line, whitespace-only line, or trailing spaces
   before the closing fence paste as an extra newline, and any text after the
   fence breaks the clean copy. See "Copy-clean output (strict)" in Step 6.
10. **Ignoring commitlint** — when a commitlint config exists, its enabled
    rules (types, scopes, lengths, casing) override this skill's defaults. Do
    not apply the default 72-character limit if the config allows 100, and do
    not use a type or scope outside its enums.

---

## Quick Reference

```text
# Trigger
/commit [--only-staged] [no desc]

# What happens
1. Resolve the repository root and detect its commit rules (commitlint config
   first, resolving `extends`; then docs; then git history)
2. git add -A                     → stage all, unless --only-staged
3. git diff --staged --name-only   → list staged files
4. git diff --staged               → full diff for analysis
5. Infer: type, scope, description (within the detected commitlint rules)
6. Validate with local commitlint if installed (silent)
7. Output: ONLY one code block with the subject and bullet-point body by default;
   use only the one-line subject when no desc is supplied
```
