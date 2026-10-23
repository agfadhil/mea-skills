#!/usr/bin/env node
import { createInterface } from 'node:readline';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { applyInstallPlan, createInstallPlan, getDefaultTargets, resolveDestination } from './skill-installer.mjs';
import { renderInstallSuccess } from './installer-output.mjs';

const repositoryRootDefault = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const actionLabels = { install: 'baru', update: 'perbarui (timpa versi lama)', unchanged: 'sudah sama, lewati' };

class Cancelled extends Error {}

export async function runInstaller({
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
  try {
    print('MEA Skills — Installer');
    print(`OS: ${{ win32: 'Windows', darwin: 'macOS', linux: 'Linux' }[platform] || platform}`);
    print();
    print('Pilih tujuan instalasi:');
    print('1. Codex dan Antigravity (default)');
    print('2. Codex');
    print('3. Antigravity');
    print('0. Batal');
    let choice;
    do {
      choice = (await ask('Pilihan [1]: ')) || '1';
      if (!['0', '1', '2', '3'].includes(choice)) print('Masukkan 1, 2, 3, atau 0.');
    } while (!['0', '1', '2', '3'].includes(choice));
    if (choice === '0') throw new Cancelled();

    const defaults = getDefaultTargets({ platform, homeDirectory });
    const selected = choice === '1' ? defaults : defaults.filter((item) => item.id === (choice === '2' ? 'codex' : 'antigravity'));
    const targets = [];
    for (const target of selected) {
      print();
      print(`${target.label} — path default: ${target.directory}`);
      let directory;
      while (!directory) {
        const answer = await ask('Path instalasi (Enter = default, atau masukkan path custom): ');
        try {
          directory = resolveDestination(answer, target.directory, { platform, homeDirectory, cwd, env: environment });
        } catch (error) { print(error.message); }
      }
      targets.push({ ...target, directory });
    }

    const plan = await createInstallPlan({ repositoryRoot, targets });
    print();
    print('Rencana instalasi:');
    for (const target of plan.targets) {
      print(`${target.label}: ${target.directory}`);
      for (const operation of plan.operations.filter((item) => item.targetId === target.id)) {
        print(`  - ${operation.name}: ${actionLabels[operation.action]}`);
      }
    }
    print('Path custom perlu didukung oleh pengaturan discovery agent Anda.');
    let confirmation;
    while (true) {
      confirmation = (await ask('Lanjutkan instalasi ke path di atas? [Y/n]: ')).toLowerCase();
      if (['', 'y', 'yes', 'ya', '1'].includes(confirmation)) break;
      if (['n', 'no', 'tidak', '0'].includes(confirmation)) throw new Cancelled();
      print('Masukkan Y untuk melanjutkan atau N untuk membatalkan.');
    }
    const result = await applyInstallPlan(plan);
    output.write(renderInstallSuccess(plan, result, {
      columns: output.columns, isTTY: output.isTTY, environment,
    }));
    return { cancelled: false, ...result };
  } catch (error) {
    if (!(error instanceof Cancelled)) throw error;
    print('\nInstalasi dibatalkan. Belum ada file skill yang diubah.');
    return { cancelled: true };
  } finally { readline.close(); }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2).filter((item) => item !== '--');
  if (args.length && args.every((item) => ['--help', '-h'].includes(item))) {
    console.log('Pemakaian: pnpm run install:skills\nPilih Codex/Antigravity, periksa atau ubah path, lalu konfirmasikan instalasi.');
  } else if (args.length) {
    console.error(`Argumen tidak dikenal: ${args.join(' ')}. Gunakan --help untuk bantuan.`);
    process.exitCode = 1;
  } else {
    runInstaller().catch((error) => {
      console.error(`Instalasi gagal: ${error.message}`);
      process.exitCode = 1;
    });
  }
}
