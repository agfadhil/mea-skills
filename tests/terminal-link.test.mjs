import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { PassThrough, Writable } from 'node:stream';
import { test } from 'node:test';
import { isOnPath, renderCmdShim, renderShShim, runTerminalLink } from '../scripts/terminal-link.mjs';

async function fixture(t, mode = 0o755) {
  const directory = await fs.mkdtemp(path.join(tmpdir(), 'mea-terminal-link-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const repositoryRoot = path.join(directory, 'repository');
  const homeDirectory = path.join(directory, 'home');
  const script = path.join(repositoryRoot, 'scripts', 'trivy-porter.mjs');
  await fs.mkdir(path.dirname(script), { recursive: true });
  await fs.mkdir(homeDirectory);
  await fs.writeFile(script, '#!/usr/bin/env node\n', { mode });
  const bin = path.join(homeDirectory, '.local', 'bin');
  return { directory, repositoryRoot, homeDirectory, script, bin, linkPath: path.join(bin, 'trivy-porter') };
}

async function answerLink(setup, answers, { platform = 'darwin', environment = { PATH: setup.bin } } = {}) {
  const input = new PassThrough();
  const remaining = [...answers];
  let text = '';
  const output = new Writable({ write(chunk, _encoding, done) {
    text += chunk.toString();
    if (chunk.toString().endsWith(': ')) {
      assert.ok(remaining.length, `Terminal link requested an unexpected answer:\n${text}`);
      const answer = remaining.shift();
      queueMicrotask(() => input.write(answer + '\n'));
    }
    done();
  } });
  try {
    const result = await runTerminalLink({
      repositoryRoot: setup.repositoryRoot, homeDirectory: setup.homeDirectory, input, output,
      platform, environment, cwd: setup.directory,
    });
    assert.equal(remaining.length, 0);
    return { result, text };
  } finally {
    input.destroy();
    output.destroy();
  }
}

test('creates the folder and symlink after confirmation, then reports an unchanged rerun', async t => {
  const setup = await fixture(t);
  const { result } = await answerLink(setup, ['', '', '']);
  assert.equal(result.changed, true);
  assert.equal(await fs.readlink(setup.linkPath), setup.script);

  const rerun = await answerLink(setup, ['']);
  assert.equal(rerun.result.changed, false);
  assert.match(rerun.text, /Tidak ada yang perlu diubah/u);
});

test('declining the final confirmation leaves the home directory untouched', async t => {
  const setup = await fixture(t);
  const { result } = await answerLink(setup, ['', '', 'n']);
  assert.equal(result.cancelled, true);
  assert.deepEqual(await fs.readdir(setup.homeDirectory), []);
});

test('an existing foreign file is kept unless overwriting is confirmed', async t => {
  const setup = await fixture(t);
  await fs.mkdir(setup.bin, { recursive: true });
  await fs.writeFile(setup.linkPath, 'user-owned');
  const declined = await answerLink(setup, ['', '']);
  assert.equal(declined.result.cancelled, true);
  assert.equal(await fs.readFile(setup.linkPath, 'utf8'), 'user-owned');

  await answerLink(setup, ['', 'y', '']);
  assert.equal(await fs.readlink(setup.linkPath), setup.script);
});

test('missing execute permission is added only after confirmation', async t => {
  const setup = await fixture(t, 0o644);
  const declined = await answerLink(setup, ['', '', 'n']);
  assert.equal(declined.result.cancelled, true);
  assert.equal((await fs.stat(setup.script)).mode & 0o111, 0);

  await answerLink(setup, ['', '', '', '']);
  assert.equal((await fs.stat(setup.script)).mode & 0o111, 0o111);
});

test('a folder outside PATH needs explicit approval and shadowing commands are reported', async t => {
  const setup = await fixture(t);
  const outside = await answerLink(setup, ['', 'y', '', ''], { environment: {} });
  assert.match(outside.text, /belum ada di PATH/u);
  assert.equal(await fs.readlink(setup.linkPath), setup.script);

  const other = path.join(setup.directory, 'other-node', 'bin');
  await fs.mkdir(other, { recursive: true });
  await fs.writeFile(path.join(other, 'trivy-porter'), '', { mode: 0o755 });
  await fs.rm(setup.linkPath);
  const shadowed = await answerLink(setup, ['', ''], { environment: { PATH: `${other}:${setup.bin}` } });
  assert.match(shadowed.text, /ditemukan lebih dulu di PATH/u);
});

test('an unwritable folder asks for another destination', { skip: process.getuid?.() === 0 }, async t => {
  const setup = await fixture(t);
  const locked = path.join(setup.directory, 'locked');
  await fs.mkdir(locked, { mode: 0o555 });
  const { text } = await answerLink(setup, [locked, '', '', ''], { environment: { PATH: `${locked}:${setup.bin}` } });
  assert.match(text, /Akses ditolak/u);
  assert.equal(await fs.readlink(setup.linkPath), setup.script);
});

test('Windows asks before creating a .cmd file and declining changes nothing', async t => {
  const setup = await fixture(t);
  const { result, text } = await answerLink(setup, ['n'], { platform: 'win32', environment: {} });
  assert.equal(result.cancelled, true);
  assert.match(text, /trivy-porter\.cmd/u);
  assert.deepEqual(await fs.readdir(setup.homeDirectory), []);
});

test('Windows helpers produce a .cmd shim and match PATH case-insensitively', () => {
  assert.equal(renderCmdShim('C:\\repo\\scripts\\trivy-porter.mjs'),
    '@echo off\r\nrem Dibuat oleh mea-skills:terminal-link\r\nnode "C:\\repo\\scripts\\trivy-porter.mjs" %*\r\n');
  assert.equal(renderShShim("C:\\it's\\scripts\\trivy-porter.mjs"),
    "#!/bin/sh\n# Dibuat oleh mea-skills:terminal-link\nexec node 'C:/it'\\''s/scripts/trivy-porter.mjs' \"$@\"\n");
  const env = { Path: 'C:\\Windows;C:\\Users\\Fixture\\.local\\bin\\' };
  assert.equal(isOnPath('c:\\users\\fixture\\.local\\bin', { platform: 'win32', env }), true);
  assert.equal(isOnPath('C:\\Users\\Fixture\\bin', { platform: 'win32', env }), false);
});

test('Windows adds the Git Bash shim next to an existing .cmd install', { skip: process.platform !== 'win32' }, async t => {
  const setup = await fixture(t);
  await fs.mkdir(setup.bin, { recursive: true });
  await fs.writeFile(`${setup.linkPath}.cmd`, renderCmdShim(setup.script));
  const { result, text } = await answerLink(setup, ['', '', ''], { platform: 'win32', environment: { Path: setup.bin } });
  assert.equal(result.changed, true);
  assert.doesNotMatch(text, /trivy-porter\.cmd \(timpa/u);
  assert.equal(await fs.readFile(setup.linkPath, 'utf8'), renderShShim(setup.script));

  const rerun = await answerLink(setup, ['', ''], { platform: 'win32', environment: { Path: setup.bin } });
  assert.equal(rerun.result.changed, false);
});
