import type { Mission } from '../types.js'

// G15 of chapter IX: an ingestion step that keeps structure and provenance. No live call: parsing is checked on fixtures Verify writes itself.
export const mission: Mission = {
  id: 'extraction', chapter: 'voice', order: 15, title: 'Documents are not plain text', subtitle: 'Extract runbooks and reports into passages with provenance', sector: 'The archive', icon: '▤',
  block: 'The archive', files: ['ingest.py', 'runbook.md', 'incident.html', 'report.layout.json', 'demo.py'],
  nudge: 'Rumour says the archivist can quote a runbook back to the exact character and never has to search for it.',
  skills: ['Structure-preserving extraction', 'Provenance', 'Parser extension point'], prerequisites: ['embeddings', 'ledger'], xp: 240, duration: 'Self-paced', kind: 'build',
  briefs: {
    guided: 'The archive holds runbooks in Markdown, incident reports in HTML and supply reports that arrive as PDF layout JSON. Turn the starter that flattens them into text into an ingestion step whose passages keep headings, step order and table cells, and know which document, version and place they came from. Hints are available; guided work earns the same rewards.',
    connected: 'Replace an extract_text-style flattener with parsers that keep heading levels and chains, step numbers, table cells with row and column plus one line per row, line ranges or pages, and report every file they cannot read instead of raising. Prove it on fixtures where every cell has an expected row and column.',
    independent: 'Build an ingestion step for Markdown, HTML and parser-emitted layout JSON that never flattens a table, carries doc_id, version and a location on every passage, reports unparseable files without stopping the batch and takes a new format through a published extension point.',
  },
  objectives: [
    'Keep ingest.py importable with the class ParseError and the functions ingest(path, *, doc_id, version), ingest_batch(items) and register_parser(ext, fn). Both ingest functions return {passages, report}; items are {path, doc_id, version} dicts.',
    'Every passage carries doc_id and version as given, a text and a location with kind (heading, step, table or paragraph), path (the enclosing heading chain, outermost first; a heading ends with itself) and lines [first, last] for Markdown and HTML or page for layout JSON. Headings carry their integer level; steps carry the number as written, in document order; a list that continues after a note keeps counting.',
    'A table yields one passage per cell with location.table {index, row, col} (0-based, row 0 the header) and one passage per row whose text is the cells joined with " | " and whose table has no col. A passage holding cells of two rows is a flattened stream and fails.',
    'Markdown is parsed line by line: # headings, N. or N) steps, pipe tables with the delimiter row skipped, any other run of lines a paragraph. HTML is parsed with html.parser: h1–h6, ol/li steps, ul/li and p paragraphs, tr rows with th/td cells wherever they sit, text with entities decoded and whitespace collapsed, lines from start tag to end tag. Layout JSON (format layout/1, the output of a PDF layout parser) keeps page, bbox, heading levels and the cells’ own row and col indices regardless of their order in the list.',
    'A file with no registered extension (matched case-insensitively), invalid UTF-8, bad or non-layout JSON, HTML that ends with a table, tbody, tr, td, ol, ul, heading, body or html still open, or any exception from a parser is reported, never raised: ingest returns no passages and the report names the reason; ingest_batch records it and continues, and the other documents of the batch still produce their passages.',
    'The report has documents (one entry per input in order with doc_id, version, path, status, passages counted by heading, step, table, paragraph and total, and reason when unparseable), unparseable (the failed entries in order, [] when clean) and total (the number of passages).',
    'register_parser(ext, fn) makes fn(source, path) the parser for that extension from the next call on without touching the built-in parsers; fn returns {location, text} records and raises ParseError for a file it cannot read. Verify writes its own fixtures with fresh ids, versions and values and never calls a model. There is no live part.',
  ],
  languageGoal: 'Explain what a document loses when it becomes plain text and what provenance a quoted passage must carry.', prompt: 'Explain to the operator why the assistant can now quote a supply count from a report with the page and the table cell it came from, and what the old flattened text would have given instead. Name one file the archive could not read and what the report says about it.',
  hints: ['Run the demo and compare the runbook table with the one in runbook.md. Which passage holds the count 42, and what would you need to know to put it back into its row and column?', 'Each format has a small grammar: a heading opens a level, a step carries its number, a table is rows of cells. Write the location you want for each kind first, then make every parser produce exactly that; the report and the batch loop then stop depending on the format.', 'Keep a stack of (level, text) for the heading chain and pop everything at or below a new heading’s level. For Markdown, number steps from the digits on the line; for HTML, count inside the ol from its start attribute and collect td/th text in a tag stack; for the layout JSON, group cells by their own row and sort by col. Wrap each parser call in one try/except that fills the unparseable entry and continues.'],
  sources: [
    { title: 'Docling: supported formats and document provenance', url: 'https://docling-project.github.io/docling/' },
    { title: 'PyMuPDF: Page.find_tables() returns cells with row and column', url: 'https://pymupdf.readthedocs.io/en/latest/page.html#Page.find_tables' },
    { title: 'pdfplumber README: extract_tables() on machine-generated PDFs', url: 'https://github.com/jsvine/pdfplumber' },
    { title: 'Python html.parser: HTMLParser handlers and getpos()', url: 'https://docs.python.org/3.10/library/html.parser.html' },
  ],
  commands: ['python3 -B demo.py', 'python3 -B demo.py runbook.md', 'python3 -B demo.py report.layout.json broken.html memo.docx'],
  lesson: 'The starter strips Markdown markers and HTML tags into plain text, splits on blank lines so every passage is a paragraph without a heading chain or a line number, joins the cells of every table into one stream of words, drops the version from its passages, counts only a total and raises on the first file it cannot read so the rest of the batch never runs. LEARN.md publishes the passage shape, the grammar of each format, the table rule (cells with row and col plus one " | " line per row), the unparseable rule and the report. Verify writes fresh fixtures with hand-listed expected cells, steps and chains and checks every passage’s provenance; a flattened table or a batch that stops is caught by name. Out of scope: real PDF parsing (the layout JSON stands in for a maintained parser’s output), fenced code, nested lists, escaped pipes and chunking for retrieval, which is the next mission.',
  artifact: 'Ingestion step with an extraction report',
}

export const followUps: string[] = [
  'A new batch of reports arrives as real PDFs. Explain which parser you would put in front of your ingestion step, what its output must contain for your table rule to hold, and how you would check that a table survived.',
  'The operator asks why a supply count the assistant quoted cannot be found in the report. Explain what the passage’s location lets you do in under a minute, and what you would have had to do with flattened text.',
]
