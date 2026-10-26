"""Safe text extraction from uploaded files.

Files are treated as untrusted: the declared extension must match the file's real signature, archives are
checked for zip bombs before parsing, nothing in a file is executed (spreadsheet formulas are read as cached
values, PDF scripts are ignored), and extraction fails loudly rather than pretending a file was read.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass

from django.conf import settings

EXTENSIONS = {
    "pdf": "pdf",
    "docx": "docx",
    "xlsx": "xlsx",
    "csv": "csv",
    "txt": "text",
    "md": "text",
    "markdown": "text",
    "json": "text",
    "py": "text",
    "js": "text",
    "ts": "text",
    "tsx": "text",
    "jsx": "text",
    "java": "text",
    "go": "text",
    "rb": "text",
    "php": "text",
    "cs": "text",
    "c": "text",
    "h": "text",
    "cpp": "text",
    "rs": "text",
    "kt": "text",
    "swift": "text",
    "sql": "text",
    "html": "text",
    "css": "text",
    "yaml": "text",
    "yml": "text",
    "toml": "text",
    "xml": "text",
    "sh": "text",
    "dart": "text",
}


class ExtractionError(Exception):
    """A user-facing reason why a file could not be read."""


@dataclass(frozen=True)
class Segment:
    text: str
    page: int | None = None
    location: str = ""


@dataclass(frozen=True)
class Extracted:
    segments: list[Segment]
    page_count: int | None = None

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.segments)


def kind_for(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    kind = EXTENSIONS.get(ext)
    if not kind:
        supported = "PDF, DOCX, XLSX, CSV, TXT, Markdown and common source-code files"
        raise ExtractionError(f"Unsupported file type '.{ext}'. Supported: {supported}.")
    return kind


def check_signature(kind: str, head: bytes) -> None:
    """Rejects files whose content does not match their extension (e.g. an executable renamed to .pdf)."""
    if kind == "pdf" and not head.startswith(b"%PDF-"):
        raise ExtractionError("This file is not a valid PDF.")
    if kind in ("docx", "xlsx") and not head.startswith(b"PK\x03\x04"):
        raise ExtractionError(f"This file is not a valid .{kind} document.")
    if kind in ("text", "csv"):
        if b"\x00" in head and not head.startswith((b"\xff\xfe", b"\xfe\xff")):  # allow UTF-16 with BOM
            raise ExtractionError("This file looks binary, not text.")
        if head.startswith((b"MZ", b"\x7fELF", b"%PDF-", b"PK\x03\x04")):
            raise ExtractionError("This file's content does not match its text extension.")


CODE_EXTENSIONS = {"py", "js", "ts", "tsx", "jsx", "java", "go", "rb", "php", "cs", "c", "h", "cpp", "rs", "kt",
                   "swift", "sql", "html", "css", "sh", "dart", "yaml", "yml", "toml", "xml", "json"}
CODE_LINES_PER_SEGMENT = 60


def extract(kind: str, data: bytes, filename: str = "") -> Extracted:
    if not data:
        raise ExtractionError("The file is empty.")
    check_signature(kind, data[:8])
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if kind == "text" and ext in CODE_EXTENSIONS:
        result = _code(data)
    else:
        result = {"pdf": _pdf, "docx": _docx, "xlsx": _xlsx, "csv": _csv, "text": _text}[kind](data)
    if result.char_count > settings.MAX_EXTRACTED_CHARS:
        raise ExtractionError(
            f"The document contains more than {settings.MAX_EXTRACTED_CHARS:,} characters of text, which exceeds "
            "this workspace's limit."
        )
    if not any(s.text.strip() for s in result.segments):
        raise ExtractionError("No readable text was found in this file.")
    return result


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    # Fallback for legacy Windows files; reject content that is clearly not text.
    text = data.decode("cp1252", errors="replace")
    if text.count("\ufffd") > len(text) * 0.01:
        raise ExtractionError("Could not decode this file as text.")
    return text


def _text(data: bytes) -> Extracted:
    return Extracted([Segment(_decode(data).replace("\r\n", "\n"))])


def _code(data: bytes) -> Extracted:
    """Source code in line-numbered sections, so answers can cite exact line ranges."""
    lines = _decode(data).replace("\r\n", "\n").split("\n")
    segments = []
    for start in range(0, len(lines), CODE_LINES_PER_SEGMENT):
        block = lines[start : start + CODE_LINES_PER_SEGMENT]
        if any(line.strip() for line in block):
            first, last = start + 1, start + len(block)
            numbered = "\n".join(f"{first + i:>5} | {line}" for i, line in enumerate(block))
            segments.append(Segment(numbered, location=f"Lines {first}–{last}"))
    return Extracted(segments)


def _pdf(data: bytes) -> Extracted:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("This PDF is password-protected. Remove the password and upload it again.")
        pages = reader.pages
        if len(pages) > settings.MAX_PDF_PAGES:
            raise ExtractionError(f"This PDF has {len(pages)} pages; the limit is {settings.MAX_PDF_PAGES}.")
        segments = []
        for number, page in enumerate(pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                segments.append(Segment(text, page=number, location=f"Page {number}"))
    except ExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise ExtractionError("This PDF is damaged or uses an unsupported format.") from e
    if not segments:
        raise ExtractionError(
            "No text could be extracted from this PDF. It may be a scanned image; OCR is not supported yet."
        )
    return Extracted(segments, page_count=len(pages))


def _check_zip(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile as e:
        raise ExtractionError("This file is damaged or not a valid Office document.") from e
    total = sum(i.file_size for i in infos)
    if len(infos) > 10_000 or total > settings.MAX_UNCOMPRESSED_MB * 1024 * 1024:
        raise ExtractionError("This file expands to an unsafe size and was rejected.")


def _docx(data: bytes) -> Extracted:
    _check_zip(data)
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as e:  # python-docx raises a variety of parser errors
        raise ExtractionError("This Word document is damaged or unsupported.") from e

    segments: list[Segment] = []
    heading = ""
    buffer: list[str] = []

    def flush():
        if buffer:
            segments.append(Segment("\n".join(buffer), location=f"Section: {heading}" if heading else ""))
            buffer.clear()

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if (paragraph.style.name or "").lower().startswith("heading"):
            flush()
            heading = text[:150]
            buffer.append(f"## {text}")
        else:
            buffer.append(text)
    flush()
    for n, table in enumerate(document.tables, start=1):
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        if any(r.strip(" |") for r in rows):
            segments.append(Segment("\n".join(rows), location=f"Table {n}"))
    return Extracted(segments)


def _rows_to_segments(rows: list[list[str]], sheet: str | None, rows_per_segment: int = 60) -> list[Segment]:
    if not rows:
        return []
    header, body = rows[0], rows[1:]
    segments = []
    prefix = f"{sheet}, " if sheet else ""
    for start in range(0, max(len(body), 1), rows_per_segment):
        block = body[start : start + rows_per_segment]
        lines = [", ".join(header)] + [", ".join(r) for r in block]
        first, last = start + 2, start + 1 + len(block)  # spreadsheet row numbers (header is row 1)
        segments.append(Segment("\n".join(lines), location=f"{prefix}rows {first}–{last}"))
    return segments


def _csv(data: bytes) -> Extracted:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = []
    for i, row in enumerate(csv.reader(io.StringIO(text), dialect)):
        if i > settings.MAX_SPREADSHEET_ROWS:
            raise ExtractionError(f"This CSV has more than {settings.MAX_SPREADSHEET_ROWS:,} rows.")
        rows.append([c.strip() for c in row])
    return Extracted(_rows_to_segments(rows, None))


def _xlsx(data: bytes) -> Extracted:
    _check_zip(data)
    import openpyxl

    try:
        # data_only=True reads cached cell values; formulas are never evaluated.
        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        raise ExtractionError("This Excel file is damaged or unsupported.") from e
    segments: list[Segment] = []
    total = 0
    try:
        for sheet in workbook.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                total += 1
                if total > settings.MAX_SPREADSHEET_ROWS:
                    raise ExtractionError(f"This workbook has more than {settings.MAX_SPREADSHEET_ROWS:,} rows.")
                values = ["" if v is None else str(v).strip() for v in row]
                if any(values):
                    rows.append(values)
            segments += _rows_to_segments(rows, sheet.title)
    finally:
        workbook.close()
    return Extracted(segments)
