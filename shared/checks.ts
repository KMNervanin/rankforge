import type { Check } from './types.js'

export const isBonusCheck = (check: Check) => check.optional === true
export const requiredChecks = (checks: Check[]) => checks.filter((check) => !isBonusCheck(check))
export const bonusChecks = (checks: Check[]) => checks.filter(isBonusCheck)
// "passed" on a CheckResult means every required check passed; a bonus check cannot change that.
export const requiredPassed = (checks: Check[]) => requiredChecks(checks).length > 0 && requiredChecks(checks).every((check) => check.passed)
// The bonus is earned only when this run carried hidden checks and all of them passed.
export const bonusPassed = (checks: Check[]) => bonusChecks(checks).length > 0 && bonusChecks(checks).every((check) => check.passed)
