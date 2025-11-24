#!/usr/bin/env python3
"""Test the force command validation logic."""

import re
from typing import List

def _parse_dice_modifiers(expression: str) -> tuple:
    """Parse dice expression with multiple modifiers."""
    # Find the dice part (everything before first + or -)
    dice_match = re.match(r'([^+-]+)', expression)
    if not dice_match:
        return expression, 0

    dice_part = dice_match.group(1)
    modifier_part = expression[len(dice_part):]

    if not modifier_part:
        return dice_part, 0

    # Parse all modifiers using regex
    modifier_matches = re.findall(r'([+-])(\d+)', modifier_part)

    total_modifier = 0
    for sign, value in modifier_matches:
        if sign == '+':
            total_modifier += int(value)
        else:
            total_modifier -= int(value)

    return dice_part, total_modifier

def _validate_forced_results(dice_expr: str, results: List[int]) -> tuple:
    """Validate that forced results are possible for the given dice expression."""
    dice_expr_lower = dice_expr.lower()

    # Check for fudge dice first (XdF or XdFudge)
    fudge_match = re.match(r'(\d+)d[fF]', dice_expr_lower)
    if fudge_match:
        num_dice = int(fudge_match.group(1))
        min_result = -num_dice
        max_result = num_dice

        for result in results:
            if result < min_result or result > max_result:
                return False, f"{result} is impossible for {dice_expr} (range: {min_result} to {max_result})"
        return True, ""

    # Check for fallout dice (XdD) - must check before standard dice
    fallout_match = re.match(r'(\d+)d[dD]', dice_expr_lower)
    if fallout_match:
        num_dice = int(fallout_match.group(1))
        max_result = num_dice * 2
        for result in results:
            if result < 0 or result > max_result:
                return False, f"{result} is impossible for {dice_expr} (range: 0 to {max_result})"
        return True, ""

    # Check for standard dice (XdY) - check last since it's most general
    standard_match = re.match(r'(\d+)d(\d+)', dice_expr_lower)
    if standard_match:
        num_dice = int(standard_match.group(1))
        die_size = int(standard_match.group(2))

        min_result = num_dice
        max_result = num_dice * die_size

        for result in results:
            if result < min_result or result > max_result:
                return False, f"{result} is impossible for {standard_match.group(0)} (range: {min_result} to {max_result})"
        return True, ""

    return True, ""

# Test cases
test_cases = [
    ("1d20", [21], False, "should reject 21 for 1d20"),
    ("1d20", [0], False, "should reject 0 for 1d20"),
    ("1d20", [20], True, "should accept 20 for 1d20"),
    ("1d20", [1], True, "should accept 1 for 1d20"),
    ("1d20+5", [10], True, "should accept 10 for 1d20+5 (base dice)"),
    ("1d20+5", [25], False, "should reject 25 for 1d20+5 (exceeds base dice)"),
    ("4df", [5], False, "should reject 5 for 4df"),
    ("4df", [-5], False, "should reject -5 for 4df"),
    ("4df", [4], True, "should accept 4 for 4df"),
    ("4df", [-4], True, "should accept -4 for 4df"),
    ("4df", [0], True, "should accept 0 for 4df"),
    ("3dd", [-1], False, "should reject -1 for 3dd"),
    ("3dd", [0], True, "should accept 0 for 3dd"),
    ("3dd", [6], True, "should accept 6 for 3dd (max: 3×2)"),
    ("3dd", [7], False, "should reject 7 for 3dd (exceeds max)"),
    ("2d6", [2], True, "should accept 2 for 2d6 (min)"),
    ("2d6", [12], True, "should accept 12 for 2d6 (max)"),
    ("2d6", [1], False, "should reject 1 for 2d6 (below min)"),
    ("2d6", [13], False, "should reject 13 for 2d6 (above max)"),
]

print("🎲 FORCE COMMAND VALIDATION TESTS 🎲")
print("=" * 50)

passed = 0
failed = 0

for dice_expr, results, should_pass, description in test_cases:
    is_valid, error_msg = _validate_forced_results(dice_expr, results)

    if is_valid == should_pass:
        print(f"✓ {description}")
        passed += 1
    else:
        print(f"✗ {description}")
        print(f"  Expected: {should_pass}, Got: {is_valid}")
        if error_msg:
            print(f"  Error: {error_msg}")
        failed += 1

print("=" * 50)
print(f"Results: {passed} passed, {failed} failed")

if failed == 0:
    print("🎉 All validation tests passed!")
else:
    print(f"❌ {failed} test(s) failed")
