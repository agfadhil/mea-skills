import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { replaceReadmeVersion, syncReadmeVersion } from '../scripts/sync-readme-version.mjs';

test('replaces only the current version line, including versions that start with a digit after the prefix', () => {
  const text = 'Intro 1.0.0\n\nCurrent version: **1.0.0**. Check it.\n';
  assert.equal(replaceReadmeVersion(text, '1.13.0'), 'Intro 1.0.0\n\nCurrent version: **1.13.0**. Check it.\n');
});

test('fails loudly when the README no longer has a version line', () => {
  assert.throws(() => replaceReadmeVersion('No version here\n', '1.3.0'), /Current version/u);
});

test('replaces both the current version line and the logo banner version when present', () => {
  const text = [
    '│  ██║╚██╗██╔╝██║  │   ██║ ╚═╝ ██║███████╗██║  ██║          v1.0.0',
    '',
    'Current version: **1.0.0**.',
  ].join('\n');
  const updated = replaceReadmeVersion(text, '2.5.1');
  assert.equal(updated, [
    '│  ██║╚██╗██╔╝██║  │   ██║ ╚═╝ ██║███████╗██║  ██║          v2.5.1',
    '',
    'Current version: **2.5.1**.',
  ].join('\n'));
});

test('syncs README.md and the trivy-porter VERSION file with package.json', async t => {
  const directory = await fs.mkdtemp(path.join(tmpdir(), 'mea-readme-version-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  await fs.writeFile(path.join(directory, 'package.json'), JSON.stringify({ version: '2.4.0' }));
  await fs.writeFile(path.join(directory, 'README.md'), 'Current version: **1.0.0**.\n');
  await fs.mkdir(path.join(directory, 'trivy-porter'));
  await fs.writeFile(path.join(directory, 'trivy-porter', 'VERSION'), '1.0.0\n');
  assert.equal(await syncReadmeVersion(directory), '2.4.0');
  assert.equal(await fs.readFile(path.join(directory, 'README.md'), 'utf8'), 'Current version: **2.4.0**.\n');
  assert.equal(await fs.readFile(path.join(directory, 'trivy-porter', 'VERSION'), 'utf8'), '2.4.0\n');
});
