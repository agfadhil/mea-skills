#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repositoryRootDefault = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

export async function readVersion(repositoryRoot = repositoryRootDefault) {
  const manifest = JSON.parse(await readFile(path.join(repositoryRoot, 'package.json'), 'utf8'));
  return manifest.version;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  readVersion().then((version) => console.log(`mea-skills v${version}`)).catch((error) => {
    console.error(`Gagal membaca versi: ${error.message}`);
    process.exitCode = 1;
  });
}
