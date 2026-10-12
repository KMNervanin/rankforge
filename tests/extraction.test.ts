import test from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { run, root } from '../server/labs.js'
import type { Check } from '../shared/types.js'
import { bonusChecks, bonusPassed } from '../shared/checks.js'

// No live part: the verifier writes its own fixtures and never opens a socket, so no stub endpoint is needed.
async function candidate(t: test.TestContext, source?: string) {
  const workspace = await mkdtemp(path.join(os.tmpdir(), 'rankforge-extraction-'))
  t.after(() => rm(workspace, { recursive: true, force: true }))
  await cp(path.join(root, 'labs', 'extraction'), workspace, { recursive: true })
  if (source !== undefined) await writeFile(path.join(workspace, 'ingest.py'), source)
  const result = await run('python3', ['-I', '-B', path.join(root, 'server', 'verify_extraction.py'), 'extraction', workspace], workspace)
  assert.notEqual(result.code, 124, result.stderr)
  const parsed = JSON.parse(result.stdout.trim().split('\n').at(-1) ?? '') as { checks: Check[] }
  assert.ok(parsed.checks.length, JSON.stringify(result))
  return { ...result, checks: parsed.checks }
}
const solution = (name = 'stream') => readFile(path.join(root, 'tests', 'solutions', 'extraction', `${name}.py`), 'utf8')
function rejected(result: Awaited<ReturnType<typeof candidate>>, check: string) {
  assert.equal(result.code, 1, JSON.stringify(result.checks))
  assert.ok(result.checks.some((item) => !item.passed && item.name.includes(check)), JSON.stringify(result.checks))
}

test('Extraction: the starter is RED on every structure and provenance requirement', async (t) => {
  const result = await candidate(t)
  for (const name of ['headings keep their level and chain', 'pipe table', 'HTML incident report', 'Layout JSON', 'Provenance', 'Unparseable', 'Report', 'Transfer']) rejected(result, name)
  assert.equal(bonusPassed(result.checks), false)
  assert.ok(!result.checks.some((item) => item.name === 'Environment blocked'), 'Nothing in this mission depends on the environment')
})

for (const name of ['stream', 'tree']) {
  test(`Extraction: the ${name} implementation is GREEN with the exact check count and earns the bonus`, async (t) => {
    const result = await candidate(t, await solution(name))
    assert.equal(result.code, 0, JSON.stringify(result.checks))
    assert.equal(result.checks.length, 9)
    assert.ok(result.checks.every((item) => item.passed), JSON.stringify(result.checks))
    assert.equal(bonusPassed(result.checks), true)
  })
}

const mutations: [string, string, string, string][] = [
  ['cells emitted without their column index', 'table={"index": tables, "row": row, "col": col}', 'table={"index": tables, "row": row}', 'pipe table'],
  ['a row joined with spaces instead of " | "', '" | ".join(text for text, _, _ in cells)', '" ".join(text for text, _, _ in cells)', 'pipe table'],
  ['the heading chain never popped', '        while self.stack and self.stack[-1][0] >= level:', '        while False:', 'headings keep their level and chain'],
  ['steps emitted as paragraphs', 'passage("step", chain.path(), match.group(2), number=int(match.group(1))', 'passage("paragraph", chain.path(), match.group(2), number=int(match.group(1))', 'steps keep their numbers and order'],
  ['Markdown line numbers counted from zero', 'lines=[index + 1, index + 1]', 'lines=[index, index]', 'headings keep their level and chain'],
  ['the version dropped from every passage', 'passages.append({"doc_id": doc_id, "version": version, "location": location, "text": item_found["text"]})', 'passages.append({"doc_id": doc_id, "location": location, "text": item_found["text"]})', 'Provenance'],
  ['the batch stopped at the first unparseable file', '        except Exception as error:\n            entry["status"] = "unparseable"', '        except Exception as error:\n            raise\n            entry["status"] = "unparseable"', 'Unparseable'],
  ['a truncated HTML file accepted as complete', '            if tag in MUST_CLOSE:\n                raise ParseError', '            if False:\n                raise ParseError', 'Unparseable'],
  ['layout cells indexed by their position in the list', '                for cell in block.get("cells", []):\n                    rows.setdefault(int(cell["row"]), {})[int(cell["col"])] = str(cell["text"])', '                for position, cell in enumerate(block.get("cells", [])):\n                    rows.setdefault(position // 4, {})[position % 4] = str(cell["text"])', 'Layout JSON'],
  ['every HTML heading reported as level 1', 'level=HEADING_TAGS[tag]', 'level=1', 'HTML incident report'],
  ['register_parser ignored', '    PARSERS[ext if ext.startswith(".") else "." + ext] = fn', '    return None', 'Transfer'],
]
for (const [name, before, after, check] of mutations) {
  test(`Extraction rejects ${name}`, async (t) => {
    const source = await solution()
    assert.ok(source.includes(before), `Mutation anchor missing: ${name}`)
    rejected(await candidate(t, source.replaceAll(before, after)), check)
  })
}

test('Extraction: passages without span pass the contract but miss the hidden bonus; the bonus never fails the run', async (t) => {
  const source = (await solution()).replace('            location = dict(item_found["location"])\n', '            location = dict(item_found["location"])\n            location.pop("span", None)\n')
  assert.notEqual(source, await solution())
  const result = await candidate(t, source)
  assert.equal(result.code, 0, JSON.stringify(result.checks))
  assert.equal(bonusChecks(result.checks).length, 1)
  assert.ok(bonusChecks(result.checks)[0]!.name.startsWith('bonus:'))
  assert.equal(bonusPassed(result.checks), false)
})

test('Extraction: an extractor that returns every file as one paragraph with full provenance is still RED on structure', async (t) => {
  const source = 'class ParseError(Exception):\n    pass\n\n\ndef register_parser(ext, fn):\n    pass\n\n\ndef ingest(path, *, doc_id, version):\n    return ingest_batch([{"path": path, "doc_id": doc_id, "version": version}])\n\n\ndef ingest_batch(items):\n    passages, documents, bad = [], [], []\n    for item in items:\n        try:\n            text = open(item["path"], encoding="utf-8").read()\n        except Exception as error:\n            bad.append({"doc_id": item["doc_id"], "version": item["version"], "path": item["path"], "reason": str(error)})\n            documents.append({"doc_id": item["doc_id"], "version": item["version"], "path": item["path"], "status": "unparseable", "reason": str(error), "passages": {"heading": 0, "step": 0, "table": 0, "paragraph": 0, "total": 0}})\n            continue\n        passages.append({"doc_id": item["doc_id"], "version": item["version"], "location": {"kind": "paragraph", "path": [], "lines": [1, max(1, text.count("\\n"))]}, "text": text})\n        documents.append({"doc_id": item["doc_id"], "version": item["version"], "path": item["path"], "status": "parsed", "passages": {"heading": 0, "step": 0, "table": 0, "paragraph": 1, "total": 1}})\n    return {"passages": passages, "report": {"documents": documents, "unparseable": bad, "total": len(passages)}}\n'
  const result = await candidate(t, source)
  for (const name of ['headings keep their level and chain', 'pipe table', 'HTML incident report', 'Layout JSON', 'Unparseable', 'Report', 'Transfer']) rejected(result, name)
})

test('Extraction reports import failure as a failed check', async (t) => {
  rejected(await candidate(t, 'raise ValueError("Controlled import failure")\n'), 'Load ingestion step')
})
