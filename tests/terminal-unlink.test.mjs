import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { PassThrough, Writable } from 'node:stream';
import { test } from 'node:test';
import { runTerminalUnlink } from '../scripts/terminal-unlink.mjs';

async function fixture(t) {
  const directory = await fs.mkdtemp(path.join(tmpdir(), 'mea-terminal-unlink-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const repositoryRoot = path.join(directory, 'repository');
  const homeDirectory = path.join(directory, 'home');
  const script = path.join(repositoryRoot, 'scripts', 'trivy-porter.mjs');
  const bin = path.join(homeDirectory, '.local', 'bin');
  await fs.mkdir(path.dirname(script), { recursive: true });
  await fs.mkdir(bin, { recursive: true });
  await fs.writeFile(script, '#!/usr/bin/env node\n', { mode: 0o755 });
  return { directory, repositoryRoot, homeDirectory, script, bin, linkPath: path.join(bin, 'trivy-porter') };
}

async function answerUnlink(setup, answers, { platform = 'darwin', environment = { PATH: setup.bin } } = {}) {
  const input = new PassThrough();
  const remaining = [...answers];
  let text = '';
  const output = new Writable({ write(chunk, _encoding, done) {
    text += chunk.toString();
    if (chunk.toString().endsWith(': ')) {
      assert.ok(remaining.length, `Terminal unlink requested an unexpected answer:\n${text}`);
      const answer = remaining.shift();
      queueMicrotask(() => input.write(answer + '\n'));
    }
    done();
  } });
  try {
    const result = await runTerminalUnlink({
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

test('removes the mea-skills symlink after confirmation and keeps the script and folder', async t => {
  const setup = await fixture(t);
  await fs.symlink(setup.script, setup.linkPath);
  const declined = await answerUnlink(setup, ['', 'n']);
  assert.equal(declined.result.cancelled, true);
  assert.equal(await fs.readlink(setup.linkPath), setup.script);

  const { result, text } = await answerUnlink(setup, ['', '']);
  assert.equal(result.changed, true);
  await assert.rejects(fs.lstat(setup.linkPath), { code: 'ENOENT' });
  await fs.access(setup.script);
  await fs.access(setup.bin);
  assert.match(text, /npm unlink -g mea-skills/u);
});

test('reports a missing link without prompting further', async t => {
  const setup = await fixture(t);
  const { result, text } = await answerUnlink(setup, ['']);
  assert.equal(result.changed, false);
  assert.match(text, /Tidak ada yang perlu dihapus/u);
});

test('never removes a file that mea-skills did not create', async t => {
  const setup = await fixture(t);
  await fs.writeFile(setup.linkPath, 'user-owned');
  const { result, text } = await answerUnlink(setup, ['']);
  assert.equal(result.changed, false);
  assert.match(text, /bukan dibuat oleh mea-skills/u);
  assert.equal(await fs.readFile(setup.linkPath, 'utf8'), 'user-owned');
});

test('a symlink to another location needs explicit approval', async t => {
  const setup = await fixture(t);
  await fs.symlink('/old/mea-skills/scripts/trivy-porter.mjs', setup.linkPath);
  const declined = await answerUnlink(setup, ['', '']);
  assert.equal(declined.result.cancelled, true);
  await fs.lstat(setup.linkPath);

  await answerUnlink(setup, ['', 'y']);
  await assert.rejects(fs.lstat(setup.linkPath), { code: 'ENOENT' });
});

test('reports another trivy-porter still on PATH after removal', async t => {
  const setup = await fixture(t);
  await fs.symlink(setup.script, setup.linkPath);
  const other = path.join(setup.directory, 'node-24', 'bin');
  await fs.mkdir(other, { recursive: true });
  await fs.writeFile(path.join(other, 'trivy-porter'), '', { mode: 0o755 });
  const { text } = await answerUnlink(setup, ['', ''], { environment: { PATH: `${setup.bin}:${other}` } });
  assert.match(text, /Masih ada command trivy-porter lain di PATH/u);
});
