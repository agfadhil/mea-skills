---
name: trivy-porter
description: Run interactive Trivy filesystem or image scans, explain findings in Indonesian, remediate in resumable batches, and stage all changes with commit-message suggestions while preserving application behavior. Use when the user invokes /trivy-porter or /trivy-porter continue, or explicitly requests this interactive scan-and-remediation workflow.
---

# Trivy Porter

Guide the user through scan choices, run the chosen command, and fix findings in bounded batches. After every remediation batch, stage all repository changes and generate a commit suggestion using the companion skill `commit-message-generator` with `with desc`. Leave the actual commit to the user. Use Indonesian for questions, explanations, inventories, and reports; preserve the generated commit message's project conventions. Keep CLI flags, package names, advisory IDs, and severity labels unchanged.

## Entry points and defaults

- `/trivy-porter`: start a new session and ask for the scan method first.
- `/trivy-porter continue`: resume a saved session; do not restart configuration or silently launch a batch.
- The skill name is `trivy-porter`; the leading slash belongs to its invocation.
- Put the default first in every menu. Default method: `fs`; custom flags: none; severity: all; batch size: `1`.
- A submitted blank answer or Enter accepts the displayed default. A preselected option, elapsed time, or silence is not a submitted answer. If the interface cannot submit a blank answer, accept `1` or `default`.
- Ask one stage at a time and wait for its answer. Do not bundle future choices or execute a scan before configuration is answered. Use a supported interactive-choice tool when available; otherwise show a numbered menu in chat.

Read [interaction.md](references/interaction.md) when configuring a scan or collecting a batch size. Read [session-state.md](references/session-state.md) before creating, saving, or resuming session state. Read [git-commit.md](references/git-commit.md) before preparing a batch's staged changes and commit suggestion.

## 1. Configure the scan

1. Ask `Metode scan yang ingin digunakan?` with `1. fs — folder kerja saat ini (default)` and `2. image — container image`.
2. Determine the canonical working directory. Check `trivy --version` and the selected mode's `--help`. If Trivy is unavailable, explain the prerequisite and stop the scan workflow; do not silently install it.
3. For `fs`, use `.` in that working directory. For `image`, ask for an image reference or an explicitly chosen `--input` archive path; there is no invented default image and an archive-only scan needs no dummy image reference. Validate that one usable target is present. Preserve the explicitly selected archive input during later customization.
4. Offer custom flags: option `1` is no optional flags, option `2` is `--scanners`, and subsequent options come from the installed selected command's help. Collect values for each selected flag before offering another flag. Preserve prior choices when the user finishes customization.
5. Ask severity separately: `1. Seluruh kategori (default)`, `2. CRITICAL`, `3. HIGH`, `4. MEDIUM`, `5. LOW`. All means omit `--severity`; another choice adds only that exact severity. Do not duplicate severity in the custom-flags menu.
6. Save the choices and pending stage. Show the exact command, then execute it using the submitted choices without an additional routine confirmation question.

With all defaults the command must be exactly:

```bash
trivy fs .
```

The equivalent default for an image is `trivy image IMAGE_REFERENCE`. Add only flags the user actually chose. Do not silently append `--format json`, `--output`, scanner, severity, ignore, database, or offline flags to aid reporting. Treat flag values as literal arguments, not shell code.

Inspect relevant existing Trivy configuration, ignore rules, and nonsecret environment settings without exposing credentials. No extra flags still inherits these settings. If an inherited restriction contradicts the user's requested coverage, explain the conflict and obtain a focused choice; do not silently edit configuration, override it, or label a restricted scan as complete coverage. All severities is not the same as enabling all scanners.

## 2. Scan and explain findings

- Capture the real command result and its exit status. A scan with findings can exit zero; a selected `--exit-code` can make successful detection exit nonzero. Distinguish detection from an operational failure or incomplete scan.
- Use the actual chosen output format. Do not add a second scan with different flags for convenience. If the output is insufficient, first use existing source/lockfiles and authoritative advisory details; explain a remaining evidence gap before requesting a separate diagnostic scan.
- Inventory each detected issue with a stable ID such as `F001`, scanner type, advisory/rule ID, severity, affected package or file, installed version, known fixed versions, Indonesian explanation, and likely impact. Redact secrets and never quote their values.
- Explain exposure as supported by the application context. Separate an advisory's potential impact from demonstrated exploitability; do not invent a fixed version, severity, or reachability claim.
- Distinguish remaining unfixed findings from suppressed, excluded, unsupported, or unscanned areas. A dash in a table or missing output is not proof of zero findings.
- Persist the sanitized inventory. If findings exist, set `awaiting_batch`, display the inventory, and ask for the batch size. Do not edit the application until this answer arrives.
- If the scan completed with zero findings, report the target, actual coverage, exclusions, and result, save `complete`, and stop. If it failed, save `scan_failed`, explain the error and recovery step, and do not fabricate an inventory.

Suggested inventory:

| Item | Severity | Paket / file | Advisory / aturan | Masalah dan dampak | Perbaikan yang tersedia |
| --- | --- | --- | --- | --- | --- |
| F001 | HIGH | package@version | CVE / rule ID | Penjelasan berdasarkan bukti | Versi aman atau batasan |

## 3. Choose and remediate one batch

Ask how many findings to address now. Default is `1`; accept any positive integer directly, including `3` as three findings rather than menu option three. Reject zero, negative numbers, fractions, and invalid input without changing files.

