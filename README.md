# mea-skills

A collection of skills to assist AI agents with writing commit messages, preparing MR/PR descriptions, and remediating Trivy scan findings in iterative batches. An interactive cross-platform installer copies the skills to your user directories for Codex, Antigravity, or both. Supports macOS, Linux, and Windows.

## Getting Started

Ensure **Node.js 20 or later** and **pnpm** are installed, then run from the root of this repository:

```sh
pnpm run install:skills
```

The installer uses Node.js built-in modules and does not require running `pnpm install` or installing external npm dependencies. The same command works across macOS/Linux terminals and Windows PowerShell or Command Prompt.

## Installation Flow

1. Choose a target:

   ```text
   1. Both — Codex and Antigravity (default)
   2. Codex
   3. Antigravity
   0. Cancel
   ```

2. Review the destination path for each target. Press **Enter** to accept the default, or enter a custom path. The installer displays the resolved user path.
3. Review the complete installation plan: list of skills, copy destinations, and actions to be performed.
4. Confirm with **`[Y/n]`**. Pressing Enter or `y` proceeds; `n` cancels. File operations begin only after this confirmation.

Selecting `0`, rejecting the prompt, or terminating input before confirmation leaves all destination directories untouched. The installer copies every folder at the repository root containing a `SKILL.md` file, including supporting resources such as `scripts/` and `references/`.

### Default Locations

| Target | macOS / Linux | Windows |
| --- | --- | --- |
| Codex | `~/.codex/skills` | `%USERPROFILE%\.codex\skills` |
| Antigravity | `~/.gemini/config/skills` | `%USERPROFILE%\.gemini\config\skills` |

This installer's Codex target uses the skills directory under the default [Codex home](https://learn.chatgpt.com/docs/config-file/environment-variables), `~/.codex`. If you use a custom `CODEX_HOME`, enter its `skills` directory when the installer asks for a custom path. The Antigravity target follows the documented [App/IDE skill location](https://antigravity.google/docs/skills?app=antigravity-ide).

For custom paths, the installer accepts `~/...`, `$HOME/...`, `%USERPROFILE%\...`, as well as quoted paths containing spaces. Custom paths specify the copy destination; the installer does not automatically register arbitrary directories with the agent. Choose a location natively supported by your agent or configure its discovery settings.

### Updates

Run `pnpm run install:skills` again whenever repository contents are updated. Skills with identical contents are skipped. Other skill folders at the destination remain untouched.

The installer prepares and verifies the new copies before replacing each selected skill folder. Updates replace the entire folder, including removing files no longer present in the source. Previous versions are overwritten without creating backup folders or retaining old snapshots.

If installation fails after replacements begin, completed updates remain installed. Run the installer again from the source repository to finish the remaining work.

## Available Skills

Open the agent chat in your working repository, then select or invoke the skill according to your agent's interface.

| Skill | Example Invocation | Purpose |
| --- | --- | --- |
| [commit-message-generator](commit-message-generator/SKILL.md) | `/commit-message-generator` | Stages all repository changes by default, then suggests a commit subject and brief bulleted body following project rules. Use `no desc` for a one-line subject; `/commit` is also supported. |
| [mr-description](mr-description/SKILL.md) | `/mr-description 6` | Generates an English MR/PR title and structured description from the last N commits, including commit IDs. Defaults to **1** commit if N is omitted. |
| [trivy-porter](trivy-porter/SKILL.md) | `trivy-porter` in a terminal | Selects `fs` or `image` scans, flags, and severities locally, then hands the saved session to the agent for explanations and fixes. |
| trivy-porter — continue | `/trivy-porter continue SESSION_ID` in the agent chat | Reads the saved session, explains findings in Indonesian, and remediates the batch selected in the terminal. Defaults to one finding per batch. |

`commit-message-generator` automatically runs `git add -A` from the repository root before generating a subject and brief bullet-point description, including modified, new, and deleted files while respecting Git ignore rules. Pass `--only-staged` to preserve the current index and analyze only changes already staged. Add `no desc` for a one-line message; it combines with `--only-staged` in either order:

