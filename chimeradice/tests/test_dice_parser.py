#!/usr/bin/env python3
"""
Simplified tests for the dice parser functionality that don't require discord.py.
These tests focus on the core dice parsing and mathematical functions.
"""

import unittest
import sys
import os
import re
from datetime import datetime, timedelta

# Add the parent directory to sys.path to import the module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock the discord and redbot imports since we're only testing core logic
class MockDiscord:
    class Member:
        pass
    class Color:
        @staticmethod
        def blue():
            return "blue"
        @staticmethod
        def green():
            return "green"
        @staticmethod
        def red():
            return "red"
        @staticmethod
        def purple():
            return "purple"
    class Embed:
        def __init__(self, **kwargs):
            pass
        def add_field(self, **kwargs):
            pass
    class File:
        def __init__(self, **kwargs):
            pass
    class utils:
        class BytesIO:
            def __init__(self, data):
                pass

class MockCommands:
    class Cog:
        pass
    class Context:
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
    def register_guild(self, **kwargs):
        pass
    def register_user(self, **kwargs):
        pass

# Inject mocks into sys.modules
sys.modules['discord'] = MockDiscord()
sys.modules['redbot'] = type('MockRedbot', (), {})()
sys.modules['redbot.core'] = type('MockRedbotCore', (), {})()
sys.modules['redbot.core.commands'] = MockCommands()
sys.modules['redbot.core.Config'] = MockConfig()

# Now we can import our module
from chimeradice import ChimeraDice, FUDGE_FACES, FALLOUT_FACES


