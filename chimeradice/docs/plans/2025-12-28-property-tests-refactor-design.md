# Property Tests Refactor Design

**Date:** 2025-12-28
**Status:** Approved
**Goal:** Improve property tests by refactoring for testability, expanding coverage, and improving test quality

## Problem Statement

Current property tests in `test_chimeradice_properties.py` cannot run because:
1. `hypothesis` library is not installed
2. Tests import `chimeradice.py` which imports `discord`, failing outside the bot environment
3. Many critical pure functions lack property test coverage

## Solution: Extract Pure Functions to Core Module

Create `chimeradice_core.py` containing all pure functions that don't depend on Discord or async operations. This enables clean imports for testing.

## Module Structure

```
chimeradice/
├── chimeradice.py           # Discord cog (imports from core)
├── chimeradice_core.py      # Pure functions (no discord deps)
├── chimeradice_test.py      # GM tool (gitignored, unchanged)
├── chimeradice.py.bak       # Backup before refactor
├── tests/
│   ├── test_chimeradice_properties.py  # Property tests (import core only)
│   └── ...
```

## Extracted Components

### Constants
- `FUDGE_FACES`
- `FALLOUT_FACES`
- `FUDGE_PROBABILITIES`
- `DEFAULT_GUILD_USER`
- `DEFAULT_GUILD`

### Result Classes
- `DiceRollResult`
- `SimpleRollResult`

### Percentile Functions
- `single_die_percentile(result, die_size)`
- `multiple_dice_percentile(result, num_dice, die_size)`
- `calculate_fudge_percentile(roll_string, result)`
- `estimate_keep_percentile(roll_string, result, num_dice, die_size)`
- `calculate_roll_percentile(roll_string, result)`

### Weighted Rolling Functions
- `roll_weighted_standard_die(die_size, debt)`
- `roll_weighted_fudge_dice(num_dice, debt)`
- `generate_fudge_dice_for_sum(num_dice, target_sum)`
- `generate_realistic_fudge_faces(num_dice, target_sum)`

### Parsing/Validation Functions
- `parse_dice_modifiers(expression)`
- `validate_dice_expression(expression)`
- `normalize_dice_key(dice_expr)`
- `parse_roll_and_label(roll_string)`
- `translate_dice_syntax(expression)`
- `extract_base_dice(expression)`

## What Stays in the Cog

- All preset/queue functionality (GM tool support)
- All async methods
- All Discord command handlers
- Instance state management

## Function Signature Changes

Methods become module-level functions:
- Remove `self` parameter
- Drop leading underscore (now public API of core module)

```python
# Before (method):
def _single_die_percentile(self, result: int, die_size: int) -> float:

# After (function):
def single_die_percentile(result: int, die_size: int) -> float:
```

## Property Test Coverage

### Existing Tests to Fix
| Test | Fix |
|------|-----|
| `test_single_die_percentile_properties` | Import from core |
| `test_multiple_dice_percentile_properties` | Import from core |
| `test_fudge_dice_generation_properties` | Import from core |
| `test_fudge_percentile_properties` | Import from core |
| `test_validation_robustness` | Import from core |
| `DiceStateMachine` | Rewrite for core functions |

### New Property Tests to Add
| Function | Key Properties |
|----------|---------------|
| `translate_dice_syntax` | Idempotence, preserves valid syntax, dl/kh equivalence |
| `roll_weighted_standard_die` | Always in range [1, die_size], bias direction matches debt sign |
| `roll_weighted_fudge_dice` | Sum matches face values, faces in {-1, 0, 1}, bias direction correct |
| `normalize_dice_key` | Idempotence, `d20` = `1d20`, case insensitive |
| `parse_roll_and_label` | Label extraction, dice part always valid |
| `generate_realistic_fudge_faces` | Sum equals target, all faces valid, length = num_dice |

## Test Infrastructure

### Dependencies
- Install `hypothesis` in venv

### Hypothesis Settings
- Default `max_examples=100` for fast runs
- `@settings(max_examples=1000)` for probability tests
- Deadline disabled for weighted-rolling tests

### Test Runner
- Import from `chimeradice_core` (no Discord needed)
- Graceful fallback if hypothesis unavailable

## Implementation Steps

1. Back up current cog (`chimeradice.py.bak`)
2. Create `chimeradice_core.py` with extracted functions
3. Update `chimeradice.py` to import from core
4. Update `tests/test_chimeradice_properties.py` to import from core
5. Install hypothesis in venv
6. Run tests to verify nothing broke
7. Add new property tests for uncovered functions

## Risk Mitigation

- Backup ensures easy rollback
- Tests verify behavior unchanged
- Core module is purely additive
