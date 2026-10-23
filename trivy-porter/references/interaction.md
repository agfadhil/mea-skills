# Interaction and CLI choices

## Terminal and chat handoffs

The bundled `scripts/trivy_porter.py` runs the menu loop locally. The user types answers in their own integrated terminal; the agent does not route every menu answer through chat. The CLI never calls an AI service, edits application dependencies, stages files, or sends a message to a Codex chat.

Start a new session from the scan project:

```text
trivy-porter
```

With no storage override, this creates sessions under `.trivy-porter` in the terminal's current directory. `--project` changes the scan directory and identity, while that storage default still follows the directory where the command was launched. An explicit `--state-dir` or `TRIVY_PORTER_STATE_DIR` overrides it.

The installed command is a convenience wrapper. Without it, provide the loaded skill's actual path and an explicit project directory, quoting both for the user's shell:

```text
python3 SKILL_DIR/scripts/trivy_porter.py --project PROJECT_PATH
```

After scanning, the CLI prints `$trivy-porter analyze SESSION_ID --project PROJECT_PATH --state-dir STATE_ROOT`. The user pastes and sends that line in Codex chat; `$trivy-porter` explicitly invokes the installed skill. Other agents may use their own skill picker while retaining the same action and arguments. Legacy `/trivy-porter ...` text remains accepted by the skill. The agent reads the saved scan, explains findings, and saves an inventory before batch choices are available. This is a chat instruction, not a terminal subcommand or a request for another scan. Without a fresh explicit remediation count in the user message, analysis stops before remediation and an already inventoried session receives a recap rather than consuming a new batch. A fresh chat count, including `0` for all unresolved inventory findings, authorizes work after analysis without another terminal count question. Older chat `continue` handoffs still analyze sessions in `awaiting_analysis` for compatibility. For the next choice, the user runs:

```text
trivy-porter continue --session SESSION_ID --project PROJECT_PATH
```

The equivalent without the wrapper is `python3 SKILL_DIR/scripts/trivy_porter.py continue --session SESSION_ID --project PROJECT_PATH`. Add the same `--state-dir STATE_ROOT` when the session uses a custom storage root. After submitting a count, the user returns to chat with the complete printed `$trivy-porter continue SESSION_ID --project PROJECT_PATH --state-dir STATE_ROOT`. This manual handoff is required; an integrated terminal and the Codex chat do not automatically exchange messages. The workflow does not require installing Codex CLI or supplying an API key.

Always carry the same canonical project path, storage root, and session ID across terminal and chat. The printed handoff includes `--project PROJECT_PATH`, which matters when scanning a monorepo subdirectory rather than the editor's workspace root, and `--state-dir STATE_ROOT`, which does not rely on the extension inheriting terminal environment settings. Terminal continuation can display a session picker; chat must resolve an ambiguous session rather than guessing. Terminal `continue` during pending scan analysis prints the `analyze` handoff; during an interrupted batch it prints the `continue` handoff instead of collecting a count for new work.

The completion/handoff panel separates the scan process outcome, current stage, session and storage details, and next step. Use the displayed outcome as process evidence, not proof of complete coverage or zero findings. Colors follow terminal support and `NO_COLOR`; narrow terminals use a readable compact layout. The exact chat command is printed on its own line outside the panel, preserving quoting and every argument without inserting line breaks or border characters. Terminal soft wrapping is expected for long paths. Use `analyze` for `awaiting_analysis`; keep `continue` for selected batches and interruption recovery.

Terminal `storage` shows the resolved storage paths and `sessions` lists the current project's saved sessions. Terminal `clean --session SESSION_ID` or `clean --all` previews recognized session files, then requires a submitted affirmative answer to `[y/N]`. Enter, EOF, and Ctrl+C do not approve deletion. Cleanup is an explicit user action, separate from scan/remediation completion, and does not delete application files or the user's Trivy `--output` files. See [session-state.md](session-state.md) for scope and active-work restrictions.

## Export, chat prompt and full local cleanup

