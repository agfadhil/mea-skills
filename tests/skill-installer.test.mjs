import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { PassThrough, Writable } from 'node:stream';
import { test } from 'node:test';
import { runInstaller } from '../scripts/install-skills.mjs';
import { renderInstallSuccess } from '../scripts/installer-output.mjs';
import { applyInstallPlan, createInstallPlan, getDefaultTargets } from '../scripts/skill-installer.mjs';

async function fixture(t) {
  const directory = await fs.mkdtemp(path.join(tmpdir(), 'mea-skill-installer-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const repositoryRoot = path.join(directory, 'repository');
  const homeDirectory = path.join(directory, 'home');
  await fs.mkdir(repositoryRoot);
  await fs.mkdir(homeDirectory);
  return { directory, repositoryRoot, homeDirectory };
}

async function skill(repository, name, version) {
  const directory = path.join(repository, name);
  await fs.mkdir(path.join(directory, 'scripts'), { recursive: true });
  await fs.writeFile(path.join(directory, 'SKILL.md'), `---\nname: ${name}\ndescription: Fixture ${version}\n---\n${version}\n`);
  await fs.writeFile(path.join(directory, 'scripts', 'tool.txt'), version);
  return directory;
}

async function descendants(directory) {
  const result = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    result.push(filename);
    if (entry.isDirectory()) result.push(...await descendants(filename));
  }
  return result;
}

async function assertNoInstallerArtifacts(directory) {
  const names = (await descendants(directory)).map(filename => path.basename(filename));
  assert.equal(names.some(name => name === '.mea-skills-backups' || name.startsWith('.mea-skills-install-')), false);
}

test('default targets resolve Claude, Codex, and Antigravity skill directories across platforms', () => {
  for (const platform of ['darwin', 'linux', 'win32']) {
    const paths = platform === 'win32' ? path.win32 : path.posix;
    const homeDirectory = platform === 'win32' ? 'C:\\Users\\fixture' : '/home/fixture';
    const targets = getDefaultTargets({ platform, homeDirectory });
    assert.deepEqual(targets.map(target => target.id), ['claude', 'codex', 'antigravity']);
    assert.deepEqual(targets.map(target => target.directory), [
      paths.join(homeDirectory, '.claude', 'skills'),
      paths.join(homeDirectory, '.codex', 'skills'),
      paths.join(homeDirectory, '.gemini', 'config', 'skills'),
    ]);
  }
});

test('install and update replace selected skills without retaining backups or obsolete files', async t => {
  const setup = await fixture(t);
  const source = await skill(setup.repositoryRoot, 'sample', 'first');
  const targets = getDefaultTargets({ platform: 'darwin', homeDirectory: setup.homeDirectory });
  const initial = await createInstallPlan({ repositoryRoot: setup.repositoryRoot, targets });
  assert.equal((await applyInstallPlan(initial)).installed.length, 3);
  for (const target of targets) {
    assert.equal(await fs.readFile(path.join(target.directory, 'sample', 'scripts', 'tool.txt'), 'utf8'), 'first');
    await fs.mkdir(path.join(target.directory, 'sample', 'obsolete', 'nested'), { recursive: true });
    await fs.writeFile(path.join(target.directory, 'sample', 'obsolete', 'nested', 'old.txt'), 'old');
    await skill(target.directory, 'unrelated', 'user-owned');
  }
  await fs.writeFile(path.join(source, 'scripts', 'tool.txt'), 'second');
  const update = await createInstallPlan({ repositoryRoot: setup.repositoryRoot, targets });
  assert.deepEqual(update.operations.map(operation => operation.action), ['update', 'update', 'update']);
  const result = await applyInstallPlan(update);
  assert.equal(result.installed.length, 3);
  for (const target of targets) {
    assert.equal(await fs.readFile(path.join(target.directory, 'sample', 'scripts', 'tool.txt'), 'utf8'), 'second');
    await assert.rejects(fs.access(path.join(target.directory, 'sample', 'obsolete')), { code: 'ENOENT' });
    assert.equal(await fs.readFile(path.join(target.directory, 'unrelated', 'scripts', 'tool.txt'), 'utf8'), 'user-owned');
  }
  const unchanged = await applyInstallPlan(await createInstallPlan({ repositoryRoot: setup.repositoryRoot, targets }));
  assert.equal(unchanged.installed.length, 0);
  assert.equal(unchanged.unchanged.length, 3);
  await assertNoInstallerArtifacts(setup.directory);
});

test('source changes after planning leave the installed version intact', async t => {
  const setup = await fixture(t);
  const source = await skill(setup.repositoryRoot, 'sample', 'source');
  const targets = getDefaultTargets({ platform: 'darwin', homeDirectory: setup.homeDirectory });
  await skill(targets[0].directory, 'sample', 'installed');
  const plan = await createInstallPlan({ repositoryRoot: setup.repositoryRoot, targets: [targets[0]] });
  await fs.writeFile(path.join(source, 'scripts', 'tool.txt'), 'changed-after-planning');
  await assert.rejects(applyInstallPlan(plan));
  assert.equal(await fs.readFile(path.join(targets[0].directory, 'sample', 'scripts', 'tool.txt'), 'utf8'), 'installed');
  await assertNoInstallerArtifacts(setup.directory);
});

test('destination changes invalidate the entire plan before any selected skill is replaced', async t => {
  const setup = await fixture(t);
  await skill(setup.repositoryRoot, 'first', 'source-first');
  await skill(setup.repositoryRoot, 'second', 'source-second');
  const [target] = getDefaultTargets({ platform: 'darwin', homeDirectory: setup.homeDirectory });
  await skill(target.directory, 'first', 'installed-first');
  await skill(target.directory, 'second', 'installed-second');
  const plan = await createInstallPlan({ repositoryRoot: setup.repositoryRoot, targets: [target] });
  const changed = path.join(target.directory, 'second', 'scripts', 'tool.txt');
  await fs.writeFile(changed, 'user-edit-after-planning');
  await assert.rejects(applyInstallPlan(plan));
  assert.equal(await fs.readFile(path.join(target.directory, 'first', 'scripts', 'tool.txt'), 'utf8'), 'installed-first');
  assert.equal(await fs.readFile(changed, 'utf8'), 'user-edit-after-planning');
  await assertNoInstallerArtifacts(setup.directory);
});

async function answerInstaller(setup, answers) {
  const input = new PassThrough();
  const remaining = [...answers];
  const output = new Writable({ write(chunk, _encoding, done) {
    if (chunk.toString().endsWith(': ')) {
      assert.ok(remaining.length, 'Installer requested an unexpected answer');
      const answer = remaining.shift();
      queueMicrotask(() => input.write(answer + '\n'));
    }
    done();
  } });
  try {
    const result = await runInstaller({ ...setup, input, output, platform: 'darwin', environment: {}, cwd: setup.directory });
    assert.equal(remaining.length, 0);
    return result;
  } finally {
    input.destroy();
    output.destroy();
  }
}

test('menu selections install to all targets or the requested individual target', async t => {
  for (const [name, answers, ids] of [
    ['all', ['', '', '', '', 'y'], ['claude', 'codex', 'antigravity']],
    ['Claude', ['2', '', 'y'], ['claude']],
    ['Codex', ['3', '', 'y'], ['codex']],
    ['Antigravity', ['4', '', 'y'], ['antigravity']],
  ]) {
    await t.test(name, async subtest => {
      const setup = await fixture(subtest);
      await skill(setup.repositoryRoot, 'sample', 'source');
      const result = await answerInstaller(setup, answers);
      assert.deepEqual(result.installed.map(operation => operation.targetId), ids);
      for (const target of getDefaultTargets({ platform: 'darwin', homeDirectory: setup.homeDirectory })) {
        const installed = path.join(target.directory, 'sample', 'SKILL.md');
        if (ids.includes(target.id)) assert.match(await fs.readFile(installed, 'utf8'), /Fixture source/);
        else await assert.rejects(fs.access(installed), { code: 'ENOENT' });
      }
      await assertNoInstallerArtifacts(setup.directory);
    });
  }
});

test('canceling before confirmation leaves destination directories untouched', async t => {
  const setup = await fixture(t);
  await skill(setup.repositoryRoot, 'sample', 'source');
  const result = await answerInstaller(setup, ['', '', '', '', 'n']);
  assert.equal(result.cancelled, true);
  assert.deepEqual(await fs.readdir(setup.homeDirectory), []);
  await assertNoInstallerArtifacts(setup.directory);
});

test('next steps explain npm link for one Node.js version and terminal-link for several', () => {
  const plan = { skills: [{ name: 'trivy-porter' }], targets: [{ id: 'claude', label: 'Claude', directory: '/skills' }] };
  const text = renderInstallSuccess(plan, { installed: [], unchanged: [] }, { columns: 200 });
  assert.match(text, /INSTRUKSI SELANJUTNYA/u);
  assert.match(text, /satu versi Node\.js[\s\S]*npm link/u);
  assert.match(text, /beberapa versi Node\.js[\s\S]*pnpm run mea-skills:terminal-link/u);
  assert.match(text, /npm unlink -g mea-skills/u);
  assert.match(text, /pnpm run mea-skills:terminal-unlink/u);
});
