# mea-skills

A collection of skills to assist AI agents with writing commit messages, preparing MR/PR descriptions, and remediating Trivy scan findings in iterative batches. An interactive cross-platform installer copies the skills to your user directories for VS Code (Copilot/Codex), Antigravity IDE, or both. Supports macOS, Linux, and Windows.

## Getting Started

Ensure **Node.js 20 or later** and **pnpm** are installed, then run from the root of this repository:

```sh
pnpm run install:skills
```

The installer uses Node.js built-in modules and does not require running `pnpm install` or installing external npm dependencies. The same command works across macOS/Linux terminals and Windows PowerShell or Command Prompt.

## Installation Flow

1. Choose a target:

   ```text
   1. Both — VS Code and Antigravity IDE (default)
   2. VS Code — Copilot/Codex
   3. Antigravity IDE
   0. Cancel
   ```

2. Review the destination path for each target. Press **Enter** to accept the default, or enter a custom path. The installer displays the resolved user path.
3. Review the complete installation plan: list of skills, copy destinations, and actions to be performed.
4. Confirm with **`[Y/n]`**. Pressing Enter or `y` proceeds; `n` cancels. File operations begin only after this confirmation.

Selecting `0`, rejecting the prompt, or terminating input before confirmation leaves all destination directories untouched. The installer copies every folder at the repository root containing a `SKILL.md` file, including supporting resources such as `scripts/` and `references/`.

### Default Locations

| Target | macOS / Linux | Windows |
| --- | --- | --- |
| VS Code — Copilot/Codex | `~/.agents/skills` | `%USERPROFILE%\.agents\skills` |
| Antigravity IDE | `~/.gemini/config/skills` | `%USERPROFILE%\.gemini\config\skills` |

The personal `~/.agents/skills` directory is supported by [VS Code Agent Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills) and [Codex](https://learn.chatgpt.com/docs/build-skills). The Antigravity location follows the [IDE skills documentation](https://www.antigravity.google/docs/skills?tab=ide).

For custom paths, the installer accepts `~/...`, `$HOME/...`, `%USERPROFILE%\...`, as well as quoted paths containing spaces. Custom paths specify the copy destination; the installer does not automatically register arbitrary directories with the IDE. Choose a location natively supported by your agent or configure custom discovery paths in your IDE settings.

### Updates and Backups

Run `pnpm run install:skills` again whenever repository contents are updated. Skills with identical contents are skipped. Other existing skills at the destination remain untouched.

Before replacing a skill whose contents have changed, the installer backs up the previous version into a backup folder alongside the destination `skills` directory:

```text
<destination-parent-folder>/.mea-skills-backups/<run-id>/<target-id>/<skill-name>/
```

For example, backups for the `~/.agents/skills` target are stored in `~/.agents/.mea-skills-backups/`. Backups reside outside the skill root directory so they are not inadvertently discovered as active skills. Check the backup path printed by the installer if you need to restore an earlier version.

## Available Skills

Open the agent chat in your working repository, then select or invoke the skill according to your IDE's interface.

| Skill | Example Invocation | Purpose |
| --- | --- | --- |
| [commit-message-generator](commit-message-generator/SKILL.md) | `/commit-message-generator with desc` | Analyzes staged diffs and project rules to suggest a conventional commit header and bulleted body. The `/commit with desc` alias is also supported. |
| [mr-description](mr-description/SKILL.md) | `/mr-description 6` | Generates an English MR/PR title and structured description from the last N commits, including commit IDs. Defaults to **1** commit if N is omitted. |
| [trivy-porter](trivy-porter/SKILL.md) | `trivy-porter` in a terminal | Selects `fs` or `image` scans, flags, and severities locally, then hands the saved session to the agent for explanations and fixes. |
| trivy-porter — continue | `/trivy-porter continue SESSION_ID` in the agent chat | Reads the saved session, explains findings in Indonesian, and remediates the batch selected in the terminal. Defaults to one finding per batch. |

`commit-message-generator` requires changes to already be staged. `trivy-porter` automatically stages **all repository changes** after each batch and includes a commit suggestion generated via `commit-message-generator with desc`; this may include preexisting uncommitted changes or prior batches. The actual commit must still be executed by the user.

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
python3 ~/.agents/skills/trivy-porter/scripts/trivy_porter.py --project /path/to/app
python3 ~/.agents/skills/trivy-porter/scripts/trivy_porter.py continue --project /path/to/app --session SESSION_ID
```

Adjust the installed path for your chosen destination. On Windows, use `py -3` or another Python 3 executable and the corresponding installed path, for example `%USERPROFILE%\.agents\skills\trivy-porter\scripts\trivy_porter.py` in Command Prompt.

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

Verify that each installed skill folder contains a `<skill-name>/SKILL.md` file and that the name in the YAML frontmatter matches the directory name. In VS Code, run **Chat: Open Customizations**; in Antigravity, check the **Customizations** menu in the agent panel. Codex detects skill changes automatically; restart Codex if new skills do not appear immediately. Refer to the [Codex documentation](https://learn.chatgpt.com/docs/build-skills) for local skill discovery details.

WSL uses a Linux home directory separate from the Windows user profile. Run the installer inside the environment where the agent operates: running from WSL installs to the WSL home directory, whereas running from native Windows installs to the Windows user profile. For remote or containerized environments, verify the path read by the agent in that container. After installation, start a new chat session or reload the IDE window if changes are not detected.

## Testing

```sh
pnpm test
pnpm run test:trivy-porter
```

Run tests from the repository root. `pnpm test` checks the Node launcher; `pnpm run test:trivy-porter` checks the Python CLI and session workflow using local fixtures, without a real scan. The Python test command requires `python3`; if your system provides Python 3 as `python` or `py -3`, use that executable with `-B -m unittest discover -s tests -p "test_*.py"`. Neither the installer nor the test suite requires installing npm dependencies.
