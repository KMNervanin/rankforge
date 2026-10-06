import type { Check } from './types.js'

export type PracticeMode = 'guided' | 'independent'
export type SkillEvidence = {
  missionId: string; contractVersion: string; checkedAt: string
  hintsUsed: number; mode: PracticeMode; checks: Check[]
}
export type RewardDefinition = {
  id: string; kind: 'chip' | 'cosmetic' | 'mission'; name: string; description: string
  charge: number; missionId?: string
}
export type EarnedReward = RewardDefinition & { earnedAt: string; source: string }
export type CheckpointDefinition = {
  name: string; scope: string; missionIds: string[]; rewards: RewardDefinition[]
}
export type BranchDefinition = {
  id: string; name: string; icon: string; description: string; checkpoints: CheckpointDefinition[]
}
export type CheckpointSnapshot = CheckpointDefinition & {
  level: number; earnedAt: string | null; evidence: SkillEvidence[]; missingMissionIds: string[]
}
export type BranchSnapshot = Omit<BranchDefinition, 'checkpoints'> & {
  level: number; checkpoints: CheckpointSnapshot[]
}
export type ProgressionSnapshot = {
  contractVersion: string; branches: BranchSnapshot[]; evidence: SkillEvidence[]
  unlockedMissionIds: string[]
  inventory: {
    chips: EarnedReward[]; bankedCharge: number; cosmetics: EarnedReward[]
    equippedCosmeticId: string | null
  }
}

export const chargeDescription = 'Game charge banked for a future bounded tutor harness. Not questions, tokens or money. Nothing is spent here; your current subscription is not debited by this reserve.'
export const evidenceDescription = 'Checkpoints describe these lab contracts, not universal mastery. Independent means no in-game hints or coaching recorded before that check; outside assistance is not measured. Guided practice earns the same rewards.'
export const starterChip: RewardDefinition = { id: 'starter-chip', kind: 'chip', name: 'First evidence chip', description: 'One verified outcome starts your reserve.', charge: 20 }
export const relayFrame: RewardDefinition = { id: 'relay-frame', kind: 'cosmetic', name: 'Relay frame', description: 'An amber profile frame earned by applying HTTP across the relay and gateway.', charge: 0 }
export const archiveFrame: RewardDefinition = { id: 'archive-frame', kind: 'cosmetic', name: 'Archive frame', description: 'A jade profile frame earned by protecting persistent data through recovery.', charge: 0 }
export const httpTrialUnlock: RewardDefinition = { id: 'http-trial-unlock', kind: 'mission', name: 'HTTP field trial', description: 'An optional outpost quest: transfer routing knowledge to a paginated supply endpoint.', charge: 0, missionId: 'http-trial' }

function checkpoint(branch: string, level: number, name: string, scope: string, missionIds: string[], extra: RewardDefinition[] = []): CheckpointDefinition {
  return { name, scope, missionIds, rewards: [
    { id: `${branch}-${level}-chip`, kind: 'chip', name: `${name} chip`, description: `${branch} checkpoint ${level}; granted once.`, charge: level * 5 },
    ...extra,
  ] }
}

export const skillBranches: BranchDefinition[] = [
  { id: 'http', name: 'HTTP boundaries', icon: '⇌', description: 'From one endpoint to a proxy, then a new request contract.', checkpoints: [
    checkpoint('http', 1, 'First contact', 'Direct health and unknown-route responses verified.', ['signal']),
    checkpoint('http', 2, 'Applied', 'Direct responses and proxy path/query forwarding verified in different labs.', ['signal', 'gateway'], [relayFrame, httpTrialUnlock]),
    checkpoint('http', 3, 'Transfer', 'A new paginated endpoint preserves route, query and read-only snapshot semantics.', ['signal', 'gateway', 'http-trial']),
  ] },
  { id: 'integrity', name: 'Data integrity', icon: '⬡', description: 'Protect records, replay identities and a recoverable database.', checkpoints: [
    checkpoint('integrity', 1, 'Storage boundary', 'Persistent relational constraints reject the published invalid writes.', ['vault']),
    checkpoint('integrity', 2, 'Repeat-safe writes', 'Schema constraints and durable replay/conflict behavior checked together.', ['vault', 'echo']),
    checkpoint('integrity', 3, 'Safe replacement', 'Recovery replaces state and preserves the old database on invalid input.', ['vault', 'echo', 'recovery'], [archiveFrame]),
  ] },
  { id: 'processing', name: 'Data processing', icon: '▥', description: 'Carry identity and input quality through more than one transformation.', checkpoints: [
    checkpoint('processing', 1, 'Identity matters', 'Distinct events, exact replays and conflicting identities are distinguished.', ['echo']),
    checkpoint('processing', 2, 'Trustworthy totals', 'Replay semantics, normalization, exact amounts and rejected-row evidence verified.', ['echo', 'ledger']),
    checkpoint('processing', 3, 'Archive transfer', 'Apply validated identities to rebuilding state, not just reporting it.', ['echo', 'ledger', 'recovery']),
  ] },
  { id: 'design', name: 'Design with evidence', icon: '◇', description: 'Connect a ticket, a unit-aware estimate and an executable consumer contract.', checkpoints: [
    checkpoint('design', 1, 'Traceable promises', 'Structured ticket facts, assumptions and observations stay distinct.', ['briefing']),
    checkpoint('design', 2, 'Sized assumptions', 'Traceable requirements and published capacity equations verified; throughput is not measured.', ['briefing', 'capacity']),
    checkpoint('design', 3, 'Executable boundary', 'The consumer probe distinguishes compatible responses, wrong effects and unavailable transport.', ['briefing', 'capacity', 'contract']),
  ] },
]
