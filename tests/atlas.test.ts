import test from 'node:test'
import assert from 'node:assert/strict'
import { missions } from '../shared/content.js'
import { isProposal, roadmapEntries, roadmapRuntime, roadmapSpine, roadmapTrial } from '../shared/roadmap.js'
import { NODE_H, NODE_W, ancestors, layoutAtlas } from '../src/atlas-layout.js'

const ids = new Set(roadmapEntries.map((entry) => entry.id))

test('the roadmap catalog is consistent: 92 unique ids, every prerequisite and spine id exists', () => {
  assert.equal(roadmapEntries.length, 92)
  assert.equal(ids.size, 92, 'duplicate ids')
  assert.equal(roadmapEntries.filter((entry) => isProposal(entry.id)).length, 6, 'X01–X03 and P01–P03 are the proposals')
  for (const entry of roadmapEntries) for (const pre of entry.pre) assert.ok(ids.has(pre), `${entry.id} requires unknown ${pre}`)
  for (const id of roadmapSpine) assert.ok(ids.has(id), `spine id ${id} is not in the catalog`)
  assert.equal(new Set(roadmapSpine).size, roadmapSpine.length)
  for (const entry of roadmapEntries) assert.equal(entry.spine, roadmapSpine.includes(entry.id), `${entry.id} spine flag disagrees with roadmapSpine`)
  for (const pre of roadmapTrial.pre) assert.ok(ids.has(pre))
})

test('every runtimeId names a mission the game ships, and every shipped mission is on the atlas', () => {
  const shipped = new Set(missions.map((mission) => mission.id))
  const placed = new Map<string, string>()
  for (const entry of [...roadmapEntries, roadmapTrial]) {
    if (!entry.runtimeId) continue
    assert.ok(shipped.has(entry.runtimeId), `${entry.id} points at unknown mission ${entry.runtimeId}`)
    assert.equal(placed.get(entry.runtimeId), undefined, `${entry.runtimeId} appears twice`)
    placed.set(entry.runtimeId, entry.id)
    if (entry.id !== 'HT') assert.equal(roadmapRuntime[entry.id], entry.runtimeId)
  }
  for (const mission of missions) assert.ok(placed.has(mission.id), `${mission.id} has no atlas node`)
  assert.equal(Object.keys(roadmapRuntime).length, placed.size - 1)
})

test('the prerequisite graph is a DAG', () => {
  const byId = new Map(roadmapEntries.map((entry) => [entry.id, entry]))
  const state = new Map<string, 'visiting' | 'done'>()
  const visit = (id: string, trail: string[]) => {
    if (state.get(id) === 'done') return
    assert.notEqual(state.get(id), 'visiting', `cycle: ${[...trail, id].join(' → ')}`)
    state.set(id, 'visiting')
    for (const pre of byId.get(id)!.pre) visit(pre, [...trail, id])
    state.set(id, 'done')
  }
  for (const entry of roadmapEntries) visit(entry.id, [])
  for (const entry of roadmapEntries) assert.ok(!ancestors(entry.id, byId).has(entry.id))
})

test('the oak layout places every node, keeps the trunk centred and leaves limb nodes apart', () => {
  const leaves = Object.keys(roadmapRuntime).map((id) => ({ id: `${id}★`, pre: [id], color: '#ffe1a3', block: 'Third star', branch: '', leaf: true }))
  const nodes = [...roadmapEntries, roadmapTrial, ...leaves]
  const layout = layoutAtlas(nodes, roadmapSpine)
  for (const node of nodes) assert.ok(layout.pos.has(node.id), `${node.id} has no position`)
  assert.equal(layout.pos.size, nodes.length)
  for (const id of roadmapSpine) assert.equal(layout.pos.get(id)!.x, layout.cx)
  const first = layout.pos.get(roadmapSpine[0]!)!, last = layout.pos.get(roadmapSpine.at(-1)!)!
  assert.ok(first.y > last.y, 'the trunk grows upward')
  for (const root of roadmapEntries.filter((entry) => entry.id.startsWith('F'))) assert.ok(layout.pos.get(root.id)!.y > first.y, `${root.id} hangs below the first trunk node`)
  const limbs = nodes.filter((node) => !roadmapSpine.includes(node.id)).map((node) => layout.pos.get(node.id)!)
  for (let i = 0; i < limbs.length; i++) for (let j = i + 1; j < limbs.length; j++) {
    const a = limbs[i]!, b = limbs[j]!
    assert.ok(Math.abs(a.x - b.x) >= NODE_W + 12 || Math.abs(a.y - b.y) >= NODE_H + 10, `limb nodes overlap at ${a.x},${a.y}`)
  }
  assert.equal(layout.pos.get('HT')!.parent, 'I03', 'the HTTP trial hangs off Gateway, its deepest prerequisite')
  assert.deepEqual(layout.segments.map((segment) => segment.block), ['I · The silent outpost', "II · The architect's guild", 'III · The service workshop', 'IV · Testing', 'IV · Security', 'V · Reliable operations', 'VI · Under pressure', 'VII · The event frontier', 'VIII · The data district', 'IX · The independent outpost'])
})
