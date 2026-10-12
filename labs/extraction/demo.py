"""Terminal demo: python3 -B demo.py [file ...]

Runs ingest.ingest_batch over the given files (default: every fixture of this lab) with
doc ids derived from the file names and version "v1", prints one line per passage with
its kind, heading chain, place and text, then the extraction report.
"""
import json
import os
import sys

import ingest

FIXTURES = ["runbook.md", "incident.html", "report.layout.json", "broken.html", "memo.docx"]

if __name__ == "__main__":
    files = sys.argv[1:] or FIXTURES
    items = [{"path": path, "doc_id": os.path.splitext(os.path.basename(path))[0], "version": "v1"} for path in files]
    result = ingest.ingest_batch(items)
    for passage in result["passages"]:
        location = passage["location"]
        place = location.get("lines") or location.get("page")
        table = location.get("table")
        where = f"table {table['index']} r{table['row']}" + (f" c{table['col']}" if table and "col" in table else "") if table else ""
        print(f"{passage['doc_id']}@{passage.get('version', '?')} {location.get('kind', '?'):9} {place!s:9} {' > '.join(location.get('path', [])) or '-'} {where}".rstrip())
        print(f"    {passage['text']}")
    print("--- report")
    print(json.dumps(result["report"], indent=2, ensure_ascii=False))
