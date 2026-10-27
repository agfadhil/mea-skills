# mea-skills

A collection of skills to assist AI agents with writing commit messages, preparing MR/PR descriptions, creating unit tests without production changes, and remediating Trivy scan findings in iterative batches. An interactive cross-platform installer copies the skills to your user directories for Claude, Codex, and Antigravity (all three by default, or a single agent). Supports macOS, Linux, and Windows.

## Getting Started

Ensure **Node.js 20 or later** and **pnpm** are installed, then run from the root of this repository:

```sh
pnpm run mea-skills:install
```

Current version: **1.3.0**. Check the installed repository version at any time with:

```sh
pnpm run mea-skills:version
```

The installer also shows the version in its completion summary.

The installer uses Node.js built-in modules and does not require running `pnpm install` or installing external npm dependencies. The same command works across macOS/Linux terminals and Windows PowerShell or Command Prompt.

## Installation Flow

1. Choose a target:

   ```text
   1. All — Claude, Codex, and Antigravity (default)
   2. Claude
   3. Codex
   4. Antigravity
   0. Cancel
   ```

2. Review the destination path for each target. Press **Enter** to accept the default, or enter a custom path. The installer displays the resolved user path.
3. Review the complete installation plan: list of skills, copy destinations, and actions to be performed.
4. Confirm with **`[Y/n]`**. Pressing Enter or `y` proceeds; `n` cancels. File operations begin only after this confirmation.

Selecting `0`, rejecting the prompt, or terminating input before confirmation leaves all destination directories untouched. The installer copies every folder at the repository root containing a `SKILL.md` file, including supporting resources such as `scripts/` and `references/`.

### Default Locations

| Target | macOS / Linux | Windows |
| --- | --- | --- |
| Claude | `~/.claude/skills` | `%USERPROFILE%\.claude\skills` |
| Codex | `~/.codex/skills` | `%USERPROFILE%\.codex\skills` |
| Antigravity | `~/.gemini/config/skills` | `%USERPROFILE%\.gemini\config\skills` |

