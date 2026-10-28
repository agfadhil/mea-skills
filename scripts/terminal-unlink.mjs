#!/usr/bin/env node
import * as fs from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveDestination } from './skill-installer.mjs';
import {
  Cancelled, commandName, createPrompt, findShadowingCommand, getDefaultLinkDirectory, inspectLink, osLabel, pathApi,
  repositoryRootDefault,
} from './terminal-link.mjs';

export async function runTerminalUnlink({
  repositoryRoot = repositoryRootDefault, input = process.stdin, output = process.stdout,
  platform = process.platform, homeDirectory = homedir(), environment = process.env, cwd = process.cwd(),
} = {}) {
  const { print, ask, confirm, close } = createPrompt({ input, output });
  const windows = platform === 'win32';
  const script = pathApi(platform).join(repositoryRoot, 'scripts', 'trivy-porter.mjs');
  const npmHint = () => {
    print();
    print('Jika sebelumnya juga memakai npm link, jalankan di setiap versi Node.js yang pernah dipakai:');
    print('  npm unlink -g mea-skills');
    print('Dengan mise: mise exec node@<versi> -- npm unlink -g mea-skills, lalu mise reshim.');
  };

  try {
    print('MEA Skills — Terminal Unlink');
    print(`OS: ${osLabel(platform)}`);
    print();
    print(`Perintah ini menghapus command ${windows ? `${commandName}.cmd dan ${commandName}` : commandName} yang dibuat oleh mea-skills:terminal-link.`);
    print('Script di repository ini dan folder tujuan tidak ikut dihapus.');

    const fallback = getDefaultLinkDirectory({ platform, homeDirectory });
    let state;
    while (!state) {
      print();
      print(`Folder default: ${fallback}`);
      const answer = await ask('Folder link (Enter = default, atau masukkan path custom): ');
      let directory;
      try { directory = resolveDestination(answer, fallback, { platform, homeDirectory, cwd, env: environment }); }
      catch (error) { print(error.message); continue; }
      const inspected = await inspectLink({ directory, script, platform });
      if (inspected.blocked) { print(inspected.blocked); continue; }
      state = inspected;
    }

    const removable = state.files.filter((file) => !['missing', 'foreign'].includes(file.existing));
    const foreign = state.files.filter((file) => file.existing === 'foreign');
    if (state.existing === 'missing') {
      print();
      print(`Tidak ada ${state.files.map((file) => path.basename(file.path)).join(' atau ')} di ${state.directory}. Tidak ada yang perlu dihapus.`);
      npmHint();
      return { cancelled: false, changed: false };
    }
    if (!removable.length) {
      print();
      for (const file of foreign) print(`${file.path} bukan dibuat oleh mea-skills, jadi tidak dihapus.`);
      print('Periksa file tersebut dan hapus secara manual jika memang tidak dipakai.');
      return { cancelled: false, changed: false };
    }
    if (!state.writable) {
      print();
      print(`Akses ditolak: tidak ada izin tulis ke ${state.writableCheck}.`);
      print(`Perintah ini tidak menjalankan ${windows ? 'sebagai Administrator' : 'sudo'}. Perbaiki izin folder tersebut secara manual.`);
      return { cancelled: false, changed: false };
    }

    print();
    for (const file of foreign) print(`${file.path} bukan dibuat oleh mea-skills, jadi tidak dihapus.`);
    const otherLink = removable.find((file) => file.existing === 'other-link');
    const targets = removable.map((file) => file.path).join(' dan ');
    if (otherLink) {
      print(`${otherLink.path} menunjuk ke ${otherLink.currentTarget},`);
      print('bukan ke repository ini (mungkin dari lokasi repository lama).');
      if (!(await confirm('Tetap hapus symlink tersebut?', false))) throw new Cancelled();
    } else {
      for (const file of removable) {
        print(file.existing === 'outdated'
          ? `${file.path} dibuat oleh mea-skills, tetapi menunjuk ke lokasi script lain.`
          : `${file.path} menunjuk ke script di repository ini.`);
      }
      if (!(await confirm(`Hapus ${targets}?`, true))) throw new Cancelled();
    }

    for (const file of removable) await fs.rm(file.path);
    print();
    print(`✓ ${targets} sudah dihapus.`);
    const remaining = await findShadowingCommand(commandName, undefined, { platform, env: environment });
    if (remaining) {
      print();
      print('Masih ada command trivy-porter lain di PATH:');
      print(`  ${remaining}`);
    }
    npmHint();
    print();
    print(windows ? 'Buka terminal baru agar perubahan terbaca.' : 'Buka terminal baru (atau jalankan `hash -r`) agar perubahan terbaca.');
    return { cancelled: false, changed: true, linkPath: state.linkPath };
  } catch (error) {
    if (!(error instanceof Cancelled)) throw error;
    print('\nDibatalkan. Belum ada file yang dihapus.');
    return { cancelled: true };
  } finally { close(); }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2).filter((item) => item !== '--');
  if (args.length && args.every((item) => ['--help', '-h'].includes(item))) {
    console.log('Pemakaian: pnpm run mea-skills:terminal-unlink\nHapus command trivy-porter yang dibuat oleh mea-skills:terminal-link.');
  } else if (args.length) {
    console.error(`Argumen tidak dikenal: ${args.join(' ')}. Gunakan --help untuk bantuan.`);
    process.exitCode = 1;
  } else {
    runTerminalUnlink().catch((error) => {
      const denied = ['EACCES', 'EPERM'].includes(error.code);
      console.error(denied ? `Akses ditolak: ${error.message}` : `Terminal unlink gagal: ${error.message}`);
      process.exitCode = 1;
    });
  }
}
