import { createHash } from 'node:crypto';
import * as fs from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';

const ignored = (name) => ['.git', 'node_modules', '__pycache__', '.DS_Store'].includes(name) || name.endsWith('.pyc');
const pathApi = (platform) => platform === 'win32' ? path.win32 : path.posix;

export function getDefaultTargets({ platform = process.platform, homeDirectory = homedir() } = {}) {
  const paths = pathApi(platform);
  return [
    { id: 'claude', label: 'Claude', directory: paths.join(homeDirectory, '.claude', 'skills') },
    { id: 'codex', label: 'Codex', directory: paths.join(homeDirectory, '.codex', 'skills') },
    { id: 'antigravity', label: 'Antigravity', directory: paths.join(homeDirectory, '.gemini', 'config', 'skills') },
  ];
}

export function resolveDestination(raw, fallback, {
  platform = process.platform, homeDirectory = homedir(), cwd = process.cwd(), env = process.env,
} = {}) {
  const paths = pathApi(platform);
  let value = raw.trim() || fallback;
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    value = value.slice(1, -1);
  }
  if (!value || /[\0\r\n]/u.test(value)) throw new Error('Path instalasi tidak valid.');
  if (value === '~') value = homeDirectory;
  else if (/^~[/\\]/u.test(value)) value = paths.join(homeDirectory, value.slice(2));
  else if (value.startsWith('~')) throw new Error('Gunakan ~ atau path lengkap untuk folder pengguna.');

  const variables = { ...env, HOME: homeDirectory, USERPROFILE: homeDirectory };
  const lookup = (name) => {
    const key = platform === 'win32'
      ? Object.keys(variables).find((item) => item.toLowerCase() === name.toLowerCase()) : name;
    if (key === undefined || variables[key] === undefined) throw new Error(`Variabel path tidak ditemukan: ${name}`);
    return variables[key];
  };
  value = value.replace(/%([A-Za-z_][\w]*)%|\$\{([A-Za-z_][\w]*)\}|\$([A-Za-z_][\w]*)/gu,
    (_match, percent, braces, plain) => lookup(percent || braces || plain));
  if (platform === 'win32' && /^[A-Za-z]:[^/\\]/u.test(value)) {
    throw new Error('Gunakan path Windows lengkap, misalnya C:\\Users\\Nama\\skills.');
  }
  if (platform !== 'win32' && (/^[A-Za-z]:[/\\]/u.test(value) || value.startsWith('\\\\'))) {
    throw new Error('Path Windows tidak dapat digunakan pada OS ini.');
  }
  return paths.resolve(cwd, value);
}

async function lstatOrNull(filename) {
  try { return await fs.lstat(filename); }
  catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}

async function manifest(directory) {
  const result = [];
  async function visit(folder, prefix = '') {
    const entries = (await fs.readdir(folder, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      if (ignored(entry.name)) continue;
      const filename = path.join(folder, entry.name);
      const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isSymbolicLink()) throw new Error(`Symlink dalam skill tidak didukung: ${filename}`);
      if (entry.isDirectory()) {
        result.push([relative, 'directory']);
        await visit(filename, relative);
      } else if (entry.isFile()) {
        result.push([relative, createHash('sha256').update(await fs.readFile(filename)).digest('hex')]);
      } else throw new Error(`File skill tidak didukung: ${filename}`);
    }
  }
  await visit(directory);
  return JSON.stringify(result);
}

async function existingManifest(directory) {
  const stat = await lstatOrNull(directory);
  if (!stat) return null;
  if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error(`Tujuan skill harus berupa folder biasa: ${directory}`);
  return manifest(directory);
}

export async function discoverSkills(repositoryRoot) {
  const skills = [];
  for (const entry of await fs.readdir(repositoryRoot, { withFileTypes: true })) {
    if (entry.name.startsWith('.') || !entry.isDirectory() || ignored(entry.name)) continue;
    const source = path.join(repositoryRoot, entry.name);
    const metadata = await lstatOrNull(path.join(source, 'SKILL.md'));
    if (!metadata) continue;
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/u.test(entry.name) || !metadata.isFile() || metadata.isSymbolicLink()) {
      throw new Error(`Folder skill atau SKILL.md tidak valid: ${source}`);
    }
    await manifest(source);
    skills.push({ name: entry.name, source });
  }
  if (skills.length === 0) throw new Error('Tidak ada folder skill dengan SKILL.md di repository ini.');
  return skills.sort((a, b) => a.name.localeCompare(b.name));
}

