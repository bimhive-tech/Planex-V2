"""Turns an uploaded chat attachment into plain text the model can read.
Excel/MD/TXT now; PDF is a stated v1 gap (see the plan) — it returns a clear
placeholder instead of crashing, so the assistant can tell the user why.

No character cap here — a hardcoded truncation point silently cut off real
schedules mid-file, producing an incomplete-but-plausible-looking import with
no clear signal why. If a file is genuinely too large for the model's own
context window, that now surfaces as a clear error from the API (see
services.py's timeout + logging) instead of a silent partial read."""
import openpyxl

TEXT_EXTENSIONS = {"txt", "md"}
EXCEL_EXTENSIONS = {"xlsx", "xlsm"}


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _dump_workbook(file_obj) -> str:
    wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
    try:
        lines = []
        for ws in wb.worksheets:
            lines.append(f"Sheet: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                if all(c is None or c == "" for c in row):
                    continue
                cells = [str(c) for c in row if c is not None and c != ""]
                lines.append(" | ".join(cells))
        return "\n".join(lines)
    finally:
        wb.close()


def extract_text(file_obj, filename: str, content_type: str = "") -> str:
    ext = _ext(filename)
    if ext in EXCEL_EXTENSIONS:
        text = _dump_workbook(file_obj)
    elif ext in TEXT_EXTENSIONS:
        raw = file_obj.read()
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    elif ext == "pdf":
        return "[PDF attachment received — PDF text extraction isn't implemented yet in Planex's AI assistant.]"
    else:
        return f"[Unsupported file type .{ext} — couldn't extract text.]"

    return text
