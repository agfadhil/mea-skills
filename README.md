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
| [trivy-porter](trivy-porter/SKILL.md) | `/trivy-porter` | Interactively selects `fs` or `image` scans, flags, and severities, then explains findings in Indonesian and fixes them in batches. Defaults to one finding per batch. |
| trivy-porter — continue | `/trivy-porter continue` | Resumes a previous session, provides a summary, and prompts for the batch size for the next iteration. |

`commit-message-generator` requires changes to already be staged. `trivy-porter` automatically stages **all repository changes** after each batch and includes a commit suggestion generated via `commit-message-generator with desc`; this may include preexisting uncommitted changes or prior batches. The actual commit must still be executed by the user.

### Runtime Requirements

The installer only copies skill files. The IDE/agent extension, Git, Trivy, and Python must be installed separately as needed:

- **commit-message-generator** and **mr-description** require Git in the working repository.
- **trivy-porter** requires Trivy, Git for staging/commit suggestions, and Python 3 for session state management. The container image workflow also requires container runtime/image access and an appropriate build environment when rebuilding images.
- On Windows, ensure `trivy.exe` and Git are available in the agent's PATH. Python 3 may be invoked via `python3`, `python`, or `py -3`; ensure an executable is available when running the session helper.

## Troubleshooting Skill Discovery

Verify that each installed skill folder contains a `<skill-name>/SKILL.md` file and that the name in the YAML frontmatter matches the directory name. In VS Code, run **Chat: Open Customizations**; in Antigravity, check the **Customizations** menu in the agent panel. Codex detects skill changes automatically; restart Codex if new skills do not appear immediately. Refer to the [Codex documentation](https://learn.chatgpt.com/docs/build-skills) for local skill discovery details.

WSL uses a Linux home directory separate from the Windows user profile. Run the installer inside the environment where the agent operates: running from WSL installs to the WSL home directory, whereas running from native Windows installs to the Windows user profile. For remote or containerized environments, verify the path read by the agent in that container. After installation, start a new chat session or reload the IDE window if changes are not detected.

## Testing

```sh
pnpm test
```

Run tests from the repository root. Neither the installer nor the test suite requires installing npm dependencies.
