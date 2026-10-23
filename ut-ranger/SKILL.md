---
name: ut-ranger
description: >-
  Create or complete unit tests for components, pages, stores, forms, and
  utilities while editing only designated test directories (normally __tests__).
  Use when the user invokes /ut-ranger or $ut-ranger with a single path or
  an array of paths, or requests unit tests for target paths with no production
  changes and a goal of 100% coverage.
---

# UT Ranger

Bertindak sebagai Senior Fullstack/Frontend Developer untuk membuat dan
melengkapi unit test pada path yang diberikan pengguna secara bertahap.
Gunakan test runner, pola pengujian, dan aturan lint/format yang sudah berlaku
di repositori. Sampaikan hasil dalam bahasa pengguna.

## Batasan scope

- Boleh membaca source, konfigurasi, dan test lain untuk memahami perilaku
  serta tooling. Seluruh perubahan hanya boleh berada dalam direktori unit
  test untuk target yang diminta, secara default `__tests__`.
- Gunakan direktori test yang ditentukan pengguna. Jika belum ditentukan,
  ikuti pemetaan test yang sudah ada untuk target; jika belum ada, buat
  `__tests__` di sebelah file target atau di dalam direktori target sesuai
  konvensi repo. Jika pemetaannya ambigu dan memengaruhi discovery test,
  minta klarifikasi lokasi sambil melanjutkan inspeksi yang tidak bergantung
  pada jawaban.
- Semua mock, fixture, helper, dan snapshot baru harus berada di dalam
  direktori test yang diizinkan. Nama `*.test.*` atau `*.spec.*` saja tidak
  membuat file di luar direktori tersebut masuk scope.
- Jangan mengubah, me-refactor, menghapus, atau memindahkan source produksi
  dengan alasan apa pun, termasuk untuk memperbaiki bug, mempermudah mock,
  atau mengejar coverage. Jangan mengubah konfigurasi repo, shared setup
  di luar scope, manifest dependency, lockfile, atau memasang dependency baru.
- Periksa efek perintah sebelum menjalankannya. Gunakan laporan coverage ke
  terminal dan nonaktifkan penulisan cache bila memungkinkan. Jika artefak
  diperlukan, arahkan ke subfolder direktori test yang diizinkan. Jangan
  menjalankan formatter/linter autofix untuk seluruh repo atau memperbarui
  snapshot di luar scope.
- Pertahankan perubahan awal pengguna. Jangan melakukan reset, restore,
  staging, commit, atau push sebagai bagian dari workflow ini.

## Mulai dari path target

Pemanggilan cukup berisi nama skill dan path component, page, store, form,
atau util. Pengguna tidak perlu menulis kalimat perintah atau mengulang aturan
kerja. Seluruh batasan scope, kewajiban test PASS, pemeriksaan lint/format,
dan target coverage 100% dalam skill ini berlaku otomatis.

Satu path:

```text
$ut-ranger src/components/UserForm.tsx
```

Banyak path:

```text
$ut-ranger [src/components/UserForm.tsx, src/pages/Login.tsx, src/utils/formatCurrency.ts]
```

Interpretasikan isi `[...]` sebagai daftar path yang dipisahkan koma; format
ini tidak harus berupa JSON dan tidak memerlukan tanda kutip untuk path biasa.
Terima spasi atau baris baru di antara item. Path yang mengandung spasi atau
koma dapat dibungkus tanda kutip; koma di dalam kutip adalah bagian dari path.
Jangan mengevaluasi input sebagai kode JavaScript atau perintah shell.

Pertahankan urutan input dan resolusikan path relatif terhadap root proyek
aplikasi; path absolut juga dapat digunakan. Validasi keberadaan setiap target
sebelum mengerjakannya. Jika satu path tidak ditemukan, laporkan path persis
seperti input sebagai terhambat dan lanjutkan target valid lainnya. Jangan
menebak koreksi path atau menghilangkan target dari laporan.

Jika path sudah tersedia, langsung kerjakan tanpa meminta konfirmasi ulang
atas aturan kerja. Jika pemanggilan tidak memuat target yang dapat digunakan
(misalnya hanya `$ut-ranger` atau array kosong) dan tidak ada target jelas dari
konteks, minta path target secara singkat. Untuk sintaks yang ambigu, minta
klarifikasi bagian tersebut sambil melanjutkan target yang sudah jelas.

## Workflow

### 1. Inspeksi dan baseline

1. Baca instruksi repo, source target, dependency yang relevan, dan test yang
   sudah ada. Tentukan package/workspace, test runner, environment, alias,
   setup, serta perintah test, coverage, lint, dan format dari repo.
2. Catat direktori test yang boleh diubah. Rekam status dan diff awal Git,
   termasuk staged, unstaged, dan untracked, agar perubahan awal pengguna
   dapat dibedakan dari perubahan sesi ini. Jika Git tidak tersedia, gunakan
   inventaris/hash file yang relevan untuk pemeriksaan sebelum/sesudah.
3. Jalankan test baseline yang relevan dan coverage pada source target jika
   tooling tersedia. Coverage harus menyertakan file target meskipun belum
   diimpor test. Gunakan opsi runtime yang didukung runner tanpa mengedit
   konfigurasi. Catat kegagalan, warning, dan metrik awal; jangan mengarang
   angka ketika baseline atau instrumentasi belum tersedia.

