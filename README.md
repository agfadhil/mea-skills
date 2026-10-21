# mea-skills

Kumpulan skill untuk membantu agent menulis pesan commit, menyiapkan deskripsi MR/PR, dan menangani findings Trivy secara bertahap. Installer menyalin skill ke lokasi pengguna untuk VS Code (Copilot/Codex), Antigravity IDE, atau keduanya. Mendukung macOS, Linux, dan Windows.

## Mulai

Siapkan **Node.js 20 atau lebih baru** dan **pnpm**, lalu jalankan dari root repository ini:

```sh
pnpm run install:skill
```

Installer memakai modul bawaan Node.js dan tidak membutuhkan `pnpm install` atau dependency npm tambahan. Perintah yang sama dapat digunakan di terminal macOS/Linux maupun PowerShell/Command Prompt pada Windows.

## Alur instalasi

1. Pilih target:

   ```text
   1. Keduanya — VS Code dan Antigravity (default)
   2. VS Code — Copilot/Codex
   3. Antigravity IDE
   0. Batal
   ```

2. Periksa path untuk setiap target. Tekan **Enter** untuk memakai default atau ketik path custom. Installer menampilkan path pengguna yang sebenarnya.
3. Tinjau rencana lengkap: daftar skill, tujuan salinan, dan perubahan yang akan dilakukan.
4. Jawab konfirmasi **`[Y/n]`**. Enter atau `y` menyetujui; `n` membatalkan. Penulisan dimulai setelah konfirmasi ini.

Pilihan `0`, penolakan konfirmasi, atau input yang berakhir sebelum konfirmasi tidak mengubah folder tujuan. Installer menyalin semua folder di root repository yang memiliki `SKILL.md`, termasuk file pendukung seperti `scripts/` dan `references/`.

### Lokasi default

| Target | macOS / Linux | Windows |
| --- | --- | --- |
| VS Code — Copilot/Codex | `~/.agents/skills` | `%USERPROFILE%\.agents\skills` |
| Antigravity IDE | `~/.gemini/config/skills` | `%USERPROFILE%\.gemini\config\skills` |

Folder personal `~/.agents/skills` didukung oleh [VS Code Agent Skills](https://code.visualstudio.com/docs/agent-customization/agent-skills) dan [Codex](https://learn.chatgpt.com/docs/build-skills). Lokasi Antigravity mengikuti [dokumentasi skill IDE](https://www.antigravity.google/docs/skills?tab=ide).

Untuk path custom, installer menerima notasi `~/...`, `$HOME/...`, `%USERPROFILE%\...`, serta path bertanda kutip yang mengandung spasi. Path custom menentukan lokasi salinan; installer tidak otomatis mendaftarkan folder sembarang ke IDE. Pilih lokasi yang didukung agent atau atur discovery lokasinya melalui konfigurasi IDE yang tersedia.

### Pembaruan dan backup

Jalankan kembali `pnpm run install:skill` setelah memperbarui isi repository. Skill dengan isi identik dilewati. Skill lain yang sudah ada pada tujuan tetap dipertahankan.

Sebelum mengganti skill yang berbeda isinya, installer menyimpan versi sebelumnya di folder backup di samping folder tujuan `skills`:

```text
<parent-folder-tujuan>/.mea-skills-backups/<run-id>/<target-id>/<nama-skill>/
```

Contohnya, backup untuk tujuan `~/.agents/skills` berada di `~/.agents/.mea-skills-backups/`. Backup berada di luar root skill agar tidak ikut ditemukan sebagai skill tambahan. Periksa lokasi backup yang ditampilkan installer jika ingin mengambil kembali versi lama.

## Skill yang tersedia

Buka chat agent pada repository kerja, kemudian pilih atau sebut nama skill sesuai antarmuka IDE.

| Skill | Contoh pemanggilan | Kegunaan |
| --- | --- | --- |
| [commit-message-generator](commit-message-generator/SKILL.md) | `/commit-message-generator with desc` | Membaca seluruh staged diff dan aturan proyek, lalu menyarankan subject commit beserta body berbentuk bullet. Alias `/commit with desc` juga dijelaskan dalam skill. |
| [mr-description](mr-description/SKILL.md) | `/mr-description 6` | Menyiapkan judul dan deskripsi MR/PR berbahasa Inggris dari N commit terakhir, termasuk daftar ID commit. Tanpa angka, default N adalah **1**. |
| [trivy-porter](trivy-porter/SKILL.md) | `/trivy-porter` | Memilih scan `fs` atau `image`, flag dan severity, lalu menjelaskan serta memperbaiki findings dalam batch. Default satu finding per batch. |
| trivy-porter — lanjutkan | `/trivy-porter continue` | Memuat sesi sebelumnya, memberi ringkasan, dan meminta jumlah finding untuk batch berikutnya. |

`commit-message-generator` memerlukan perubahan yang sudah staged. `trivy-porter` melakukan staging **seluruh perubahan repository** setelah setiap batch dan menyertakan saran commit melalui `commit-message-generator with desc`; ini dapat mencakup perubahan yang sudah ada atau batch sebelumnya yang belum di-commit. Commit tetap dilakukan oleh pengguna.

### Kebutuhan saat menjalankan skill

Installer hanya menyalin file skill. IDE/extension agent, Git, Trivy, dan Python dipasang terpisah sesuai kebutuhan:

- **commit-message-generator** dan **mr-description** menggunakan Git pada repository kerja.
- **trivy-porter** membutuhkan Trivy, Git untuk staging/saran commit, serta Python 3 untuk menyimpan sesi. Metode image juga memerlukan akses image dan lingkungan build yang sesuai bila melakukan perbaikan image.
- Pada Windows, pastikan `trivy.exe` dan Git dapat dipanggil dari terminal agent. Python 3 dapat tersedia sebagai `python3`, `python`, atau `py -3`; gunakan executable yang tersedia saat menjalankan helper sesi.

## Jika skill belum muncul

Periksa bahwa tujuan memiliki struktur `<nama-skill>/SKILL.md` dan nama pada frontmatter sesuai foldernya. Di VS Code, periksa **Chat: Open Customizations**; di Antigravity, periksa menu **Customizations** pada panel agent. Codex mendeteksi perubahan skill secara otomatis; jika belum terlihat, mulai ulang Codex. Lihat [petunjuk Codex](https://learn.chatgpt.com/docs/build-skills) untuk discovery skill lokal.

WSL menggunakan home Linux yang terpisah dari profil pengguna Windows. Jalankan installer di lingkungan tempat agent bekerja: instalasi dari WSL memakai home WSL, sedangkan instalasi native Windows memakai profil Windows. Untuk target remote/container, periksa kembali lokasi yang dibaca agent tersebut. Setelah instalasi, buka sesi chat baru atau refresh IDE bila discovery belum diperbarui.

## Pengujian

```sh
pnpm test
```

Jalankan pengujian dari root repository. Installer dan pengujian tidak membutuhkan pemasangan dependency npm.
