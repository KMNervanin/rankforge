// This installs static shader/uniform sync paths so the renderer needs no unsafe-eval CSP permission.
import 'pixi.js/unsafe-eval'
import { Application, Container, Graphics } from 'pixi.js'
import { useEffect, useRef, useState } from 'react'
import type { MissionView } from '../shared/types.js'

const positions = [[.49, .22], [.25, .42], [.75, .42], [.38, .64], [.67, .69], [.5, .87]]

export function Outpost({ missions, selected, onSelect, disabled }: { missions: MissionView[]; selected: string; onSelect: (id: string) => void; disabled: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  const pixi = useRef<Application | null>(null)
  const redraw = useRef<(() => void) | null>(null)
  const data = useRef({ missions, selected })
  data.current = { missions, selected }
  const [fallback, setFallback] = useState(false)
  useEffect(() => {
    const element = host.current!
    const app = new Application()
    let disposed = false
    let observer: ResizeObserver | undefined
    let pulse: Graphics | undefined
    const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const draw = () => {
      if (disposed) return
      const width = element.clientWidth; const height = element.clientHeight
      app.renderer.resize(width, height)
      app.stage.removeChildren().forEach((child) => child.destroy({ children: true }))
      const grid = new Graphics()
      const centerX = width / 2; const centerY = height * .49
      for (let n = -12; n <= 12; n++) {
        grid.moveTo(centerX + n * 44 - width, centerY - height * .45).lineTo(centerX + n * 44 + width, centerY + height * .55)
        grid.moveTo(centerX + n * 44 + width, centerY - height * .45).lineTo(centerX + n * 44 - width, centerY + height * .55)
      }
      grid.stroke({ color: 0x385478, alpha: .17, width: 1 })
      app.stage.addChild(grid)
      const connections = [[0, 1], [0, 2], [1, 3], [3, 4], [2, 5], [4, 5]]
      const paths = new Graphics()
      for (const [from, to] of connections) {
        const a = positions[from!]!; const b = positions[to!]!
        const lit = data.current.missions[from!]?.status === 'completed'
        paths.moveTo(a[0]! * width, a[1]! * height).lineTo(b[0]! * width, b[1]! * height)
          .stroke({ color: lit ? 0x63dfd0 : 0x395570, alpha: lit ? .6 : .32, width: lit ? 2 : 1 })
      }
      app.stage.addChild(paths)
      data.current.missions.forEach((mission, index) => {
        const p = positions[index]!
        const tower = new Container()
        tower.position.set(p[0]! * width, p[1]! * height)
        const active = mission.id === data.current.selected
        const alive = mission.status === 'completed'
        const locked = mission.status === 'locked'
        const color = alive ? 0x66e7bc : active ? 0x91b5ff : locked ? 0x324763 : 0x738ab2
        const size = index === 0 ? 40 : 30
        const tall = index === 0 ? 60 : 28 + index * 5
        const platform = new Graphics().poly([-size - 14, 0, 0, -size * .55 - 9, size + 14, 0, 0, size * .55 + 9]).fill({ color: 0x101f35 }).stroke({ color, alpha: active || alive ? .75 : .25, width: 1 })
        for (let layer = 0; layer < 3; layer++) {
          const y = -8 - layer * 5
          platform.moveTo(-size, y).lineTo(0, y + size * .5).lineTo(size, y).stroke({ color, alpha: .25, width: 1 })
        }
        tower.addChild(platform)
        const building = new Graphics()
        building.poly([-size * .55, -12, 0, -12 + size * .28, 0, -tall + size * .28, -size * .55, -tall]).fill({ color: active ? 0x243e65 : 0x192b45 })
        building.poly([0, -12 + size * .28, size * .55, -12, size * .55, -tall, 0, -tall + size * .28]).fill({ color: active ? 0x182e51 : 0x122238 })
        building.poly([-size * .55, -tall, 0, -tall - size * .28, size * .55, -tall, 0, -tall + size * .28]).fill({ color: active ? 0x42608c : 0x2b4363 }).stroke({ color, alpha: .6, width: 1 })
        for (let window = 0; window < 3; window++) {
          const y = -18 - window * (tall / 4)
          building.moveTo(-size * .4, y).lineTo(-4, y + size * .16).stroke({ color, alpha: locked ? .2 : .85, width: 2 })
        }
        if (index === 0) building.moveTo(0, -tall - 6).lineTo(0, -tall - 35).stroke({ color, alpha: .8, width: 2 }).circle(0, -tall - 37, 3).fill(color)
        if (alive) building.circle(0, -tall - 12, 3).fill(0x66e7bc)
        tower.addChild(building)
        if (active) {
          pulse = new Graphics().ellipse(0, 0, size + 23, size * .55 + 15).stroke({ color: 0x86aefa, width: 1, alpha: .5 })
          tower.addChild(pulse)
        }
        app.stage.addChild(tower)
      })
    }
    void app.init({ backgroundAlpha: 0, antialias: true, resolution: Math.min(window.devicePixelRatio || 1, 2), autoDensity: true, preference: 'webgl' }).then(() => {
      if (disposed) { app.destroy(true, { children: true }); return }
      element.appendChild(app.canvas)
      pixi.current = app; redraw.current = draw
      draw()
      observer = new ResizeObserver(draw); observer.observe(element)
      app.ticker.add(() => { if (pulse) pulse.alpha = motionPreference.matches ? .65 : .5 + .35 * Math.sin(performance.now() / 1100) })
    }).catch(() => { if (!disposed) setFallback(true) })
    return () => { disposed = true; observer?.disconnect(); redraw.current = null; if (pixi.current === app) { pixi.current = null; app.destroy(true, { children: true }) } }
  }, [])
  const signature = missions.map((item) => item.status).join(',')
  useEffect(() => { redraw.current?.() }, [signature, selected])
  return <div className={`outpost-map ${fallback ? 'fallback-map' : ''}`} aria-label="Interactive outpost map">
    <div ref={host} className="map-canvas" aria-hidden="true" />
    <span className="map-coordinates">SECTOR 07 / NORTHERN REACH</span>
    <span className="map-scale">FIELD VIEW · {missions.filter((item) => item.status === 'completed').length}/6 SYSTEMS RESTORED</span>
    {missions.map((mission, index) => <button key={mission.id} className={`map-node ${mission.status} ${selected === mission.id ? 'selected' : ''}`} style={{ left: `${positions[index]![0]! * 100}%`, top: `${positions[index]![1]! * 100}%` }} onClick={() => onSelect(mission.id)} disabled={disabled || mission.status === 'locked'} aria-label={`Enter ${mission.title}`}>
      {fallback && <span className="fallback-building">{mission.icon}</span>}
      <span className="node-label"><span className="node-index">0{mission.order}</span>{mission.sector}<span className="node-dot" /></span>
    </button>)}
  </div>
}
