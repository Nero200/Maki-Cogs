# CPR Mode & Initiative System Design

**Date:** 2026-02-01
**Status:** Approved
**Feature:** Cyberpunk Red support for ChimeraDice

---

## Overview

Add Cyberpunk Red (CPR) game support to ChimeraDice with:
1. **CPR Mode** - Channel toggle that modifies d10 and d6 behavior
2. **Initiative System** - Batch rolling for per-round initiative

---

## CPR Mode

### Commands

| Command | Aliases | Purpose |
|---------|---------|---------|
| `>cpr enable` | `>cpr on` | Enable CPR mode for channel |
| `>cpr disable` | `>cpr off` | Disable CPR mode for channel |
| `>cpr status` | - | Show current state |

**Storage:** Per-channel, persisted to Red's config system.

### d10 Behavior (Skill Checks)

**Trigger:** Only `1d10+X` rolls (single d10 with optional modifier). Multi-die rolls like `3d10` are unaffected.

**Exploding 10:**
- Roll a natural 10 → roll another d10, add to result (max once)
- Display: `1d10 (10→10!+6) + 5 = 21 = **21**`

**Imploding 1:**
- Roll a natural 1 → roll another d10, subtract from result (max once)
- Display: `1d10 (1→1!-7) + 5 = -1 = **-1** [Luck? **6** (1+5)]`
- Luck shows what the result would be without the penalty (1 + modifier)

**Normal (2-9):** Standard output, unchanged.

### d6 Behavior (Damage Rolls)

**Trigger:** Rolls of 2+ d6 only (e.g., `2d6`, `3d6+2`, `4d6`). Does not apply to mixed expressions like `1d10+2d6`.

**Critical Condition:** 2 or more dice show a natural 6.

**Effect:** Add +5 to total, append "Critical Damage" label.

**Display:**
```
Result: 3d6 (**6**, 4, **6**) = 16 **+5** = **21** Critical Damage
```

**Non-critical (only one 6):**
```
Result: 3d6 (**6**, 4, 3) = 13 = **13**
```

---

## Initiative System

### Commands

| Command | Purpose | Example |
|---------|---------|---------|
| `>init add NAME MOD` | Add/overwrite character | `>init add Darius 14+2` |
| `>init remove NAME` | Remove one character | `>init remove Darius` |
| `>init roll` | Roll for all, display sorted | See output below |
| `>init clear` | Wipe the group | - |

### Storage

- Per-channel (different channels = different initiative groups)
- Persisted to Red's config (survives bot restarts)
- Stores both the expression (`14+2`) and evaluated total (`16`)
- Name matching is case-insensitive

### Modifier Parsing

| Input | Evaluated | Display |
|-------|-----------|---------|
| `14+2` | 16 | `14+2` |
| `+14+2` | 16 | `14+2` (leading + stripped) |
| `12-1` | 11 | `12-1` |
| `-2` | -2 | `-2` (leading - preserved) |
| `8` | 8 | `8` |

**Overwrite Behavior:** If name already exists, replace the modifier.

### Roll Mechanics

- Each character rolls `1d10 + modifier`
- A natural 10 explodes (roll another d10, add once) - same as CPR mode
- Results sorted highest to lowest

### Output Format

```
**Initiative Round**
1. Darius [28] (1d10→10!+4 +14+2)
2. James [19] (1d10+12-1)
3. Sasha [14] (1d10+8)
4. Goon #1 [9] (1d10+4)
```

The breakdown shows: die result (with explosion if applicable) + stored modifier expression.

---

## Edge Cases & Error Handling

### Initiative System

| Scenario | Behavior |
|----------|----------|
| `>init roll` with empty group | "No characters in initiative. Use `>init add NAME MOD` to add some." |
| `>init remove` non-existent name | "Character not found in initiative." |
| `>init add` with invalid modifier | "Invalid modifier. Use numbers and +/- operators (e.g., `14+2`)." |
| Name matching | Case-insensitive (`Darius` = `darius`) |

### CPR Mode

| Scenario | Behavior |
|----------|----------|
| CPR mode off | Normal dice behavior, no explosions/crits |
| Roll with luck/karma + CPR mode | Both systems apply (luck/karma weights + CPR explosions) |
| Complex expressions in CPR | Only simple `1d10+X` and `Nd6` patterns trigger CPR mechanics |

---

## Implementation Notes

### Integration Points

- CPR mode hooks into the existing roll pipeline after dice are generated
- Initiative uses its own rolling logic (bypasses luck/karma since it's for multiple characters)
- Both features use Red's config system for persistence

### Testing Considerations

- Test d10 explosion/implosion edge cases
- Test d6 critical damage with exactly 2 sixes, more than 2, and fewer than 2
- Test initiative sorting with ties
- Test modifier parsing with various formats
- Test persistence across bot restarts
