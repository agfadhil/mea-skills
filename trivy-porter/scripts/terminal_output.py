"""Readable terminal handoffs; keep the copyable chat command untouched."""

import os
import re
import shutil
import unicodedata


_TONES = {
    "border": "90", "brand": "1;36", "heading": "1;37",
    "label": "1;36", "muted": "90", "success": "1;32", "warning": "1;33",
}
_STAGES = {
    "configuring": "Konfigurasi scan", "scan_failed": "Scan perlu dipulihkan",
    "awaiting_analysis": "Menunggu analisis", "awaiting_batch": "Menunggu pilihan batch",
    "batch_in_progress": "Batch sedang dikerjakan", "paused": "Sesi dijeda",
    "complete": "Sesi selesai",
}


def _clean(value):
    text = str(value)
    text = re.sub(r"\x1b\].*?(?:\x07|\x1b\\|$)", "", text, flags=re.S)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)


def _cell_width(character):
    if unicodedata.combining(character) or unicodedata.category(character) == "Cf":
        return 0
    return 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1


def _width(text):
    return sum(_cell_width(character) for character in text)


def _wrap(value, width, preserve_whitespace=False):
    text = _clean(value)
    if _width(text) <= width:
        return [text]
    # Prefer directory boundaries for metadata paths; retain every character.
    words = re.findall(r".*?[/\\]|[^/\\]+$", text) if preserve_whitespace else text.split()
    lines, line = [], ""
    for word in words:
        spacing = 0 if preserve_whitespace else 1
        if line and _width(line) + spacing + _width(word) > width:
            lines.append(line)
            line = ""
        if line and not preserve_whitespace:
            line += " "
        for character in word:
            if line and _width(line) + _cell_width(character) > width:
                lines.append(line)
                line = ""
            line += character
    if line:
        lines.append(line)
    return lines or [""]


def _headline(data, result):
    stage = data.get("stage")
    request = data.get("batch_request") or {}
    if stage == "awaiting_analysis":
        if result.get("interrupted"):
            return "! Scan terinterupsi", "warning", "Laporan tersimpan perlu ditinjau agent."
        if result.get("truncated"):
            return "! Tangkapan laporan terbatas", "warning", "Bukti yang tersimpan mungkin belum lengkap."
        if result.get("exit_code") not in (None, 0):
            return "! Laporan perlu ditinjau", "warning", "Exit code dapat menandakan temuan atau kendala scan."
        if not result or result.get("exit_code") is None:
            return "! Bukti scan perlu diperiksa", "warning", "Agent perlu memeriksa laporan sesi ini."
        return "✓ Laporan scan tersimpan", "success", "Siap dianalisis di chat agent."
    if stage == "batch_in_progress":
        return "↻ Lanjutkan batch berjalan", "warning", "Agent akan meninjau pekerjaan batch yang sudah dimulai."
    if request.get("status") == "pending":
        return "✓ Pilihan batch tersimpan", "success", "Lanjutkan permintaan batch ini di chat agent."
    return "↻ Lanjutkan sesi", "label", "Agent akan meninjau status dan langkah sesi berikutnya."


def render_handoff(data, project, state_base, command, columns=None, is_tty=False, environment=None):
    """Render metadata in a panel, then one raw, unwrapped command line.

    The caller supplies a command with literal arguments already quoted. It is
    deliberately excluded from styling and wrapping so copying preserves it.
    """
    environment = os.environ if environment is None else environment
    if columns is None:
        columns = shutil.get_terminal_size((88, 24)).columns
    try:
        columns = int(columns)
    except (TypeError, ValueError, OverflowError):
        columns = 88
    width = min(88, columns) if columns > 0 else 88
    boxed = width >= 56
    outer_indent = 0 if width < 12 else 2
    content_width = max(1, width - (6 if boxed else outer_indent))
    color = ("NO_COLOR" not in environment and environment.get("TERM") != "dumb"
             and environment.get("FORCE_COLOR") != "0"
             and bool(is_tty or environment.get("FORCE_COLOR")))

    def paint(text, tone=None):
        return "\x1b[" + _TONES[tone] + "m" + text + "\x1b[0m" if color and tone else text

    rows = []

    def add(text="", tone=None, indent=0, preserve_whitespace=False):
        indent = min(indent, max(0, content_width - 2))
        for line in _wrap(text, max(1, content_width - indent), preserve_whitespace):
            rows.append((" " * indent + line, tone))

    scan = data.get("scan") if isinstance(data.get("scan"), dict) else {}
    result = scan.get("result") if isinstance(scan.get("result"), dict) else {}
    title, tone, subtitle = _headline(data, result)
    add("TRIVY PORTER", "brand")
    add()
    add(title, tone)
    add(subtitle, "muted")
    if result:
        method = {"fs": "Filesystem", "image": "Container image"}.get(scan.get("method"), scan.get("method") or "Scan")
        exit_code = result.get("exit_code")
        status = method + (" · exit " + str(exit_code) if exit_code is not None else " · exit belum tersedia")
        add(status, tone if tone == "warning" else "heading")
        if scan.get("target"):
            add("Target: " + str(scan["target"]), "muted", preserve_whitespace=True)
    add()
    add("DETAIL SESI", "label")
    add("Sesi   " + str(data.get("session_id", "Belum tersedia")), "heading")
    add("Tahap  " + _STAGES.get(data.get("stage"), "Perlu ditinjau"), "muted")
    add()
    add("PROYEK", "label")
    add(project, "muted", 2, True)
    add()
    add("PENYIMPANAN SESI", "label")
    add(state_base, "muted", 2, True)
    add()
    rows.append((None, None))
    add()
    add("LANJUT DI CHAT AGENT", "label")
    add("Buka chat pada proyek ini, lalu salin perintah di bawah.", "heading")
    if data.get("stage") == "awaiting_analysis":
        add("Exit code saja tidak membuktikan nol temuan atau cakupan scan lengkap.", "muted")
        if result.get("truncated") and result.get("interrupted"):
            add("Tangkapan output juga terbatas.", "warning")
    add("Kirim secara manual; terminal tidak mengirim pesan ke chat.", "muted")
    add()

    def border(left, right):
        return paint(left + "─" * (width - 2) + right, "border")

    lines = [border("╭", "╮")] if boxed else []
    for text, row_tone in rows:
        if text is None:
            lines.append(border("├", "┤") if boxed else paint("─" * width, "border"))
        elif boxed:
            lines.append(paint("│", "border") + "  " + paint(text, row_tone)
                         + " " * max(0, content_width - _width(text)) + "  " + paint("│", "border"))
        else:
            lines.append(" " * outer_indent + paint(text, row_tone))
    if boxed:
        lines.append(border("╰", "╯"))
    return "\n" + "\n".join(lines) + "\n\n" + paint("SALIN KE CHAT", "label") + "\n" + command + "\n"
