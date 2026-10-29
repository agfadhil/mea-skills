#!/usr/bin/env node
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readVersion } from './mea-skills-version.mjs';

const repositoryRootDefault = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const pattern = /(Current version: \*\*)[^*]+(\*\*)/u;
const logoPattern = /(│.+?██║\s+╚═╝\s+██║███████╗██║\s+██║)\s+v\d+\.\d+\.\d+/u;

export function replaceReadmeVersion(text, version) {
  if (!pattern.test(text)) throw new Error('Baris "Current version: **x.y.z**" tidak ditemukan di README.md.');
  let updated = text.replace(pattern, (_match, before, after) => `${before}${version}${after}`);
  if (logoPattern.test(updated)) {
    const tag = `v${version}`;
    const padding = ' '.repeat(Math.max(1, 16 - tag.length));
    updated = updated.replace(logoPattern, (_match, prefix) => `${prefix}${padding}${tag}`);
  }
  return updated;
}

// Installed skill copies have no package.json, so trivy-porter ships its own VERSION file.
export const skillVersionFile = path.join('trivy-porter', 'VERSION');

export async function syncReadmeVersion(repositoryRoot = repositoryRootDefault) {
  const version = await readVersion(repositoryRoot);
  const readme = path.join(repositoryRoot, 'README.md');
  const text = await readFile(readme, 'utf8');
  const updated = replaceReadmeVersion(text, version);
  if (updated !== text) await writeFile(readme, updated);
  await writeFile(path.join(repositoryRoot, skillVersionFile), `${version}\n`);
  return version;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  syncReadmeVersion().then((version) => console.log(`README.md dan ${skillVersionFile} diselaraskan ke v${version}`)).catch((error) => {
    console.error(`Gagal menyelaraskan versi: ${error.message}`);
    process.exitCode = 1;
  });
}