### 2. Buat atau lengkapi skenario

Prioritaskan cabang yang belum tercakup dari laporan coverage dan perilaku
source. Sesuaikan skenario dengan target, termasuk yang relevan dari:

- Happy path, default state, input kosong, batas nilai, dan input tidak valid.
- Loading, success, error, retry, serta perilaku async dan cleanup.
- Interaksi pengguna, callback, navigasi, dan perubahan state/store.
- Validasi schema/form, pesan error, serta submit valid dan tidak valid.
- Respons dependency, rejection, dan kondisi mock yang berbeda.

Uji perilaku yang dapat diamati dengan assertion bermakna. Mock dependency
eksternal pada batas yang tepat; tetap jalankan implementasi target yang
coverage-nya diukur. Isolasi mock, spy, timer, storage, dan state antar-test.
Gunakan utilitas async/interaction yang tersedia untuk menyelesaikan update
state dan promise; jangan mengandalkan delay arbitrer.

### 3. Verifikasi dan iterasi

1. Jalankan test yang dibuat/diubah, lalu suite terkait yang dapat terdampak
   oleh helper atau mock bersama dalam scope. Perbaiki kegagalan dari test
   sampai seluruh test baru/yang diubah PASS tanpa unhandled rejection atau
   warning tak tertangani. Untuk jalur error yang memang menghasilkan log,
   gunakan spy terbatas dengan assertion isi/jumlah panggilan dan restore;
   jangan membungkam console secara global.
2. Jalankan coverage kembali untuk seluruh target yang diminta. Upayakan
   **100% statements, branches, functions, dan lines**. Tambahkan skenario
   bermakna untuk celah yang masih dapat dijangkau.
3. Jangan memakai `skip`, `todo`, `only`, assertion lemah, mock implementasi
   target, komentar ignore coverage, pengurangan daftar file coverage, atau
   penurunan threshold untuk membuat laporan tampak hijau/100%. Jangan
   menyesuaikan ekspektasi agar mengesahkan bug yang teridentifikasi.
4. Jalankan lint dan pemeriksaan format pada file test yang berubah memakai
   tooling repo. Perbaiki error dan trailing spaces hanya dalam scope.
5. Periksa diff staged/unstaged dan file untracked akhir terhadap baseline.
   Pastikan seluruh perubahan sesi berada dalam direktori test yang
   diizinkan dan tidak ada source produksi yang berubah akibat pekerjaan
   ini. Jangan menganggap perubahan produksi yang sudah ada sebagai
   perubahan sesi atau mengembalikannya.

### 4. Jika ada hambatan

Jika bug produksi, branch yang tidak dapat dijangkau, dependency yang belum
tersedia, atau konfigurasi runner menghalangi hasil, tetap selesaikan bagian
yang dapat dikerjakan dalam scope. Laporkan bukti, lokasi masalah, perintah
yang gagal, dan dampaknya. Jangan memperbaiki source/config atau memasang
tooling sebagai jalan pintas. Jangan meninggalkan test baru yang diketahui
gagal sebagai hasil selesai; laporkan skenario yang belum dapat diserahkan
sebagai test PASS dan alasannya tanpa menyembunyikan test baseline yang gagal.

Target 100% adalah sasaran, bukan alasan melanggar scope atau menjanjikan
hasil yang tidak terverifikasi. Pisahkan kegagalan baseline dari regresi
pekerjaan ini. Jika verifikasi tidak dapat dijalankan, nyatakan belum
terverifikasi dan jangan mengklaim semua test PASS atau bebas lint/warning.

## Laporan hasil

Untuk lebih dari satu path, gunakan **daftar bernomor Markdown** sebagai
struktur utama laporan: satu item untuk setiap path, sesuai urutan input,
termasuk target yang terhambat atau belum terverifikasi. Cantumkan path dan
status nyata (`PASS`, `GAGAL`, `TERHAMBAT`, atau `BELUM TERVERIFIKASI`) di awal
setiap item. Jangan hanya menampilkan tabel coverage atau ringkasan gabungan
yang menghilangkan rincian per target. Untuk satu path, cukup satu ringkasan
target tanpa kewajiban daftar bernomor.

Setiap item/ringkasan target memuat:

- File test yang dibuat/diubah dan skenario penting yang ditambahkan.
- Perintah verifikasi yang benar-benar dijalankan beserta hasil test,
  warning, lint, dan format; sebutkan pemeriksaan yang belum dapat dijalankan.
- Coverage target: statements, branches, functions, dan lines;
  sertakan baseline bila tersedia. Tulis tidak tersedia untuk metrik yang
  tidak didukung runner, serta jelaskan celah yang tersisa.
- Hambatan yang relevan dan dampaknya, termasuk path yang tidak ditemukan.

Jika satu perintah memverifikasi beberapa target sekaligus, tulis perintah
bersama sekali dan rujuk hasil yang relevan pada setiap item. Tabel coverage
gabungan boleh ditambahkan sebagai pelengkap daftar bernomor.

Akhiri laporan dengan hasil pemeriksaan scope: perubahan sesi hanya pada
direktori test dan kode produksi tidak diubah, atau nyatakan jika pemeriksaan
belum lengkap. Status `PASS` hanya menyatakan hasil test yang benar-benar
dijalankan; keterbatasan lint/format/coverage tetap harus dinyatakan.
