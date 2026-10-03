// This installs static shader/uniform sync paths so the renderer needs no unsafe-eval CSP permission.
import 'pixi.js/unsafe-eval'
import { Application, Container, Graphics } from 'pixi.js'
import { useEffect, useRef, useState } from 'react'
import type { MissionView } from '../shared/types.js'

const positions = [[.29, .20], [.74, .24], [.23, .49], [.73, .53], [.32, .79], [.77, .82]]
const palettes = [
  { main: 0xffbf58, light: 0xffedb0, dark: 0x956039, land: 0x686149 },
  { main: 0x70e2b2, light: 0xd1ffe8, dark: 0x34786d, land: 0x426d61 },
  { main: 0xba95ff, light: 0xeddfff, dark: 0x6950a0, land: 0x645176 },
  { main: 0xff8eb5, light: 0xffdcea, dark: 0x985374, land: 0x735367 },
  { main: 0x77dce8, light: 0xd2fbff, dark: 0x397b93, land: 0x446c73 },
  { main: 0xd3e879, light: 0xf5ffcc, dark: 0x748345, land: 0x626d49 },
]

function drawBuilding(graphic: Graphics, index: number, active: boolean) {
  const color = palettes[index]!
  const outline = { color: 0x302437, width: 3 }
  if (index === 0) {
    graphic.roundRect(-33, -60, 66, 66, 9).fill(color.dark).stroke(outline)
      .roundRect(-25, -59, 50, 60, 6).fill(0xe1ac68)
      .poly([-40, -58, 0, -92, 40, -58]).fill(color.main).stroke(outline)
      .roundRect(-11, -27, 22, 33, 10).fill(0x493349)
      .roundRect(-22, -50, 12, 15, 4).fill(color.light)
      .roundRect(10, -50, 12, 15, 4).fill(color.light)
      .poly([0, -128, 14, -107, 0, -86, -14, -107]).fill(color.light).stroke({ color: color.main, width: 3 })
      .moveTo(0, -122).lineTo(0, -95).stroke({ color: 0xffffff, width: 2, alpha: .7 })
      .roundRect(-39, 4, 78, 9, 3).fill(0xd6a564)
  } else if (index === 1) {
    graphic.roundRect(-47, -38, 94, 48, 8).fill(color.dark).stroke(outline)
      .roundRect(-48, -68, 96, 38, 15).fill(color.main).stroke(outline)
      .roundRect(-38, -62, 76, 23, 10).fill(0xa3efd0)
      .rect(-27, -66, 10, 73).fill(0xf5cf78)
      .rect(17, -66, 10, 73).fill(0xf5cf78)
      .roundRect(-12, -39, 24, 24, 5).fill(color.light).stroke(outline)
      .circle(0, -29, 4).fill(0x305c59)
      .rect(-2, -29, 4, 10).fill(0x305c59)
  } else if (index === 2) {
    graphic.ellipse(0, -44, 43, 54).fill({ color: color.main, alpha: .14 })
      .roundRect(-34, -89, 68, 98, 32).fill(color.dark).stroke(outline)
      .roundRect(-23, -78, 46, 83, 23).fill(active ? 0x8d60cf : 0x40324f)
      .ellipse(0, -38, 17, 31).fill({ color: color.main, alpha: active ? .6 : .22 })
      .roundRect(-45, 2, 90, 12, 5).fill(0xb6a0d5)
      .poly([0, -100, 10, -88, 0, -76, -10, -88]).fill(color.light)
    for (const x of [-30, 30]) graphic.roundRect(x - 7, -42, 14, 47, 4).fill(0xd0b8ec).stroke(outline)
  } else if (index === 3) {
    graphic.roundRect(-47, -18, 94, 29, 7).fill(color.dark).stroke(outline)
    for (const x of [-28, 28]) {
      graphic.roundRect(x - 15, -65, 30, 58, 6).fill(color.main).stroke(outline)
        .ellipse(x, -65, 18, 9).fill(color.light).stroke(outline)
      for (let n = 0; n < 3; n++) graphic.roundRect(x - 19, -53 + n * 14, 38, 7, 3).fill(0xf9c8db).stroke({ color: color.dark, width: 2 })
    }
    graphic.poly([-5, -79, 9, -79, 1, -57, 13, -57, -9, -30, -3, -52, -14, -52]).fill(0xffe49b).stroke({ color: 0x76594e, width: 2 })
  } else if (index === 4) {
    graphic.roundRect(-43, -43, 86, 50, 8).fill(color.dark).stroke(outline)
      .circle(0, -47, 43).fill(color.main).stroke(outline)
      .ellipse(-8, -56, 24, 28).fill({ color: color.light, alpha: .5 })
      .rect(-47, -28, 94, 11).fill(0xcfdfc9).stroke(outline)
      .roundRect(-17, -12, 34, 20, 5).fill(0x314c63)
      .moveTo(-10, 0).lineTo(-3, -5).lineTo(3, -2).lineTo(12, -9).stroke({ color: color.light, width: 3 })
      .poly([10, -91, 43, -105, 49, -91, 16, -78]).fill(0xcfdfc9).stroke(outline)
      .ellipse(45, -99, 7, 10).fill(color.dark).stroke(outline)
  } else {
    graphic.ellipse(0, 4, 50, 16).fill(color.dark).stroke(outline)
      .ellipse(0, -5, 44, 14).fill(color.light).stroke(outline)
      .poly([0, -108, 29, -70, 17, -18, -17, -18, -29, -70]).fill(color.main).stroke(outline)
      .poly([0, -108, 0, -21, -17, -18, -29, -70]).fill(0xf1f9af)
      .poly([0, -108, 29, -70, 17, -18, 10, -57]).fill(0xa2bd59)
      .ellipse(0, -48, 45, 10).stroke({ color: color.light, width: 4 })
  }
}

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
    let particles: { graphic: Graphics; from: number[]; to: number[]; offset: number }[] = []
    const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const draw = () => {
      if (disposed) return
      const width = element.clientWidth; const height = element.clientHeight
      app.renderer.resize(width, height)
      app.stage.removeChildren().forEach((child) => child.destroy({ children: true }))
      particles = []
      const sky = new Graphics()
      for (let n = 0; n < 48; n++) {
        const x = ((n * 137.5 + 41) % 997) / 997 * width
        const y = ((n * 73.7 + 31) % 701) / 701 * height
        sky.circle(x, y, n % 7 === 0 ? 2 : 1).fill({ color: n % 3 ? 0xb39acf : 0xffd696, alpha: .2 + (n % 4) * .08 })
        if (n % 11 === 0) sky.moveTo(x - 5, y).lineTo(x + 5, y).moveTo(x, y - 5).lineTo(x, y + 5).stroke({ color: 0xffdbad, alpha: .35, width: 1 })
      }
      app.stage.addChild(sky)
      const connections = [[0, 1], [0, 2], [1, 3], [3, 4], [2, 5], [4, 5]]
      const paths = new Graphics()
      for (const [from, to] of connections) {
        const a = positions[from!]!; const b = positions[to!]!
        const lit = data.current.missions[from!]?.status === 'completed'
        const start = [a[0]! * width, a[1]! * height + 12]
        const end = [b[0]! * width, b[1]! * height + 12]
        for (let step = 0; step <= 24; step++) {
          const t = step / 24
          paths.circle(start[0]! + (end[0]! - start[0]!) * t, start[1]! + (end[1]! - start[1]!) * t, lit ? 2.8 : 2)
            .fill({ color: lit ? palettes[from!]!.main : 0x796389, alpha: lit ? .72 : .45 })
        }
        if (lit) {
          const graphic = new Graphics().circle(0, 0, 5).fill(palettes[from!]!.light)
          particles.push({ graphic, from: start, to: end, offset: from! * .17 })
        }
      }
      app.stage.addChild(paths)
      particles.forEach((particle) => app.stage.addChild(particle.graphic))
      data.current.missions.forEach((mission, index) => {
        const p = positions[index]!
        const tower = new Container()
        tower.position.set(p[0]! * width, p[1]! * height)
        const active = mission.id === data.current.selected
        const alive = mission.status === 'completed'
        const locked = mission.status === 'locked'
        const palette = palettes[index]!
        tower.scale.set(Math.max(.78, Math.min(1.08, width / 760)))
        tower.alpha = locked ? .62 : 1
        const platform = new Graphics()
          .ellipse(0, 52, 79, 22).fill({ color: 0x08050f, alpha: .25 })
          .poly([-82, 0, -42, -29, 38, -29, 82, 0, 46, 27, -44, 27]).fill(palette.land).stroke({ color: 0x302437, width: 3 })
          .poly([-82, 0, -44, 27, 46, 27, 82, 0, 55, 40, 19, 65, -25, 56, -59, 35]).fill(0x40304e).stroke({ color: 0x2c2038, width: 3 })
          .poly([-82, 0, -44, 27, -25, 56, -59, 35]).fill(0x58405c)
          .poly([-44, 27, 19, 65, -25, 56]).fill(0x67475c)
          .poly([46, 27, 82, 0, 55, 40, 19, 65]).fill(0x32263f)
          .poly([-82, -6, -42, -34, 38, -34, 82, -6, 46, 20, -44, 20]).fill(palette.land).stroke({ color: active ? palette.main : 0x98836e, alpha: active ? 1 : .35, width: active ? 3 : 1 })
        for (const [x, y, size] of [[-61, -10, 13], [58, -9, 10], [-56, 11, 8]]) {
          platform.rect(x! - 2, y! - 7, 4, 16).fill(0x69524e)
            .poly([x!, y! - size! - 15, x! + size!, y! - 2, x! - size!, y! - 2]).fill(index % 2 ? 0x7fa887 : 0xaf96ba)
            .poly([x!, y! - size! - 15, x!, y! - 2, x! - size!, y! - 2]).fill(index % 2 ? 0x527d69 : 0x786189)
        }
        platform.poly([51, 18, 56, 4, 63, 20, 57, 27]).fill(palette.main)
        tower.addChild(platform)
        const building = new Graphics()
        if (active || alive) building.circle(0, -58, 63).fill({ color: palette.main, alpha: .07 })
        drawBuilding(building, index, active || alive)
        tower.addChild(building)
        if (active) {
          pulse = new Graphics().ellipse(0, -6, 96, 40).stroke({ color: palette.main, width: 2, alpha: .6 })
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
      app.ticker.add(() => {
        if (pulse) pulse.alpha = motionPreference.matches ? .8 : .65 + .3 * Math.sin(performance.now() / 1100)
        for (const particle of particles) {
          const t = motionPreference.matches ? .5 : (performance.now() / 4000 + particle.offset) % 1
          particle.graphic.position.set(particle.from[0]! + (particle.to[0]! - particle.from[0]!) * t, particle.from[1]! + (particle.to[1]! - particle.from[1]!) * t)
        }
      })
    }).catch(() => { if (!disposed) setFallback(true) })
    return () => { disposed = true; observer?.disconnect(); redraw.current = null; if (pixi.current === app) { pixi.current = null; app.destroy(true, { children: true }) } }
  }, [])
  const signature = missions.map((item) => item.status).join(',')
  useEffect(() => { redraw.current?.() }, [signature, selected])
  return <div className={`outpost-map ${fallback ? 'fallback-map' : ''}`} aria-label="Interactive outpost map">
    <div ref={host} className="map-canvas" aria-hidden="true" />
    <span className="map-coordinates">✦ The Northern Reach</span>
    <span className="map-scale">{missions.filter((item) => item.status === 'completed').length} of 6 places brought to life</span>
    {missions.map((mission, index) => <button key={mission.id} className={`map-node sector-${mission.id} ${mission.status} ${selected === mission.id ? 'selected' : ''}`} style={{ left: `${positions[index]![0]! * 100}%`, top: `${positions[index]![1]! * 100}%` }} onClick={() => onSelect(mission.id)} disabled={disabled || mission.status === 'locked'} aria-label={`Enter ${mission.title}`}>
      {fallback && <span className="fallback-building">{mission.icon}</span>}
      <span className="node-label"><span className="node-index">{mission.status === 'completed' ? '✓' : mission.order}</span><span>{mission.sector}<small>{mission.status === 'completed' ? 'Restored!' : mission.status === 'locked' ? 'Yet to discover' : 'Your next quest'}</small></span></span>
    </button>)}
  </div>
}
