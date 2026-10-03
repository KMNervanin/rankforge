import { useEffect, useRef, useState } from 'react'
import type { MissionView, Snapshot } from '../shared/types.js'
import { futureChapters } from '../shared/content.js'
import { Outpost } from './Outpost.js'
import { ChatPanel, type ChatPositions } from './ChatPanel.js'

type Tab = 'outpost' | 'chat' | 'skills' | 'journal' | 'connection'

export function App() {
  const savedChat = useRef({ open: localStorage.getItem('rankforge.chat.open') === 'true', mode: localStorage.getItem('rankforge.chat.mode'), mission: localStorage.getItem('rankforge.chat.mission') })
  const [state, setState] = useState<Snapshot | null>(null)
  const [selected, setSelected] = useState('signal')
  const [tab, setTab] = useState<Tab>(() => savedChat.current.open ? 'chat' : 'outpost')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [hint, setHint] = useState('')
  const [loginUrl, setLoginUrl] = useState('')
  const [mode, setMode] = useState<'coach' | 'debrief'>(() => savedChat.current.mode === 'coach' ? 'coach' : 'debrief')
  const [drafts, setDrafts] = useState<Record<string, string>>(() => { try { return JSON.parse(localStorage.getItem('rankforge.drafts') ?? '{}') } catch { return {} } })
  const token = useRef(''); const epoch = useRef(0); const initialized = useRef(false)
  const chatPositions = useRef<ChatPositions>({})
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
            const previousMission = savedChat.current.open && snapshot.missions.find((item) => item.id === savedChat.current.mission && item.status !== 'locked')
            const missionId = previousMission ? previousMission.id : snapshot.activeMissionId ?? 'signal'
            setSelected(missionId)
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
    setSelected(id); setHint(''); setTab('outpost')
    await action(`/api/missions/${id}/start`, { openEditor })
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

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={(event) => { event.preventDefault(); setTab('outpost') }} aria-label="Rankforge outpost"><span className="brand-mark">R<span>◈</span></span><span>RANKFORGE<small>THE ASCENT BEGINS HERE</small></span></a>
      <div className="operator-card"><div className="rank-emblem">{state?.rank[0] ?? 'E'}</div><span className="eyebrow">YOUR ADVENTURER</span><strong>The Pathfinder</strong><span className="muted">{state?.rank ?? 'E · Initiate'}</span><div className="xp-line"><span>{state?.xp ?? 0} XP</span><span>{Math.max(0, 1240 - (state?.xp ?? 0))} TO CHAPTER CLEAR</span></div><div className="progress-track"><i style={{ width: `${Math.min(100, (state?.xp ?? 0) / 12.4)}%` }} /></div></div>
      <nav aria-label="Main navigation">{([['outpost', '◇', 'The outpost'], ['chat', '✉', 'Operator chat'], ['skills', '⌘', 'Abilities'], ['journal', '≡', 'Field journal'], ['connection', '⏣', 'Connection']] as const).map(([id, icon, label]) => <button key={id} aria-label={label} className={tab === id ? 'nav-active' : ''} onClick={() => setTab(id)}><span aria-hidden="true">{icon}</span>{label}{id === 'outpost' && <small>{completed}/6</small>}</button>)}</nav>
      <div className="sidebar-bottom"><span className="eyebrow">LANGUAGE ATTUNEMENT</span><strong>{state?.language.band ?? 'guided'} English</strong><p>The world grows with your words.</p><div className="language-dots">{[0, 1, 2].map((n) => <i key={n} className={n <= ['guided', 'connected', 'independent'].indexOf(state?.language.band ?? 'guided') ? 'lit' : ''} />)}</div><span className="micro">WRITTEN PRACTICE · {state?.language.evidenceCount ?? 0} EVIDENCE</span></div>
      <div className="local-status"><i className={state ? 'online-dot' : 'offline-dot'} /> LOCAL INSTANCE <span>v0.1</span></div>
    </aside>
    <div className={`main-shell ${tab === 'chat' ? 'chat-active' : ''}`}>
      <header className="topbar"><div><span className="breadcrumb">EXPEDITION / CHAPTER I</span><span className="chapter-name">The silent outpost</span></div><div className="header-right"><span className="status-chip"><i className={paused ? 'amber-dot' : 'online-dot'} />{paused ? 'TRAINING PAUSED' : 'SYSTEM ONLINE'}</span><button className="avatar" onClick={() => setTab('connection')} aria-label="Account connection">K</button></div></header>
      {error && <div role="alert" className="error-banner"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
      {paused && <div className="pause-banner" role="status"><span>Ⅱ</span><div><strong>The System is resting.</strong><p>{state?.connection.reason}</p><small>Your work and submitted answer are safe. No paid fallback.</small></div>{savedPending && <button className="secondary" disabled={busy || evaluating} onClick={() => void action('/api/answers/resume', { id: savedPending.id })}>Resume saved answer</button>}</div>}
      {!state && <main className="loading"><div className="loading-sigil">◈</div><h1>Establishing a signal…</h1><p>Connecting to your local outpost.</p></main>}
      {state && tab === 'outpost' && mission && <main className="outpost-layout">
        <section className="world-column">
          <div className="world-heading"><div><span className="eyebrow">YOUR FIRST EXPEDITION</span><h1>A world worth restoring.</h1><p>Every system you repair becomes a skill you carry.</p></div><div className="chapter-counter"><strong>{String(completed).padStart(2, '0')}</strong><span>/ 06<br />RESTORED</span></div></div>
          <div className="map-frame"><div className="map-top"><span>✦ THE FLOATING OUTPOST</span><span>CHAPTER 01</span></div><Outpost missions={state.missions} selected={selected} disabled={busy || paused} onSelect={(id) => void enter(id)} /><div className="map-legend"><span><i className="legend-dot restored" /> Restored</span><span><i className="legend-dot available" /> Ready to explore</span><span><i className="legend-dot locked" /> Undiscovered</span><small>CHOOSE A PLACE. START A QUEST.</small></div></div>
          <div className="system-message"><span className="system-symbol">◈</span><div><span className="eyebrow">MESSAGE FROM THE SYSTEM</span><p>{completed === 0 ? 'The outpost is quiet, but not beyond repair. Restore the command relay. The rest will follow.' : completed === 6 ? 'The outpost is awake. Your first chapter is complete. Return to explain a decision, test your memory, or prepare for the frontier.' : `${completed} ${completed === 1 ? 'system has' : 'systems have'} returned to life. Your work leaves a mark here. Choose the next connection to restore.`}</p></div></div>
          <div className="section-heading"><h2>Your quest board</h2><span>CHAPTER I</span></div>
          <div className="mission-grid">{state.missions.map((item) => <article key={item.id} className={`mission-card sector-${item.id} ${item.status} ${selected === item.id ? 'focused' : ''}`}><span className="mission-card-icon">{item.icon}</span><span className="micro">{item.status === 'completed' ? 'QUEST COMPLETE' : item.status === 'locked' ? 'UP AHEAD' : item.kind === 'assessment' ? 'RANK CHALLENGE' : 'ADVENTURE QUEST'}</span><h3>{item.title}</h3><p>{item.subtitle}</p><div><span>{item.duration}</span><span>+{item.xp} XP</span></div><button disabled={busy || paused || item.status === 'locked'} onClick={() => void enter(item.id)}>{item.status === 'completed' ? 'Revisit workshop' : item.status === 'locked' ? `Requires ${item.prerequisites.join(' + ')}` : 'Enter workshop'} <span>↗</span></button><button className="briefing-link" onClick={() => { setSelected(item.id); setHint('') }}>Read briefing</button></article>)}</div>
        </section>
        <aside className={`mission-panel sector-${mission.id}`} aria-label="Mission briefing">
          <div className="panel-header"><span className="eyebrow">{mission.kind === 'assessment' ? '✦ RANK CHALLENGE' : '✦ YOUR QUEST'}</span><span>0{mission.order}</span></div>
          <div className="mission-title-row"><div className="mission-seal">{mission.icon}</div><h2>{mission.title}</h2></div><p className="brief">{mission.briefs[state.language.band]}</p><div className="mission-meta"><span>◷ {mission.duration}</span><span className="reward">+{mission.xp} XP</span></div>
          <div className="button-stack"><button className="primary" disabled={busy || paused || mission.status === 'locked'} onClick={() => void enter(mission.id)}>↗ {mission.workspace ? 'Open workshop' : 'Accept mission & open VS Code'}</button><button className="secondary" disabled={busy || paused || mission.status === 'locked'} onClick={() => void (mission.workspace ? action(`/api/missions/${mission.id}/check`) : enter(mission.id, false))}>{busy ? 'Working…' : mission.workspace ? 'Verify lab' : 'Prepare workspace only'}</button></div>
          <h3>How to complete this quest</h3><ul className="objectives">{mission.objectives.map((item, index) => <li key={item}><span>{mission.status === 'completed' ? '✓' : index + 1}</span><div>{item}</div></li>)}</ul>
          {mission.workspace && <details className="workspace-info"><summary>Workspace details</summary><span className="micro">{state.connection.editorConnected ? 'EDITOR CONNECTED' : 'EDITOR NOT CONNECTED'}</span><code>{mission.workspace}</code></details>}
          {mission.checks && <CheckReport mission={mission} />}
          <details><summary>Field manual</summary><p>{mission.lesson}</p><h4>Terminal starting points</h4><pre>{mission.commands.join('\n')}</pre>{mission.sources.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title} ↗</a>)}</details>
          <button className="hint-button" disabled={busy || paused || mission.status === 'locked'} onClick={async () => { const data = await action<{ hint: string }>(`/api/missions/${mission.id}/hint`); if (data) setHint(data.hint) }}>◇ Request a hint <small>{mission.hintsUsed ? `${mission.hintsUsed} used · guided practice` : 'marks this as guided practice'}</small></button>
          {hint && <div className="hint-box">{hint}</div>}
          <section className="chat-preview"><span className="eyebrow">✦ YOUR OPERATOR</span><h3>A place to think out loud.</h3><p>{conversationMessages ? `${conversationMessages} messages saved with this quest. Continue in your conversation workspace.` : 'Ask for guidance or share what you learned. Your conversation has its own space.'}</p><button type="button" className="secondary" onClick={() => setTab('chat')}>Open conversation ↗</button></section>
        </aside>
      </main>}
      {state && tab === 'chat' && mission && <ChatPanel mission={mission} missions={state.missions} exchanges={conversation} signedIn={state.connection.signedIn} busy={busy} evaluating={evaluating} paused={paused} mode={mode} draft={draftValue} positions={chatPositions} onMode={setMode} onDraft={draft} onSend={submitAnswer} onRetry={(id) => void action('/api/answers/resume', { id })} onMission={setSelected} onBack={() => setTab('outpost')} />}
      {state && tab === 'skills' && <main className="content-page"><span className="eyebrow">YOUR ABILITY NETWORK</span><h1>Earned through experience.</h1><p className="page-intro">Restoring a system is practice. Using knowledge independently, in another situation and after a delay, is stronger evidence of mastery.</p><div className="skills-grid">{state.missions.map((item) => <article className={`ability-card sector-${item.id}`} key={item.id}><span className={`ability-icon ${item.status === 'completed' ? 'earned' : ''}`}>{item.icon}</span><h2>{item.artifact}</h2><p>{item.skills.join(' · ')}</p><span className="status-chip">{item.completedAt ? item.independent ? 'UNASSISTED COMPLETION' : 'GUIDED COMPLETION' : 'NOT YET EVIDENCED'}</span><small>{item.completedAt ? `Evidence recorded ${new Date(item.completedAt).toLocaleDateString('en-GB')}` : 'Complete the related lab to acquire this artifact.'}</small></article>)}</div><section className="language-card"><span className="eyebrow">LANGUAGE ATTUNEMENT</span><h2>{state.language.band} written English</h2><p>{state.language.evidenceCount} qualifying mission/day observations across {state.language.distinctMissions} missions. Repeating the same answer today does not raise your level.</p><p>{state.language.coverage}</p><h3>Return to these patterns</h3>{state.language.due.length ? state.language.due.map((item, index) => <p key={index}>◇ {item}</p>) : <p>After a day, patterns from your completed debriefs return here for use in a new context.</p>}</section><h2>Beyond the first frontier</h2><div className="future-chapters">{futureChapters.map((chapter, index) => <article key={chapter.title}><span>0{index + 2}</span><div><h3>{chapter.title}</h3><p>{chapter.topics}</p></div><small>CURRICULUM PLANNED</small></article>)}</div></main>}
      {state && tab === 'journal' && <main className="content-page"><span className="eyebrow">EXPEDITION RECORD</span><h1>Your work leaves a trace.</h1><p className="page-intro">Evidence, setbacks and discoveries. A history you can return to.</p><div className="journal-list">{state.journal.length === 0 && <div className="empty-state"><span>≡</span><h2>The first page is yours.</h2><p>Enter a mission to begin your field journal.</p></div>}{state.journal.map((entry) => <article key={entry.id}><div className={`journal-symbol ${entry.kind}`}>{entry.kind === 'victory' ? '✧' : '◇'}</div><div><span className="eyebrow">{entry.kind} {entry.missionId && ` / ${entry.missionId}`}</span><p>{entry.text}</p><time>{new Date(entry.createdAt).toLocaleString('en-GB')}</time></div></article>)}</div></main>}
      {state && tab === 'connection' && <main className="content-page narrow"><span className="eyebrow">SYSTEM CONNECTION</span><h1>Your account. Your outpost.</h1><p className="page-intro">Use your existing ChatGPT subscription. A direct local adapter handles sign-in and token refresh; no Codex CLI or API-credit fallback is involved.</p><section className="connection-card"><div className="provider-heading"><span>◈</span><div><h2>ChatGPT subscription</h2><p>{state.connection.signedIn ? 'Account linked to this local instance.' : 'Not connected. Technical labs are available; the tutor needs a link.'}</p></div><i className={state.connection.signedIn ? 'online-dot' : 'offline-dot'} /></div><label htmlFor="model">Tutor model</label><select id="model" value={state.connection.model} disabled={busy || evaluating} onChange={(event) => void action('/api/settings/model', { model: event.target.value })}><option value="gpt-6-astra">GPT-6 Astra</option><option value="gpt-6-sol">GPT-6 Sol</option><option value="gpt-6-luna">GPT-6 Luna</option></select><small>Model availability follows your subscription. Actual tutoring quality is still being calibrated.</small><div className="button-row"><button className="primary" disabled={busy || evaluating} onClick={async () => { const result = await action<{ url: string }>('/api/auth/begin'); if (result) setLoginUrl(result.url) }}>{state.connection.signedIn ? 'Reconnect account' : 'Connect ChatGPT'}</button>{state.connection.signedIn && <button className="secondary" disabled={busy || evaluating} onClick={() => void action('/api/auth/logout')}>Disconnect</button>}</div>{loginUrl && <div className="login-link"><p>Sign-in is ready. Continue when you choose:</p><a href={loginUrl} target="_blank" rel="noreferrer">Continue with ChatGPT ↗</a><p>Return here after authorization. Credentials stay in macOS Keychain or Linux Secret Service.</p></div>}</section><section className="connection-notes"><h2>A quiet local companion</h2><p>Your progress lives on this computer, outside the source checkout. Closing the tab does not erase a mission. If the tutor runs out of subscription capacity, your answer is retained and training pauses.</p><p>The workshop opens in its own VS Code window with the Rankforge extension. Existing work windows and previous mission files stay intact. First use may ask you to trust the local workspace.</p><p>Python labs run code you wrote locally as your user. The gateway lab uses an isolated, named Compose project. Docker and a terminal remain real tools you practice with.</p></section></main>}
    </div>
  </div>
}

function CheckReport({ mission }: { mission: MissionView }) {
  const result = mission.checks!
  return <section className={`check-report ${result.passed ? 'pass' : ''}`} aria-label="Lab verification"><h3>{!result.supported ? 'Check unavailable' : result.passed ? 'System restored' : 'Evidence needs attention'}</h3>{result.checks.map((item, index) => <details key={index}><summary><span>{item.passed ? '✓' : '×'}</span>{item.name}</summary><pre>{item.detail}</pre></details>)}{result.output && <pre>{result.output}</pre>}<time>{new Date(result.checkedAt).toLocaleTimeString('en-GB')}</time></section>
}
