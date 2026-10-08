import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import type { MissionView } from '../shared/types.js'
import { isProposal, roadmapEntries, roadmapSpine, roadmapTrial, type RoadmapEntry } from '../shared/roadmap.js'
import { stars } from '../shared/progression.js'
import { NODE_H, NODE_W, STEP, TRUNK, ancestors, layoutAtlas, type Layout } from './atlas-layout.js'
import './atlas.css'

// The Atlas shows the roadmap's own English titles; nothing here is translated.
type Status = 'completed' | 'available' | 'locked' | 'ahead'
type AtlasEntry = RoadmapEntry & { leaf?: boolean; proposal?: boolean; trial?: boolean; mission?: MissionView; status: Status }
type Transform = { k: number; x: number; y: number }

const MIN_K = 0.08, MAX_K = 2.5, LEAF_COLOR = '#ffe1a3'
const statusLabel: Record<Status, string> = { completed: 'completed', available: 'available', locked: 'locked', ahead: 'ahead' }
const cardStatus: Record<Status, string> = { completed: 'completed', available: 'playable now', locked: 'locked: finish the missions listed under “After” first', ahead: 'ahead, not authored yet' }
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value))
const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

// Status comes from the same mission views the outpost map draws; the catalog's `pre` list is never used for locks.
function liveStatus(mission: MissionView | undefined): Status {
  if (!mission) return 'ahead'
  if (mission.status === 'completed') return 'completed'
  if (mission.status === 'locked') return 'locked'
  return 'available'
}