```text
/commit-message-generator
/commit-message-generator --only-staged
/commit-message-generator no desc
/commit-message-generator --only-staged no desc
```

`trivy-porter` automatically stages **all repository changes** after each batch and includes a commit suggestion generated via `commit-message-generator` without additional parameters, using its default subject-plus-description output; this may include preexisting uncommitted changes or prior batches. The actual commit must still be executed by the user.

### Trivy Porter in the Terminal

Run from this repository, pointing to the application you want to scan:

```sh
pnpm run trivy-porter --project /path/to/app
```

The terminal handles the Indonesian menus, input validation, and Trivy execution locally. Press **Enter** to submit the displayed default. By default, the CLI keeps sessions in `.trivy-porter` under the terminal's current directory and prints the session ID and next action. Scan execution still takes the time required by Trivy; analysis and remediation still require the agent.

After the scan, open Codex or another compatible agent in the application project and copy the complete handoff printed by the CLI, including its project and storage paths:

```text
/trivy-porter continue SESSION_ID --project /path/to/app --state-dir /path/to/trivy-results
```

When a findings inventory is ready, return to the terminal to select the next batch:

```sh
pnpm run trivy-porter continue --project /path/to/app --session SESSION_ID
```

Then copy the printed `/trivy-porter continue ...` handoff into the agent chat to process that batch. The terminal accepts a positive integer directly; `3` selects up to three related findings. Each completed batch stops for review before another batch is selected. Keep the same `--state-dir` when continuing a session saved in a custom location.

An integrated VS Code terminal works like any other terminal. The CLI does not automatically send messages to the Codex extension, and does not require Codex CLI, an API key, or an additional npm dependency. The saved session provides the handoff between the terminal and agent.

To expose `trivy-porter` as a command from any project, optionally run `npm link` once in this repository. Then, in your application directory:

```sh
trivy-porter
trivy-porter continue --session SESSION_ID
```

`--project` defaults to the current working directory. Keep this repository available when using its linked command. The skill installer copies skill folders and supporting scripts; it does not register this global command. An installed skill can instead be run directly with Python 3, without Node.js:

```sh
python3 ~/.codex/skills/trivy-porter/scripts/trivy_porter.py --project /path/to/app
python3 ~/.codex/skills/trivy-porter/scripts/trivy_porter.py continue --project /path/to/app --session SESSION_ID
```

Adjust the installed path for your chosen destination. On Windows, use `py -3` or another Python 3 executable and the corresponding installed path, for example `%USERPROFILE%\.codex\skills\trivy-porter\scripts\trivy_porter.py` in Command Prompt.

### Storage Location and Cleanup

From your application directory, these shortcuts export the report, print a chat prompt, or remove local session storage:

```sh
trivy-porter --download
trivy-porter --prompt
trivy-porter --clean
```

`--download` writes one self-contained, sanitized JSON report to `~/Downloads` and prints its full path. It selects this project's most recently updated session that has scan output; use `--session SESSION_ID` to select one explicitly, or `--download-dir /path/to/folder` to change the export destination. Source selection still accepts `--project` and `--state-dir`. Attach the exported JSON to an AI agent and ask it to analyze the findings and propose solutions. Exporting does not run a new scan or upload anything automatically; the report describes the saved scan and session snapshot.

`--prompt` prints this copyable text without reading a session, creating files, or running a scan:

```text
$trivy-porter Analisis laporan JSON terlampir, jelaskan temuannya dan rekomendasi perbaikannya.

Perbaiki terlebih dahulu dengan jumlah temuan: n
```

Upload the exported JSON to the agent chat, copy the printed prompt, and replace `n` with a positive number before sending it. The placeholder itself does not select a batch.

