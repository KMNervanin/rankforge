import { useLayoutEffect, useRef, useState, type FormEvent, type RefObject } from 'react'
import type { Exchange, MissionView } from '../shared/types.js'
import { Markdown } from './Markdown.js'

export type ChatPositions = Record<string, { top: number; following: boolean }>
type Props = {
  mission: MissionView
  missions: MissionView[]
  exchanges: Exchange[]
  signedIn: boolean
  busy: boolean
  evaluating: boolean
  paused: boolean
  mode: 'coach' | 'debrief'
  draft: string
  positions: RefObject<ChatPositions>
  onMode: (mode: 'coach' | 'debrief') => void
  onDraft: (text: string) => void
  onSend: () => Promise<void>
  onRetry: (id: string) => void
  onMission: (id: string) => void
  onBack: () => void
}

export function ChatPanel(props: Props) {
  const { mission, exchanges, busy, evaluating, paused, mode, draft, positions } = props
  const history = useRef<HTMLDivElement>(null)
  const content = useRef<HTMLDivElement>(null)
  const following = useRef(true)
  const previousMission = useRef<string | null>(null)
  const previousRevision = useRef('')
  const [atLatest, setAtLatest] = useState(true)
  const [hasNew, setHasNew] = useState(false)
  const revision = exchanges.map((item) => `${item.id}:${item.status}:${item.reply?.length ?? 0}:${item.error ?? ''}`).join('|')
  const messageCount = exchanges.reduce((count, item) => count + 1 + Number(Boolean(item.reply)), 0)
  const cannotSend = busy || paused || evaluating || !draft.trim() || mission.status === 'locked'

  function savePosition() {
    if (history.current) positions.current[mission.id] = { top: history.current.scrollTop, following: following.current }
  }
  function latest() {
    following.current = true
    if (history.current) history.current.scrollTop = history.current.scrollHeight
    setAtLatest(true); setHasNew(false); savePosition()
  }
  function oldest() {
    following.current = false
    if (history.current) history.current.scrollTop = 0
    setAtLatest(false); savePosition()
  }
  function onScroll() {
    const element = history.current!
    following.current = element.scrollHeight - element.clientHeight - element.scrollTop < 80
    setAtLatest(following.current)
    if (following.current) setHasNew(false)
    savePosition()
  }

  useLayoutEffect(() => {
    const element = history.current!
    if (previousMission.current !== mission.id) {
      const saved = positions.current[mission.id]
      following.current = saved?.following ?? true
      element.scrollTop = following.current ? element.scrollHeight : saved?.top ?? 0
      setAtLatest(following.current); setHasNew(false)
      previousMission.current = mission.id
    } else if (previousRevision.current !== revision) {
      if (following.current) element.scrollTop = element.scrollHeight
      else setHasNew(true)
    }
    previousRevision.current = revision
    positions.current[mission.id] = { top: element.scrollTop, following: following.current }
  }, [mission.id, revision, positions])

  useLayoutEffect(() => {
    const element = history.current!
    const observer = new ResizeObserver(() => {
      if (following.current) {
        element.scrollTop = element.scrollHeight
        positions.current[mission.id] = { top: element.scrollTop, following: true }
      }
    })
    observer.observe(element)
    observer.observe(content.current!)
    return () => observer.disconnect()
  }, [mission.id, positions])

  function send(event?: FormEvent) {
    event?.preventDefault()
    if (cannotSend) return
    latest()
    void props.onSend()
  }

  return <main className="chat-page">
    <header className="chat-page-heading">
      <div><span className="eyebrow">YOUR LEARNING COMPANION</span><h1>Operator channel</h1></div>
      <button type="button" className="secondary small" onClick={props.onBack}>← Back to outpost</button>
    </header>
    <section className="chat-panel" aria-label="Operator conversation">
      <div className="chat-toolbar">
        <div className="chat-mission-picker"><label htmlFor="chat-mission">Quest</label><select id="chat-mission" value={mission.id} onChange={(event) => props.onMission(event.target.value)}>{props.missions.map((item) => <option key={item.id} value={item.id} disabled={item.status === 'locked'}>{item.order}. {item.title}</option>)}</select></div>
        <div className="chat-history-tools"><span>{messageCount} messages</span><button type="button" onClick={oldest} disabled={!exchanges.length}>Oldest</button><button type="button" onClick={latest} disabled={!exchanges.length}>Latest ↓</button></div>
      </div>
      <details className="chat-goal" key={`${mission.id}:${mode}`}><summary>{mode === 'debrief' ? 'Your debrief question' : 'Quest context & guidance'}</summary><p>{mode === 'debrief' ? mission.prompt : mission.briefs.guided}</p><p>The operator reads saved workspace files. Unsaved editor changes and your terminal are not visible here; save changes or paste the relevant output.</p></details>
      <div className="chat-history-shell">
        <div ref={history} className="conversation" role="log" aria-label="Conversation history" aria-live="polite" aria-relevant="additions" tabIndex={0} onScroll={onScroll}>
          <div ref={content} className="conversation-content">
            {!exchanges.length && <div className="chat-empty"><span aria-hidden="true">✦</span><h2>A little help, a new perspective.</h2><p>Ask a question in your own words, or explain what you found. Your conversation stays with this quest.</p></div>}
            {exchanges.map((exchange) => <ExchangeCard key={exchange.id} exchange={exchange} busy={busy || evaluating} onRetry={() => props.onRetry(exchange.id)} />)}
          </div>
        </div>
        {!atLatest && <button type="button" className="chat-jump" onClick={latest}>{hasNew ? 'New activity ↓' : 'Jump to latest ↓'}</button>}
      </div>
      <form className="chat-composer" onSubmit={send}>
        <div className="chat-composer-top"><div className="segmented"><button type="button" aria-pressed={mode === 'debrief'} onClick={() => props.onMode('debrief')}>Mission debrief</button><button type="button" aria-pressed={mode === 'coach'} onClick={() => props.onMode('coach')}>Ask for guidance</button></div><span className="chat-link-status"><i className={props.signedIn ? 'online-dot' : 'offline-dot'} />{paused ? 'Paused · answer saved' : evaluating ? 'Operator is replying…' : props.signedIn ? 'Connected' : 'Account not connected'}</span></div>
        <label className="sr-only" htmlFor="answer">Your answer in English</label>
        <textarea id="answer" placeholder={mode === 'debrief' ? 'Tell the operator what you found…' : 'What would you like to understand?'} value={draft} onChange={(event) => props.onDraft(event.target.value)} maxLength={8000} rows={3} onKeyDown={(event) => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && !event.nativeEvent.isComposing) { event.preventDefault(); send() } }} />
        <div className="composer-footer"><small>{mode === 'coach' ? 'Save code in VS Code first · ' : 'Draft saved · '}Ctrl / ⌘ + Enter to send</small><div><span className="chat-character-count">{draft.length} / 8000</span><button type="submit" className="primary small" disabled={cannotSend}>{evaluating ? 'Receiving…' : 'Send ↗'}</button></div></div>
      </form>
    </section>
  </main>
}