Choose the easiest safely actionable finding first: prefer a narrow compatible package fix with a known secure version and low application impact. Choose subsequent findings by shared dependency/root cause, remediation, manifest/lockfile, or component. Show the selected IDs and why they belong together before working. If fewer related actionable findings exist than requested, explain the smaller batch; do not fill it with unrelated changes merely to meet a number.

Persist `batch_in_progress` and selected IDs before editing. Investigate and remediate only this batch:

- Prefer the smallest compatible upgrade to a verified fixed release. Consider a downgrade only when the advisory and compatibility evidence show that the older release is secure and preserves required functionality.
- For transitive findings, identify the owning direct dependency and prefer its supported fix. Use the project's package manager and keep manifests and lockfiles synchronized. Avoid broad forced updates or hand-editing lockfile internals.
- Preserve application logic, flow, APIs, routes, permissions, data formats, and observable behavior as far as possible. Respect unrelated existing changes. Do not suppress findings, weaken checks, or alter scan filters to claim a fix.
- If a logic/flow change is necessary, explain it **before editing**: affected files/functions, current and proposed behavior, why a package-only fix is insufficient, alternatives, impacts, risks, and validation. Keep any change within the user's authorized scope and honor any request to wait. If the change needs a product/behavior decision that has not been supplied, mark the item blocked and ask for that decision instead of guessing. Routine compatible dependency changes need no extra approval gate.
- For an image finding, identify the actual image's source and build context. Package or Dockerfile changes alone do not fix an already built image. Rebuild a local verification image when the source/build inputs are available, record its identity, and scan it. Do not push images or deploy as part of this workflow. If the source mapping or build prerequisites are unavailable, report the blocker.
- For secret, configuration, license, or other non-package findings, investigate the appropriate remedy. Do not force a package change as a universal fix. Secret rotation/revocation or other external actions require the necessary user authorization; removing a string alone does not prove a leaked credential safe.

One coherent package change can resolve more advisories than the requested count. Record those as incidentally resolved findings, verify them, and report them separately. Do not start additional unrelated fixes. A blocked or unverified finding still counts as investigated work; never claim all selected items were fixed.

## 4. Verify, stage, report, and stop

Run checks appropriate to the changed packages and affected behavior, using the project's established commands. Rescan with the original method, scanner selection, severity, ignore rules, and relevant configuration. For image verification, use the rebuilt image and disclose that target/identity change. Report any changed vulnerability database or other material comparison difference.

Mark an item `resolved` only when the scan actually verifies its absence for a fixed issue and the applicable checks pass. Otherwise use `blocked`, `unverified`, or `pending`, with an explanation. A filtered-out issue, unchanged old image, disabled scanner, failed scan, or test failure cannot establish successful remediation.

After verification, automatically stage **all** changes from the Git repository root with `git add -A`, then load and run `commit-message-generator` with the `with desc` parameter against the complete staged diff. This also applies when some selected findings remain blocked or unverified and the batch leaves changes; report those outcomes truthfully. Do not narrow staging to the current batch's paths or ask for routine staging confirmation. Normal ignored files remain ignored.

Capture the generator's single code block as the suggested commit subject plus bullet-point body and include it in the batch report. Its code-block-only output rule applies to that generated message, not to the entire Trivy report. Do not run `git commit`, push, or unstage changes. Follow [git-commit.md](references/git-commit.md) for empty diffs, cumulative/unrelated changes, missing dependencies, Git failures, and interruption recovery.

Save the updated inventory, batch evidence, staging/generation status, commit suggestion, remaining counts, and recap. Set `paused` if findings or unfinished Git preparation remain, otherwise `complete`. Report in Indonesian, covering:

1. Requested and selected batch sizes; selected and incidentally resolved IDs.
2. For each item: problem, potential/observed impact, cause, actual solution, package versions and changed files, logic/flow impact, validation evidence, and final status.
3. Commands/checks run and their results; skipped checks, blockers, residual risk, and remaining items.
4. Staging status, staged scope, and the suggested commit message in one copyable code block containing its subject and description. Disclose pre-existing or earlier-batch changes included in the index, and any Git/generator blocker. The user performs the commit.
5. The saved session ID and next action: `/trivy-porter continue` when work remains.

Then stop. Do not start another batch, automatically submit the default, or immediately ask the next batch question in the same completion report. A final default batch size never authorizes fixing the full inventory.

## 5. Continue a session

1. Load the session associated with this chat and project. If the chat lacks an ID, use the session helper to discover candidates; ask which one if ambiguous. If none exists, explain that and offer a new `/trivy-porter` run. Do not invent past results.
2. Summarize in Indonesian: method/target and scan settings, previous findings and impact, last batch's solutions and verification, staging status and commit suggestion, unresolved or blocked items, and the last completed stage. Recheck the current index before presenting a saved suggestion as current.
3. Compare the relevant project files, dependency versions, and image identity to the saved baseline. Reconcile interruptions or user changes before applying more fixes; do not replay a package update blindly or overwrite user work.
4. If configuration or the initial scan was interrupted, resume the pending stage instead of asking to repair nonexistent findings. If a previous batch was interrupted, reconcile its selected items and finish pending verification, staging, or commit-message generation, then report that batch and stop. Do not replay completed fixes or select a new batch as part of this recovery.
5. On a normal continuation from an already completed batch report, if findings remain, ask a fresh batch-size question with default `1`, wait for the answer, then repeat selection, remediation, verification, staging, commit-message generation, reporting, and stopping. Do not reuse the previous batch size as implicit consent.
6. If all findings are verified resolved, finish any pending Git preparation, report completion, and stop. If only blocked items remain, explain the dependencies/decisions needed; do not loop through already resolved items or force an unsafe fix.
