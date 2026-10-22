# Stage all changes and suggest a commit

After every remediation batch, complete verification, stage all repository changes, generate a suggested commit message with a description, include it in the Indonesian report, and stop. The user performs the commit. This is preparation only: do not run `git commit` or push.

## 1. Stage the whole repository

Resolve the repository root with `git rev-parse --show-toplevel`. Inspect `git status --short` and the current staged scope, noting pre-existing and earlier-batch changes. Record the Git step as pending before mutating the index.

For project-local session storage, check that the active partition and any other managed partitions under the selected storage root within this repository are ignored and have no tracked files before staging. Each partition's managed `.gitignore` should keep generated state out of `git add -A`; an ignore rule cannot protect files already tracked. If state files are tracked or an ignore rule is missing/changed, record Git preparation as blocked and explain it. Do not force-add, automatically untrack, or unstage those files. This does not narrow staging of application changes.

Run from the repository root, with the root passed as a literal argument:

```text
git -C REPO_ROOT add -A
git -C REPO_ROOT diff --staged --name-status
git -C REPO_ROOT diff --staged --stat
```

The user explicitly requested **all changes**: include additions, modifications, deletions, pre-existing work, and previous batches that remain uncommitted. Do not replace this with staging only remediation files or ask for confirmation merely because unrelated work exists. Preserve normal ignore rules; do not force-add ignored files. Do not reset, clean, restore, unstage, or otherwise discard user work to isolate a batch.

If the repository has unresolved merge conflicts, do not mark them resolved by staging conflict markers. If Git is unavailable, no repository exists, or staging fails, record the Git preparation as blocked and report the actual cause. Do not initialize a repository for a non-Git scan target. Keep completed remediation evidence and existing index contents; do not claim all changes were staged or bypass an index lock. Do not generate a message that pretends a failed staging step succeeded.

If staging succeeds but the index is empty, record `skipped_empty`, explain that there are no staged changes, and omit a fabricated commit suggestion. This is not a reason to make extra edits.

## 2. Invoke the companion skill

Discover and read the available skill named `commit-message-generator`, then invoke its workflow without additional parameters, using its default subject-plus-description output:

```text
/commit-message-generator
```

Use the skill installed in the current environment. Do not treat the slash invocation as a shell executable or silently substitute a hand-written message. If the skill is missing, preserve the staged changes, mark generation blocked, and report the missing dependency and its searched location.

The generator must inspect the **entire current staged diff**, detect the project's commit rules, and produce one compliant message: a subject, a blank line, and a concise bullet-point description. Follow its detected language/format conventions. Do not generate a message based only on remembered findings or the latest batch if other changes are staged.

The companion skill returns only a single code block. Capture that block as this step's result and embed it unchanged under `Saran commit message` in the broader Trivy report. Its output-only rule does not remove the required findings, impact, solution, and verification report.

## 3. Persist and report the result

Store per batch:

- Repository root, current HEAD (or null for an unborn branch), staging command/result, staged file statuses, and a fingerprint of the staged diff.
- Whether the staged scope includes pre-existing or previous-batch changes.
- Generator skill name, arguments (empty or omitted for the default invocation), generation status, and complete suggested message.
- Any blocker and the pending Git substep needed for continuation.

Use statuses such as `pending`, `staged`, `generated`, `skipped_empty`, or `blocked` for this preparation; they do not replace finding statuses. A dependency test or scan failure must remain visible even when its changes are staged and a suggestion has been generated.

The report must show staging status/scope and the subject-plus-description in one copyable code block. Explain if the suggestion covers cumulative or unrelated staged work. Leave the index staged for the user; do not commit automatically or claim a commit hash was created.

## 4. Continue without stale messages

On `/trivy-porter continue`, compare the actual current HEAD, index, and repository state with saved evidence. The user may have committed, edited, staged, or unstaged files after the previous report. A saved message is historical unless both its HEAD and staged-diff fingerprint still match; regenerate from the current index after the required staging step when preparing a batch completion report. A normal continuation recap does not itself trigger staging or bypass the fresh batch-size question.

If interruption occurred between remediation, staging, and generation, finish only the pending substeps for that batch, save and report the result, then stop. A staging/generation blocker is not permission to start a new remediation batch. Return to terminal continue for a fresh batch request before any additional findings are selected.
