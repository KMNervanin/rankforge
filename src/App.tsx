import { useEffect, useRef, useState } from 'react'
import type { MissionView, Snapshot } from '../shared/types.js'
import { chapters, futureChapters } from '../shared/content.js'
import { currentContractVersion } from '../shared/contracts.js'
import { bonusChecks, requiredChecks } from '../shared/checks.js'
import { starNames, stars } from '../shared/progression.js'
import { ProgressionPanel } from './ProgressionPanel.js'
import { Outpost } from './Outpost.js'
import { Atlas } from './Atlas.js'
import { ChatPanel, type ChatPositions } from './ChatPanel.js'

type Tab = 'outpost' | 'chat' | 'atlas' | 'skills' | 'journal' | 'connection'

export function App() {
  const savedChat = useRef({ open: localStorage.getItem('rankforge.chat.open') === 'true', mode: localStorage.getItem('rankforge.chat.mode'), mission: localStorage.getItem('rankforge.chat.mission') })
  const [state, setState] = useState<Snapshot | null>(null)
  const [selected, setSelected] = useState('signal')
  const [overview, setOverview] = useState<'map' | 'cards'>(() => localStorage.getItem('rankforge.overview') === 'cards' ? 'cards' : 'map')
  const [chapterId, setChapterId] = useState<'outpost' | 'guild'>('outpost')
  const [tab, setTab] = useState<Tab>(() => savedChat.current.open ? 'chat' : 'outpost')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [rewardNotice, setRewardNotice] = useState('')
  const [hint, setHint] = useState('')
  const [loginUrl, setLoginUrl] = useState('')
  const [mode, setMode] = useState<'coach' | 'debrief'>(() => savedChat.current.mode === 'coach' ? 'coach' : 'debrief')
  const [drafts, setDrafts] = useState<Record<string, string>>(() => { try { return JSON.parse(localStorage.getItem('rankforge.drafts') ?? '{}') } catch { return {} } })
  const token = useRef(''); const epoch = useRef(0); const initialized = useRef(false)
  const chatPositions = useRef<ChatPositions>({})
  const missionPanel = useRef<HTMLElement>(null)
  const profileMenu = useRef<HTMLDetailsElement>(null)
  const navigationEpoch = useRef(0)
  useEffect(() => { localStorage.setItem('rankforge.overview', overview) }, [overview])
  useEffect(() => { if (initialized.current) localStorage.setItem('rankforge.selected', selected) }, [selected])
  useEffect(() => { localStorage.setItem('rankforge.drafts', JSON.stringify(drafts)) }, [drafts])
  useEffect(() => { localStorage.setItem('rankforge.chat.open', String(tab === 'chat')) }, [tab])
  useEffect(() => { localStorage.setItem('rankforge.chat.mode', mode) }, [mode])
  useEffect(() => { if (tab === 'chat' && initialized.current) localStorage.setItem('rankforge.chat.mission', selected) }, [selected, tab])
  useEffect(() => {
    let disposed = false
    const controller = new AbortController()
    const refresh = async () => {
      const version = epoch.current
      try {
        const response = await fetch('/api/bootstrap', { signal: controller.signal })
        if (!response.ok) throw new Error('The local service is not available.')
        const data = await response.json()
        if (!disposed && version === epoch.current) {
          token.current = data.token; setState(data.snapshot)
          if (!initialized.current) {
            initialized.current = true
            const snapshot = data.snapshot as Snapshot
            const savedMission = savedChat.current.open ? savedChat.current.mission : localStorage.getItem('rankforge.selected')
            const previousMission = snapshot.missions.find((item) => item.id === savedMission)
            const missionId = previousMission ? previousMission.id : snapshot.activeMissionId ?? 'signal'
            setSelected(missionId)
            setChapterId(snapshot.missions.find((item) => item.id === missionId)?.chapter ?? 'outpost')
            if (!savedChat.current.mode) setMode(snapshot.exchanges.findLast((item) => item.missionId === missionId)?.mode ?? 'debrief')
          }
        }
      } catch (cause) { if (!disposed) setError(cause instanceof Error ? cause.message : 'Unable to reach the local service.') }
    }
    void refresh()
    const timer = setInterval(() => { void refresh() }, 1800)
    return () => { disposed = true; controller.abort(); clearInterval(timer) }
  }, [])

  async function action<T>(url: string, body: unknown = {}): Promise<T | null> {
    setBusy(true); setError(''); epoch.current++
    try {
      const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'x-rankforge-token': token.current }, body: JSON.stringify(body) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error ?? 'The action could not be completed.')
      const updated = await fetch('/api/state').then((res) => res.json())
      epoch.current++; setState(updated)
      return data as T
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Connection interrupted. Your saved progress is preserved.'); return null }
    finally { setBusy(false) }
  }
  async function enter(id: string, openEditor = true) {
    setSelected(id); navigate('outpost')
    await action(`/api/missions/${id}/start`, { openEditor })
  }
  function navigate(next: Tab) {
    navigationEpoch.current++
    setRewardNotice('')
    if (profileMenu.current) profileMenu.current.open = false
    setTab(next)
  }
  function showMission(id: string) {
    if (id !== selected) setHint('')
    setChapterId(state?.missions.find((item) => item.id === id)?.chapter ?? 'outpost')
    setSelected(id); navigate('outpost')
    requestAnimationFrame(() => {
      missionPanel.current?.focus({ preventScroll: true })
      missionPanel.current?.scrollIntoView({ block: 'start' })
    })
  }
  async function verifyMission(id: string) {
    const navigation = navigationEpoch.current
    const previous = state?.progression?.inventory
    setRewardNotice('')
    const result = await action<Snapshot>(`/api/missions/${id}/check`)
    if (result) requestAnimationFrame(() => {
      if (navigation === navigationEpoch.current) {
        missionPanel.current?.querySelector<HTMLElement>('.check-report')?.focus()
        const inventory = result.progression?.inventory
        const gained = (inventory?.bankedCharge ?? 0) - (previous?.bankedCharge ?? 0)
        const cosmetics = (inventory?.cosmetics ?? []).filter((item) => !previous?.cosmetics.some((owned) => owned.id === item.id))
        if (gained || cosmetics.length) setRewardNotice(`Checkpoint rewards: +${gained} banked game charge${cosmetics.length ? ` · ${cosmetics.map((item) => item.name).join(', ')}` : ''}.`)
      }
    })
  }
  function draft(value: string) {
    setDrafts((previous) => ({ ...previous, [`${selected}:${mode}`]: value }))
  }
  async function submitAnswer() {
    const key = `${selected}:${mode}`
    const original = drafts[key] ?? ''
    const text = original.trim()
    let saved: Record<string, { id: string; text: string }>
    try { saved = JSON.parse(localStorage.getItem('rankforge.submissions') ?? '{}') } catch { saved = {} }
    const submission = saved[key]?.text === text ? saved[key]! : { id: crypto.randomUUID(), text }
    saved[key] = submission
    localStorage.setItem('rankforge.submissions', JSON.stringify(saved))
    const response = await action(`/api/missions/${selected}/answer`, { id: submission.id, mode, text })
    if (response) {
      setDrafts((previous) => previous[key] === original ? { ...previous, [key]: '' } : previous)
      delete saved[key]
      localStorage.setItem('rankforge.submissions', JSON.stringify(saved))
    }
  }
  const mission = state?.missions.find((item) => item.id === selected)
  const paused = !!state?.connection.paused
  const completed = state?.missions.filter((item) => item.status === 'completed').length ?? 0
  const draftValue = drafts[`${selected}:${mode}`] ?? ''
  const evaluating = state?.exchanges.some((item) => item.status === 'pending' || item.status === 'processing') ?? false
  const savedPending = state?.exchanges.findLast((item) => item.status === 'paused' || item.status === 'failed')
  const conversation = state?.exchanges.filter((item) => item.missionId === selected) ?? []
  const conversationMessages = conversation.reduce((count, item) => count + 1 + Number(Boolean(item.reply)), 0)
  const chapter = chapters.find((item) => item.id === chapterId)!
  const chapterMissions = state?.missions.filter((item) => (item.chapter ?? 'outpost') === chapterId) ?? []
  const coreMissions = chapterMissions.filter((item) => !item.bonus)
  const chapterCompleted = coreMissions.filter((item) => item.completedAt).length
  const currentPass = mission?.checks?.passed && mission.checks.contractVersion === currentContractVersion

  return <div className="app-shell">
    <div className={`main-shell ${tab === 'chat' ? 'chat-active' : tab === 'atlas' ? 'atlas-active' : ''}`}>
      <header className="topbar">
        <a className="brand" href="#" onClick={(event) => { event.preventDefault(); navigate('outpost'); window.scrollTo(0, 0) }} aria-label="Rankforge outpost"><span className="brand-mark">R<span>◈</span></span><span>RANKFORGE</span></a>
        <nav aria-label="Main navigation">{([['outpost', '◇', 'The outpost'], ['chat', '✉', 'Operator chat'], ['atlas', '⋔', 'Atlas'], ['journal', '≡', 'Field journal']] as const).map(([id, icon, label]) => <button key={id} aria-label={label} aria-current={tab === id ? 'page' : undefined} className={tab === id ? 'nav-active' : ''} onClick={() => { navigate(id); window.scrollTo(0, 0) }}><span aria-hidden="true">{icon}</span>{label}</button>)}</nav>
        <details className={`profile-menu frame-${state?.progression?.inventory.equippedCosmeticId ?? 'default'}`} ref={profileMenu} onKeyDown={(event) => { if (event.key === 'Escape') { profileMenu.current!.open = false; profileMenu.current?.querySelector('summary')?.focus() } }}>
          <summary aria-label="Player profile"><span className="player-rank">{state?.rank[0] ?? 'E'}</span><span className="player-copy"><strong>Pathfinder</strong><span className="xp-line">{state?.xp ?? 0} XP</span></span><span className={paused ? 'amber-dot' : state ? 'online-dot' : 'offline-dot'} /><span className="profile-chevron">⌄</span></summary>
          <div className="profile-popover"><span className="eyebrow">YOUR EXPEDITION</span><h2>{state?.rank ?? 'E · Initiate'}</h2><p>{completed} / {state?.missions.length ?? 6} quests completed. Each records a specific result, not mastery of a whole discipline.</p><div className="profile-language"><strong>{state?.language.band ?? 'guided'} English</strong><span>{state?.language.evidenceCount ?? 0} written observations</span></div><button onClick={() => { navigate('skills'); window.scrollTo(0, 0) }}>Skills &amp; rewards <span>↗</span></button><button onClick={() => navigate('connection')}>Connection <span className={paused ? 'amber-dot' : state?.connection.signedIn ? 'online-dot' : 'offline-dot'} /></button><a href="/progression.html" target="_blank" rel="noreferrer">Progression design · RU ↗</a><small>Local progress · {paused ? 'Tutor paused · answer saved' : 'Your work stays on this computer'}</small></div>
        </details>
      </header>
      {rewardNotice && <aside className="reward-toast" role="status"><span>✦</span><div><strong>{rewardNotice}</strong><button onClick={() => { navigate('skills'); window.scrollTo(0, 0) }}>Inspect rewards ↗</button></div><button aria-label="Dismiss reward notification" onClick={() => setRewardNotice('')}>×</button></aside>}
      {error && <div role="alert" className="error-banner"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
      {paused && <div className="pause-banner" role="status"><span>Ⅱ</span><div><strong>The System is resting.</strong><p>{state?.connection.reason}</p><small>Your answer is safe. Labs and hints remain available; only the tutor is paused. No paid fallback.</small></div>{savedPending && <button className="secondary" disabled={busy || evaluating} onClick={() => void action('/api/answers/resume', { id: savedPending.id })}>Resume saved answer</button>}</div>}
      {!state && <main className="loading"><div className="loading-sigil">◈</div><h1>Establishing a signal…</h1><p>Connecting to your local outpost.</p></main>}
      {state && tab === 'outpost' && mission && <main className="outpost-layout">
        <section className="world-column">
          <div className="world-heading"><div><span className="eyebrow">EXPEDITION / CHAPTER {chapter.number}</span><h1>{chapter.heading}</h1><p>{chapter.description}</p></div><div className="chapter-counter"><strong>{String(chapterCompleted).padStart(2, '0')}</strong><span>/ {String(coreMissions.length).padStart(2, '0')}<br />RESTORED</span></div></div>
          <div className="chapter-picker"><label htmlFor="chapter">Explore</label><select id="chapter" value={chapterId} disabled={busy} onChange={(event) => { const id = event.target.value as typeof chapterId; navigationEpoch.current++; setChapterId(id); setHint(''); const first = state.missions.find((item) => item.chapter === id); if (first) setSelected(first.id) }}>{chapters.map((item) => <option key={item.id} value={item.id} disabled={!state.missions.some((mission) => mission.chapter === item.id)}>{item.number} · {item.title}</option>)}</select><span>{coreMissions.length} core quests{chapterMissions.some((item) => item.bonus) ? ' + an optional skill trial' : ' · more chapters are planned'}</span></div>
          <section className="map-frame" aria-label="Expedition overview"><div className="map-top"><span>✦ {chapter.place}</span><div className="view-switch" role="group" aria-label="Overview view" data-view={overview}><span className="view-switch-thumb" aria-hidden="true" />{(['map', 'cards'] as const).map((view) => <button key={view} type="button" aria-pressed={overview === view} onClick={() => setOverview(view)}>{view === 'map' ? '◇ Map' : '▦ Cards'}</button>)}</div></div>
          {overview === 'map' ? <><Outpost key={chapterId} missions={coreMissions} selected={selected} disabled={busy} onSelect={showMission} />{chapterMissions.filter((item) => item.bonus).map((item) => <div className={`bonus-map-link sector-${item.id}`} key={item.id}><span>✦ OPTIONAL SKILL TRIAL</span><button onClick={() => showMission(item.id)}>{item.title} ↘</button><small>{item.status === 'locked' ? 'Unlock with HTTP Applied · current Signal + Gateway evidence' : item.status === 'completed' ? 'Transfer recorded · revisit anytime' : 'HTTP Applied opened a new route'}</small></div>)}</> : <div className="mission-grid" aria-label="Quest cards">{chapterMissions.map((item) => <article key={item.id} className={`mission-card sector-${item.id} ${item.status} ${selected === item.id ? 'focused' : ''}`}><span className="mission-card-icon">{item.icon}</span><span className="micro">{item.bonus ? 'OPTIONAL SKILL TRIAL' : item.status === 'completed' ? 'QUEST COMPLETE' : item.status === 'locked' ? 'UP AHEAD' : item.kind === 'assessment' ? 'RANK CHALLENGE' : 'ADVENTURE QUEST'}</span><h3>{item.title}</h3><StarSlots mission={item} /><p>{item.subtitle}</p>{item.nudge && <small className="rumour">{item.nudge}</small>}<div><span>{item.duration}</span><span>+{item.xp} XP</span></div><button disabled={busy} onClick={() => showMission(item.id)}>{item.status === 'completed' ? 'Revisit quest' : item.status === 'locked' ? 'Preview quest' : 'View quest'} <span>↘</span></button>{item.status === 'locked' && <small className="prerequisite-note">{item.bonus ? 'Requires HTTP Applied · current Signal + Gateway checks' : `Requires ${item.prerequisites.map((id) => state.missions.find((candidate) => candidate.id === id)?.sector ?? id).join(' + ')}`}</small>}</article>)}</div>}
          <div className="map-legend"><span><i className="legend-dot restored" /> Restored</span><span><i className="legend-dot available" /> Ready to explore</span><span><i className="legend-dot locked" /> Undiscovered</span><small>CHOOSE A PLACE. READ YOUR QUEST BELOW.</small></div></section>
        </section>
        <section ref={missionPanel} tabIndex={-1} className={`mission-panel sector-${mission.id}`} aria-label="Mission briefing">
          <div className="panel-header"><span className="eyebrow">{mission.kind === 'assessment' ? '✦ RANK CHALLENGE' : '✦ YOUR QUEST'}</span><button className="secondary small" onClick={() => { navigationEpoch.current++; const overview = document.querySelector<HTMLElement>('.view-switch button[aria-pressed="true"]'); overview?.focus({ preventScroll: true }); document.querySelector('.map-frame')?.scrollIntoView({ block: 'start' }) }}>↑ Back to overview</button></div>
          <div className="mission-workspace"><div className="mission-instructions">
          <div className="mission-title-row"><div className="mission-seal">{mission.icon}</div><h2>{mission.title}</h2></div><p className="brief">{mission.briefs[state.language.band]}</p><div className="mission-meta"><span>◷ {mission.duration}</span><span className="reward">+{mission.xp} XP</span></div>
          {mission.nudge && <p className="rumour">{mission.nudge}</p>}
          <StarBlock mission={mission} />
          <h3>How to complete this quest</h3><ul className="objectives">{mission.objectives.map((item, index) => <li key={item}><span>{currentPass ? '✓' : index + 1}</span><div>{item}</div></li>)}</ul>
          <details className="field-manual" open><summary>Field manual · current contract</summary><p>{mission.lesson}</p><h4>Terminal starting points</h4><pre>{mission.commands.join('\n')}</pre>{mission.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title} ↗</a>)}</details>
          </div><div className="mission-evidence">
          <h3>Workshop & verification</h3><p className="muted">Save your files before checking. Verification runs against saved code, not the editor buffer or your terminal session.</p>
          {mission.status === 'locked' && <p className="locked-requirements">{mission.bonus ? 'Earn HTTP Applied by verifying Signal and Gateway on the current contract. Previous completions and XP stay yours.' : `First restore: ${mission.prerequisites.map((id) => state.missions.find((item) => item.id === id)?.title ?? id).join(' + ')}.`}</p>}
          <div className="button-stack"><button className="primary" disabled={busy || mission.status === 'locked'} onClick={() => void enter(mission.id)}>↗ {mission.workspace ? 'Open workshop' : 'Accept mission & open VS Code'}</button><button className="secondary" disabled={busy || mission.status === 'locked'} onClick={() => void (mission.workspace ? verifyMission(mission.id) : enter(mission.id, false))}>{busy ? 'Working…' : mission.workspace ? 'Verify lab' : 'Prepare workspace only'}</button></div>
          {mission.workspace && <details className="workspace-info"><summary>Workspace details</summary><span className="micro">{state.connection.editorConnected ? 'EDITOR CONNECTED' : 'EDITOR NOT CONNECTED'}</span><code>{mission.workspace}</code><p>Your code and notes are preserved. The contract above is current; existing workspace manuals are kept as you left them.</p></details>}
          {mission.checks ? <CheckReport mission={mission} /> : <div className="verification-empty"><span>◎</span><p>No checks yet. Prepare your workspace, investigate the starter, then verify your saved changes.</p></div>}
          <button className="hint-button" disabled={busy || mission.status === 'locked'} onClick={async () => { const data = await action<{ hint: string }>(`/api/missions/${mission.id}/hint`); if (data) setHint(data.hint) }}>◇ Request a hint <small>{mission.hintsUsed ? `${mission.hintsUsed} used · guided practice` : 'marks this as guided practice'}</small></button>
          {hint && <div className="hint-box">{hint}</div>}
          <section className="chat-preview"><span className="eyebrow">✦ YOUR OPERATOR</span><h3>A place to think out loud.</h3><p>{conversationMessages ? `${conversationMessages} messages saved with this quest. Continue in your conversation workspace.` : 'Ask for guidance or share what you learned. Your conversation has its own space.'}</p><button type="button" className="secondary" onClick={() => navigate('chat')}>Open conversation ↗</button></section>
          </div></div>
        </section>
      </main>}
      {state && tab === 'chat' && mission && <ChatPanel mission={mission} missions={state.missions} exchanges={conversation} signedIn={state.connection.signedIn} busy={busy} evaluating={evaluating} paused={paused} mode={mode} draft={draftValue} positions={chatPositions} onMode={setMode} onDraft={draft} onSend={submitAnswer} onRetry={(id) => void action('/api/answers/resume', { id })} onMission={(id) => { navigationEpoch.current++; if (id !== selected) setHint(''); setSelected(id) }} onBack={() => showMission(selected)} />}
      {state && tab === 'atlas' && <Atlas missions={state.missions} onOpenMission={showMission} />}
      {state && tab === 'skills' && <main className="content-page"><ProgressionPanel progression={state.progression} skills={state.skills ?? []} missions={state.missions} busy={busy} onEquip={(id) => void action('/api/profile/equip', { id })} onMission={showMission} /><section className="language-card"><span className="eyebrow">LANGUAGE ATTUNEMENT</span><h2>{state.language.band} written English</h2><p>{state.language.evidenceCount} qualifying mission/day observations across {state.language.distinctMissions} missions. Repeating the same answer today does not raise your level.</p><p>{state.language.coverage}</p><h3>Return to these patterns</h3>{state.language.due.length ? state.language.due.map((item, index) => <p key={index}>◇ {item}</p>) : <p>After a day, patterns from your completed debriefs return here for use in a new context.</p>}</section><details className="future-roadmap"><summary>Beyond the current quests · planned curriculum</summary><div className="future-chapters">{futureChapters.map((chapter) => <article key={chapter.title}><div><h3>{chapter.title}</h3><p>{chapter.topics}</p></div><small>PLANNED</small></article>)}</div></details></main>}
      {state && tab === 'journal' && <main className="content-page"><span className="eyebrow">EXPEDITION RECORD</span><h1>Your work leaves a trace.</h1><p className="page-intro">Evidence, setbacks and discoveries. A history you can return to.</p><div className="journal-list">{state.journal.length === 0 && <div className="empty-state"><span>≡</span><h2>The first page is yours.</h2><p>Enter a mission to begin your field journal.</p></div>}{state.journal.map((entry) => <article key={entry.id}><div className={`journal-symbol ${entry.kind}`}>{entry.kind === 'victory' ? '✧' : '◇'}</div><div><span className="eyebrow">{entry.kind} {entry.missionId && ` / ${entry.missionId}`}</span><p>{entry.text}</p><time>{new Date(entry.createdAt).toLocaleString('en-GB')}</time></div></article>)}</div></main>}
      {state && tab === 'connection' && <main className="content-page narrow"><span className="eyebrow">SYSTEM CONNECTION</span><h1>Your account. Your outpost.</h1><p className="page-intro">Use your existing ChatGPT subscription. A direct local adapter handles sign-in and token refresh; no Codex CLI or API-credit fallback is involved.</p><section className="connection-card"><div className="provider-heading"><span>◈</span><div><h2>ChatGPT subscription</h2><p>{state.connection.signedIn ? 'Account linked to this local instance.' : 'Not connected. Technical labs are available; the tutor needs a link.'}</p></div><i className={state.connection.signedIn ? 'online-dot' : 'offline-dot'} /></div><label htmlFor="model">Tutor model</label><select id="model" value={state.connection.model} disabled={busy || evaluating} onChange={(event) => void action('/api/settings/model', { model: event.target.value })}><option value="gpt-6-astra">GPT-6 Astra</option><option value="gpt-6-sol">GPT-6 Sol</option><option value="gpt-6-luna">GPT-6 Luna</option></select><small>Model availability follows your subscription. Actual tutoring quality is still being calibrated.</small><div className="button-row"><button className="primary" disabled={busy || evaluating} onClick={async () => { const result = await action<{ url: string }>('/api/auth/begin'); if (result) setLoginUrl(result.url) }}>{state.connection.signedIn ? 'Reconnect account' : 'Connect ChatGPT'}</button>{state.connection.signedIn && <button className="secondary" disabled={busy || evaluating} onClick={() => void action('/api/auth/logout')}>Disconnect</button>}</div>{loginUrl && <div className="login-link"><p>Sign-in is ready. Continue when you choose:</p><a href={loginUrl} target="_blank" rel="noreferrer">Continue with ChatGPT ↗</a><p>Return here after authorization. Credentials stay in macOS Keychain or Linux Secret Service.</p></div>}</section><section className="connection-notes"><h2>A quiet local companion</h2><p>Your progress lives on this computer, outside the source checkout. Closing the tab does not erase a mission. If the tutor runs out of subscription capacity, your answer is retained and training pauses.</p><p>The workshop opens in its own VS Code window with the Rankforge extension. Existing work windows and previous mission files stay intact. First use may ask you to trust the local workspace.</p><p>Python labs run code you wrote locally as your user. The gateway lab uses an isolated, named Compose project. Docker and a terminal remain real tools you practice with.</p></section></main>}
    </div>
  </div>
}

