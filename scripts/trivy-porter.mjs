#!/usr/bin/env node
import { spawn, spawnSync } from 'node:child_process';
import { realpathSync } from 'node:fs';
import { constants } from 'node:os';
import { fileURLToPath } from 'node:url';

const pythonScript = fileURLToPath(new URL('../trivy-porter/scripts/trivy_porter.py', import.meta.url));

export function findPython({ platform = process.platform, probe = spawnSync } = {}) {
  const candidates = platform === 'win32'
    ? [{ command: 'py', args: ['-3'] }, { command: 'python3', args: [] }, { command: 'python', args: [] }]
    : [{ command: 'python3', args: [] }, { command: 'python', args: [] }];

  for (const candidate of candidates) {
    const result = probe(candidate.command, [...candidate.args, '-c', 'import sys; print(sys.version_info[0])'], {
      encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 5000, windowsHide: true, shell: false,
    });
    if (!result.error && result.status === 0 && result.stdout?.trim() === '3') return candidate;
  }
  return undefined;
}

export async function runTrivyPorter({
  argv = process.argv.slice(2), cwd = process.cwd(), platform = process.platform,
  probe = spawnSync, spawnProcess = spawn, signalSource = process, errorOutput = process.stderr,
} = {}) {
  const python = findPython({ platform, probe });
  if (!python) {
    errorOutput.write('Python 3 tidak ditemukan. Pasang Python 3 dan pastikan python3, python, atau py -3 tersedia di PATH.\n');
    return 1;
  }

  return new Promise((resolve) => {
    let child;
    try {
      child = spawnProcess(python.command, [...python.args, pythonScript, ...argv], {
        cwd, stdio: 'inherit', shell: false,
      });
    } catch (error) {
      errorOutput.write(`Gagal menjalankan Trivy Porter: ${error.message}\n`);
      resolve(1);
      return;
    }

    const handlers = new Map(['SIGINT', 'SIGTERM'].map((signal) => [signal, () => {
      if (child.exitCode === null && child.signalCode === null) child.kill(signal);
    }]));
    for (const [signal, handler] of handlers) signalSource.on(signal, handler);

    const finish = (code) => {
      for (const [signal, handler] of handlers) signalSource.off(signal, handler);
      resolve(code);
    };
    child.once('error', (error) => {
      errorOutput.write(`Gagal menjalankan Trivy Porter: ${error.message}\n`);
      finish(1);
    });
    child.once('exit', (code, signal) => finish(code ?? (128 + (constants.signals[signal] ?? 1))));
  });
}

let isMain = false;
if (process.argv[1]) {
  try { isMain = realpathSync(process.argv[1]) === fileURLToPath(import.meta.url); } catch { /* Imported module. */ }
}
if (isMain) process.exitCode = await runTrivyPorter();