function within(parent, child) {
  const relative = path.relative(parent, child);
  return relative === '' || (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}

async function canonicalDestination(directory) {
  const suffix = [];
  let current = path.resolve(directory);
  while (!(await lstatOrNull(current))) {
    suffix.unshift(path.basename(current));
    const parent = path.dirname(current);
    if (parent === current) throw new Error(`Root path tidak ditemukan: ${directory}`);
    current = parent;
  }
  if (!(await fs.stat(current)).isDirectory()) throw new Error(`Path induk bukan folder: ${current}`);
  return path.join(await fs.realpath(current), ...suffix);
}

export async function createInstallPlan({ repositoryRoot, targets }) {
  const root = await fs.realpath(repositoryRoot);
  const skills = await discoverSkills(root);
  if (!Array.isArray(targets) || targets.length === 0) throw new Error('Pilih minimal satu tujuan instalasi.');
  const normalizedTargets = [];
  for (const target of targets) {
    if (!/^[a-z0-9-]+$/u.test(target.id)) throw new Error('ID target tidak valid.');
    const directory = await canonicalDestination(target.directory);
    const existing = normalizedTargets.find((item) => path.relative(item.directory, directory) === '');
    if (existing) { existing.label += ` + ${target.label}`; continue; }
    if (normalizedTargets.some((item) => within(item.directory, directory) || within(directory, item.directory))) {
      throw new Error('Folder tujuan instalasi tidak boleh saling berada di dalam folder tujuan lainnya.');
    }
    normalizedTargets.push({ ...target, directory });
  }
  const operations = [];
  for (const target of normalizedTargets) {
    for (const skill of skills) {
      const destination = path.join(target.directory, skill.name);
      if (skills.some((item) => within(item.source, destination) || within(destination, item.source))) {
        throw new Error(`Tujuan instalasi bertumpang tindih dengan sumber skill: ${destination}`);
      }
      const sourceManifest = await manifest(skill.source);
      const destinationManifest = await existingManifest(destination);
      const action = destinationManifest === sourceManifest ? 'unchanged' : destinationManifest === null ? 'install' : 'update';
      operations.push({
        name: skill.name, source: skill.source, destination, targetId: target.id,
        targetLabel: target.label, sourceManifest, destinationManifest, action,
      });
    }
  }
  return { repositoryRoot: root, skills, targets: normalizedTargets, operations };
}

export async function applyInstallPlan(plan) {
  // Recheck the whole confirmed plan before changing any destination.
  for (const operation of plan.operations) {
    if (await manifest(operation.source) !== operation.sourceManifest
        || await existingManifest(operation.destination) !== operation.destinationManifest) {
      throw new Error(`File berubah setelah rencana dibuat. Jalankan installer lagi: ${operation.name}`);
    }
  }
  const preparedCopies = [];
  const installed = [];
  const temporaryDirectories = [];
  try {
    for (const operation of plan.operations) {
      if (operation.action === 'unchanged') continue;
      const parent = path.dirname(path.dirname(operation.destination));
      await fs.mkdir(parent, { recursive: true });
      const temporary = await fs.mkdtemp(path.join(parent, '.mea-skills-install-'));
      temporaryDirectories.push(temporary);
      const prepared = path.join(temporary, operation.name);
      await fs.cp(operation.source, prepared, {
        recursive: true,
        filter: (filename) => !ignored(path.basename(filename)),
      });
      if (await manifest(prepared) !== operation.sourceManifest) throw new Error(`Verifikasi salinan gagal: ${operation.name}`);
      preparedCopies.push({ operation, prepared });
    }
    // Prepare every new copy before replacing any installed skill. No old
    // version is saved; successfully completed replacements stay installed.
    for (const operation of plan.operations) {
      if (await existingManifest(operation.destination) !== operation.destinationManifest) {
        throw new Error(`Tujuan berubah saat salinan disiapkan. Jalankan installer lagi: ${operation.name}`);
      }
    }
    for (const { operation, prepared } of preparedCopies) {
      await fs.mkdir(path.dirname(operation.destination), { recursive: true });
      if (operation.action === 'update') {
        await fs.rm(operation.destination, { recursive: true });
      }
      await fs.rename(prepared, operation.destination);
      if (await manifest(operation.destination) !== operation.sourceManifest) throw new Error(`Verifikasi instalasi gagal: ${operation.name}`);
      installed.push(operation);
    }
    return {
      installed: plan.operations.filter((item) => item.action !== 'unchanged'),
      unchanged: plan.operations.filter((item) => item.action === 'unchanged'),
    };
  } catch (error) {
    if (installed.length) {
      throw new Error(`${error.message}\nSkill yang sudah selesai tetap terpasang:\n${installed.map((item) => `- ${item.destination}`).join('\n')}`, { cause: error });
    }
    throw error;
  } finally {
    for (const temporary of temporaryDirectories) await fs.rm(temporary, { recursive: true, force: true });
  }
}
