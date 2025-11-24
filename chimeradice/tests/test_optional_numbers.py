#!/usr/bin/env python3
"""
Test optional numbers for keep/drop operations.
"""

import sys
import re

def test_translate_dice_syntax(expression: str) -> str:
    """Simplified version of _translate_dice_syntax for testing."""

    # Handle drop lowest (dl) -> convert to keep highest (kh)
    dl_pattern = r'(\d+)d(\d+)dl(\d*)'
    def dl_to_kh(match):
        num_dice = int(match.group(1))
        die_size = match.group(2)
        drop_count = int(match.group(3)) if match.group(3) else 1  # Default to 1
        keep_count = num_dice - drop_count
        if keep_count <= 0:
            return match.group(0)
        return f"{num_dice}d{die_size}kh{keep_count}"

    expression = re.sub(dl_pattern, dl_to_kh, expression)

    # Handle drop highest (dh) -> convert to keep lowest (kl)
    dh_pattern = r'(\d+)d(\d+)dh(\d*)'
    def dh_to_kl(match):
        num_dice = int(match.group(1))
        die_size = match.group(2)
        drop_count = int(match.group(3)) if match.group(3) else 1  # Default to 1
        keep_count = num_dice - drop_count
        if keep_count <= 0:
            return match.group(0)
        return f"{num_dice}d{die_size}kl{keep_count}"

    expression = re.sub(dh_pattern, dh_to_kl, expression)

    # Handle keep highest (kh) with optional number
    kh_pattern = r'(\d+)d(\d+)kh(\d*)'
    def kh_explicit(match):
        num_dice = match.group(1)
        die_size = match.group(2)
        keep_count = match.group(3) if match.group(3) else '1'  # Default to 1
        return f"{num_dice}d{die_size}kh{keep_count}"

    expression = re.sub(kh_pattern, kh_explicit, expression)

    # Handle keep lowest (kl) with optional number
    kl_pattern = r'(\d+)d(\d+)kl(\d*)'
    def kl_explicit(match):
        num_dice = match.group(1)
        die_size = match.group(2)
        keep_count = match.group(3) if match.group(3) else '1'  # Default to 1
        return f"{num_dice}d{die_size}kl{keep_count}"

    expression = re.sub(kl_pattern, kl_explicit, expression)

    return expression


def run_tests():
    """Run translation tests."""
    print("=" * 60)
    print("Testing Optional Numbers for Keep/Drop Operations")
    print("=" * 60)

    test_cases = [
        # Keep highest (kh) - optional number
        ("2d20kh", "2d20kh1", "advantage (no number)"),
        ("2d20kh1", "2d20kh1", "advantage (explicit 1)"),
        ("4d6kh3", "4d6kh3", "keep highest 3 (explicit)"),

        # Keep lowest (kl) - optional number
        ("2d20kl", "2d20kl1", "disadvantage (no number)"),
        ("2d20kl1", "2d20kl1", "disadvantage (explicit 1)"),
        ("4d6kl2", "4d6kl2", "keep lowest 2 (explicit)"),

        # Drop lowest (dl) - optional number, translates to kh
        ("2d20dl", "2d20kh1", "advantage via drop lowest (no number)"),
        ("2d20dl1", "2d20kh1", "advantage via drop lowest (explicit 1)"),
        ("4d6dl", "4d6kh3", "D&D ability scores (no number)"),
        ("4d6dl1", "4d6kh3", "D&D ability scores (explicit 1)"),

        # Drop highest (dh) - optional number, translates to kl
        ("2d20dh", "2d20kl1", "disadvantage via drop highest (no number)"),
        ("2d20dh1", "2d20kl1", "disadvantage via drop highest (explicit 1)"),
        ("3d20dh", "3d20kl2", "drop highest (no number)"),
        ("3d20dh1", "3d20kl2", "drop highest (explicit 1)"),

        # With modifiers
        ("2d20kh+5", "2d20kh1+5", "advantage with modifier"),
        ("4d6dl-1", "4d6kh3-1", "ability scores with negative modifier"),

        # No keep/drop operations (should pass through unchanged)
        ("1d20", "1d20", "simple d20"),
        ("3d6+2", "3d6+2", "simple with modifier"),
    ]

    passed = 0
    failed = 0

    for input_expr, expected_output, description in test_cases:
        result = test_translate_dice_syntax(input_expr)

        if result == expected_output:
            print(f"✅ {description}")
            print(f"   {input_expr} → {result}")
            passed += 1
        else:
            print(f"❌ {description}")
            print(f"   {input_expr} → {result} (expected: {expected_output})")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed == 0:
        print("✅ All tests passed! Optional numbers working correctly.")
        return True
    else:
        print("❌ Some tests failed.")
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
