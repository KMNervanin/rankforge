// Oak layout for the Atlas tab, ported from public/atlas-oak.html: a thick trunk of spine entries stacked bottom to top,
// limbs for everything else attached to the deepest trunk prerequisite, roots hanging below the first trunk node.
export type AtlasNode = { id: string; pre: string[]; color: string; block: string; branch: string; leaf?: boolean }
export type Position = { x: number; y: number; depth: number; side: number; parent: string }
export type Segment = { block: string; color: string; from: number; to: number }
export type Layout = { pos: Map<string, Position>; segments: Segment[]; width: number; height: number; minY: number; cx: number }

export const STEP = 66, NODE_W = 210, NODE_H = 48, TRUNK = 300, TOP = 90, SIDE = 520
const ROOT = '__root'
const LEFT_ROOTS = new Set(['F02', 'F03', 'F04', 'F05', 'F07', 'F08', 'F09'])
const isRoot = (id: string) => id[0] === 'F'

export function layoutAtlas(nodes: AtlasNode[], spine: string[]): Layout {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const spineIndex = new Map(spine.map((id, index) => [id, index]))
  const width = TRUNK + 2 * SIDE + 2 * 40, cx = width / 2
  const spineY = (index: number) => TOP + (spine.length - 1 - index) * STEP
  const pos = new Map<string, Position>()
  spine.forEach((id, index) => pos.set(id, { x: cx, y: spineY(index), depth: 0, side: 0, parent: '' }))
  pos.set(ROOT, { x: cx, y: spineY(0) + 10, depth: 0, side: 0, parent: '' })

  // Attach to the prerequisite placed highest on the tree (smallest y); ties go to the deeper limb.
  function attach(id: string, seen = new Set<string>()): Position | null {
    const known = pos.get(id)
    if (known) return known
    if (seen.has(id)) return null
    seen.add(id)
    const node = byId.get(id)
    if (!node) return null
    const pre = node.pre.length ? node.pre : [ROOT]
    let best: (Position & { id: string }) | null = null
    for (const parent of pre) {
      const candidate = attach(parent, seen)
      if (candidate && (!best || candidate.y < best.y || (candidate.y === best.y && candidate.depth > best.depth))) best = { ...candidate, id: parent }
    }
    if (!best) best = { ...pos.get(ROOT)!, id: ROOT }
    const roots = isRoot(id)
    const depth = best.depth + 1
    const side = node.leaf ? (best.side || 1) : best.side || (roots ? (LEFT_ROOTS.has(id) ? -1 : 1) : (id[0] === 'M' ? 1 : -1))
    const dir = roots ? 1 : -1
    const placed: Position = {
      x: cx + side * (TRUNK / 2 + 70 + Math.min(depth, 2) * 215),
      y: best.y + dir * (depth > 2 ? 2 * 56 + (depth - 2) * STEP : depth * 56),
      depth, side, parent: best.id,
    }
    pos.set(id, placed)
    return placed
  }
  nodes.forEach((node) => attach(node.id))

  // Nudge overlapping limb nodes apart: roots move down, everything else moves up.
  const settled: Position[] = []
  nodes.filter((node) => !spineIndex.has(node.id)).sort((a, b) => pos.get(a.id)!.y - pos.get(b.id)!.y).forEach((node) => {
    const p = pos.get(node.id)!
    let guard = 0
    while (settled.some((q) => Math.abs(q.x - p.x) < NODE_W + 12 && Math.abs(q.y - p.y) < NODE_H + 10) && guard++ < 40) p.y += (isRoot(node.id) ? 1 : -1) * (NODE_H + 12)
    settled.push(p)
  })
  pos.delete(ROOT)

  const segments: Segment[] = []
  spine.forEach((id, index) => {
    const node = byId.get(id)!
    const last = segments.at(-1)
    if (last && last.block === node.block) last.to = index
    else segments.push({ block: node.block, color: node.color, from: index, to: index })
  })
  const ys = [...pos.values()].map((p) => p.y)
  return { pos, segments, width, height: Math.max(...ys) + 120, minY: Math.min(...ys), cx }
}

export const spineY = (spineLength: number, index: number) => TOP + (spineLength - 1 - index) * STEP

// Every prerequisite reachable from the node, for the highlighted chain.
export function ancestors(id: string, byId: Map<string, { pre: string[] }>, acc = new Set<string>()): Set<string> {
  for (const parent of byId.get(id)?.pre ?? []) if (!acc.has(parent)) { acc.add(parent); ancestors(parent, byId, acc) }
  return acc
}
