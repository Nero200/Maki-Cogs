#!/usr/bin/env python3
"""
Test the dice syntax translation function.
"""

import re

def _translate_dice_syntax(expression: str) -> str:
    """Translate user-friendly dice syntax to d20 library syntax."""
    import re
    
    # Handle drop lowest (dl) -> convert to keep highest (kh)
    dl_pattern = r'(\d+)d(\d+)dl(\d+)'
    def dl_to_kh(match):
        num_dice = int(match.group(1))
        die_size = match.group(2)
        drop_count = int(match.group(3))
        keep_count = num_dice - drop_count
        if keep_count <= 0:
            # Can't drop more dice than we have, fall back to original
            return match.group(0)
        return f"{num_dice}d{die_size}kh{keep_count}"
    
    expression = re.sub(dl_pattern, dl_to_kh, expression)
    
    # Handle drop highest (dh) -> convert to keep lowest (kl)
    dh_pattern = r'(\d+)d(\d+)dh(\d+)'
    def dh_to_kl(match):
        num_dice = int(match.group(1))
        die_size = match.group(2)
        drop_count = int(match.group(3))
        keep_count = num_dice - drop_count
        if keep_count <= 0:
            # Can't drop more dice than we have, fall back to original
            return match.group(0)
        return f"{num_dice}d{die_size}kl{keep_count}"
    
    expression = re.sub(dh_pattern, dh_to_kl, expression)
    
    return expression

def test_translation():
    """Test the translation function."""
    
    print("Testing Dice Syntax Translation")
    print("=" * 40)
    
    test_cases = [
        # Drop lowest cases
        ("2d20dl1", "2d20kh1", "Drop lowest 1 from 2d20 = keep highest 1"),
        ("4d6dl1", "4d6kh3", "Drop lowest 1 from 4d6 = keep highest 3"),
        ("6d6dl2", "6d6kh4", "Drop lowest 2 from 6d6 = keep highest 4"),
        
        # Drop highest cases
        ("3d20dh1", "3d20kl2", "Drop highest 1 from 3d20 = keep lowest 2"),
        ("5d8dh2", "5d8kl3", "Drop highest 2 from 5d8 = keep lowest 3"),
        
        # Edge cases
        ("2d6dl2", "2d6dl2", "Can't drop all dice - should remain unchanged"),
        ("1d20dl1", "1d20dl1", "Can't drop from single die - should remain unchanged"),
        
        # Should not change (already valid d20 syntax)
        ("4d6kh3", "4d6kh3", "Already valid - should not change"),
        ("1d20", "1d20", "Simple roll - should not change"),
        ("2d10+5", "2d10+5", "With modifier - should not change"),
        ("1d20ro<3", "1d20ro<3", "Reroll syntax - should not change"),
    ]
    
    print("Translation tests:")
    all_passed = True
    
    for input_expr, expected, description in test_cases:
        result = _translate_dice_syntax(input_expr)
        status = "✓" if result == expected else "❌"
        print(f"  {status} {input_expr:<12} -> {result:<12} ({description})")
        
        if result != expected:
            print(f"      Expected: {expected}")
            all_passed = False
    
    print("\n" + "=" * 40)
    
    if all_passed:
        print("🎉 All translation tests passed!")
        print("\nKey translations:")
        print("  • 2d20dl1 -> 2d20kh1 (drop lowest = keep highest)")
        print("  • 4d6dl1 -> 4d6kh3 (classic D&D ability scores)")
        print("  • 3d20dh1 -> 3d20kl2 (drop highest = keep lowest)")
        return True
    else:
        print("❌ Some translation tests failed!")
        return False

def test_specific_case():
    """Test the specific failing case."""
    
    print("\nTesting Specific Problem Case")
    print("=" * 40)
    
    problem_input = "2d20dl1"
    expected_output = "2d20kh1"
    
    result = _translate_dice_syntax(problem_input)
    
    print(f"Input:  {problem_input}")
    print(f"Output: {result}")
    print(f"Expected: {expected_output}")
    
    if result == expected_output:
        print("\n✅ Translation successful!")
        print("The user's '2d20dl1' will be converted to '2d20kh1'")
        print("which the d20 library should accept.")
        return True
    else:
        print("\n❌ Translation failed!")
        return False

if __name__ == "__main__":
    print("Dice Syntax Translation Test")
    print("=" * 50)
    
    test1_passed = test_translation()
    test2_passed = test_specific_case()
    
    print("\n" + "=" * 50)
    print("Summary:")
    
    if test1_passed and test2_passed:
        print("✅ Translation function working correctly!")
        print("\nThis should fix the '2d20dl1' error by converting it to")
        print("'2d20kh1' which the d20 library supports.")
    else:
        print("❌ Translation function needs more work.")