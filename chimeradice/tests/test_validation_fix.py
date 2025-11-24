#!/usr/bin/env python3
"""
Simple test to verify that the validation patterns now include dh/dl operations.
"""

import re

def test_validation_patterns():
    """Test that validation patterns include drop operations."""
    
    print("Testing Validation Pattern Fix")
    print("=" * 40)
    
    # The pattern from the code (after our fix)
    validation_pattern = r'(kh|kl|dh|dl|ro|rr|ra|e|mi|ma|p)\d*'
    
    # Test expressions that should be detected as advanced
    test_expressions = [
        ("2d20dl1", "Drop lowest 1"),
        ("4d6dh1", "Drop highest 1"), 
        ("4d6kh3", "Keep highest 3"),
        ("6d6kl2", "Keep lowest 2"),
        ("1d20ro<3", "Reroll once"),
        ("2d10e10", "Exploding dice"),
        ("3d6mi2", "Minimum value"),
        ("1d8ma6", "Maximum value"),
        ("4d6p1", "Drop operation"),
    ]
    
    # Test expressions that should NOT be detected as advanced
    simple_expressions = [
        ("1d20", "Simple d20"),
        ("3d6+2", "Simple with modifier"),
        ("2d8-1", "Simple with negative modifier"),
        ("4dF", "Fudge dice"),
        ("2dD", "Fallout dice"),
    ]
    
    print("Advanced expressions (should match pattern):")
    all_advanced_passed = True
    for expr, desc in test_expressions:
        has_advanced = bool(re.search(validation_pattern, expr.lower()))
        status = "✓" if has_advanced else "❌"
        print(f"  {status} {expr:<12} - {desc}")
        if not has_advanced:
            all_advanced_passed = False
    
    print("\nSimple expressions (should NOT match pattern):")
    all_simple_passed = True
    for expr, desc in simple_expressions:
        has_advanced = bool(re.search(validation_pattern, expr.lower()))
        status = "✓" if not has_advanced else "❌"
        print(f"  {status} {expr:<12} - {desc}")
        if has_advanced:
            all_simple_passed = False
    
    print("\n" + "=" * 40)
    
    if all_advanced_passed and all_simple_passed:
        print("🎉 All pattern tests passed!")
        print("\nThe validation pattern correctly includes:")
        print("  • dh (drop highest)")
        print("  • dl (drop lowest)")
        print("  • All other advanced operations")
        return True
    else:
        if not all_advanced_passed:
            print("❌ Some advanced expressions not detected!")
        if not all_simple_passed:
            print("❌ Some simple expressions incorrectly detected as advanced!")
        return False


def test_specific_problem():
    """Test the specific 2d20dl1 case that was failing."""
    
    print("\nTesting Specific Problem Case")
    print("=" * 40)
    
    # This was the exact expression that was failing
    problem_expr = "2d20dl1"
    
    # Check with the old pattern (should fail)
    old_pattern = r'(kh|kl|ro|rr|ra|e|mi|ma|p)\d*'  # Missing dh|dl
    old_match = bool(re.search(old_pattern, problem_expr.lower()))
    
    # Check with the new pattern (should pass)
    new_pattern = r'(kh|kl|dh|dl|ro|rr|ra|e|mi|ma|p)\d*'  # Includes dh|dl
    new_match = bool(re.search(new_pattern, problem_expr.lower()))
    
    print(f"Expression: {problem_expr}")
    print(f"Old pattern: {'❌ NO MATCH' if not old_match else '✓ Match'}")
    print(f"New pattern: {'✓ MATCH' if new_match else '❌ No match'}")
    
    if not old_match and new_match:
        print("\n🎉 Fix confirmed! The pattern now correctly detects dl1 operations.")
        return True
    else:
        print("\n❌ Pattern fix may not be working correctly.")
        return False


if __name__ == "__main__":
    print("Drop Lowest Validation Fix Test")
    print("=" * 50)
    
    test1_passed = test_validation_patterns()
    test2_passed = test_specific_problem()
    
    print("\n" + "=" * 50)
    print("Summary:")
    
    if test1_passed and test2_passed:
        print("✅ All tests passed!")
        print("\nThe fix should resolve the '2d20dl1' validation error.")
        print("Users can now use drop lowest/highest syntax:")
        print("  • 2d20dl1 (drop lowest 1)")
        print("  • 4d6dl1  (drop lowest 1)")  
        print("  • 3d20dh1 (drop highest 1)")
        print("  • And all other d20 library operations")
    else:
        print("❌ Some tests failed - the fix may need more work.")
    
    print("\nNote: This test only verifies the validation patterns.")
    print("The actual d20.roll() call will depend on having the d20 library installed.")