function ExchangeCard({ exchange, busy, onRetry }: { exchange: Exchange; busy: boolean; onRetry: () => void }) {
  const time = new Date(exchange.createdAt).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  return <article className="exchange chat-exchange" data-exchange-id={exchange.id}>
    <div className="learner-message"><div className="message-meta"><span>YOU · {exchange.mode === 'coach' ? 'GUIDANCE' : 'DEBRIEF'}</span><time dateTime={exchange.createdAt}>{time}</time></div><Markdown text={exchange.text} /></div>
    {exchange.reply && <div className="operator-message"><div className="message-meta"><span>✦ OPERATOR</span></div><Markdown text={exchange.reply} />
      {exchange.grade && <div className="chat-feedback"><span className="grade-label">{exchange.grade.communicativeGoal.replaceAll('_', ' ')} · {exchange.grade.clarity.replaceAll('_', ' ')}</span>{exchange.grade.corrections.map((item, index) => <div className="correction" key={index}><q>{item.quote}</q><strong>→ {item.suggestion}</strong><p>{item.explanation}</p></div>)}<details><summary>Why this feedback?</summary>{exchange.grade.evidence.map((item, index) => <p key={index}><q>{item.quote}</q> — {item.observation}</p>)}</details></div>}
    </div>}
    {['pending', 'processing'].includes(exchange.status) && <p className="receiving" role="status">Signal received. The operator is considering your answer…</p>}
    {exchange.error && <div className="saved-error"><p>{exchange.error}</p><button type="button" className="secondary small" disabled={busy} onClick={onRetry}>Retry saved answer</button></div>}
  </article>
}
