#!/usr/bin/env node
import { constants } from 'node:fs';
import * as fs from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { resolveDestination } from './skill-installer.mjs';

const repositoryRootDefault = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const commandName = 'trivy-porter';
const shimMarker = 'rem Dibuat oleh mea-skills:terminal-link';
const pathApi = (platform) => platform === 'win32' ? path.win32 : path.posix;

class Cancelled extends Error {}

export function getDefaultLinkDirectory({ platform = process.platform, homeDirectory = homedir() } = {}) {
  return pathApi(platform).join(homeDirectory, '.local', 'bin');
}

export function renderCmdShim(script) {
  return ['@echo off', shimMarker, `node "${script}" %*`, ''].join('\r\n');
}

function envValue(env, name, platform) {
  const key = platform === 'win32' ? Object.keys(env).find((item) => item.toLowerCase() === name.toLowerCase()) : name;
  return key === undefined ? undefined : env[key];
}

function samePath(platform) {
  const paths = pathApi(platform);
  const normal = (value) => platform === 'win32' ? paths.resolve(value).toLowerCase() : paths.resolve(value);
  return (left, right) => normal(left) === normal(right);
}

function pathEntries(platform, env) {
  return (envValue(env, 'PATH', platform) || '').split(pathApi(platform).delimiter).filter(Boolean);
}

export function isOnPath(directory, { platform = process.platform, env = process.env } = {}) {
  const same = samePath(platform);
  return pathEntries(platform, env).some((entry) => same(entry, directory));
}

// Returns the first command found in PATH entries listed before `stopAt`, i.e. one that would shadow a link there.
export async function findShadowingCommand(name, stopAt, { platform = process.platform, env = process.env } = {}) {
  const paths = pathApi(platform);
  const same = samePath(platform);
  const extensions = platform === 'win32'
    ? (envValue(env, 'PATHEXT', platform) || '.COM;.EXE;.BAT;.CMD').split(';').filter(Boolean) : [''];
  for (const entry of pathEntries(platform, env)) {
    if (same(entry, stopAt)) return undefined;
    for (const extension of extensions) {
      const candidate = paths.join(entry, name + extension);
      try {
        await fs.access(candidate, platform === 'win32' ? constants.F_OK : constants.X_OK);
        return candidate;
      } catch { /* Not in this folder. */ }
    }
  }
  return undefined;
}

async function lstatOrNull(filename) {
  try { return await fs.lstat(filename); }
  catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}

async function canAccess(filename, mode) {
  try { await fs.access(filename, mode); return true; } catch { return false; }
}

export async function inspectLink({ directory, script, platform = process.platform }) {
  const paths = pathApi(platform);
  const windows = platform === 'win32';
  const linkPath = paths.join(directory, windows ? `${commandName}.cmd` : commandName);
  const state = { directory, script, linkPath, kind: windows ? 'cmd' : 'symlink', existing: 'missing' };

  const folder = await lstatOrNull(directory);
  if (folder && !folder.isDirectory()) return { ...state, blocked: `${directory} bukan folder.` };
  state.exists = Boolean(folder);
  let writableCheck = directory;
  while (!(await lstatOrNull(writableCheck)) && paths.dirname(writableCheck) !== writableCheck) {
    writableCheck = paths.dirname(writableCheck);
  }
  state.writableCheck = writableCheck;
  state.writable = await canAccess(writableCheck, constants.W_OK);
  state.executable = windows || await canAccess(script, constants.X_OK);

  const link = await lstatOrNull(linkPath);
  if (link?.isDirectory()) return { ...state, blocked: `${linkPath} sudah ada sebagai folder.` };
  if (windows && link?.isFile()) {
    const content = await fs.readFile(linkPath, 'utf8');
    state.existing = content === renderCmdShim(script) ? 'current' : content.includes(shimMarker) ? 'outdated' : 'foreign';
  } else if (!windows && link?.isSymbolicLink()) {
    state.currentTarget = await fs.readlink(linkPath);
    state.existing = state.currentTarget === script ? 'current' : 'other-link';
  } else if (link) state.existing = 'foreign';
  return state;
}

