import { DatabaseSync } from 'node:sqlite'
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { missions, missionById, followUpQuestions } from '../shared/content.js'
import type { CheckResult, Exchange, JournalEntry, LanguageBand, LanguageGrade, MissionView, Snapshot } from '../shared/types.js'

type Progress = { id: string; workspace: string | null; hints: number; checks: string | null; completed: string | null; independent: number }
type ExchangeRow = { id: string; mission_id: string; mode: 'debrief' | 'coach'; text: string; question: string; status: Exchange['status']; reply: string | null; grade: string | null; error: string | null; created: string; supported: number }

export class DomainError extends Error {
  constructor(message: string, public statusCode = 400) { super(message) }
}

export class Store {
  readonly db: DatabaseSync
  constructor(readonly home: string, private readonly now = () => new Date().toISOString()) {
    mkdirSync(home, { recursive: true, mode: 0o700 })
    this.db = new DatabaseSync(path.join(home, 'progress.sqlite'), { timeout: 3000 })
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;
      CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS progress (id TEXT PRIMARY KEY, workspace TEXT, hints INTEGER NOT NULL DEFAULT 0, checks TEXT, completed TEXT, independent INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS awards (mission_id TEXT PRIMARY KEY REFERENCES progress(id), xp INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, mission_id TEXT, text TEXT NOT NULL, created TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS exchanges (id TEXT PRIMARY KEY, mission_id TEXT NOT NULL REFERENCES progress(id), mode TEXT NOT NULL, text TEXT NOT NULL, question TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, reply TEXT, grade TEXT, error TEXT, created TEXT NOT NULL, supported INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS editor_command (id INTEGER PRIMARY KEY, workspace TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0);
    `)
    const columns = this.db.prepare('PRAGMA table_info(exchanges)').all() as { name: string }[]
    if (!columns.some((column) => column.name === 'question')) this.db.exec("ALTER TABLE exchanges ADD COLUMN question TEXT NOT NULL DEFAULT ''")
    for (const mission of missions) this.db.prepare('INSERT OR IGNORE INTO progress(id) VALUES (?)').run(mission.id)
    const interrupted = this.db.prepare("UPDATE exchanges SET status='paused', error='The service restarted. Your answer is saved; resume when ready.' WHERE status IN ('pending','processing')").run()
    if (Number(interrupted.changes)) this.set('pause', 'An evaluation was interrupted. Resume your saved answer.')
  }
  close() { this.db.close() }
  get(key: string): string | null { return (this.db.prepare('SELECT value FROM settings WHERE key=?').get(key) as { value: string } | undefined)?.value ?? null }
  set(key: string, value: string) { this.db.prepare('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value').run(key, value) }
  record(kind: string, missionId: string | null, text: string) { this.db.prepare('INSERT INTO journal(kind,mission_id,text,created) VALUES (?,?,?,?)').run(kind, missionId, text, this.now()) }
  progress(id: string): Progress {
    missionById(id)
    return this.db.prepare('SELECT * FROM progress WHERE id=?').get(id) as Progress
  }
  language(): Snapshot['language'] {
    const rows = this.db.prepare("SELECT mission_id,created,grade,text FROM exchanges WHERE mode='debrief' AND status='completed' AND supported=0 AND grade IS NOT NULL ORDER BY created,id").all() as { mission_id: string; created: string; grade: string; text: string }[]
    const seenAnswers = new Set<string>()
    const good = rows.filter((row) => {
      const grade = JSON.parse(row.grade) as LanguageGrade
      const key = `${row.mission_id}:${row.text.toLowerCase().replace(/\s+/g, ' ').trim()}`
      if (seenAnswers.has(key) || grade.communicativeGoal !== 'met' || grade.clarity !== 'clear' || grade.independence !== 'independent') return false
      seenAnswers.add(key)
      return true
    })
    const unique = new Set(good.map((row) => `${row.mission_id}:${row.created.slice(0, 10)}`))
    const distinctMissions = new Set(good.map((row) => row.mission_id)).size
    const days = new Set(good.map((row) => row.created.slice(0, 10))).size
    const band: LanguageBand = unique.size >= 10 && distinctMissions >= 5 && days >= 4 ? 'independent' : unique.size >= 4 && distinctMissions >= 3 && days >= 2 ? 'connected' : 'guided'
    const recent = this.db.prepare("SELECT grade,created FROM exchanges WHERE mode='debrief' AND status='completed' AND grade IS NOT NULL ORDER BY created DESC LIMIT 30").all() as { grade: string; created: string }[]
    const due = recent.filter((row) => Date.parse(this.now()) - Date.parse(row.created) >= 24 * 60 * 60 * 1000).slice(0, 3).map((row) => (JSON.parse(row.grade) as LanguageGrade).practice)
    return { band, evidenceCount: unique.size, distinctMissions, due, coverage: 'Written interaction only. No speaking/listening level or CEFR certification is inferred.' }
  }
  views(): MissionView[] {
    const active = this.get('active')
    return missions.map((mission) => {
      const progress = this.progress(mission.id)
      const unlocked = mission.prerequisites.every((id) => this.progress(id).completed !== null)
      return { ...mission, prompt: this.question(mission.id), status: progress.completed ? 'completed' : active === mission.id ? 'active' : unlocked ? 'available' : 'locked', workspace: progress.workspace, hintsUsed: progress.hints, checks: progress.checks ? JSON.parse(progress.checks) : null, completedAt: progress.completed, independent: !!progress.independent }
    })
  }
  question(id: string) {
    const count = Number((this.db.prepare("SELECT COUNT(*) AS count FROM exchanges WHERE mission_id=? AND mode='debrief' AND status='completed'").get(id) as { count: number }).count)
    const followUps = followUpQuestions[id] ?? []
    return count && followUps.length ? followUps[(count - 1) % followUps.length]! : missionById(id).prompt
  }
  assertAvailable(id: string) {
    const mission = missionById(id)
    if (mission.prerequisites.some((key) => !this.progress(key).completed)) throw new DomainError('Complete the prerequisite missions first.', 409)
  }
  assertRunning() { if (this.get('pause')) throw new DomainError('Training is paused. Resume the saved evaluation first.', 409) }
  select(id: string, workspace: string) {
    this.assertRunning(); this.assertAvailable(id)
    this.db.prepare('UPDATE progress SET workspace=? WHERE id=?').run(workspace, id)
    this.set('active', id)
    this.record('mission', id, `Entered ${missionById(id).sector}. Workspace preserved at ${workspace}.`)
  }
  hint(id: string): string {
    this.assertRunning(); this.assertAvailable(id)
    const mission = missionById(id)
    const count = this.progress(id).hints
    this.db.prepare('UPDATE progress SET hints=? WHERE id=?').run(Math.min(count + 1, mission.hints.length), id)
    const hint = mission.hints[Math.min(count, mission.hints.length - 1)]!
    this.record('hint', id, hint)
    return hint
  }
  saveCheck(id: string, result: CheckResult) {
    this.db.exec('BEGIN IMMEDIATE')
    try {
      const before = this.progress(id)
      this.db.prepare('UPDATE progress SET checks=? WHERE id=?').run(JSON.stringify(result), id)
      if (result.passed && result.supported) {
        if (!before.completed) {
          this.db.prepare('UPDATE progress SET completed=?,independent=? WHERE id=?').run(this.now(), before.hints === 0 ? 1 : 0, id)
          this.db.prepare('INSERT OR IGNORE INTO awards VALUES (?,?)').run(id, missionById(id).xp)
          this.record('victory', id, `${missionById(id).sector} restored. ${missionById(id).artifact} acquired. ${before.hints ? 'Guided practice' : 'Unassisted technical completion'} recorded.`)
        }
      } else this.record('check', id, result.supported ? 'The lab still needs work. Evidence saved in the mission panel.' : 'Check unavailable. No failure or reward recorded.')
      this.db.exec('COMMIT')
    } catch (error) { this.db.exec('ROLLBACK'); throw error }
  }
  submit(id: string, missionId: string, text: string, mode: 'debrief' | 'coach'): Exchange {
    this.assertAvailable(missionId)
    const prior = this.exchange(id)
    if (prior) {
      if (prior.missionId !== missionId || prior.text !== text || prior.mode !== mode) throw new DomainError('This request identifier belongs to a different answer.', 409)
      return prior
    }
    this.assertRunning()
    const lastSupport = this.get(`language-support:${missionId}`)
    const supported = lastSupport && Date.parse(this.now()) - Date.parse(lastSupport) < 24 * 60 * 60 * 1000 ? 1 : 0
    this.db.prepare("INSERT INTO exchanges(id,mission_id,mode,text,question,status,created,supported) VALUES (?,?,?,?,?,'pending',?,?)").run(id, missionId, mode, text, this.question(missionId), this.now(), supported)
    return this.exchange(id)!
  }
  exchangeRow(id: string) { return this.db.prepare('SELECT * FROM exchanges WHERE id=?').get(id) as ExchangeRow | undefined }
  exchange(id: string): Exchange | undefined {
    const row = this.exchangeRow(id)
    return row && { id: row.id, missionId: row.mission_id, mode: row.mode, text: row.text, question: row.question || missionById(row.mission_id).prompt, status: row.status, reply: row.reply, grade: row.grade ? JSON.parse(row.grade) : null, error: row.error, createdAt: row.created }
  }
  processing(id: string) { this.db.prepare("UPDATE exchanges SET status='processing',error=NULL WHERE id=?").run(id) }
  finish(id: string, reply: string, grade: LanguageGrade | null) {
    const row = this.exchangeRow(id)!
    if (row.status === 'completed') return
    if (row.mode === 'coach') {
      this.db.prepare('UPDATE progress SET hints=MAX(hints,1) WHERE id=?').run(row.mission_id)
      this.set(`language-support:${row.mission_id}`, this.now())
    }
    if (grade && row.supported) grade.independence = 'supported'
    this.db.prepare("UPDATE exchanges SET status='completed',reply=?,grade=?,error=NULL WHERE id=?").run(reply, grade ? JSON.stringify(grade) : null, id)
    this.record('language', row.mission_id, grade ? `Debrief: ${grade.communicativeGoal.replaceAll('_', ' ')}. ${grade.practice}` : 'Operator conversation recorded. No proficiency points awarded for coaching.')
    this.set('pause', '')
  }
  fail(id: string, reason: string, pause: boolean) {
    this.db.prepare('UPDATE exchanges SET status=?,error=? WHERE id=?').run(pause ? 'paused' : 'failed', reason, id)
    if (pause) this.set('pause', reason)
  }
  queueEditor(workspace: string) {
    this.db.prepare('UPDATE editor_command SET acknowledged=1 WHERE acknowledged=0').run()
    const result = this.db.prepare('INSERT INTO editor_command(workspace) VALUES (?)').run(workspace)
    return Number(result.lastInsertRowid)
  }
  editorCommand() { return this.db.prepare('SELECT id,workspace FROM editor_command WHERE acknowledged=0 ORDER BY id DESC LIMIT 1').get() as { id: number; workspace: string } | undefined }
  acknowledgeEditor(id: number) { this.db.prepare('UPDATE editor_command SET acknowledged=1 WHERE id=?').run(id) }
  snapshot(connection: Snapshot['connection']): Snapshot {
    const xp = Number((this.db.prepare('SELECT COALESCE(SUM(xp),0) AS xp FROM awards').get() as { xp: number }).xp)
    const exchanges = this.db.prepare('SELECT id FROM exchanges ORDER BY created,id').all() as { id: string }[]
    const journal = this.db.prepare('SELECT id,kind,mission_id AS missionId,text,created AS createdAt FROM journal ORDER BY id DESC LIMIT 60').all() as JournalEntry[]
    return { missions: this.views(), activeMissionId: this.get('active'), xp, rank: xp >= 1000 ? 'D · Pathfinder' : xp >= 400 ? 'E · Operator' : 'E · Initiate', language: this.language(), exchanges: exchanges.map((item) => this.exchange(item.id)!), journal, connection }
  }
}