function CheckReport({ mission }: { mission: MissionView }) {
  const result = mission.checks!
  const current = result.contractVersion === currentContractVersion
  const required = requiredChecks(result.checks)
  const bonus = bonusChecks(result.checks)
  return <section tabIndex={-1} className={`check-report ${current && result.passed ? 'pass' : ''}`} aria-label="Lab verification"><h3>{!current ? 'Previous contract result' : !result.supported ? 'Check unavailable' : result.passed ? 'System restored' : 'Evidence needs attention'}</h3>{!current && <p className="legacy-evidence">Your completion and XP are preserved. Run Verify lab again to check the current requirements and earn current skill evidence.</p>}<p className="check-count" role="status">{result.supported ? `${required.filter((item) => item.passed).length} / ${required.length} checks passed` : 'No result recorded'} · {current && result.passed ? 'Saved work verified.' : 'Review the evidence below.'}</p>{required.map((item, index) => <details key={`${result.checkedAt}:${index}`} open={!item.passed}><summary><span>{item.passed ? '✓' : '×'}</span>{item.name}</summary><pre>{item.detail}</pre></details>)}{bonus.length > 0 && <div className="bonus-report"><h4>Bonus</h4>{bonus.map((item, index) => item.passed
    ? <details key={`${result.checkedAt}:bonus:${index}`} open><summary><span>✦</span>{item.name}</summary><pre>{item.detail}</pre></details>
    : <details key={`${result.checkedAt}:bonus:${index}`}><summary><span>◇</span>Hidden bonus check · not yet</summary><pre>{current && result.passed ? `${item.name}\n${item.detail}` : 'The bonus never fails a mission. Pass the mission first; the rumour on the card is the only hint until then.'}</pre></details>)}</div>}{result.output && <details open={!result.passed}><summary>Runner output</summary><pre>{result.output}</pre></details>}<time>{new Date(result.checkedAt).toLocaleString('en-GB')} · contract {result.contractVersion ?? 'legacy'}</time></section>
}

