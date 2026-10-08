import type { MissionStars, ProgressionSnapshot, SkillSnapshot } from './progression.js'

export type LanguageBand = 'guided' | 'connected' | 'independent'
export type MissionStatus = 'locked' | 'available' | 'active' | 'completed'
// An optional check is a hidden bonus: it can only add to a run and never fails the mission.
export type Check = { name: string; passed: boolean; detail: string; optional?: boolean }
export type CheckResult = { passed: boolean; checks: Check[]; output: string; checkedAt: string; supported: boolean; contractVersion?: string }
export type LanguageGrade = {
  communicativeGoal: 'met' | 'partial' | 'not_met'
  clarity: 'clear' | 'mostly_clear' | 'unclear'
  independence: 'independent' | 'supported'
  evidence: { quote: string; observation: string }[]
  corrections: { quote: string; suggestion: string; explanation: string }[]
  reply: string
  practice: string
}
export type Mission = {
  chapter: 'outpost' | 'guild'
  bonus?: boolean
  nudge?: string
  id: string; order: number; title: string; subtitle: string; sector: string; icon: string
  skills: string[]; prerequisites: string[]; xp: number; duration: string; kind: 'build' | 'repair' | 'assessment'
  briefs: Record<LanguageBand, string>
  objectives: string[]; languageGoal: string; prompt: string; hints: string[]; sources: { title: string; url: string }[]
  commands: string[]; lesson: string; artifact: string
}
export type MissionView = Mission & {
  status: MissionStatus; workspace: string | null; hintsUsed: number; checks: CheckResult | null
  completedAt: string | null; independent: boolean; stars: MissionStars
}
export type Exchange = {
  id: string; missionId: string; mode: 'debrief' | 'coach'; text: string; question: string
  status: 'pending' | 'processing' | 'completed' | 'paused' | 'failed'
  reply: string | null; grade: LanguageGrade | null; error: string | null; createdAt: string
}
export type JournalEntry = { id: number; kind: string; missionId: string | null; text: string; createdAt: string }
export type Snapshot = {
  progression?: ProgressionSnapshot
  skills: SkillSnapshot[]
  missions: MissionView[]; activeMissionId: string | null; xp: number; rank: string
  language: { band: LanguageBand; evidenceCount: number; distinctMissions: number; due: string[]; coverage: string }
  journal: JournalEntry[]; exchanges: Exchange[]
  connection: { signedIn: boolean; model: string; paused: boolean; reason: string | null; editorConnected: boolean }
}
