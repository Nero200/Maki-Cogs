"""
Property-based tests for ChimeraDice cog using hypothesis library.

These tests generate random inputs and verify that the code behaves correctly
across a wide range of possible inputs.

To run these tests, you need to install hypothesis:
pip install hypothesis
"""

import unittest
import sys
import os
from unittest.mock import Mock, AsyncMock
import re
from datetime import datetime, timedelta

try:
    from hypothesis import given, strategies as st, assume, settings
    from hypothesis.stateful import RuleBasedStateMachine, Bundle, rule, multiple
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    print("Hypothesis not available. Install with: pip install hypothesis")

# Add the parent directory to sys.path to import the module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chimeradice import ChimeraDice, DEFAULT_GUILD_USER, FUDGE_FACES, FALLOUT_FACES


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestChimeraDiceProperties(unittest.TestCase):
    """Property-based tests for ChimeraDice functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.bot = Mock()
        self.cog = ChimeraDice(self.bot)
    
    @given(st.integers(min_value=1, max_value=1000), st.integers(min_value=1, max_value=1000))
    def test_single_die_percentile_properties(self, result, die_size):
        """Test properties of single die percentile calculation."""
        assume(1 <= result <= die_size)  # Only test valid results
        
        percentile = self.cog._single_die_percentile(result, die_size)
        
        # Property: percentile should always be between 0 and 100
        self.assertTrue(0 <= percentile <= 100)
        
        # Property: result of 1 should give lowest percentile
        if result == 1:
            self.assertLessEqual(percentile, 100/die_size)
        
        # Property: result of max should give highest percentile
        if result == die_size:
            self.assertGreaterEqual(percentile, 100 - 100/die_size)
        
        # Property: higher results should generally give higher percentiles
        if result < die_size:
            higher_percentile = self.cog._single_die_percentile(result + 1, die_size)
            self.assertGreaterEqual(higher_percentile, percentile)
    
    @given(st.integers(min_value=1, max_value=100), st.integers(min_value=2, max_value=100))
    def test_multiple_dice_percentile_properties(self, num_dice, die_size):
        """Test properties of multiple dice percentile calculation."""
        min_result = num_dice
        max_result = num_dice * die_size
        
        # Test minimum result
        min_percentile = self.cog._multiple_dice_percentile(min_result, num_dice, die_size)
        self.assertLessEqual(min_percentile, 5)  # Should be very low
        
        # Test maximum result
        max_percentile = self.cog._multiple_dice_percentile(max_result, num_dice, die_size)
        self.assertGreaterEqual(max_percentile, 95)  # Should be very high
        
        # Test a middle result
        mid_result = (min_result + max_result) // 2
        mid_percentile = self.cog._multiple_dice_percentile(mid_result, num_dice, die_size)
        self.assertTrue(0 <= mid_percentile <= 100)
    
    @given(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    def test_extract_base_dice_robustness(self, random_text):
        """Test that _extract_base_dice doesn't crash on random input."""
        try:
            result = self.cog._extract_base_dice(random_text)
            # Should always return a string
            self.assertIsInstance(result, str)
        except Exception as e:
            # If it does raise an exception, it should be a reasonable one
            self.assertIsInstance(e, (ValueError, AttributeError, TypeError))
    
    @given(st.integers(min_value=1, max_value=10), st.integers(min_value=-10, max_value=10))
    def test_fudge_dice_generation_properties(self, num_dice, target_sum):
        """Test properties of fudge dice generation."""
        # Clamp target to valid range
        actual_target = max(-num_dice, min(num_dice, target_sum))
        
        dice = self.cog._generate_fudge_dice_for_sum(num_dice, actual_target)
        
        # Property: should generate exactly num_dice dice
        self.assertEqual(len(dice), num_dice)
        
        # Property: all dice should be valid fudge faces
        for die in dice:
            self.assertIn(die, FUDGE_FACES)
        
        # Property: sum should equal the (clamped) target
        self.assertEqual(sum(dice), actual_target)
    
    @given(st.text(min_size=1, max_size=50, alphabet="0123456789+-d "))
    def test_parse_dice_modifiers_robustness(self, expression):
        """Test that _parse_dice_modifiers doesn't crash on various inputs."""
        try:
            dice_part, modifier = self.cog._parse_dice_modifiers(expression)
            
            # Property: should always return a string and an integer
            self.assertIsInstance(dice_part, str)
            self.assertIsInstance(modifier, int)
            
            # Property: dice_part should be non-empty if expression is non-empty
            if expression.strip():
                self.assertTrue(len(dice_part) > 0)
                
        except Exception as e:
            # If it does raise an exception, it should be a reasonable one
            self.assertIsInstance(e, (ValueError, AttributeError, TypeError))
    
    @given(st.integers(min_value=1, max_value=6), st.integers(min_value=-6, max_value=6))
    def test_fudge_percentile_properties(self, num_dice, result):
        """Test properties of fudge dice percentile calculation."""
        # Only test valid results
        assume(-num_dice <= result <= num_dice)
        
        roll_string = f"{num_dice}dF"
        percentile = self.cog._calculate_fudge_percentile(roll_string, result)
        
        if percentile is not None:
            # Property: percentile should be between 0 and 100
            self.assertTrue(0 <= percentile <= 100)
            
            # Property: result of 0 should be near the median
            if result == 0:
                self.assertTrue(40 <= percentile <= 60)
            
            # Property: extreme results should have extreme percentiles
            if result == num_dice:  # Maximum positive
                self.assertGreater(percentile, 80)
            if result == -num_dice:  # Maximum negative
                self.assertLess(percentile, 20)
    
    @given(st.lists(st.integers(min_value=1, max_value=20), min_size=1, max_size=10))
    def test_forced_rolls_cleanup_properties(self, forced_values):
        """Test properties of forced rolls cleanup."""
        current_time = datetime.now()
        
        # Create test data with various timestamps
        self.cog.forced_rolls = {}
        for i, value in enumerate(forced_values):
            user_id = 1000 + i
            # Some recent, some expired
            if i % 2 == 0:
                timestamp = current_time - timedelta(hours=1)  # Recent
            else:
                timestamp = current_time - timedelta(hours=13)  # Expired
            
            self.cog.forced_rolls[user_id] = {
                "1d20": {
                    "values": [value],
                    "timestamp": timestamp
                }
            }
        
        initial_count = len(self.cog.forced_rolls)
        self.cog._cleanup_expired_forced_rolls()
        final_count = len(self.cog.forced_rolls)
        
        # Property: cleanup should reduce or maintain the count
        self.assertLessEqual(final_count, initial_count)
        
        # Property: all remaining entries should be recent
        for user_id, user_rolls in self.cog.forced_rolls.items():
            for dice_expr, data in user_rolls.items():
                if isinstance(data, dict) and "timestamp" in data:
                    time_diff = current_time - data["timestamp"]
                    self.assertLess(time_diff, timedelta(hours=12))
    
    @given(st.text(min_size=1, max_size=100))
    def test_validation_robustness(self, expression):
        """Test that validation doesn't crash on any input."""
        try:
            is_valid, error_msg = self.cog._validate_dice_expression(expression)
            
            # Property: should always return a boolean and a string
            self.assertIsInstance(is_valid, bool)
            self.assertIsInstance(error_msg, str)
            
            # Property: if invalid, should have a non-empty error message
            if not is_valid:
                self.assertTrue(len(error_msg) > 0)
            
        except Exception as e:
            # Should not crash - if it does, that's a bug
            self.fail(f"Validation crashed on input '{expression}': {e}")


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class DiceStateMachine(RuleBasedStateMachine):
    """Stateful testing for dice rolling operations."""
    
    def __init__(self):
        super().__init__()
        self.bot = Mock()
        self.cog = ChimeraDice(self.bot)
        self.forced_rolls_count = 0
    
    expressions = Bundle('expressions')
    
    @rule(target=expressions, 
          num_dice=st.integers(min_value=1, max_value=10),
          die_size=st.integers(min_value=2, max_value=20))
    def generate_simple_expression(self, num_dice, die_size):
        """Generate simple dice expressions."""
        return f"{num_dice}d{die_size}"
    
    @rule(target=expressions,
          base_expr=expressions,
          modifier=st.integers(min_value=-10, max_value=10))
    def add_modifier(self, base_expr, modifier):
        """Add modifiers to existing expressions."""
        if modifier >= 0:
            return f"{base_expr}+{modifier}"
        else:
            return f"{base_expr}{modifier}"
    
    @rule(expr=expressions)
    def test_validation_consistency(self, expr):
        """Test that validation is consistent."""
        # Run validation multiple times - should get same result
        result1 = self.cog._validate_dice_expression(expr)
        result2 = self.cog._validate_dice_expression(expr)
        assert result1 == result2, f"Validation inconsistent for '{expr}'"
    
    @rule(expr=expressions)
    def test_base_dice_extraction(self, expr):
        """Test base dice extraction properties."""
        try:
            base = self.cog._extract_base_dice(expr)
            
            # Property: base should be a substring of the original
            # (might not be true for all cases, but generally should be)
            if 'd' in expr:
                assert 'd' in base, f"Base '{base}' should contain 'd' if original '{expr}' does"
                
        except Exception:
            # Some malformed expressions might fail - that's OK
            pass
    
    @rule(user_id=st.integers(min_value=1, max_value=1000),
          dice_expr=expressions,
          value=st.integers(min_value=1, max_value=20))
    def add_forced_roll(self, user_id, dice_expr, value):
        """Add a forced roll to the system."""
        if user_id not in self.cog.forced_rolls:
            self.cog.forced_rolls[user_id] = {}
        
        self.cog.forced_rolls[user_id][dice_expr] = {
            "values": [value],
            "timestamp": datetime.now()
        }
        self.forced_rolls_count += 1
    
    @rule()
    def cleanup_forced_rolls(self):
        """Clean up expired forced rolls."""
        initial_count = sum(len(user_rolls) for user_rolls in self.cog.forced_rolls.values())
        self.cog._cleanup_expired_forced_rolls()
        final_count = sum(len(user_rolls) for user_rolls in self.cog.forced_rolls.values())
        
        # Property: cleanup should not increase the count
        assert final_count <= initial_count, "Cleanup should not increase forced rolls count"