function StarSlots({ mission }: { mission: MissionView }) {
  const earned = stars.filter((star) => mission.stars[star]).length
  return <span className="stars" role="img" aria-label={`${earned} of 3 stars`}>{stars.map((star) => <i key={star} className={mission.stars[star] ? 'star earned' : 'star'} aria-hidden="true">★</i>)}</span>
}

function StarBlock({ mission }: { mission: MissionView }) {
  const howTo: Record<1 | 2 | 3, string> = {
    1: 'Pass Verify lab on the current contract, with or without hints.',
    2: 'Write a debrief that answers the question and matches your verified results.',
    3: mission.nudge ? `${mission.nudge} A passing run that also clears this hidden check earns it.` : 'A passing run that also clears the hidden bonus check earns it.',
  }
  return <section className="star-block" aria-label="Stars"><h3>Stars</h3><ul>{stars.map((star) => {
    const earnedAt = mission.stars[star]
    return <li key={star} className={earnedAt ? 'earned' : ''}><span className="star-mark" aria-hidden="true">{'★'.repeat(star)}</span><div><strong>{starNames[star]}</strong>{star > 1 && <small> · +{Math.round(mission.xp / 2)} XP</small>}<p>{earnedAt ? `Earned ${new Date(earnedAt).toLocaleDateString('en-GB')}.` : howTo[star]}</p></div></li>
  })}</ul></section>
}