`--clean` immediately removes the entire `.trivy-porter` folder in the terminal's current directory, including all partitions and unknown contents, without another confirmation. It does not use the storage environment override and cannot be combined with `--state-dir`, `--session`, `--all`, another action, or a different `--project`. A missing folder is a no-op; linked or mounted storage, an active scan/batch, or an ongoing state write is refused. Export before cleanup if you need the evidence. The default exported file in Downloads remains available after cleanup, as do files outside `.trivy-porter`, including user-selected Trivy output files.

Without `--state-dir` or a storage environment override, results stay with the directory where you run the command:

```sh
cd /path/to/app
trivy-porter
```

The storage root is `/path/to/app/.trivy-porter/`. Each project's sessions are separated in a subdirectory based on its canonical path. `--project` selects the scan directory and session identity; it does not change the storage default when you launch the CLI from somewhere else. For example, running `pnpm run trivy-porter --project /path/to/app` from this repository stores sessions under this repository's `.trivy-porter/`.

Choose a different folder with `--state-dir`:

```sh
pnpm run trivy-porter --project /path/to/app --state-dir /path/to/trivy-results
```

Relative paths resolve from the terminal's working directory. Precedence is `--state-dir`, then `TRIVY_PORTER_STATE_DIR`, then `<terminal cwd>/.trivy-porter/`; `XDG_STATE_HOME` no longer sets the default. Changing the root does not move existing sessions. Older sessions remain accessible by passing their original root, such as `--state-dir ~/.local/state/trivy-porter` (or their former XDG path). The printed chat handoff includes the resolved storage root, so the agent does not depend on inheriting your terminal's environment or current directory.

Each managed hash partition contains its own `.gitignore` so generated session files stay out of Git without editing the storage root or application's root `.gitignore`. Already tracked storage is refused rather than silently removed from the index. For filesystem scans, the CLI displays and records a `--skip-dirs` argument for each marker-owned managed partition inside the target, leaving other files in a custom storage root visible to the scan. It preserves explicit user exclusions or the nonempty `TRIVY_SKIP_DIRS` list. If a YAML configuration's inherited exclusions cannot be established, it returns to flag customization or cancellation instead of overriding them. Verification uses the saved exclusions, and reports disclose them. Storage outside the target needs no extra scan argument.

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

The installer only copies skill files. The IDE/agent extension, Git, Trivy, and Python must be installed separately as needed:

- **commit-message-generator** and **mr-description** require Git in the working repository.
- **trivy-porter** requires Trivy, Git for staging/commit suggestions, and Python 3 for its interactive CLI and session state management. The Node launcher also requires Node.js 20 or later and automatically locates Python 3. The container image workflow also requires container runtime/image access and an appropriate build environment when rebuilding images.
- On Windows, ensure `trivy.exe` and Git are available in both the terminal and agent's PATH. Python 3 may be invoked via `python3`, `python`, or `py -3`; ensure an executable is available when running the CLI or session helper.

## Troubleshooting Skill Discovery

Verify that each installed skill folder contains a `<skill-name>/SKILL.md` file and that the name in the YAML frontmatter matches the directory name. Codex detects skill changes automatically; restart Codex if new skills do not appear immediately. For Antigravity, start a new agent session after installation. Refer to the [Codex documentation](https://learn.chatgpt.com/docs/build-skills) and [Antigravity documentation](https://antigravity.google/docs/skills?app=antigravity-ide) for local skill discovery details.

WSL uses a Linux home directory separate from the Windows user profile. Run the installer inside the environment where the agent operates: running from WSL installs to the WSL home directory, whereas running from native Windows installs to the Windows user profile. For remote or containerized environments, verify the path read by the agent in that container. After installation, start a new agent session if changes are not detected.

## Testing

```sh
pnpm test
pnpm run test:trivy-porter
```

Run tests from the repository root. `pnpm test` checks the Node launcher and skill installer; `pnpm run test:trivy-porter` checks the Python CLI and session workflow using local fixtures, without a real scan. The Python test command requires `python3`; if your system provides Python 3 as `python` or `py -3`, use that executable with `-B -m unittest discover -s tests -p "test_*.py"`. Neither the installer nor the test suite requires installing npm dependencies.