class TestDiceParserCore(unittest.TestCase):
    """Test core dice parsing functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.cog = ChimeraDice(None)
    
    def test_extract_base_dice(self):
        """Test extraction of base dice notation from complex expressions."""
        test_cases = [
            ("4d6kh3", "4d6"),
            ("1d20ro<3+5", "1d20"),
            ("2d10e10mi2", "2d10"),
            ("3d6+2", "3d6"),
            ("1d8", "1d8"),
            ("4dF+2", "4df"),
            ("2dD", "2dd"),
        ]
        
        for expression, expected in test_cases:
            with self.subTest(expression=expression):
                result = self.cog._extract_base_dice(expression)
                self.assertEqual(result.lower(), expected.lower())
    
    def test_parse_dice_modifiers(self):
        """Test parsing dice expressions with multiple modifiers."""
        test_cases = [
            ("4dF+5+2-1", ("4dF", 6)),
            ("1d20+3-2+1", ("1d20", 2)),
            ("4dF", ("4dF", 0)),
            ("2d6-3", ("2d6", -3)),
            ("1d8+10-5+2", ("1d8", 7)),
            ("3d6+2-1+4-3", ("3d6", 2)),
        ]
        
        for expression, expected in test_cases:
            with self.subTest(expression=expression):
                dice_part, modifier = self.cog._parse_dice_modifiers(expression)
                self.assertEqual((dice_part, modifier), expected)
    
    def test_validate_dice_expression_basic(self):
        """Test basic dice expression validation."""
        # Valid expressions (basic ones that don't require d20 library)
        valid_expressions = [
            "4dF+2",
            "2dD",
            "3df-1",
            "1dd+5",
        ]
        
        for expr in valid_expressions:
            with self.subTest(expression=expr):
                is_valid, error_msg = self.cog._validate_dice_expression(expr)
                self.assertTrue(is_valid, f"Expression '{expr}' should be valid but got error: {error_msg}")
        
        # Invalid expressions
        invalid_expressions = [
            ("", "too long"),  # Empty
            ("x" * 200, "too long"),  # Too long
        ]
        
        for expr, expected_error_part in invalid_expressions:
            with self.subTest(expression=expr):
                is_valid, error_msg = self.cog._validate_dice_expression(expr)
                self.assertFalse(is_valid, f"Expression '{expr}' should be invalid")
    
    def test_single_die_percentile(self):
        """Test percentile calculation for single die rolls."""
        test_cases = [
            (1, 20, 2.5),   # 1 on d20 = 2.5th percentile
            (10, 20, 47.5), # 10 on d20 = 47.5th percentile
            (20, 20, 97.5), # 20 on d20 = 97.5th percentile
            (3, 6, 41.67),  # 3 on d6 ≈ 41.67th percentile
            (1, 6, 8.33),   # 1 on d6 ≈ 8.33th percentile
            (6, 6, 91.67),  # 6 on d6 ≈ 91.67th percentile
        ]
        
        for result, die_size, expected in test_cases:
            with self.subTest(result=result, die_size=die_size):
                percentile = self.cog._single_die_percentile(result, die_size)
                self.assertAlmostEqual(percentile, expected, places=1)
    
    def test_multiple_dice_percentile(self):
        """Test percentile calculation for multiple dice."""
        # Test some basic cases
        result = self.cog._multiple_dice_percentile(7, 2, 6)  # 7 on 2d6
        self.assertIsNotNone(result)
        self.assertTrue(0 <= result <= 100)
        
        # Test edge cases
        result = self.cog._multiple_dice_percentile(2, 2, 6)  # Minimum on 2d6
        self.assertAlmostEqual(result, 0, places=1)
        
        result = self.cog._multiple_dice_percentile(12, 2, 6)  # Maximum on 2d6
        self.assertAlmostEqual(result, 100, places=1)
        
        # Test that percentiles increase with results
        percentile_low = self.cog._multiple_dice_percentile(3, 2, 6)
        percentile_mid = self.cog._multiple_dice_percentile(7, 2, 6)
        percentile_high = self.cog._multiple_dice_percentile(11, 2, 6)
        
        self.assertLess(percentile_low, percentile_mid)
        self.assertLess(percentile_mid, percentile_high)
    
    def test_calculate_fudge_percentile(self):
        """Test percentile calculation for fudge dice."""
        test_cases = [
            ("4dF", 0, 50),   # 0 on 4dF should be around median
            ("4dF", 4, 90),   # +4 on 4dF should be very high
            ("4dF", -4, 10),  # -4 on 4dF should be very low
            ("2dF", 0, 50),   # 0 on 2dF should be around median
        ]
        
        for roll_string, result, expected_range in test_cases:
            with self.subTest(roll_string=roll_string, result=result):
                percentile = self.cog._calculate_fudge_percentile(roll_string, result)
                self.assertIsNotNone(percentile)
                # Allow some tolerance for approximation
                if expected_range == 50:
                    self.assertAlmostEqual(percentile, expected_range, delta=15)
                elif expected_range in [10, 90]:
                    self.assertTrue(abs(percentile - expected_range) <= 25)
    
    def test_generate_fudge_dice_for_sum(self):
        """Test fudge dice generation for specific sums."""
        # Test various target sums
        for num_dice in range(2, 6):
            for target in range(-num_dice, num_dice + 1):
                with self.subTest(num_dice=num_dice, target=target):
                    dice = self.cog._generate_fudge_dice_for_sum(num_dice, target)
                    
                    self.assertEqual(len(dice), num_dice)
                    self.assertEqual(sum(dice), target)
                    
                    # Check all dice are valid fudge faces
                    for die in dice:
                        self.assertIn(die, FUDGE_FACES)
    
    def test_estimate_keep_percentile(self):
        """Test percentile estimation for keep operations."""
        # Keep highest should bias toward higher percentiles
        percentile_kh = self.cog._estimate_keep_percentile("4d6kh3", 15, 4, 6)
        self.assertIsNotNone(percentile_kh)
        self.assertTrue(0 <= percentile_kh <= 100)
        
        # Keep lowest should bias toward lower percentiles
        percentile_kl = self.cog._estimate_keep_percentile("4d6kl3", 6, 4, 6)
        self.assertIsNotNone(percentile_kl)
        self.assertTrue(0 <= percentile_kl <= 100)
        
        # Test edge cases
        percentile_max = self.cog._estimate_keep_percentile("4d6kh3", 18, 4, 6)  # Max result
        self.assertGreater(percentile_max, 80)
        
        percentile_min = self.cog._estimate_keep_percentile("4d6kl3", 3, 4, 6)   # Min result  
        self.assertLess(percentile_min, 20)
    
    def test_cleanup_expired_forced_rolls(self):
        """Test cleanup of expired forced rolls."""
        # Setup test data with expired and non-expired rolls
        current_time = datetime.now()
        expired_time = current_time - timedelta(hours=13)  # 13 hours ago
        recent_time = current_time - timedelta(hours=1)    # 1 hour ago
        
        self.cog.forced_rolls = {
            123: {
                "1d20": {
                    "values": [15],
                    "timestamp": expired_time
                },
                "1d6": {
                    "values": [4],
                    "timestamp": recent_time
                }
            },
            456: {
                "2d6": {
                    "values": [8],
                    "timestamp": expired_time
                }
            }
        }
        
        self.cog._cleanup_expired_forced_rolls()
        
        # Only recent rolls should remain
        self.assertIn(123, self.cog.forced_rolls)
        self.assertIn("1d6", self.cog.forced_rolls[123])
        self.assertNotIn("1d20", self.cog.forced_rolls[123])
        self.assertNotIn(456, self.cog.forced_rolls)
    
    def test_percentile_ordering(self):
        """Test that percentiles maintain proper ordering."""
        # Test single die ordering
        d20_percentiles = []
        for i in range(1, 21):
            percentile = self.cog._single_die_percentile(i, 20)
            d20_percentiles.append(percentile)
        
        # Percentiles should be in ascending order
        for i in range(1, len(d20_percentiles)):
            self.assertGreaterEqual(d20_percentiles[i], d20_percentiles[i-1])
        
        # Test multiple dice ordering (sample points)
        results_2d6 = [2, 4, 7, 10, 12]  # Min, low, average, high, max
        percentiles_2d6 = []
        
        for result in results_2d6:
            percentile = self.cog._multiple_dice_percentile(result, 2, 6)
            percentiles_2d6.append(percentile)
        
        # Should be in ascending order
        for i in range(1, len(percentiles_2d6)):
            self.assertGreaterEqual(percentiles_2d6[i], percentiles_2d6[i-1])


class TestAdvancedDiceOperations(unittest.TestCase):
    """Test advanced dice operation detection and parsing."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.cog = ChimeraDice(None)
    
    def test_advanced_operation_detection(self):
        """Test detection of advanced d20 operations."""
        # Expressions with advanced operations
        advanced_expressions = [
            "4d6kh3",
            "1d20ro<3",
            "2d10e10",
            "3d6mi2",
            "1d8ma6",
            "4d6p1",
            "1d20rr<5",
            "2d6ra1",
        ]
        
        # Simple expressions without advanced operations
        simple_expressions = [
            "1d20",
            "3d6+2",
            "2d8-1",
            "4dF+3",
            "1dD",
        ]
        
        import re
        advanced_pattern = r'(kh|kl|ro|rr|ra|e|mi|ma|p)\d*'
        
        for expr in advanced_expressions:
            with self.subTest(expression=expr):
                has_advanced = bool(re.search(advanced_pattern, expr.lower()))
                self.assertTrue(has_advanced, f"Should detect advanced operations in '{expr}'")
        
        for expr in simple_expressions:
            with self.subTest(expression=expr):
                has_advanced = bool(re.search(advanced_pattern, expr.lower()))
                self.assertFalse(has_advanced, f"Should not detect advanced operations in '{expr}'")
    
    def test_keep_operation_parsing(self):
        """Test parsing of keep operations."""
        import re
        
        # Test keep highest parsing
        kh_expressions = [
            ("4d6kh3", 3),
            ("6d6kh4", 4),
            ("8d6kh1", 1),
        ]
        
        for expr, expected_keep in kh_expressions:
            with self.subTest(expression=expr):
                match = re.search(r'kh(\d+)', expr.lower())
                self.assertIsNotNone(match)
                self.assertEqual(int(match.group(1)), expected_keep)
        
        # Test keep lowest parsing
        kl_expressions = [
            ("4d6kl1", 1),
            ("6d6kl2", 2),
            ("8d6kl3", 3),
        ]
        
        for expr, expected_keep in kl_expressions:
            with self.subTest(expression=expr):
                match = re.search(r'kl(\d+)', expr.lower())
                self.assertIsNotNone(match)
                self.assertEqual(int(match.group(1)), expected_keep)


def run_core_tests():
    """Run the core dice parser tests."""
    print("=" * 60)
    print("ChimeraDice Core Functionality Tests")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Load tests
    suite.addTests(loader.loadTestsFromTestCase(TestDiceParserCore))
    suite.addTests(loader.loadTestsFromTestCase(TestAdvancedDiceOperations))
    
    # Run the tests
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout,
        descriptions=True
    )
    
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    
    print(f"Total tests run: {total_tests}")
    print(f"Failures: {failures}")
    print(f"Errors: {errors}")
    print(f"Success rate: {((total_tests - failures - errors) / total_tests * 100):.1f}%" if total_tests > 0 else "N/A")
    
    if result.wasSuccessful():
        print("\n🎉 All core tests passed!")
        return True
    else:
        print("\n❌ Some tests failed!")
        
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}")
                print(f"    {traceback.split('AssertionError:')[-1].strip()}")
        
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}")
                print(f"    {traceback.split('Exception:')[-1].strip()}")
        
        return False


if __name__ == "__main__":
    success = run_core_tests()
    sys.exit(0 if success else 1)