export function Atlas({ missions, onOpenMission }: { missions: MissionView[]; onOpenMission: (id: string) => void }) {
  const entries = useMemo<AtlasEntry[]>(() => {
    const byRuntime = new Map(missions.map((mission) => [mission.id, mission]))
    const catalog: AtlasEntry[] = [...roadmapEntries, roadmapTrial].map((entry) => {
      const mission = entry.runtimeId ? byRuntime.get(entry.runtimeId) : undefined
      return { ...entry, mission, status: liveStatus(mission), proposal: isProposal(entry.id), trial: entry.id === roadmapTrial.id }
    })
    // One hidden-bonus leaf per runtime mission that carries a rumour; it is earned with that mission's third star.
    const leaves: AtlasEntry[] = catalog.filter((entry) => entry.mission?.nudge).map((entry) => ({
      id: `${entry.id}★`, title: 'Hidden bonus check', goal: entry.mission!.nudge!, pre: [entry.id], block: 'Third star', color: LEAF_COLOR,
      spine: false, branch: '', leaf: true, mission: entry.mission, status: entry.mission!.stars[3] ? 'completed' : entry.status === 'completed' ? 'available' : entry.status,
    }))
    return [...catalog, ...leaves]
  }, [missions])
  const byId = useMemo(() => new Map(entries.map((entry) => [entry.id, entry])), [entries])
  const layoutKey = entries.map((entry) => entry.id).join(',')
  const layout = useMemo(() => layoutAtlas(entries, roadmapSpine), [layoutKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const [selected, setSelected] = useState<string | null>(null)
  const [transform, setTransformState] = useState<Transform>({ k: 1, x: 0, y: 0 })
  const transformRef = useRef(transform)
  const animation = useRef(0)
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<{ id: number; sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null)
  const suppressClick = useRef(false)

  function setTransform(next: Transform) { transformRef.current = next; setTransformState(next) }
  function animateTo(target: Transform) {
    cancelAnimationFrame(animation.current)
    if (reducedMotion()) { setTransform(target); return }
    const from = transformRef.current, started = performance.now(), duration = 420
    const step = (now: number) => {
      const t = clamp((now - started) / duration, 0, 1), e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2
      setTransform({ k: from.k + (target.k - from.k) * e, x: from.x + (target.x - from.x) * e, y: from.y + (target.y - from.y) * e })
      if (t < 1) animation.current = requestAnimationFrame(step)
    }
    animation.current = requestAnimationFrame(step)
  }
  const box = () => svgRef.current?.getBoundingClientRect() ?? new DOMRect(0, 0, 1200, 800)
  const centreOn = (id: string, k: number): Transform | null => {
    const p = layout.pos.get(id)
    if (!p) return null
    const b = box()
    return { k, x: b.width / 2 - p.x * k, y: b.height / 2 - p.y * k }
  }
  const whereAmI = () => entries.find((entry) => entry.mission && !entry.leaf && entry.status === 'available') ?? entries.findLast((entry) => entry.mission && !entry.leaf && entry.status === 'completed') ?? byId.get(roadmapSpine[0]!)!
  const fitAll = (): Transform => {
    const b = box(), span = layout.height - layout.minY + 60
    const k = clamp(Math.min(b.width / layout.width, b.height / span) * 0.96, MIN_K, MAX_K)
    return { k, x: (b.width - layout.width * k) / 2, y: (b.height - span * k) / 2 - (layout.minY - 60) * k }
  }
  const zoomBy = (factor: number) => {
    const b = box(), t = transformRef.current, k = clamp(t.k * factor, MIN_K, MAX_K), mx = b.width / 2, my = b.height / 2
    animateTo({ k, x: mx - (mx - t.x) * (k / t.k), y: my - (my - t.y) * (k / t.k) })
  }

  useLayoutEffect(() => { const start = centreOn(whereAmI().id, 1); if (start) setTransform(start) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => cancelAnimationFrame(animation.current), [])
  // React registers wheel listeners as passive, so page scrolling and browser zoom have to be stopped at the DOM level.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      cancelAnimationFrame(animation.current)
      const b = svg.getBoundingClientRect(), t = transformRef.current
      const delta = event.deltaY * (event.deltaMode === 1 ? 20 : event.deltaMode === 2 ? 400 : 1)
      const k = clamp(t.k * 2 ** (-delta * (event.ctrlKey ? 0.01 : 0.002)), MIN_K, MAX_K)
      const mx = event.clientX - b.left, my = event.clientY - b.top
      setTransform({ k, x: mx - (mx - t.x) * (k / t.k), y: my - (my - t.y) * (k / t.k) })
    }
    svg.addEventListener('wheel', onWheel, { passive: false })
    return () => svg.removeEventListener('wheel', onWheel)
  }, [])
  useEffect(() => {
    if (!selected) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setSelected(null)
      svgRef.current?.querySelector<SVGGElement>(`[data-id="${CSS.escape(selected)}"]`)?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected])

  function onPointerDown(event: ReactPointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return
    cancelAnimationFrame(animation.current)
    suppressClick.current = false
    drag.current = { id: event.pointerId, sx: event.clientX, sy: event.clientY, ox: transformRef.current.x, oy: transformRef.current.y, moved: false }
  }
  function onPointerMove(event: ReactPointerEvent<SVGSVGElement>) {
    const d = drag.current
    if (!d || d.id !== event.pointerId) return
    const dx = event.clientX - d.sx, dy = event.clientY - d.sy
    if (!d.moved && Math.hypot(dx, dy) < 4) return
    // Capture only once a real drag starts so that a plain click still reaches the node underneath.
    if (!d.moved) { d.moved = true; event.currentTarget.setPointerCapture(event.pointerId) }
    setTransform({ k: transformRef.current.k, x: d.ox + dx, y: d.oy + dy })
  }
  function onPointerUp(event: ReactPointerEvent<SVGSVGElement>) {
    const d = drag.current
    if (!d || d.id !== event.pointerId) return
    if (d.moved) { suppressClick.current = true; event.currentTarget.releasePointerCapture(event.pointerId) }
    drag.current = null
  }
  function pick(id: string) {
    if (suppressClick.current) { suppressClick.current = false; return }
    setSelected((current) => current === id ? null : id)
  }
  function jumpTo(id: string) {
    setSelected(id)
    const target = centreOn(id, Math.max(transformRef.current.k, 0.8))
    if (target) animateTo(target)
  }

  const current = selected ? byId.get(selected) ?? null : null
  const chain = useMemo(() => selected ? ancestors(selected, byId) : null, [selected, byId])
  const counts = {
    done: entries.filter((entry) => !entry.leaf && entry.status === 'completed').length,
    play: entries.filter((entry) => !entry.leaf && entry.status === 'available').length,
    ahead: entries.filter((entry) => !entry.leaf && !entry.proposal && (entry.status === 'locked' || entry.status === 'ahead')).length,
    proposed: entries.filter((entry) => entry.proposal).length,
  }

  return <main className="atlas-view" aria-label="Campaign atlas">
    <header className="atlas-head">
      <div><h1>The campaign oak</h1><p>Trunk: the {roadmapSpine.length} core missions, bottom to top · limbs: specialisations · leaves: hidden bonuses · roots: the entry workshop</p></div>
      <div className="atlas-counts" role="status"><span>completed <b>{counts.done}</b></span><span>available <b>{counts.play}</b></span><span>ahead <b>{counts.ahead}</b></span><span>proposed <b>{counts.proposed}</b></span></div>
    </header>
    <div className="atlas-stage">
      <svg ref={svgRef} className="atlas-tree" role="group" aria-label="Campaign tree" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}>
        <g transform={`translate(${transform.x},${transform.y}) scale(${transform.k})`}>
          <TreeBody entries={entries} layout={layout} selected={selected} chain={chain} onPick={pick} />
        </g>
      </svg>
      <p className="atlas-hint">wheel or pinch to zoom · drag to pan · click a node for its card</p>
      <div className="atlas-controls">
        <button type="button" onClick={() => { const t = centreOn(whereAmI().id, 1); if (t) animateTo(t) }}>Where am I</button>
        <button type="button" onClick={() => animateTo(fitAll())}>Whole tree</button>
        <button type="button" aria-label="Zoom in" onClick={() => zoomBy(1.4)}>+</button>
        <button type="button" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.4)}>−</button>
      </div>
      {current && <aside className="atlas-card" role="dialog" aria-label="Mission card" style={{ '--c': current.color } as CSSProperties}>
        <button type="button" className="atlas-card-close" aria-label="Close the card" onClick={() => setSelected(null)}>×</button>
        <span className="eyebrow">{current.block}{current.leaf ? ` · mission ${current.pre[0]}` : current.branch ? ` · ${current.branch}` : ' · trunk'}</span>
        <h2>{current.leaf ? '★' : current.id} · {current.title}</h2>
        <p>{current.goal}{current.goal.endsWith('.') ? '' : '.'}</p>
        <dl>
          <dt>Status</dt><dd><span className="atlas-pill">{current.proposal ? 'proposed by the 08.10 review, not in the roadmap yet' : current.leaf ? (current.status === 'completed' ? 'third star earned' : 'hidden bonus: look for it inside the mission') : cardStatus[current.status]}</span></dd>
          {current.mission && !current.leaf && <><dt>Stars</dt><dd><Stars mission={current.mission} /> <small>{stars.filter((star) => current.mission!.stars[star]).length} of 3</small></dd></>}
          <dt>After</dt><dd className="atlas-pre">{current.pre.length ? current.pre.map((id) => { const pre = byId.get(id); return pre && <button type="button" key={id} onClick={() => jumpTo(id)}>{id} · {pre.title}</button> }) : <span>nothing, this is a starting point</span>}</dd>
        </dl>
        {current.mission && <button type="button" className="atlas-open" onClick={() => onOpenMission(current.mission!.id)}>Open mission <span aria-hidden="true">↘</span></button>}
      </aside>}
    </div>
  </main>
}