export async function applyLink(plan) {
  if (plan.createDirectory) await fs.mkdir(plan.directory, { recursive: true });
  if (plan.makeExecutable) {
    const { mode } = await fs.stat(plan.script);
    await fs.chmod(plan.script, (mode & 0o777) | 0o111);
  }
  const temporary = `${plan.linkPath}.mea-skills-${process.pid}`;
  try {
    if (plan.kind === 'cmd') await fs.writeFile(temporary, renderCmdShim(plan.script));
    else await fs.symlink(plan.script, temporary);
    await fs.rename(temporary, plan.linkPath);
  } catch (error) {
    await fs.rm(temporary, { force: true });
    throw error;
  }
}

export async function runTerminalLink({
  repositoryRoot = repositoryRootDefault, input = process.stdin, output = process.stdout,
  platform = process.platform, homeDirectory = homedir(), environment = process.env, cwd = process.cwd(),
} = {}) {
  const readline = createInterface({ input, output, terminal: Boolean(input.isTTY && output.isTTY) });
  const lines = readline[Symbol.asyncIterator]();
  readline.on('SIGINT', () => readline.close());
  const print = (message = '') => output.write(`${message}\n`);
  const ask = async (prompt) => {
    output.write(prompt);
    const answer = await lines.next();
    if (answer.done) throw new Cancelled();
    return answer.value.trim();
  };
  const confirm = async (prompt, fallback) => {
    while (true) {
      const answer = (await ask(`${prompt} ${fallback ? '[Y/n]' : '[y/N]'}: `)).toLowerCase();
      if (!answer) return fallback;
      if (['y', 'yes', 'ya'].includes(answer)) return true;
      if (['n', 'no', 'tidak'].includes(answer)) return false;
      print('Masukkan Y atau N.');
    }
  };
  const windows = platform === 'win32';
  const script = pathApi(platform).join(repositoryRoot, 'scripts', 'trivy-porter.mjs');

  try {
    print('MEA Skills — Terminal Link');
    print(`OS: ${{ win32: 'Windows', darwin: 'macOS', linux: 'Linux' }[platform] || platform}`);
    print();
    print('Perintah ini membuat command trivy-porter yang tidak bergantung pada versi Node.js aktif');
    print('(nvm, mise, fnm, dan sejenisnya). Command menunjuk langsung ke script di repository ini:');
    print(`  ${script}`);
    print('Jika Anda hanya memakai satu versi Node.js, `npm link` sudah cukup.');

    if (windows) {
      print();
      print('Windows: symlink membutuhkan hak Administrator atau Developer Mode, jadi command dibuat');
      print(`sebagai file ${commandName}.cmd yang menjalankan: node "${script}"`);
      if (!(await confirm(`Izinkan pembuatan file ${commandName}.cmd?`, true))) throw new Cancelled();
    }
    if (!(await lstatOrNull(script))) throw new Error(`Script tidak ditemukan: ${script}`);

    const fallback = getDefaultLinkDirectory({ platform, homeDirectory });
    let plan;
    while (!plan) {
      print();
      print(`Folder tujuan default: ${fallback}`);
      const answer = await ask('Folder tujuan (Enter = default, atau masukkan path custom): ');
      let directory;
      try { directory = resolveDestination(answer, fallback, { platform, homeDirectory, cwd, env: environment }); }
      catch (error) { print(error.message); continue; }

      const state = await inspectLink({ directory, script, platform });
      if (state.blocked) { print(state.blocked); continue; }
      if (!state.writable) {
        print(`Akses ditolak: tidak ada izin tulis ke ${state.writableCheck}.`);
        print(`Perintah ini tidak menjalankan ${windows ? 'sebagai Administrator' : 'sudo'}. Pilih folder lain di dalam folder pengguna,`);
        print('atau perbaiki izin folder tersebut secara manual.');
        continue;
      }
      if (!isOnPath(directory, { platform, env: environment })) {
        print(`Peringatan: ${directory} belum ada di PATH, jadi command belum bisa dipanggil langsung.`);
        print(windows
          ? 'Tambahkan lewat System Properties → Environment Variables → Path, lalu buka terminal baru.'
          : `Tambahkan ke ~/.zshrc atau ~/.bashrc: export PATH="${directory}:$PATH"`);
        if (!(await confirm('Tetap gunakan folder ini?', false))) continue;
      }
      if (!state.exists && !(await confirm(`Folder ${directory} belum ada. Buat folder ini?`, true))) {
        print('Pilih folder lain, atau tekan Ctrl+C untuk batal.');
        continue;
      }
      plan = { ...state, createDirectory: !state.exists };
    }

    if (plan.existing === 'other-link' || plan.existing === 'foreign') {
      print();
      print(plan.existing === 'other-link'
        ? `${plan.linkPath} sudah ada dan menunjuk ke ${plan.currentTarget}.`
        : `${plan.linkPath} sudah ada dan bukan dibuat oleh mea-skills.`);
      if (!(await confirm('Timpa file tersebut?', false))) throw new Cancelled();
    }
    if (!plan.executable) {
      print();
      print(`Script belum memiliki izin eksekusi: ${script}`);
      print('Tanpa izin ini shell menolak menjalankan command (permission denied).');
      if (!(await confirm('Tambahkan izin eksekusi (chmod +x)?', true))) throw new Cancelled();
      plan.makeExecutable = true;
    }
    if (plan.existing === 'current' && !plan.makeExecutable) {
      print();
      print(`✓ ${plan.linkPath} sudah menunjuk ke script ini. Tidak ada yang perlu diubah.`);
      return { cancelled: false, changed: false, linkPath: plan.linkPath };
    }

    const shadow = await findShadowingCommand(commandName, plan.directory, { platform, env: environment });
    if (shadow) {
      print();
      print('Peringatan: command trivy-porter lain ditemukan lebih dulu di PATH:');
      print(`  ${shadow}`);
      print('Command itu yang akan dipakai. Hapus dulu (misalnya `npm unlink -g mea-skills` pada versi Node.js');
      print('tersebut, lalu `mise reshim` jika memakai mise), atau letakkan folder tujuan lebih awal di PATH.');
    }

    print();
    print('Rencana:');
    if (plan.createDirectory) print(`  - Buat folder: ${plan.directory}`);
    if (plan.makeExecutable) print(`  - Tambahkan izin eksekusi: ${script}`);
    const replace = plan.existing === 'missing' ? '' : ' (timpa yang lama)';
    print(plan.kind === 'cmd'
      ? `  - Buat file: ${plan.linkPath}${replace}`
      : `  - Buat symlink: ${plan.linkPath} → ${script}${replace}`);
    if (!(await confirm('Lanjutkan?', true))) throw new Cancelled();

    await applyLink(plan);
    print();
    print(`✓ Command trivy-porter siap: ${plan.linkPath}`);
    print(windows ? 'Buka terminal baru, lalu cek:' : 'Buka terminal baru (atau jalankan `hash -r`), lalu cek:');
    print(`  ${windows ? 'where' : 'which'} trivy-porter`);
    print('  trivy-porter --help');
    print();
    print('Untuk menghapusnya nanti:');
    print(windows ? `  Remove-Item "${plan.linkPath}"` : `  rm "${plan.linkPath}"`);
    return { cancelled: false, changed: true, linkPath: plan.linkPath };
  } catch (error) {
    if (!(error instanceof Cancelled)) throw error;
    print('\nDibatalkan. Belum ada file yang diubah.');
    return { cancelled: true };
  } finally { readline.close(); }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2).filter((item) => item !== '--');
  if (args.length && args.every((item) => ['--help', '-h'].includes(item))) {
    console.log('Pemakaian: pnpm run mea-skills:terminal-link\nBuat command trivy-porter di ~/.local/bin (file .cmd di Windows) yang berlaku untuk semua versi Node.js.');
  } else if (args.length) {
    console.error(`Argumen tidak dikenal: ${args.join(' ')}. Gunakan --help untuk bantuan.`);
    process.exitCode = 1;
  } else {
    runTerminalLink().catch((error) => {
      const denied = ['EACCES', 'EPERM'].includes(error.code);
      console.error(denied ? `Akses ditolak: ${error.message}` : `Terminal link gagal: ${error.message}`);
      process.exitCode = 1;
    });
  }
}
