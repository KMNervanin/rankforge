import type { DatabaseSync } from 'node:sqlite'
import { currentContractVersion } from '../shared/contracts.js'
import { skillBranches, starterChip } from '../shared/progression.js'
import type { EarnedReward, ProgressionSnapshot, RewardDefinition, SkillEvidence } from '../shared/progression.js'
import type { CheckResult } from '../shared/types.js'

type MilestoneRow = { branch_id: string; level: number; earned_at: string; evidence: string }

export class Rewards {
  constructor(private readonly db: DatabaseSync) {
    db.exec(`
      CREATE TABLE IF NOT EXISTS skill_evidence (
        mission_id TEXT NOT NULL REFERENCES progress(id), contract_version TEXT NOT NULL,
        mode TEXT NOT NULL, evidence TEXT NOT NULL,
        PRIMARY KEY (mission_id, contract_version, mode)
      );
      CREATE TABLE IF NOT EXISTS skill_milestones (
        branch_id TEXT NOT NULL, level INTEGER NOT NULL, earned_at TEXT NOT NULL, evidence TEXT NOT NULL,
        PRIMARY KEY (branch_id, level)
      );
      CREATE TABLE IF NOT EXISTS reward_grants (id TEXT PRIMARY KEY, reward TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS reward_equipment (
        slot TEXT PRIMARY KEY CHECK (slot = 'frame'), reward_id TEXT NOT NULL REFERENCES reward_grants(id)
      );
    `)
  }

  private evidence(): SkillEvidence[] {
    return (this.db.prepare('SELECT evidence FROM skill_evidence ORDER BY mission_id,contract_version,mode').all() as { evidence: string }[]).map((row) => JSON.parse(row.evidence))
  }
  private milestones(): MilestoneRow[] {
    return this.db.prepare('SELECT * FROM skill_milestones ORDER BY branch_id,level').all() as MilestoneRow[]
  }
  private grant(reward: RewardDefinition, earnedAt: string, source: string) {
    this.db.prepare('INSERT OR IGNORE INTO reward_grants(id,reward) VALUES (?,?)').run(reward.id, JSON.stringify({ ...reward, earnedAt, source }))
  }

  // The caller owns the completion transaction: evidence, milestones and inventory commit together.
  recordCheck(missionId: string, result: CheckResult, hintsUsed: number, earnedAt: string) {
    if (!result.passed || !result.supported || result.contractVersion !== currentContractVersion || !result.checks.length || result.checks.some((check) => !check.passed)) return
    const evidence: SkillEvidence = { missionId, contractVersion: currentContractVersion, checkedAt: result.checkedAt, hintsUsed, mode: hintsUsed ? 'guided' : 'independent', checks: result.checks }
    this.db.prepare('INSERT OR IGNORE INTO skill_evidence VALUES (?,?,?,?)').run(missionId, currentContractVersion, evidence.mode, JSON.stringify(evidence))
    this.grant(starterChip, earnedAt, missionId)
    const current = this.evidence().filter((item) => item.contractVersion === currentContractVersion)
    for (const branch of skillBranches) {
      for (const [index, checkpoint] of branch.checkpoints.entries()) {
        const evidence = checkpoint.missionIds.map((id) => current.find((item) => item.missionId === id && item.mode === 'independent') ?? current.find((item) => item.missionId === id))
        if (evidence.some((item) => !item)) break
        const inserted = this.db.prepare('INSERT OR IGNORE INTO skill_milestones VALUES (?,?,?,?)').run(branch.id, index + 1, earnedAt, JSON.stringify(evidence))
        if (Number(inserted.changes)) for (const reward of checkpoint.rewards) this.grant(reward, earnedAt, `${branch.id}:${index + 1}`)
      }
    }
  }

  isUnlocked(missionId: string): boolean {
    return missionId !== 'http-trial' || !!this.db.prepare("SELECT 1 FROM skill_milestones WHERE branch_id='http' AND level>=2").get()
  }
  equip(id: string): boolean {
    if (id === 'default') { this.db.prepare("DELETE FROM reward_equipment WHERE slot='frame'").run(); return true }
    const row = this.db.prepare('SELECT reward FROM reward_grants WHERE id=?').get(id) as { reward: string } | undefined
    if (!row || (JSON.parse(row.reward) as EarnedReward).kind !== 'cosmetic') return false
    this.db.prepare("INSERT INTO reward_equipment VALUES ('frame',?) ON CONFLICT(slot) DO UPDATE SET reward_id=excluded.reward_id").run(id)
    return true
  }

  snapshot(): ProgressionSnapshot {
    const evidence = this.evidence()
    const milestones = this.milestones()
    const grants = (this.db.prepare('SELECT reward FROM reward_grants ORDER BY id').all() as { reward: string }[]).map((row) => JSON.parse(row.reward) as EarnedReward)
    const chips = grants.filter((reward) => reward.kind === 'chip')
    const equipped = this.db.prepare("SELECT reward_id FROM reward_equipment WHERE slot='frame'").get() as { reward_id: string } | undefined
    return {
      contractVersion: currentContractVersion, evidence,
      branches: skillBranches.map((branch) => ({ ...branch,
        level: milestones.filter((item) => item.branch_id === branch.id).reduce((level, item) => Math.max(level, item.level), 0),
        checkpoints: branch.checkpoints.map((checkpoint, index) => {
          const earned = milestones.find((item) => item.branch_id === branch.id && item.level === index + 1)
          return { ...checkpoint, level: index + 1, earnedAt: earned?.earned_at ?? null, evidence: earned ? JSON.parse(earned.evidence) : [],
            missingMissionIds: earned ? [] : checkpoint.missionIds.filter((id) => !evidence.some((item) => item.missionId === id && item.contractVersion === currentContractVersion)),
          }
        }),
      })),
      unlockedMissionIds: this.isUnlocked('http-trial') ? ['http-trial'] : [],
      inventory: { chips, bankedCharge: chips.reduce((sum, chip) => sum + chip.charge, 0), cosmetics: grants.filter((reward) => reward.kind === 'cosmetic'), equippedCosmeticId: equipped?.reward_id ?? null },
    }
  }
}
