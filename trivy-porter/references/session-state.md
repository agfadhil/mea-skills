# Durable sessions and resuming

Use the bundled `scripts/session_store.py` from this skill's directory. It stores sanitized JSON outside the repository so neither IDE needs a separate copy of session history. The helper manages project isolation, IDs, revisions, and atomic file writes; the agent manages scan/remediation decisions and meaningful evidence.

## Storage and helper usage

Default root: `${XDG_STATE_HOME:-$HOME/.local/state}/trivy-porter/`. The helper partitions state by a hash of the canonical project path and gives every new session its own file. `TRIVY_PORTER_STATE_DIR` overrides the storage root, including for isolated evaluation. Session directories should be private and state files have mode 0600.

Invoke with the available Python 3 interpreter. Resolve `scripts/session_store.py` relative to the loaded skill; do not assume a Codex-specific install path.

```text
python3 SKILL_DIR/scripts/session_store.py create --project PROJECT_PATH --from-file PAYLOAD_JSON
python3 SKILL_DIR/scripts/session_store.py list --project PROJECT_PATH
python3 SKILL_DIR/scripts/session_store.py read --project PROJECT_PATH --session SESSION_ID
python3 SKILL_DIR/scripts/session_store.py save --project PROJECT_PATH --session SESSION_ID --from-file PAYLOAD_JSON
```

Prepare PAYLOAD_JSON in a private temporary file, or use `--from-file -` with JSON on stdin. For updates, read the complete current state, preserve its identity and revision, change the relevant fields, and call `save`. Saving replaces the payload; it does not merge a partial patch. The helper owns `schema_version`, `session_id`, `project_root`, `revision`, `created_at`, and `updated_at`; do not fabricate or transplant these fields. A rejected stale revision requires rereading and reconciling changes, not overwriting another writer.

Use the explicit session ID remembered in the chat. Without one, `list` discovers sessions. An unqualified `read` may select the sole session, but multiple sessions require an explicit choice; do not guess which chat's work to resume. Starting a new scan creates another session and preserves older ones.

If persistence is unavailable, state that limitation before remediation. Preserve a sanitized recap in the current chat, do not claim durable storage succeeded, and resolve storage access before promising cross-session continuation.

## Payload fields

At creation, `stage` is required; omit helper-managed fields. Extend the remaining fields only when they support this workflow. A representative payload is:

```json
{
  "stage": "configuring",
  "pending_question": "method",
  "scan": {
    "method": null,
    "target": null,
    "cwd": "/absolute/project/path",
    "argv_redacted": [],
    "severity": "ALL",
    "explicit_flags": [],
    "credential_sources": [],
    "trivy_version": null,
    "effective_coverage": null,
    "configuration_fingerprint": null,
    "image_identity": null,
    "last_scan_at": null,
    "last_scan_exit_code": null,
    "last_scan_complete": false
  },
  "baseline": {
    "git_head": null,
    "relevant_file_hashes": {}
  },
  "findings": [],
  "batches": [],
  "last_report": null
}
```

`explicit_flags` contains only sanitized names/values. `credential_sources` can name environment variables or a credential mechanism, never their contents. Obtain credentials again through that mechanism when resuming; a redaction marker is not an executable argument.

Each finding needs a stable display ID and fingerprint, scanner, advisory/rule ID, affected target/path, package or resource, installed and fixed versions where applicable, severity, evidence, Indonesian problem/impact summaries, status, and blocking reason if any. Fingerprint package issues by scanner + target + package + advisory; location-dependent issues also need their rule and stable location. Preserve original display IDs across rescans and record changed versions separately. New findings get new IDs.

Finding statuses: `pending`, `in_progress`, `resolved`, `blocked`, `unverified`. Absence under different coverage is not evidence of resolution. Items later justified as not applicable need that evidence recorded and must not be mislabeled as patched.

Each batch records requested count, selected IDs, selection rationale, incidental IDs, planned/actual dependency changes, changed files and versions, logic-impact notice if needed, commands with results, rescan scope/identity, item outcomes, timestamp, and final Indonesian report. It also records `git_preparation`: repository root, HEAD (or null for an unborn branch), staging status/command/result, staged file statuses and diff fingerprint, whether pre-existing or previous-batch work is included, generator name (`commit-message-generator`), argument (`with desc`), generation status, complete suggested message, blocker, and pending substep. Keep reports concise enough to resume without rereading raw output.

The Git preparation status is separate from finding resolution. Save a checkpoint before staging, after staging, and after generating the suggestion. Never save a commit hash as evidence of an agent-created commit: the workflow leaves committing to the user. See [git-commit.md](git-commit.md) for composition with the companion skill and current-index checks.

Do not persist raw secret values, secret snippets, credential flag values, registry tokens, private keys, or environment dumps. Store sanitized summaries and references to affected files instead. If raw scan artifacts are necessary, keep them outside tracked files with appropriate access and explicit redaction; do not treat a raw secret report as safe merely because it came from Trivy.

## Stages and checkpoints

| Stage | Meaning and next action |
| --- | --- |
| `configuring` | A method, target, flag/value, or severity answer is pending; resume that question. |
| `scan_failed` | No complete usable initial scan; explain the error and resolve it before remediation. |
| `awaiting_batch` | Initial findings are saved; ask for a positive batch count, default 1. |
| `batch_in_progress` | Selected IDs and planned edits are saved; reconcile actual file/image/check/index state and finish pending Git preparation after an interruption. |
| `paused` | A batch report has been saved and findings or Git preparation remain. Resolve a pending Git substep for that batch before selecting new findings; otherwise recap and ask for a fresh batch count. |
| `complete` | The initial scan found no issues, or all findings are verified resolved and required batch staging/generation is finished or skipped for an empty index. Pending, blocked, unverified findings or blocked Git preparation keep the session paused. |

Save after each answered configuration stage, after the scan/inventory, before the first edit of a batch, after meaningful edits/checks, and before the final report. A checkpoint is not a claim that remediation succeeded.

On continuation, compare relevant manifests, lockfiles, source/build inputs, config fingerprints, and image identity with saved evidence. Do not revert unrelated changes. A changed vulnerability database can add findings; reconcile by fingerprint and report the difference. If a baseline has materially changed, explain and refresh the evidence before choosing new work.

An interrupted batch must be reconciled rather than blindly repeated: inspect whether edits already landed, rerun incomplete verification as necessary, update statuses, finish pending staging/commit-message generation, and report that batch. Check the current index before reusing a saved commit suggestion; user commits or later index changes can make it stale. Ask a fresh count before selecting any additional findings. Never convert `in_progress` to `resolved` simply because a saved command was started.
