import { chargeDescription, evidenceDescription } from '../shared/progression'
import type { ProgressionSnapshot, SkillSnapshot } from '../shared/progression'
import type { MissionView } from '../shared/types'
import './progression.css'

export type ProgressionPanelProps = {
  progression: ProgressionSnapshot | undefined
  skills: SkillSnapshot[]
  missions: MissionView[]
  busy: boolean
  onEquip: (id: string) => void
  onMission: (id: string) => void
}

export function ProgressionPanel({ progression, skills, missions, busy, onEquip, onMission }: ProgressionPanelProps) {
  if (!progression) return <section className="progression-panel" aria-labelledby="skills-title">
    <h1 id="skills-title">Skills &amp; rewards</h1>
    <p>Restart the local Rankforge service to load skills and rewards. Your existing mission progress stays saved.</p>
  </section>

  const completed = missions.filter((mission) => mission.completedAt)
  const title = (id: string) => missions.find((mission) => mission.id === id)?.title ?? id
  const canOpen = (id: string) => missions.some((mission) => mission.id === id && mission.status !== 'locked')
  const trial = missions.find((mission) => mission.id === 'http-trial')
  const unlocked = progression.unlockedMissionIds.includes('http-trial')
  const { inventory } = progression

  return <section className="progression-panel" aria-labelledby="skills-title">
    <header className="progression-heading">
      <div><span className="eyebrow">Your engineering paths</span><h1 id="skills-title">Skills &amp; rewards</h1>
        <p>One working endpoint is a beginning. Build evidence across tasks, then try a different problem.</p></div>
      <span className="progression-total">{progression.branches.reduce((sum, branch) => sum + branch.level, 0)}<small>checkpoints earned</small></span>
    </header>

    <section className="skill-bars" aria-labelledby="skill-bars-title">
      <div className="skill-bars-heading"><h2 id="skill-bars-title">Skills</h2><p>Every star pays XP to the skills its mission lists. ★ pays the base XP; ★★ and ★★★ add half each.</p></div>
      {skills.some((skill) => skill.xp > 0) ? <ul>{skills.filter((skill) => skill.xp > 0).map((skill) => <li key={skill.name}>
        <div className="skill-bar-label"><strong>{skill.name}</strong><span className="skill-level-name">{skill.levelName}</span><small>{skill.xp}{skill.nextThreshold ? ` / ${skill.nextThreshold}` : ''} XP</small></div>
        <progress value={skill.xp} max={skill.nextThreshold ?? skill.xp} aria-label={`${skill.name}: ${skill.levelName}, ${skill.xp} XP`} />
        <div className="skill-bar-missions">{skill.missions.map((id) => <button key={id} disabled={busy || !canOpen(id)} onClick={() => onMission(id)}>{title(id)}</button>)}</div>
      </li>)}</ul> : <p className="muted">No skill XP yet. The first star of any quest starts its skills.</p>}
      {skills.some((skill) => skill.xp === 0) && <p className="skill-bars-rest"><span>Not practiced yet:</span> {skills.filter((skill) => skill.xp === 0).map((skill) => skill.name).join(' · ')}</p>}
    </section>

    <ol className="progression-loop" aria-label="How progression works">
      <li><span aria-hidden="true">01</span><div><strong>Do real work</strong><small>A saved lab passes its current checks.</small></div></li>
      <li><span aria-hidden="true">02</span><div><strong>Connect evidence</strong><small>Different missions build a branch.</small></div></li>
      <li><span aria-hidden="true">03</span><div><strong>Keep the reward</strong><small>One-time charge, frames and bonus access.</small></div></li>
      <li><span aria-hidden="true">04</span><div><strong>Transfer the idea</strong><small>A new task tests a bounded new claim.</small></div></li>
    </ol>

    <div className="progression-branches">
      {progression.branches.map((branch) => {
        const next = branch.checkpoints.find((checkpoint) => !checkpoint.earnedAt)
        const latest = branch.checkpoints.filter((checkpoint) => checkpoint.earnedAt).at(-1)
        const transfer = latest?.evidence.find((item) => item.missionId === 'http-trial')
        return <article className={`skill-path skill-path-${branch.id}`} key={branch.id} aria-labelledby={`path-${branch.id}`}>
          <header><span className="skill-path-icon" aria-hidden="true">{branch.icon}</span><div><h2 id={`path-${branch.id}`}>{branch.name}</h2><p>{branch.description}</p></div>
            <span className="skill-level" aria-label={`${branch.level} of ${branch.checkpoints.length} checkpoints`}>{branch.level}/{branch.checkpoints.length}</span></header>
          <ol className="skill-nodes" aria-label={`${branch.name} checkpoints`}>
            {branch.checkpoints.map((checkpoint) => <li key={checkpoint.level} className={checkpoint.earnedAt ? 'earned' : checkpoint === next ? 'next' : ''}>
              <span className="skill-node" aria-hidden="true">{checkpoint.earnedAt ? '✓' : checkpoint.level}</span>
              <strong>{checkpoint.name}</strong><small>{checkpoint.earnedAt ? 'Earned' : checkpoint === next ? 'Next checkpoint' : 'Later'}</small>
            </li>)}
          </ol>
          <p className="skill-scope">{latest ? latest.scope : 'No verified evidence in this path yet.'}</p>
          {transfer && <p className="skill-mode">{transfer.mode === 'guided' ? 'Guided transfer' : 'Independent transfer (no in-game help recorded)'} · same reward</p>}
          {next ? <div className="skill-next">
            <div className="skill-progress-label"><strong>Next: {next.name}</strong><small>{next.missionIds.length - next.missingMissionIds.length}/{next.missionIds.length} distinct labs</small></div>
            <progress value={next.missionIds.length - next.missingMissionIds.length} max={next.missionIds.length} aria-label={`${branch.name}: evidence toward ${next.name}`} />
            <p>{next.scope}</p>
            <div className="skill-missing">{next.missingMissionIds.map((id) => <button key={id} disabled={busy || !canOpen(id)} onClick={() => onMission(id)}>
              {completed.some((mission) => mission.id === id) ? 'Reverify: ' : ''}{title(id)}<span aria-hidden="true"> ↗</span>
            </button>)}</div>
            <small className="skill-reward-preview">Reward: +{next.rewards.reduce((sum, reward) => sum + reward.charge, 0)} game charge{next.rewards.filter((reward) => reward.kind !== 'chip').map((reward) => ` · ${reward.name}`).join('')}</small>
          </div> : <div className="skill-next"><strong>This path's current checkpoints are complete.</strong><p>Keep practicing; these records cover only the listed lab contracts.</p></div>}
          {latest && <details className="skill-evidence"><summary>What was verified</summary>
            {branch.checkpoints.filter((checkpoint) => checkpoint.earnedAt).map((checkpoint) => <div key={checkpoint.level}>
              <strong>{checkpoint.name}</strong><p>{checkpoint.scope}</p>
              <ul>{checkpoint.evidence.map((item) => <li key={item.missionId}>{title(item.missionId)} · {item.checks.length} checks · {item.mode === 'guided' ? 'guided practice' : 'no in-game help recorded'} · contract {item.contractVersion}</li>)}</ul>
            </div>)}
          </details>}
        </article>
      })}
    </div>

    <div className="progression-bottom">
      <section className={`bonus-trial ${unlocked ? 'unlocked' : ''}`} aria-labelledby="trial-title">
        <span className="eyebrow">Optional outpost quest</span><h2 id="trial-title">Beyond the health check</h2>
        <p>Serve stable supply pages to different clients. Validate queries, handle continuation and preserve the snapshot.</p>
        <p className="muted">{unlocked ? 'HTTP Applied recorded; the transfer evidence counts toward the HTTP path.' : 'Open to everyone. Verifying Signal and Gateway on the current contract records HTTP Applied alongside it.'}</p>
        <button disabled={busy || !trial || !canOpen('http-trial')} onClick={() => onMission('http-trial')}>{trial?.completedAt ? 'Revisit HTTP field trial' : 'Enter HTTP field trial'}</button>
      </section>
      <section className="reward-inventory" aria-labelledby="inventory-title">
        <span className="eyebrow">Yours to keep</span><h2 id="inventory-title">Reward inventory</h2>
        <div className="charge-reserve"><span aria-hidden="true">▣</span><div><strong>{inventory.bankedCharge} game charge</strong><small>{inventory.chips.length} earned {inventory.chips.length === 1 ? 'chip' : 'chips'} · banked, not spendable yet</small></div></div>
        <p>{chargeDescription}</p>
        {inventory.chips.length > 0 && <details><summary>Charge receipts</summary><ul>{inventory.chips.map((chip) => <li key={chip.id}>{chip.name} · +{chip.charge} · {chip.source}</li>)}</ul></details>}
        <div className="cosmetic-inventory">{inventory.cosmetics.length ? inventory.cosmetics.map((cosmetic) => <div className="cosmetic-row" key={cosmetic.id}>
          <span className={`cosmetic-swatch cosmetic-${cosmetic.id}`} aria-hidden="true">R</span><div><strong>{cosmetic.name}</strong><small>{cosmetic.description}</small></div>
          <button disabled={busy || inventory.equippedCosmeticId === cosmetic.id} aria-pressed={inventory.equippedCosmeticId === cosmetic.id} onClick={() => onEquip(cosmetic.id)}>{inventory.equippedCosmeticId === cosmetic.id ? 'Equipped' : `Equip ${cosmetic.name}`}</button>
        </div>) : <p className="muted">Earned profile frames will appear here.</p>}</div>
        {inventory.equippedCosmeticId && <button disabled={busy} onClick={() => onEquip('default')}>Use default frame</button>}
      </section>
    </div>

    <p className="progression-scope">{evidenceDescription} Checkpoints and rewards stay earned after a later failed check. Repeating the same evidence never farms extra charge.</p>
    <details className="practice-record"><summary>Practice record · {completed.length} completed {completed.length === 1 ? 'mission' : 'missions'}</summary>
      {!completed.length && <p>Your first completed lab will appear here.</p>}
      <ul>{completed.map((mission) => {
        const evidence = progression.evidence.filter((item) => item.missionId === mission.id && item.contractVersion === progression.contractVersion).sort((a, b) => a.checkedAt.localeCompare(b.checkedAt)).at(-1)
        return <li key={mission.id}><button disabled={busy || !canOpen(mission.id)} onClick={() => onMission(mission.id)}>{mission.title}</button>
          <span>{evidence ? `${evidence.mode === 'guided' ? 'Guided practice' : 'No in-game help recorded'} · ${evidence.hintsUsed} recorded hints · ${evidence.checks.length} contract checks` : 'Legacy completion retained · reverify for current skill evidence'}</span>
          <small>{mission.skills.join(' · ')} — bounded practice, not mastery</small></li>
      })}</ul>
    </details>
  </section>
}
