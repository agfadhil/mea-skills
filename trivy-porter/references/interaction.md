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

After scanning, the CLI prints `/trivy-porter continue SESSION_ID`. The user submits that line in the extension chat. The agent reads the saved scan, explains findings, and saves an inventory before batch choices are available. For the next choice, the user runs:

```text
trivy-porter continue --session SESSION_ID --project PROJECT_PATH
```

The equivalent without the wrapper is `python3 SKILL_DIR/scripts/trivy_porter.py continue --session SESSION_ID --project PROJECT_PATH`. Add the same `--state-dir STATE_ROOT` when the session uses a custom storage root. After submitting a count, the user returns to chat with the complete printed `/trivy-porter continue SESSION_ID --project PROJECT_PATH --state-dir STATE_ROOT`. This manual handoff is required; an integrated terminal and the Codex chat do not automatically exchange messages. The workflow does not require installing Codex CLI or supplying an API key.

Always carry the same canonical project path, storage root, and session ID across terminal and chat. The printed handoff includes `--project PROJECT_PATH`, which matters when scanning a monorepo subdirectory rather than the editor's workspace root, and `--state-dir STATE_ROOT`, which does not rely on the extension inheriting terminal environment settings. Terminal continuation can display a session picker; chat must resolve an ambiguous session rather than guessing. Continue during pending scan analysis or an interrupted batch prints the existing handoff instead of collecting a count for new work.

Terminal `storage` shows the resolved storage paths and `sessions` lists the current project's saved sessions. Terminal `clean --session SESSION_ID` or `clean --all` previews recognized session files, then requires a submitted affirmative answer to `[y/N]`. Enter, EOF, and Ctrl+C do not approve deletion. Cleanup is an explicit user action, separate from scan/remediation completion, and does not delete application files or the user's Trivy `--output` files. See [session-state.md](session-state.md) for scope and active-work restrictions.

## Export, chat prompt and full local cleanup

`trivy-porter --download` selects the current project's most recently updated session with scan output and writes one sanitized, self-contained JSON report to `~/Downloads`, printing the full path. `--session SESSION_ID` selects a specific session; `--download-dir PATH` changes the destination. Normal project/storage options select the source. No Trivy command or automatic upload runs. The user attaches the file to an AI agent and asks for analysis or solutions. Missing evidence is an error, not an invitation to fabricate a report or rescan. See [session-state.md](session-state.md) for the portable report contract.

`trivy-porter --prompt` prints only this static text for the user to copy into the agent chat with the exported JSON attached:

```text
$trivy-porter Analisis laporan JSON terlampir, jelaskan temuannya dan rekomendasi perbaikannya.

Perbaiki terlebih dahulu dengan jumlah temuan: n
```

Replace `n` with a positive integer before sending; an unchanged placeholder is not a batch request. Printing the prompt does not check a project or session, read/write state, run Trivy, or submit a chat message. `--project` and `--state-dir` do not alter this static output. Do not combine `--prompt` with another action, `--clean`, `--download`, `--session`, `--all`, or `--download-dir`.

`trivy-porter --clean` is an explicit complete reset of `<terminal cwd>/.trivy-porter`, including all project partitions, locks and unknown contents, without another prompt. It ignores storage environment overrides and rejects an explicit `--state-dir`, `--session`, `--all`, another action, or a different `--project`. A missing folder is a no-op. Linked roots, mounted directories, active scans/batches and ongoing state writes are refused. Files outside that local folder are preserved, including the default Downloads export and user-selected Trivy output files. Export first if the user wants to keep the evidence.

The existing `clean --session SESSION_ID` and `clean --all` subcommands remain scoped to selected sessions in the chosen project/storage root and require `[y/N]` confirmation. They preserve unrelated files and the storage folder. Do not substitute complete `--clean` when the user requested scoped cleanup, or clean anything automatically after exporting or finishing a batch.

## Terminal questions in stages

Use Indonesian prompts. These are separate questions, not one bundled form:

1. Method (`fs` first/default, `image` second).
2. Image reference or explicitly selected `--input` archive when needed; a required target has no fabricated default. An archive-only scan needs no image reference. This input selection remains part of the command when later customization adds no other flags.
3. Custom flags and each flag's values.
4. Severity.
5. After the agent has analyzed the scan and saved an inventory, batch size on a separate terminal continuation.

