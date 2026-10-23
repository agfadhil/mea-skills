import { stripVTControlCharacters } from 'node:util';

const tones = {
  border: '90', brand: '1;36', success: '1;32', heading: '1;37',
  label: '1;36', muted: '90', command: '1;36',
};

function cellWidth(character) {
  if (/\p{Mark}/u.test(character)) return 0;
  const code = character.codePointAt(0);
  return code >= 0x1100 && (
    code <= 0x115f || code === 0x2329 || code === 0x232a ||
    (code >= 0x2e80 && code <= 0xa4cf) || (code >= 0xac00 && code <= 0xd7a3) ||
    (code >= 0xf900 && code <= 0xfaff) || (code >= 0xfe10 && code <= 0xfe6f) ||
    (code >= 0xff00 && code <= 0xff60) || (code >= 0xffe0 && code <= 0xffe6) ||
    (code >= 0x1f300 && code <= 0x1faff) || code >= 0x20000
  ) ? 2 : 1;
}

const textWidth = (value) => [...value].reduce((width, character) => width + cellWidth(character), 0);

function wrap(value, width, preserveWhitespace = false) {
  const clean = stripVTControlCharacters(String(value)).replace(/[\x00-\x1f\x7f]/gu, ' ');
  if (textWidth(clean) <= width) return [clean];
  const words = preserveWhitespace ? [clean] : clean.split(/\s+/u).filter(Boolean);
  const lines = [];
  let line = '';
  for (const word of words) {
    if (line && textWidth(line) + 1 + textWidth(word) > width) {
      lines.push(line);
      line = '';
    }
    if (line) line += ' ';
    for (const character of word) {
      if (line && textWidth(line) + cellWidth(character) > width) {
        lines.push(line);
        line = '';
      }
      line += character;
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [''];
}

export function renderInstallSuccess(plan, result, { columns = 80, isTTY = false, environment = {} } = {}) {
  const color = !Object.hasOwn(environment, 'NO_COLOR') && environment.TERM !== 'dumb' &&
    environment.FORCE_COLOR !== '0' && Boolean(isTTY || environment.FORCE_COLOR);
  const paint = (text, tone) => color && tone ? `\x1b[${tones[tone]}m${text}\x1b[0m` : text;
  const width = Math.max(12, Math.min(Number.isFinite(columns) ? Math.floor(columns) : 80, 78));
  const boxed = width >= 52;
  const contentWidth = width - (boxed ? 6 : 2);
  const rows = [];
  const add = (text = '', tone, indent = 0, preserveWhitespace = false) => {
    const padding = Math.min(indent, contentWidth - 2);
    for (const line of wrap(text, contentWidth - padding, preserveWhitespace)) rows.push({ text: ' '.repeat(padding) + line, tone });
  };
  const agents = plan.targets.map(target => target.label).join('/');
  const hasTrivy = plan.skills.some(skill => skill.name === 'trivy-porter');

  add('MEA SKILLS', 'brand');
  add();
  add(result.installed.length ? '✓ Instalasi selesai' : '✓ Semua skill sudah terbaru', 'success');
  add(`${plan.skills.length} skill · ${plan.targets.length} tujuan instalasi`, 'muted');
  add();
  add(`${result.installed.length} dipasang / diperbarui   ·   ${result.unchanged.length} sudah terbaru`, 'heading');
  add();
  add('LOKASI INSTALASI', 'label');
  for (const target of plan.targets) {
    add();
    add(target.label, 'heading');
    add(target.directory, 'muted', 2, true);
  }
  add();
  rows.push({ divider: true });
  add();
  add('LANGKAH BERIKUTNYA', 'label');
  add();
  add('01  Buka sesi agent baru', 'heading');
  add(`Jika skill belum muncul, mulai sesi ${agents} yang baru.`, 'muted', 4);

  if (hasTrivy) {
    add();
    add('02  Siapkan Trivy Porter', 'heading');
    add('Pastikan Git, Trivy, dan Python 3 tersedia di terminal.', 'muted', 4);
    add();
    add('Aktifkan command sekali dari repository mea-skills:', 'muted', 4);
    add('npm link', 'command', 4);
    add();
    add('Lalu jalankan dari folder proyek aplikasi:', 'muted', 4);
    add('trivy-porter', 'command', 4);
  }
  add();

  const border = (left, right) => paint(left + '─'.repeat(width - 2) + right, 'border');
  const lines = boxed ? [border('╭', '╮')] : [];
  for (const row of rows) {
    if (row.divider) {
      lines.push(boxed ? border('├', '┤') : paint('─'.repeat(width), 'border'));
      continue;
    }
    const text = paint(row.text, row.tone);
    lines.push(boxed
      ? `${paint('│', 'border')}  ${text}${' '.repeat(Math.max(0, contentWidth - textWidth(row.text)))}  ${paint('│', 'border')}`
      : `  ${text}`);
  }
  if (boxed) lines.push(border('╰', '╯'));
  return '\n' + lines.join('\n') + '\n';
}