type BodyProps = { entries: AtlasEntry[]; layout: Layout; selected: string | null; chain: Set<string> | null; onPick: (id: string) => void }

const TreeBody = memo(function TreeBody({ entries, layout, selected, chain, onPick }: BodyProps) {
  const { pos, segments, cx } = layout
  const spineIndex = new Map(roadmapSpine.map((id, index) => [id, index]))
  const spineY = (index: number) => pos.get(roadmapSpine[index]!)!.y
  const limbs = entries.filter((entry) => !spineIndex.has(entry.id))
  const seenBranch = new Set<string>()
  const current = selected ? entries.find((entry) => entry.id === selected) : null
  return <>
    <rect className="atlas-bark" x={cx - TRUNK / 2} y={spineY(roadmapSpine.length - 1) - 40} width={TRUNK} height={spineY(0) - spineY(roadmapSpine.length - 1) + 80} rx={60} />
    {segments.map((segment) => {
      const y1 = spineY(segment.to) - STEP / 2, y2 = spineY(segment.from) + STEP / 2
      return <g key={segment.block}>
        <rect className="atlas-seg" x={cx - TRUNK / 2 + 6} y={y1} width={TRUNK - 12} height={y2 - y1} fill={segment.color} rx={18} />
        <text className="atlas-seg-label" x={cx - TRUNK / 2 - 18} y={(y1 + y2) / 2} textAnchor="end">{segment.block}</text>
        <text className="atlas-seg-sub" x={cx - TRUNK / 2 - 18} y={(y1 + y2) / 2 + 16} textAnchor="end">{segment.to - segment.from + 1} {segment.to - segment.from === 0 ? 'mission' : 'missions'}</text>
      </g>
    })}
    {limbs.map((entry) => {
      const p = pos.get(entry.id)!, q = pos.get(p.parent)
      if (!q) return null
      const sx = q.side === 0 ? cx + p.side * (TRUNK / 2 - 10) : q.x
      return <path key={entry.id} className="atlas-limb" stroke={entry.color} d={`M${sx},${q.y} C${(sx + p.x) / 2},${q.y} ${(sx + p.x) / 2},${p.y} ${p.x},${p.y}`} />
    })}
    {limbs.map((entry) => {
      const p = pos.get(entry.id)!
      if (!entry.branch || !spineIndex.has(p.parent) || seenBranch.has(entry.branch + p.parent)) return null
      seenBranch.add(entry.branch + p.parent)
      return <text key={`branch-${entry.id}`} className="atlas-limb-label" x={p.x} y={p.y - NODE_H / 2 - 10} textAnchor="middle">{entry.branch}</text>
    })}
    {current && current.pre.map((id) => {
      const a = pos.get(id), b = pos.get(current.id)
      return a && b && <path key={`dep-${id}`} className="atlas-dep" d={`M${a.x},${a.y} C${a.x},${(a.y + b.y) / 2} ${b.x},${(a.y + b.y) / 2} ${b.x},${b.y}`} />
    })}
    {entries.map((entry) => {
      const p = pos.get(entry.id)!
      const tag = entry.leaf ? (entry.status === 'completed' ? '✦ earned' : '· hidden') : entry.proposal ? '· proposed' : entry.status === 'completed' ? '✓ completed' : entry.status === 'available' ? '· available' : entry.status === 'locked' ? '· 🔒 locked' : ''
      const className = ['atlas-node', entry.status, entry.leaf ? 'leaf' : entry.trial ? 'trial' : 'catalog', entry.proposal ? 'proposal' : '', selected === entry.id ? 'sel' : selected && !chain?.has(entry.id) ? 'dim' : ''].filter(Boolean).join(' ')
      return <g key={entry.id} className={className} role="button" tabIndex={0} aria-pressed={selected === entry.id} aria-label={`${entry.leaf ? 'Hidden bonus' : `${entry.id} · ${entry.title}`} · ${entry.proposal ? 'proposed' : statusLabel[entry.status]}`}
        data-id={entry.id} data-status={entry.proposal ? 'proposed' : entry.status} data-runtime={entry.leaf ? undefined : entry.mission?.id} transform={`translate(${p.x - NODE_W / 2},${p.y - NODE_H / 2})`} style={{ '--c': entry.color } as CSSProperties}
        onClick={() => onPick(entry.id)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onPick(entry.id) } }}>
        <rect width={NODE_W} height={NODE_H} />
        <text className="atlas-id" x={12} y={17}>{entry.leaf ? '★' : entry.id}{tag ? `  ${tag}` : ''}</text>
        <text className="atlas-title" x={12} y={35}>{entry.title.length > 28 ? `${entry.title.slice(0, 27)}…` : entry.title}</text>
        {entry.mission && !entry.leaf && stars.map((star, index) => <text key={star} className={entry.mission!.stars[star] ? 'atlas-star earned' : 'atlas-star'} x={NODE_W - 16 - index * 13} y={17} textAnchor="middle">★</text>)}
      </g>
    })}
  </>
})

function Stars({ mission }: { mission: MissionView }) {
  return <span className="atlas-stars" role="img" aria-label={`${stars.filter((star) => mission.stars[star]).length} of 3 stars`}>{stars.map((star) => <i key={star} className={mission.stars[star] ? 'earned' : ''} aria-hidden="true">★</i>)}</span>
}