`trivy-porter --download` and its shorthand `trivy-porter -d` select the current project's most recently updated session with scan output and write one sanitized, self-contained JSON report to `~/Downloads`, printing the full path. Both forms accept the same options: `--session SESSION_ID` selects a specific session; `--download-dir PATH` changes the destination. Normal project/storage options select the source. No Trivy command or automatic upload runs. The user attaches the file to an AI agent and asks for analysis or solutions. Missing evidence is an error, not an invitation to fabricate a report or rescan. See [session-state.md](session-state.md) for the portable report contract.

`trivy-porter --prompt` prints only this static text for the user to copy into the agent chat with the exported JSON attached:

```text
$trivy-porter Analisis laporan JSON terlampir, jelaskan temuannya dan rekomendasi perbaikannya.
Isi n dengan jumlah temuan; 0 = semua temuan.

Perbaiki terlebih dahulu dengan jumlah temuan: n
```

Replace `n` with a nonnegative integer before sending: `0` requests all unresolved findings in the analyzed inventory, while a positive number limits the batch. The explicit count authorizes analysis followed by that remediation scope in the same request. An unchanged placeholder, negative value, fraction, or omitted count is not a batch request. Printing the prompt does not check a project or session, read/write state, run Trivy, or submit a chat message. `--project` and `--state-dir` do not alter this static output. Do not combine `--prompt` with another action, `--clean`, `--download`, `--session`, `--all`, or `--download-dir`.

`trivy-porter --clean` is an explicit complete reset of `<terminal cwd>/.trivy-porter`, including all project partitions, locks and unknown contents, without another prompt. It ignores storage environment overrides and rejects an explicit `--state-dir`, `--session`, `--all`, another action, or a different `--project`. A missing folder is a no-op. Linked roots, mounted directories, active scans/batches and ongoing state writes are refused. Files outside that local folder are preserved, including the default Downloads export and user-selected Trivy output files. Export first if the user wants to keep the evidence.

The existing `clean --session SESSION_ID` and `clean --all` subcommands remain scoped to selected sessions in the chosen project/storage root and require `[y/N]` confirmation. They preserve unrelated files and the storage folder. Do not substitute complete `--clean` when the user requested scoped cleanup, or clean anything automatically after exporting or finishing a batch.

## Terminal questions in stages

Use Indonesian prompts. These are separate questions, not one bundled form:

1. Method (`fs` first/default, `image` second).
2. For new image scans, derive the local `REPO_NAME:scan` target from the selected project directory; there is no image-reference/archive question. Existing saved image/archive sessions retain their pending source question and recorded target.
3. Custom flags and each flag's values.
4. Severity.
5. After the agent has analyzed the scan and saved an inventory, batch size on a separate terminal continuation, unless the user already supplied a fresh explicit remediation count in chat.

Every actual default is option 1. A submitted Enter accepts the default; EOF, Ctrl+C, preselection, elapsed time, and silence do not. Save answered choices so terminal continue resumes the pending stage rather than restarting the wizard. A required legacy image reference/path has no default.

For the new image action, execute `docker build --platform=linux/amd64 -t REPO_NAME:scan .` from the selected project, then `trivy image --image-src docker --format json REPO_NAME:scan` after a successful build. Scanner/filter and severity answers add their normal arguments. Source and JSON output are fixed workflow settings: exclude `--input`, `--image-src`, `--format`, and `--output` from customization and reject direct attempts to override them. If environment/configuration could supply inherited input/output routing, explicitly clear that routing and record/display the guard arguments. Build failure or interruption saves evidence and stops before Trivy; terminal continuation offers an explicit build retry. A successful scan saves sanitized JSON as `report.json` inside the timestamped session folder; malformed/truncated evidence must not leave a stale JSON report.

## Discover flags, rather than freezing a version

Read `trivy --version` and `trivy fs --help` or `trivy image --help`. The installed per-command help is authoritative for available flags, types, enumerated values, defaults, and aliases. Consult official version-matched docs if a detail is missing.

Build this menu using only supported flags:

