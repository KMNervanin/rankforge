# Field manual — documents are not plain text

The archive of the outpost holds runbooks in Markdown, incident reports in HTML and supply reports that arrive as PDF. Before the assistant can answer from them with a source, every document has to become passages that still know what they were: a heading with its level, a numbered step in its order, a table cell with its row and column, and for each of them the document, the version and the place it came from. The starter flattens everything into plain text the way `extract_text()` would, loses the heading levels, joins a table into one stream of words and crashes on the first file it cannot read. That is the deliberate defect.

## Workshop and entry point

Python 3.10 or later, standard library only. Edit `ingest.py` and keep four names importable: the class `ParseError` and the functions `ingest`, `ingest_batch` and `register_parser`. Verify imports your module, writes its own fixtures into a fresh directory with fresh ids, versions, codes and counts, calls your functions with explicit keyword arguments and reads the passages and the report they return. The files in this lab (`runbook.md`, `incident.html`, `report.layout.json`, `broken.html`, `memo.docx`) are for your own terminal runs; Verify never reads them.

`python3 -B demo.py` ingests every fixture of the lab and prints one line per passage with its kind, heading chain and place, then the report. The starter stops at `memo.docx` with a traceback; a finished step reports that file and keeps going. There is no live call and no model in this mission.

## The problem

A PDF has no paragraphs, no headings and no tables: it has glyphs at coordinates. A plain-text extractor such as pypdf's `extract_text` returns the glyphs in stream order, so a 3×4 table becomes twelve words with nothing between them and a step list becomes one line. Layout parsers (Docling, PyMuPDF `find_tables`, pdfplumber `extract_tables`) do the geometry and hand you blocks with a type, a page, a bounding box, a heading level and, for tables, cells with row and column indices. Nothing in the standard library reads a PDF, so in this mission "PDF" means the JSON such a parser emits, `report.layout.json`; in production that file is the output of a maintained parser and your ingestion step starts where the parser ends. Markdown and HTML you parse for real.

The second half is provenance. A passage without its document id, version and location is a quote nobody can check; a cell without its row and column is a number nobody can read back into its table. Every passage you emit carries both.

## Complete public contract

```python
class ParseError(Exception): ...
ingest(path, *, doc_id, version) -> {"passages": [...], "report": {...}}
ingest_batch(items) -> {"passages": [...], "report": {...}}      # items: [{"path", "doc_id", "version"}, ...]
register_parser(ext, fn)                                          # ext ".txt"; fn(source: str, path: str) -> [{"location": {...}, "text": ...}, ...]
```

**Passage.** A dict with `doc_id` and `version` exactly as given to `ingest`, a `location` dict and a `text` string. Extra keys are allowed everywhere. The location has:

| key | value |
| --- | --- |
| `kind` | `heading`, `step`, `table` or `paragraph` |
| `path` | the heading chain: texts of the enclosing headings, outermost first; `[]` before the first heading. A heading's own path ends with itself |
| `lines` | `[first, last]`, 1-based inclusive line numbers in the file (Markdown and HTML) |
| `page` | the page number (layout JSON); `bbox` is copied from the block when it has one |
| `level` | headings only: the integer level, 1 to 6 |
| `number` | steps only: the integer written in the source, or counted from the list's start for HTML |
| `table` | table passages only: `{"index": t, "row": r, "col": c}` for a cell, `{"index": t, "row": r}` for a row. `index` counts tables in the document from 0, `row` and `col` are 0-based; row 0 is the header row |
| `span` | optional, on headings, steps, paragraphs and table cells: `[start, end]` character offsets into the file so that `source[start:end] == text` |

Chain rule for every format: a heading of level L closes every open heading of level L or deeper and opens itself; the chain crosses pages. Passages come out in document order (for the layout JSON, page order then block order).

**Tables.** For every row, one passage per cell in column order with `table.col` and the cell's text, then one passage for the row whose text is the cells joined with `" | "` (space, pipe, space) and whose `table` has no `col`. Never a single passage holding the cells of two rows: that is the flattened stream Verify rejects. A table of R rows and C columns counts R×C + R table passages.

**Markdown** (`.md`), line by line, no fenced code or nested lists in scope:

1. `#`…`######` followed by whitespace: a heading; the text is the rest of the line, stripped.
2. `N.` or `N)` followed by whitespace, optionally after leading spaces or tabs: one step per line; `number` is N as written, so a list that continues after a note keeps counting (steps 1–3, a safety paragraph, steps 4–5 are five steps numbered 1 to 5 in order with the paragraph between them).
3. A run of lines that, after stripping surrounding whitespace, start and end with `|`: a pipe table. The delimiter row (`|---|:--:|`) is skipped; every other line is a row; cells are the pieces between pipes, stripped; escaped pipes are out of scope.
4. Any other run of non-blank lines is a paragraph: the lines joined with `\n` and stripped; `lines` covers the run. A heading, step or table line ends the run.

