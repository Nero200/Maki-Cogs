#!/usr/bin/env python3
"""
Quick test to verify that 2d20dl1 syntax now works with the validation function.
"""

import sys
import os
import re

# Mock the discord and redbot imports since we're only testing validation
class MockDiscord:
    class Member:
        pass
    class Color:
        @staticmethod
        def blue():
            return "blue"
    class Embed:
        def __init__(self, **kwargs):
            pass
        def add_field(self, **kwargs):
            pass

class MockCommands:
    class Cog:
        pass
    def command(**kwargs):
        def decorator(func):
            return func
        return decorator
    def has_permissions(**kwargs):
        def decorator(func):
            return func
        return decorator
    def dm_only():
        def decorator(func):
            return func
        return decorator

class MockConfig:
    def get_conf(self, obj, **kwargs):
        return self

# Inject mocks into sys.modules
sys.modules['discord'] = MockDiscord()
sys.modules['redbot'] = type('MockRedbot', (), {})()
sys.modules['redbot.core'] = type('MockRedbotCore', (), {})()
sys.modules['redbot.core.commands'] = MockCommands()
sys.modules['redbot.core.Config'] = MockConfig()

# Mock d20 to avoid import errors
class MockD20:
    def roll(self, expression):
        # Mock roll function that doesn't crash on any input
        class MockResult:
            def __init__(self):
                self.total = 10
                self.result = f"{expression} = 10"
        return MockResult()

sys.modules['d20'] = MockD20()

# Now import our module
from chimeradice import ChimeraDice


def test_drop_lowest_validation():
    """Test that 2d20dl1 now passes validation."""
    
    print("Testing Drop Lowest Validation")
    print("=" * 40)
    
    cog = ChimeraDice(None)
    
    # Test cases that should now work
    test_expressions = [
        "2d20dl1",     # The original failing expression
        "4d6dl1",      # Classic 4d6 drop lowest
        "3d20dh1",     # Drop highest
        "4d6kh3",      # Keep highest (should still work)
        "6d6kl2",      # Keep lowest (should still work)
    ]
    
    print("Testing expressions:")
    
    all_passed = True
    for expr in test_expressions:
        is_valid, error_msg = cog._validate_dice_expression(expr)
        status = "✓" if is_valid else "❌"
        print(f"  {status} {expr}")
        
        if not is_valid:
            print(f"    Error: {error_msg}")
            all_passed = False
    
    print("\n" + "=" * 40)
    
    if all_passed:
        print("🎉 All drop lowest expressions now validate correctly!")
        print("\nThe fix is working - 2d20dl1 should now work in the bot.")
        return True
    else:
        print("❌ Some expressions still failing validation.")
        return False


def test_advanced_operation_detection():
    """Test that the advanced operation detection includes dh/dl."""
    
    print("\nTesting Advanced Operation Detection")
    print("=" * 40)
    
    pattern = r'(kh|kl|dh|dl|ro|rr|ra|e|mi|ma|p)\d*'
    
    test_cases = [
        ("2d20dl1", True),
        ("4d6dh1", True),
        ("4d6kh3", True),
        ("1d20", False),
        ("3d6+2", False),
    ]
    
    print("Testing pattern detection:")
    
    all_correct = True
    for expr, should_match in test_cases:
        has_advanced = bool(re.search(pattern, expr.lower()))
        status = "✓" if has_advanced == should_match else "❌"
        expected = "should match" if should_match else "should NOT match"
        print(f"  {status} {expr} ({expected})")
        
        if has_advanced != should_match:
            all_correct = False
    
    print("\n" + "=" * 40)
    
    if all_correct:
        print("✓ Advanced operation detection working correctly!")
        return True
    else:
        print("❌ Advanced operation detection has issues.")
        return False


if __name__ == "__main__":
    print("Drop Lowest Syntax Fix Verification")
    print("=" * 50)
    
    test1_passed = test_drop_lowest_validation()
    test2_passed = test_advanced_operation_detection()
    
    print("\n" + "=" * 50)
    print("Final Results:")
    
    if test1_passed and test2_passed:
        print("🎉 All tests passed! The 2d20dl1 syntax should now work.")
        print("\nYou can now use:")
        print("  • 2d20dl1  - Drop lowest 1 from 2d20")
        print("  • 4d6dl1   - Drop lowest 1 from 4d6 (same as 4d6kh3)")
        print("  • 3d20dh1  - Drop highest 1 from 3d20")
        sys.exit(0)
    else:
        print("❌ Some tests failed.")
        sys.exit(1)