```text
Kustomisasi scan:
1. Default — tanpa flag opsional
2. --scanners — pilih jenis pemeriksaan
3. --pkg-types — pilih jenis paket
4. --ignore-unfixed — tampilkan hanya kerentanan dengan perbaikan
5. --skip-dirs — tentukan folder yang dikecualikan
6. --skip-files — tentukan file yang dikecualikan
... flag lain dari help metode terpilih
```

The entries after 2 are illustrative, not a hardcoded compatibility list. Include concise explanations and accept a flag by its exact supported name as well as its displayed number. Use the canonical `--scanners`, not the misspelling `--scanner`. Make other supported scan flags discoverable; paginate long menus while preserving stable numbers, option 1, and access to the full list. Reserve `--severity` for its dedicated question. Flags belonging only to another method must not be accepted.

Help/version, database-download-only, and config-generation flags do not produce a findings scan. Explain that distinction if selected and return to configuration instead of interpreting their output as an empty scan. Explain options whose format disables scanners or omits finding types. Do not silently add dependent flags to compensate; ask for the necessary choices.

After selecting a flag, ask for its value before moving on:

- **Enumerated single value:** option 1 keeps Trivy's default/omits the flag; other options are the real supported values.
- **Enumerated multiple values, including scanners:** option 1 keeps the default/omits the flag; list each supported value after it and accept multiple selections. Default cannot be combined with explicit values. Join explicit values as documented, usually comma-separated. A scanner list replaces the active list; it does not add to it.
- **Boolean:** offer 1 omit/default, 2 explicitly enable, and 3 explicitly disable if supported. Emit the explicit boolean value when needed to override existing configuration.
- **String/path/integer/duration/list:** offer 1 omit/default and a custom-value input. Validate the documented type; a path, duration, or custom value is never invented because the user pressed Enter.
- **Credentials:** use existing configured authentication or secure environment mechanisms. Do not collect credential values through ordinary menu text or save them in state, logs, or reports. The menu must explain restricted credential flags instead of treating them as normal string options.

For example, if the selected mode supports these values:

```text
Nilai --scanners (boleh memilih beberapa, misalnya 2,4):
1. Default Trivy — jangan tambahkan --scanners
2. vuln — kerentanan paket
3. misconfig — kesalahan konfigurasi
4. secret — kredensial atau rahasia yang terdeteksi
5. license — informasi/isu lisensi
```

The exact list is dynamic. For example, Trivy 0.76 also offers `crypto` for image scans, while its filesystem scanner list does not. Do not assume every version/method has that option.

After one or more flags have values, option 1 changes to `Selesai — gunakan pilihan saat ini`. Enter here preserves selections. Provide an explicit `Reset ke default tanpa flag` action separately. Reject conflicting flag values and ask the smallest clarification needed. Only legacy image sessions may select `--input`; collect an existing archive path and omit a conflicting positional image reference.

## Severity question

```text
Kategori severity yang ingin ditampilkan:
1. Seluruh kategori — tanpa --severity (default)
2. CRITICAL
3. HIGH
4. MEDIUM
5. LOW
```

All uses no added severity argument and normally includes UNKNOWN. Selecting HIGH emits `--severity HIGH`, not `HIGH,CRITICAL`. Explicitly requested multi-category customization can use a supported comma-separated set. Check inherited configuration before claiming the actual coverage includes all categories.

Display the resulting build/scan commands and run after the answer, without another routine confirmation. Preserve argument boundaries with an argv API; do not evaluate strings as shell fragments. Local-image Docker source and JSON routing are the fixed choices described above; filesystem/legacy output formats, filters, and other options remain user choices, apart from managed-state exclusions below. Record inherited configuration evidence and obtain a focused terminal choice if it restricts requested coverage; accepting inherited settings does not make coverage unrestricted.

