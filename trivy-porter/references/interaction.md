# Interaction and CLI choices

## Ask in stages

Use Indonesian prompts. These are separate questions, not one bundled form:

1. Method (`fs` first/default, `image` second).
2. Image reference or explicitly selected `--input` archive when needed; a required target has no fabricated default. An archive-only scan needs no image reference. This input selection remains part of the command when later customization adds no other flags.
3. Custom flags and each flag's values.
4. Severity.
5. After scanning and displaying findings, batch size.

Every actual default is option 1. Explain `Enter = default` only when the UI can submit an empty response. Otherwise say `Pilih 1 untuk default`. A UI preselection must still be submitted. Use a free-text field when accepting a custom number or a value not representable by the choices.

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
- **Credentials:** prefer existing configured authentication or secure environment/stdin mechanisms. Do not request passwords/tokens in an ordinary chat choice or save them in state or reports.

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

Display the resulting command and run it after the answer. Preserve argument boundaries with an argv API or proper shell quoting; do not evaluate user strings as shell fragments. Redact credential arguments in displays. `--format`, `--output`, filters, and other options must be user choices, not hidden implementation conveniences.

## Batch-size question

```text
Berapa finding yang ingin diperiksa dan ditangani pada batch ini?
1. Satu finding (default)
Custom: masukkan bilangan bulat positif, misalnya 3.
```

This question accepts a number directly: `3` means a batch of three findings. In an interactive UI, offer `1 finding (default)` and `Jumlah custom`; then request the number if custom is chosen. Validate before editing. A blank custom-number submission also defaults to 1 only when it is actually submitted.

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