The Claude target uses the personal skills directory for [Claude Code](https://code.claude.com/docs/en/skills), `~/.claude/skills`. This installer's Codex target uses the skills directory under the default [Codex home](https://learn.chatgpt.com/docs/config-file/environment-variables), `~/.codex`. If you use a custom `CODEX_HOME`, enter its `skills` directory when the installer asks for a custom path. The Antigravity target follows the documented [App/IDE skill location](https://antigravity.google/docs/skills?app=antigravity-ide).

For custom paths, the installer accepts `~/...`, `$HOME/...`, `%USERPROFILE%\...`, as well as quoted paths containing spaces. Custom paths specify the copy destination; the installer does not automatically register arbitrary directories with the agent. Choose a location natively supported by your agent or configure its discovery settings.

### Updates

Run `pnpm run mea-skills:install` again whenever repository contents are updated. Skills with identical contents are skipped. Other skill folders at the destination remain untouched.

The installer prepares and verifies the new copies before replacing each selected skill folder. Updates replace the entire folder, including removing files no longer present in the source. Previous versions are overwritten without creating backup folders or retaining old snapshots.

If installation fails after replacements begin, completed updates remain installed. Run the installer again from the source repository to finish the remaining work.

## Available Skills

Open the agent chat in your working repository, then select or invoke the skill according to your agent's interface.

| Skill | Example Invocation | Purpose |
| --- | --- | --- |
| [commit-message-generator](commit-message-generator/SKILL.md) | `/commit-message-generator` | Stages all repository changes by default, then suggests a commit subject and brief bulleted body following project rules. Use `no desc` for a one-line subject; `/commit` is also supported. |
| [mr-description](mr-description/SKILL.md) | `/mr-description 6` | Generates an English MR/PR title and structured description from the last N commits, including commit IDs. Defaults to **1** commit if N is omitted. |
| [ut-ranger](ut-ranger/SKILL.md) | `$ut-ranger path` or `$ut-ranger [path1, path2]` | Creates or completes unit tests only in designated test directories, verifies tests and lint, and aims for 100% coverage without changing production code. Reports multiple targets as a numbered list in input order. |
| [trivy-porter](trivy-porter/SKILL.md) | `trivy-porter` in a terminal | Selects `fs` or `image` scans, flags, and severities locally, then hands the saved session to the agent for explanations and fixes. |
| trivy-porter — analyze | `$trivy-porter analyze SESSION_ID` in the agent chat | Reads the saved scan, explains findings in Indonesian, and creates an inventory before remediation is selected. |
| trivy-porter — continue | `$trivy-porter continue SESSION_ID` in the agent chat | Resumes a remediation batch selected in the terminal or recovers interrupted work. Defaults to one finding per batch. |

`commit-message-generator` automatically runs `git add -A` from the repository root before generating a subject and brief bullet-point description, including modified, new, and deleted files while respecting Git ignore rules. Pass `--only-staged` to preserve the current index and analyze only changes already staged. Add `no desc` for a one-line message; it combines with `--only-staged` in either order:

```text
/commit-message-generator
/commit-message-generator --only-staged
/commit-message-generator no desc
/commit-message-generator --only-staged no desc
```

`trivy-porter` automatically stages **all repository changes** after each batch and includes a commit suggestion generated via `commit-message-generator` without additional parameters, using its default subject-plus-description output; this may include preexisting uncommitted changes or prior batches. The actual commit must still be executed by the user.

### UT Ranger

Invoke the skill in the application repository with one path:

```text
$ut-ranger src/components/UserForm.tsx
```

For multiple targets, pass a comma-separated array of paths:

```text
$ut-ranger [src/components/UserForm.tsx, src/pages/Login.tsx, src/utils/formatCurrency.ts]
```

The rules are built into the skill; no extra request text or reminders are needed. The array does not need to be valid JSON: ordinary paths can be unquoted, and paths containing spaces or commas can be quoted. Relative paths resolve from the application project root.

The skill checks existing tests and coverage, adds relevant success/error/edge cases, runs test and lint verification, and compares the final changes against the initial state. It can read production code, but all changes must stay in the designated unit test directories. It creates a missing `__tests__` folder when needed and uses the application's existing tooling without changing dependencies or configuration. For multiple targets, the report uses a numbered list in input order, with status, test changes, verification results, coverage, and blockers for each path. Missing paths stay in the report while valid targets continue.

The coverage goal is 100% for statements, branches, functions, and lines. Production bugs, unreachable branches, unavailable tooling, and existing test failures are reported explicitly; the skill must not weaken tests or alter production code to claim a passing result. Invoking it without target paths prompts for the first list. `/ut-ranger` is also recognized as invocation text.

### Trivy Porter in the Terminal

Run from this repository, pointing to the application you want to scan:

```sh
pnpm run trivy-porter --project /path/to/app
```

The terminal handles the Indonesian menus, input validation, and Trivy execution locally. Press **Enter** to submit the displayed default. By default, the CLI keeps sessions in `.trivy-porter` under the terminal's current directory and prints the session ID and next action. Scan execution still takes the time required by Trivy; analysis and remediation still require the agent.

Selecting **image** builds the current project locally, then scans the built image:

```sh
docker build --platform=linux/amd64 -t app:scan .
trivy image --image-src docker --format json app:scan
```

Here `app` is the project directory name, normalized to a valid lowercase Docker image name. With `--project`, both commands run in that project. Image source and JSON format are fixed; other supported scanner/filter choices and severity remain available. The scan runs only after the build succeeds. A failed/interrupted build is saved for an explicit retry through terminal `continue`, without scanning an older image. The sanitized JSON is saved as `report.json`; `trivy-porter -d` still exports the portable upload report. Existing saved image-reference/archive sessions can still be resumed with their original source.

Add `.trivy-porter/` to the project's `.dockerignore` when session storage is inside the build context, so reports and metadata are not copied into the image. The CLI does not edit that file automatically.

After the scan, open Codex in the application project and paste the complete handoff printed by the CLI. Replace `n` with the number of findings to fix (`0` = all items at once), or drop `jumlah temuan: n` for analysis only. `--project` and `--state-dir` appear only when they differ from the defaults (terminal cwd and `<cwd>/.trivy-porter`); add `--project /path/to/app` yourself if the chat is opened in another folder. The `$trivy-porter` prefix explicitly invokes the installed skill in Codex:

```text
$trivy-porter analyze SESSION_ID jumlah temuan: n
```

The panel ends with a reminder that `trivy-porter --clean` clears local Trivy Porter data.

The completion panel separates the scan process outcome, saved session details, and next step. It adapts to terminal width and uses color when supported, respecting `NO_COLOR`. The complete copyable chat command appears outside the panel without inserted line breaks. A saved report still needs agent assessment of findings and coverage; an exit code alone is not that assessment.

Send the pasted text as a chat message; terminal commands still start with `trivy-porter` without `$`. In another agent, select the installed skill using that agent's interface and keep the same action and arguments. Legacy `/trivy-porter ...` text remains recognized by the skill for compatibility, including older `continue` handoffs for sessions awaiting initial analysis.

`analyze` is a chat instruction, not a terminal subcommand or a new scan. It analyzes saved evidence without starting remediation.

When a findings inventory is ready, return to the terminal to select the next batch:

```sh
pnpm run trivy-porter continue --project /path/to/app --session SESSION_ID
```

Then copy the printed `$trivy-porter continue ...` handoff into the agent chat to process that batch. The terminal accepts a nonnegative integer directly: `3` selects up to three related findings, while `0` requests all unresolved findings in the current inventory in one batch. Enter still selects one finding. All mode can organize work into related groups internally without another count prompt; blocked or unverified outcomes remain explicit. Each completed request stops for review before another scope is selected. Keep the same `--state-dir` when continuing a session saved in a custom location.

An integrated VS Code terminal works like any other terminal. The CLI does not automatically send messages to the Codex extension, and does not require Codex CLI, an API key, or an additional npm dependency. The saved session provides the handoff between the terminal and agent.

To expose `trivy-porter` as a command from any project, run one of these once in this repository:

| You use | Command | Result |
| --- | --- | --- |
| One Node.js version | `npm link` | Links the command into the active Node.js version's global `bin`. After switching versions with nvm, mise, or fnm, the command is not found until you run `npm link` again in that version. |
| Several Node.js versions | `pnpm run mea-skills:terminal-link` | Creates a symlink at `~/.local/bin/trivy-porter` (a `trivy-porter.cmd` file on Windows) pointing to this repository, so the command works with any active Node.js version. |

`mea-skills:terminal-link` confirms each step before changing anything: creating the `.cmd` file on Windows, choosing the destination folder, using a folder that is not on `PATH`, creating a missing folder, overwriting an existing `trivy-porter`, and adding execute permission to the script. It never runs `sudo` or requests Administrator rights; when a folder is not writable, it asks for another one. It also warns when another `trivy-porter` earlier on `PATH` (for example an old `npm link` or a mise shim) would take precedence.

When switching methods, remove the old link first so it does not shadow the new one:

| Previously used | Remove with |
| --- | --- |
| `npm link` | `npm unlink -g mea-skills` in every Node.js version where it was linked (with mise: `mise exec node@<version> -- npm unlink -g mea-skills`, then `mise reshim`) |
| `mea-skills:terminal-link` | `pnpm run mea-skills:terminal-unlink` from this repository |

`mea-skills:terminal-unlink` asks for the link folder (default `~/.local/bin`) and removes only the `trivy-porter` symlink or `trivy-porter.cmd` file that `terminal-link` created, after confirmation. A symlink pointing to another location (for example an old repository path) needs explicit approval, and files mea-skills did not create are never removed. The script, the folder, and any `npm link` stay untouched; it reports any other `trivy-porter` still on `PATH`.

Then, in your application directory:

```sh
trivy-porter
trivy-porter continue --session SESSION_ID
```

`--project` defaults to the current working directory. Keep this repository available when using its linked command. The skill installer copies skill folders and supporting scripts; it does not register this global command, but its completion summary lists both options. An installed skill can instead be run directly with Python 3, without Node.js:

```sh
python3 ~/.codex/skills/trivy-porter/scripts/trivy_porter.py --project /path/to/app
python3 ~/.codex/skills/trivy-porter/scripts/trivy_porter.py continue --project /path/to/app --session SESSION_ID
```

Adjust the installed path for your chosen destination. On Windows, use `py -3` or another Python 3 executable and the corresponding installed path, for example `%USERPROFILE%\.codex\skills\trivy-porter\scripts\trivy_porter.py` in Command Prompt.

### Storage Location and Cleanup

From your application directory, these shortcuts export the report, print a chat prompt, or remove local session storage:

```sh
trivy-porter -d          # equivalent to --download
trivy-porter --prompt
trivy-porter --clean
```

`--download` (or its shorthand `-d`) writes one self-contained, sanitized JSON report to `~/Downloads` and prints its full path. Both forms select this project's most recently updated session that has scan output; use `--session SESSION_ID` to select one explicitly, or `--download-dir /path/to/folder` to change the export destination. Source selection still accepts `--project` and `--state-dir`. Attach the exported JSON to an AI agent and ask it to analyze the findings and propose solutions. Exporting does not run a new scan or upload anything automatically; the report describes the saved scan and session snapshot.

`--prompt` prints this copyable text without reading a session, creating files, or running a scan:

```text
$trivy-porter Analisis laporan JSON terlampir, jelaskan temuannya dan rekomendasi perbaikannya.
Isi n dengan jumlah temuan; 0 = semua temuan.

Perbaiki terlebih dahulu dengan jumlah temuan: n
```

Upload the exported JSON to the agent chat, copy the printed prompt, and replace `n` before sending it. Use `0` to analyze and handle all unresolved findings in that report in the same request, or a positive integer to limit the requested batch. In all mode, the agent must not stop after the first related group or ask for the same count again. The literal `n`, a negative value, a fraction, or an absent count does not authorize remediation. All mode preserves honest blockers and verification limits; newly discovered findings outside the selected inventory need a fresh request.

`--clean` immediately removes the entire `.trivy-porter` folder in the terminal's current directory, including all partitions and unknown contents, without another confirmation. It does not use the storage environment override and cannot be combined with `--state-dir`, `--session`, `--all`, another action, or a different `--project`. A missing folder is a no-op; linked or mounted storage, an active scan/batch, or an ongoing state write is refused. Export before cleanup if you need the evidence. The default exported file in Downloads remains available after cleanup, as do files outside `.trivy-porter`, including user-selected Trivy output files.

Without `--state-dir` or a storage environment override, results stay with the directory where you run the command:

```sh
cd /path/to/app
trivy-porter
```

The storage root is `/path/to/app/.trivy-porter/`. New sessions use local creation time and scan action in the folder name: `YYYYMMDD-HHMM-image` or `YYYYMMDD-HHMM-fs`. If that name already exists, the next folder uses `-2`, `-3`, and so on. The internal session ID stays in `session.json` for chat continuation; it is not the folder name. For example:

```text
.trivy-porter/
  20261023-1430-image/
    session.json
    report.json
    scan.stderr.txt
    build.stdout.txt
    build.stderr.txt
  20261023-1440-fs/
    session.json
    ...
```

Sessions remain isolated by their saved canonical project path, even when projects share a custom storage root. Old hash/session-ID layouts remain readable without being moved. `--project` selects the scan/build directory and session identity; it does not change the storage default when you launch the CLI from somewhere else. For example, running `pnpm run trivy-porter --project /path/to/app` from this repository stores sessions under this repository's `.trivy-porter/`.

Choose a different folder with `--state-dir`:

```sh
pnpm run trivy-porter --project /path/to/app --state-dir /path/to/trivy-results
```

Relative paths resolve from the terminal's working directory. Precedence is `--state-dir`, then `TRIVY_PORTER_STATE_DIR`, then `<terminal cwd>/.trivy-porter/`; `XDG_STATE_HOME` no longer sets the default. Changing the root does not move existing sessions. Older sessions remain accessible by passing their original root, such as `--state-dir ~/.local/state/trivy-porter` (or their former XDG path). The printed chat handoff includes the resolved storage root, so the agent does not depend on inheriting your terminal's environment or current directory.

Each managed session folder and hidden `.locks` directory contains its own `.gitignore` so generated files stay out of Git without editing the storage root or application's root `.gitignore`. Already tracked storage is refused rather than silently removed from the index. For filesystem scans, the CLI displays and records a `--skip-dirs` argument for each marker-owned session/lock folder and legacy partition inside the target, leaving other files in a custom storage root visible to the scan. It preserves explicit user exclusions or the nonempty `TRIVY_SKIP_DIRS` list. If a YAML configuration's inherited exclusions cannot be established, it returns to flag customization or cancellation instead of overriding them. Verification uses the saved exclusions, and reports disclose them. Storage outside the target needs no extra scan argument.

Inspect the exact location or list sessions without running Trivy:

From the same application directory, `trivy-porter storage`, `trivy-porter sessions`, and `trivy-porter clean --all` use that directory's default storage. The `clean` subcommand still asks for confirmation and preserves the folder and unrelated files; it differs from the complete local reset flag `--clean`. For a custom root, carry its path explicitly:

```sh
pnpm run trivy-porter storage --project /path/to/app --state-dir /path/to/trivy-results
pnpm run trivy-porter sessions --project /path/to/app --state-dir /path/to/trivy-results
```

Delete one saved session, or all saved sessions for that project:

```sh
pnpm run trivy-porter clean --project /path/to/app --state-dir /path/to/trivy-results --session SESSION_ID
pnpm run trivy-porter clean --project /path/to/app --state-dir /path/to/trivy-results --all
```

The scoped `clean` subcommand previews recognized session files and asks `[y/N]`; Enter, EOF, or Ctrl+C leaves them intact. It removes saved session JSON and its stored scan artifacts only. It preserves application files, other projects, unknown files, and any user-selected Trivy `--output` file. Active scans or remediation batches must be finished before their sessions can be cleaned. Completed sessions remain available until you choose to delete them.

### Runtime Requirements

The installer only copies skill files. Agent integrations and runtime tools must be installed separately as needed:

- **commit-message-generator** and **mr-description** require Git in the working repository.
- **ut-ranger** uses the target repository's existing unit test runner, coverage tooling, and lint/format tools. Dependencies must already be available; the skill does not install them or change project configuration.
- **trivy-porter** requires Trivy, Git for staging/commit suggestions, and Python 3 for its interactive CLI and session state management. The Node launcher also requires Node.js 20 or later and automatically locates Python 3. Image scans require Docker in PATH, a running Docker daemon, and a project Dockerfile/build context that supports `linux/amd64`.
- On Windows, ensure `trivy.exe` and Git are available in both the terminal and agent's PATH. Python 3 may be invoked via `python3`, `python`, or `py -3`; ensure an executable is available when running the CLI or session helper.

## Troubleshooting Skill Discovery

Verify that each installed skill folder contains a `<skill-name>/SKILL.md` file and that the name in the YAML frontmatter matches the directory name. Claude Code picks up skills from `~/.claude/skills`; start a new session if they do not appear. Codex detects skill changes automatically; restart Codex if new skills do not appear immediately. For Antigravity, start a new agent session after installation. Refer to the [Codex documentation](https://learn.chatgpt.com/docs/build-skills) and [Antigravity documentation](https://antigravity.google/docs/skills?app=antigravity-ide) for local skill discovery details.

WSL uses a Linux home directory separate from the Windows user profile. Run the installer inside the environment where the agent operates: running from WSL installs to the WSL home directory, whereas running from native Windows installs to the Windows user profile. For remote or containerized environments, verify the path read by the agent in that container. After installation, start a new agent session if changes are not detected.

## Versioning

The repository version lives in `package.json` and starts at `1.0.0` (run `pnpm run mea-skills:version` to print it). Every push to `main` runs [`.github/workflows/bump-version.yml`](.github/workflows/bump-version.yml), which bumps the minor version (`1.0.0` → `1.1.0` → `1.2.0` …), commits it as `chore(release): vX.Y.0 [skip ci]`, and creates a matching annotated `vX.Y.0` tag. The release commit and tag message list every commit since the previous tag, one per line as `- <subject> (<short hash>)`, skipping merge and earlier release commits. The npm `version` script runs [`scripts/sync-readme-version.mjs`](scripts/sync-readme-version.mjs) during the bump, so the "Current version" line in this README is updated in the same release commit and always matches `package.json` and the tag; the script fails the release if that line is missing. Run `git pull` after pushing to pick up the release commit. For a major release, run `npm version major` locally and push with `--follow-tags`; the next push continues from the new major (`2.0.0` → `2.1.0`).

## Testing

```sh
pnpm test
pnpm run test:trivy-porter
```

Run tests from the repository root. `pnpm test` checks the Node launcher and skill installer; `pnpm run test:trivy-porter` checks the Python CLI and session workflow using local fixtures, without a real scan. The Python test command requires `python3`; if your system provides Python 3 as `python` or `py -3`, use that executable with `-B -m unittest discover -s tests -p "test_*.py"`. Neither the installer nor the test suite requires installing npm dependencies.