Project-local storage must not become a filesystem scan input. The CLI displays one `--skip-dirs` argument per marker-owned session/lock folder or legacy partition inside the target and records those paths in `scan.managed_state_exclusions`. It never excludes the entire custom root. Keep explicit skip lists; otherwise preserve nonempty `TRIVY_SKIP_DIRS` in the effective arguments. If YAML skip lists are unparsed and no explicit/environment list was supplied, return to customization or cancel rather than overriding unknown exclusions. This is the only automatic scan-filter exception; scanner/severity choices stay intact. Report exclusions as actual coverage and retain them during verification. Each managed folder's `.gitignore` keeps generated files out of Git without editing root ignores; already tracked state is refused. For Docker builds, `.gitignore` does not control context contents; the project should exclude `.trivy-porter/` through its `.dockerignore` when relevant, without the CLI editing it automatically.

The CLI deliberately does not parse arbitrary YAML configuration. For filesystem/legacy scans, an active config with uncertain output format causes non-JSON text to be withheld; the inherited-settings menu offers a return to customization to choose `--format table` or `--format json`. The local-image workflow explicitly selects JSON and guards output routing. Other custom formats remain withheld, with a notice before execution.

## Batch-size question

```text
Berapa finding yang ingin diperiksa dan ditangani pada batch ini?
1. Satu finding (default)
0. Seluruh temuan yang belum selesai
Custom: masukkan bilangan bulat positif, misalnya 3.
```

This terminal question accepts a number directly: `3` requests up to three related findings; `0` requests all unresolved findings in the current inventory. Validate a nonnegative integer before saving a request. Negative numbers, fractions, and invalid input must not create a valid request. A submitted Enter still defaults to 1. Here `0` means all; other menus retain their displayed `0 = batal` behavior, and Ctrl+C cancels this input without submitting a request.

When only blocked findings remain, terminal continuation keeps its existing review handoff rather than collecting another count; a fresh chat count `0` can still request reassessment and reporting of those blocked items.

Save a fresh `batch_request` with a unique ID, nonnegative `count`, submission timestamp, and `status: pending`. Keep `count: 0` as the explicit all-findings sentinel rather than replacing it with the current number of items. If a pending request already exists, show its handoff rather than silently replacing it or asking again. The agent marks it consumed and records the request ID before editing; a consumed request cannot authorize another batch. If unfinished Git preparation or an interrupted batch needs recovery, return to that existing batch before collecting a new count.

The CLI's scan output is sanitized before persistence. The agent still determines whether the scan completed, what findings exist, and which fixes are compatible. Withheld, truncated, or unsupported output must be reported as an evidence limitation, never proof that no issues exist.

A positive count bounds intentionally selected findings, not commands or files. One related package-manager operation may touch several required manifests/lockfiles or resolve extra advisories. Do not split an atomic fix merely to keep an advisory count, or use incidental resolutions to select unrelated work. For count `0`, snapshot all unresolved IDs and record their actual size before editing. Work through every snapshot item in the same overall request/batch, using internal groups as useful without stopping for another count. Do not force incompatible fixes or label blocked/unverified findings resolved. New findings outside the snapshot are reported and need fresh authorization; a consumed all-findings request cannot be reused.

## Official references

Use these as technical sources and follow the installed version's help when differences exist:

- [Trivy configuration and precedence](https://trivy.dev/docs/latest/configuration/)
- [Docker build platform and tag options](https://docs.docker.com/reference/cli/docker/buildx/build/)
- [Trivy container image sources](https://trivy.dev/docs/latest/target/container_image/)
- [Filesystem CLI, version 0.76](https://trivy.dev/docs/v0.76/guide/references/configuration/cli/trivy_filesystem/)
- [Image CLI, version 0.76](https://trivy.dev/docs/v0.76/guide/references/configuration/cli/trivy_image/)
- [Finding filters and severities](https://trivy.dev/docs/latest/configuration/filtering/)
- [Reporting and dependency origins](https://trivy.dev/docs/latest/configuration/reporting/)
- [Vendor vulnerability information](https://trivy.dev/docs/latest/scanner/vulnerability/)
- [SBOM behavior](https://trivy.dev/docs/latest/supply-chain/sbom/)