# Create the test case for the state machine
TestDiceStateMachine = DiceStateMachine.TestCase


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestPercentileConsistency(unittest.TestCase):
    """Test consistency of percentile calculations."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.bot = Mock()
        self.cog = ChimeraDice(self.bot)
    
    @given(st.integers(min_value=1, max_value=20))
    def test_percentile_ordering_single_die(self, die_size):
        """Test that percentiles are ordered correctly for single dice."""
        percentiles = []
        
        for result in range(1, die_size + 1):
            percentile = self.cog._single_die_percentile(result, die_size)
            percentiles.append(percentile)
        
        # Property: percentiles should be non-decreasing
        for i in range(1, len(percentiles)):
            self.assertGreaterEqual(
                percentiles[i], percentiles[i-1],
                f"Percentiles not ordered: {percentiles[i-1]} > {percentiles[i]} for results {i} and {i+1} on d{die_size}"
            )
    
    @given(st.integers(min_value=2, max_value=6), st.integers(min_value=2, max_value=6))
    def test_percentile_ordering_multiple_dice(self, num_dice, die_size):
        """Test percentile ordering for multiple dice (sampling approach)."""
        min_result = num_dice
        max_result = num_dice * die_size
        
        # Sample some results to test ordering
        sample_results = [
            min_result,
            min_result + 1,
            (min_result + max_result) // 2,
            max_result - 1,
            max_result
        ]
        
        percentiles = []
        for result in sample_results:
            percentile = self.cog._multiple_dice_percentile(result, num_dice, die_size)
            percentiles.append(percentile)
        
        # Property: percentiles should be non-decreasing
        for i in range(1, len(percentiles)):
            self.assertGreaterEqual(
                percentiles[i], percentiles[i-1],
                f"Percentiles not ordered for {num_dice}d{die_size}"
            )


if __name__ == "__main__":
    if HYPOTHESIS_AVAILABLE:
        # Run property-based tests with custom settings
        unittest.main()
    else:
        print("Hypothesis library not available. Install with: pip install hypothesis")
        print("Skipping property-based tests.")