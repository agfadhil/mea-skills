---
name: mr-synthesize
description: Generate a merge request or pull request title and description from recent git commits. Use when the user types "/mr-synthesize N", asks for an MR/PR title and description, wants to summarize the last N commits, or asks to prepare a GitLab merge request description from commit history.
---

# MR Synthesize

## Overview

Use this skill to inspect the latest N commits in the current git repository and generate a clear merge request title and description. The result should be ready to paste into GitLab, GitHub, or a similar review tool.

The primary trigger is:

```text
/mr-synthesize <number of commits behind>
```

Example:

```text
/mr-synthesize 6
```

## Workflow

### Step 1 - Parse the commit count

Read the positive integer after `/mr-synthesize`.

If no number is provided, use `1` as the default and mention that assumption briefly before doing the work.

If the number is invalid, stop and ask for a valid positive integer.

### Step 2 - Confirm repository context

Run:

```bash
git rev-parse --show-toplevel
git branch --show-current
```

If not inside a git repository, stop and tell the user to run the command from inside a git project.

### Step 3 - Inspect commits from newest to oldest

Run these commands, replacing `<N>` with the requested count:

```bash
git log -<N> --oneline --decorate
git log -<N> --name-status --pretty=format:'commit %H%n%s%n%b'
```

Keep the selected commit IDs and subjects for the Commits section. Use the same selection and newest-to-oldest order throughout the output.

Treat merge commits as context, but do not let a generic merge message dominate the MR title.

### Step 4 - Inspect the actual changes

Collect enough detail to understand the user-facing impact and changed areas:

```bash
git show --stat --summary --find-renames <commit>
git diff --stat HEAD~<N>..HEAD
git diff --name-status HEAD~<N>..HEAD
```

For important commits, inspect focused diffs with:

```bash
git show --format=medium <commit> -- <relevant-paths>
```

Use `rg`, `sed`, or targeted file reads if current code context is needed.

### Step 5 - Determine the MR story

Group the commits by product area or technical area. Identify:

- The primary feature, bug fix, or refactor.
- Secondary improvements that reviewers should know about.
- Any dependency removals, shared component changes, or behavior changes.
- Any test evidence visible in commits or run during the current session.

Prefer the overall outcome over commit-by-commit narration.

### Step 6 - Generate title and description

Write the MR title and description in English, including section headings and commit summaries. Write the title as a concise imperative or outcome-oriented phrase.

Good title patterns:

```text
Enhance NIB incomplete photo capture flow
Add reusable camera capture for verification uploads
Fix gallery upload flow for NIB verification
```

Avoid:

- Generic merge titles, such as `Merge branch ...`.
- Overly broad titles, such as `Update code`.
- Titles that only mention styling when the commits include behavior changes.

Write the description in clean Markdown with monochrome text symbols in section headings. Keep a blank line after each heading, use standard bullets, and avoid colored emoji, badges, or decorative HTML. Use this default shape:

```markdown
## ◇ Summary

- ...
- ...

## ▣ Scope

- ...
- ...

## ≡ Commits

- `<commit-id>` — English summary of the commit.

## ✓ Testing

- Not run locally.
```

Keep the Commits section immediately after Scope and before Testing. List every commit selected in Step 3 exactly once, newest to oldest, including merge commits. Each list item must contain the real, unambiguous abbreviated commit ID from Git in inline code and a concise English summary. Translate non-English commit subjects as needed while preserving their meaning and IDs. Never invent commit IDs or add commits outside the selected set. This list represents the selected N commits; do not claim it is the complete target-branch MR history without verifying that separately.

Adjust the sections when useful while preserving the Scope → Commits → Testing order:

- Use `## ◇ Changes` instead of `## ◇ Summary` if the project commonly uses that.
- Add `## ※ Notes` after Testing for migration, dependency, or reviewer notes.
- Add `## ! Risk` after Testing only when there is a meaningful risk worth calling out.
- Replace `Not run locally.` with commands actually run and their results.

## Output Requirements

Return a concise final answer with:

- A `**Title**` section containing the MR title wrapped inside a Markdown code fence (` ``` `) so the user can easily copy the title string directly using the code block copy button.
- A `**Description**` section containing the MR description inside a `markdown` code fence. Keep the commit IDs in inline code inside that fence.

Keep both code blocks copy-clean so the copy button never adds a trailing newline:

- Put the closing fence on the line directly after the last content line. Never leave a blank line, whitespace-only line, or trailing spaces before the closing fence.
- The title block contains exactly one line: the title itself.
- The description block ends with its last bullet or sentence, with no blank line after it.

Do not include raw git output unless the user asks for it.

If the user asks for "just the MR content", output only the title and description content without explanation.