Every actual default is option 1. A submitted Enter accepts the default; EOF, Ctrl+C, preselection, elapsed time, and silence do not. Save answered choices so terminal continue resumes the pending stage rather than restarting the wizard. A required image reference/path has no default.

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

After one or more flags have values, option 1 changes to `Selesai — gunakan pilihan saat ini`. Enter here preserves selections. Provide an explicit `Reset ke default tanpa flag` action separately. Reject conflicting flag values and ask the smallest clarification needed. If `--input` is selected for image mode, collect an existing archive path and omit a conflicting positional image reference.

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

Display the resulting command and run it after the answer, without another routine scan confirmation. Preserve argument boundaries with an argv API; do not evaluate user strings as shell fragments. `--format`, `--output`, filters, and other options must be user choices, not hidden implementation conveniences, apart from the managed-state exclusion below. Record inherited configuration evidence and obtain a focused terminal choice if it restricts the requested coverage; a user's acceptance of inherited settings does not make that coverage unrestricted.

Project-local storage must not become a scan input. For `fs`, the CLI displays one `--skip-dirs` argument per marker-owned managed hash partition inside the target and records the relative paths in `scan.managed_state_exclusions`. It excludes those partitions, never the entire custom storage root. Keep explicit user skip lists; otherwise preserve nonempty `TRIVY_SKIP_DIRS` in the effective arguments. If an active YAML config's skip list is unparsed and no explicit/environment list was supplied, return to flag customization or cancel instead of overriding unknown exclusions. This is the only automatic scan-filter exception; it does not change scanner or severity choices. Report the excluded partitions as actual coverage and keep the saved exclusions in verification scans. If the installed command cannot safely support them, stop before scanning state. Each partition's `.gitignore` keeps generated files out of Git without editing root ignore files; already tracked state is refused for explicit resolution.

The CLI deliberately does not parse arbitrary YAML configuration. If an active config file leaves the output format uncertain, it withholds non-JSON text from saved artifacts. The inherited-settings menu offers a return to flag customization so the user can explicitly select `--format table` or `--format json`. The CLI does not add either flag automatically. Other custom formats are also withheld, with a notice before execution.

## Batch-size question

```text
Berapa finding yang ingin diperiksa dan ditangani pada batch ini?
1. Satu finding (default)
Custom: masukkan bilangan bulat positif, misalnya 3.
```

This terminal question accepts a number directly: `3` means a batch of three findings. Validate a positive integer before saving a request. Zero, negative numbers, fractions, and invalid input must not change files or create a valid request. A submitted Enter defaults to 1.

Save a fresh `batch_request` with a unique ID, positive `count`, submission timestamp, and `status: pending`. If a pending request already exists, show its handoff rather than silently replacing it or asking again. The agent marks it consumed and records the request ID before editing; a consumed request cannot authorize another batch. If unfinished Git preparation or an interrupted batch needs recovery, return to that existing batch before collecting a new count.

The CLI's scan output is sanitized before persistence. The agent still determines whether the scan completed, what findings exist, and which fixes are compatible. Withheld, truncated, or unsupported output must be reported as an evidence limitation, never proof that no issues exist.

The count bounds intentionally selected findings, not commands or files. One related package-manager operation may touch several required manifests/lockfiles or resolve extra advisories. Do not split a necessary atomic fix merely to keep an advisory count, and do not use incidental resolutions as permission to select unrelated work.

## Official references

Use these as technical sources and follow the installed version's help when differences exist:

- [Trivy configuration and precedence](https://trivy.dev/docs/latest/configuration/)
- [Filesystem CLI, version 0.76](https://trivy.dev/docs/v0.76/guide/references/configuration/cli/trivy_filesystem/)
- [Image CLI, version 0.76](https://trivy.dev/docs/v0.76/guide/references/configuration/cli/trivy_image/)
- [Finding filters and severities](https://trivy.dev/docs/latest/configuration/filtering/)
- [Reporting and dependency origins](https://trivy.dev/docs/latest/configuration/reporting/)
- [Vendor vulnerability information](https://trivy.dev/docs/latest/scanner/vulnerability/)
- [SBOM behavior](https://trivy.dev/docs/latest/supply-chain/sbom/)