**HTML** (`.html`, `.htm`), with `html.parser`: `h1`–`h6` are headings (`level` from the tag), `li` inside `ol` are steps numbered from the list's `start` attribute (default 1) in order, `li` inside `ul` and `p` are paragraphs, `table` rows are the `tr` elements in order wherever they sit (`thead` or `tbody`), cells are `th` and `td` in order. Text is the element's text with inline tags removed, entities decoded and whitespace collapsed to single spaces. `lines` runs from the line of the start tag to the line of the end tag; `script` and `style` content and text outside these elements are ignored. Verify's fixtures are well-formed: every element is closed. A file that ends while a `table`, `tbody`, `tr`, `td`, `ol`, `ul`, `h1`–`h6`, `body` or `html` is still open is unparseable; the reason names an unclosed element.

**Layout JSON** (`.json`): `{"format": "layout/1", "pages": [{"number": 1, "blocks": [...]}]}`. Block types: `heading` with `level` and `text`; `paragraph` with `text`; `list_item` with `number` and `text`; `table` with `cells`, each `{"row", "col", "text"}`, in no particular order: the indices are the truth, not the position in the list. Every block may carry `bbox`. Any other block type is ignored. Anything else (bad JSON, another `format`, no `pages`) is unparseable.

**Unparseable files.** No parser for the extension (matched case-insensitively, so `memo.docx` and `memo.DOCX` are both `.docx`), a file that is not UTF-8, a missing file, or a `ParseError` or any other exception raised by the parser: the document is reported, never raised and never dropped. `ingest` returns `passages: []` with the report below and `report.unparseable` with that one entry; `ingest_batch` records the reason and continues with the next item. The reason is a non-empty string; for a missing parser it names the extension; for a `ParseError` it is the error's message.

**Report.** `{"documents": [...], "unparseable": [...], "total": n}`. `documents` has one entry per input in input order: `doc_id`, `version`, `path` (as given), `status` (`parsed` or `unparseable`), `passages` = `{"heading", "step", "table", "paragraph", "total"}` counts (all zero when unparseable; a kind outside the four counts in `total` only) and `reason` when unparseable. `unparseable` repeats the failed entries as `{"doc_id", "version", "path", "reason"}` in input order and is `[]` for a clean batch. `total` is the number of passages returned. `ingest_batch` concatenates passages in input order.

**New formats.** `register_parser(ext, fn)` makes `fn` the parser for that extension from the next `ingest` on; the built-in parsers are untouched. `fn(source, path)` receives the decoded file text and the path and returns the passage records without `doc_id` and `version`, which `ingest` adds; it raises `ParseError` for a file it cannot read.

Worked example: the three Markdown lines `## Spares`, `| Item | Count |`, `| --- | --- |`, `| Fuse F220 | 8 |` under the title `# Runbook` give six passages: the heading (level 2, path `["Runbook", "Spares"]`), cells `Item` (0,0), `Count` (0,1), `Fuse F220` (1,0), `8` (1,1) and rows `Item | Count` and `Fuse F220 | 8`, every one with path `["Runbook", "Spares"]` and its line number; the table counts 6 and the document 7 passages.

## What Verify runs

Every check writes fresh fixtures: a runbook with a three-level heading chain, steps 1–5 around a safety note and a pipe table; an incident report with nested headings, an ordered list, a table across `thead`/`tbody`, an entity and an inline tag; a two-page layout JSON whose cells are shuffled; the same report cut inside a table row; a file named `.docx`. The checks: heading levels, chains and line numbers with step numbers and order in Markdown; every Markdown cell with its row and column, every row as one ` | ` line and no passage holding two rows; the same for HTML with line ranges; cells keeping the parser's indices and the chain crossing pages in the layout JSON; `doc_id`, `version`, `kind`, `path` and `lines` or `page` on every passage; the two unreadable files reported with reasons while the readable ones in the same batch still produce their passages; per-document counts by kind that add up; and a `.txt` convention joining through `register_parser`, including a `ParseError` from it, without changing the Markdown parser's output. One hidden bonus check exists; it can only add to the result and never fails the run.

Two different implementations pass: a line state machine for Markdown with a streaming `html.parser` subclass and plain dicts, and a regex block scanner with an HTML node tree, dataclasses and a parser list. No structure of `ingest.py` is required beyond the four importable names.

## Sources

- Docling documentation: supported formats and the document model with page and bounding-box provenance; TableFormer for table structure.
- PyMuPDF `Page.find_tables()` (1.23.0 and later) and `page.get_text()`: tables come back as cells with row and column, plain text extraction does not.
- pdfplumber README: `extract_tables()` on machine-generated PDFs; pypdf documentation: `extract_text()` has no table API.
- Python `html.parser.HTMLParser`: `handle_starttag`, `handle_data`, `getpos()` for the line of the current tag, `convert_charrefs`.
