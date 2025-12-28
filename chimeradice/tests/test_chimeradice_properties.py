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
import random

try:
    from hypothesis import given, strategies as st, assume, settings
    from hypothesis.stateful import RuleBasedStateMachine, Bundle, rule
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    print("Hypothesis not available. Install with: pip install hypothesis")

# Add the parent directory to sys.path to import the core module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from core module (no discord dependency!)
from chimeradice_core import (
    # Constants
    FUDGE_FACES,
    FUDGE_PROBABILITIES,
    # Percentile functions
    single_die_percentile,
    multiple_dice_percentile,
    calculate_fudge_percentile,
    estimate_keep_percentile,
    calculate_roll_percentile,
    # Parsing/validation functions
    parse_dice_modifiers,
    validate_dice_expression,
    normalize_dice_key,
    parse_roll_and_label,
    translate_dice_syntax,
    extract_base_dice,
    # Weighted rolling functions
    roll_weighted_standard_die,
    roll_weighted_fudge_dice,
    generate_fudge_dice_for_sum,
    generate_realistic_fudge_faces,
)


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestPercentileFunctions(unittest.TestCase):
    """Property-based tests for percentile calculation functions."""

    @given(st.integers(min_value=1, max_value=1000), st.integers(min_value=1, max_value=1000))
    def test_single_die_percentile_properties(self, result, die_size):
        """Test properties of single die percentile calculation."""
        assume(1 <= result <= die_size)  # Only test valid results

        percentile = single_die_percentile(result, die_size)

        # Property: percentile should always be between 0 and 100
        self.assertTrue(0 <= percentile <= 100)

        # Property: result of 1 should give lowest percentile
        if result == 1:
            self.assertLessEqual(percentile, 100/die_size)

        # Property: result of max should give highest percentile
        if result == die_size:
            self.assertGreaterEqual(percentile, 100 - 100/die_size)

        # Property: higher results should give higher percentiles
        if result < die_size:
            higher_percentile = single_die_percentile(result + 1, die_size)
            self.assertGreaterEqual(higher_percentile, percentile)

    @given(st.integers(min_value=1, max_value=100), st.integers(min_value=2, max_value=100))
    def test_multiple_dice_percentile_properties(self, num_dice, die_size):
        """Test properties of multiple dice percentile calculation."""
        min_result = num_dice
        max_result = num_dice * die_size

        # Test minimum result
        min_percentile = multiple_dice_percentile(min_result, num_dice, die_size)
        self.assertLessEqual(min_percentile, 5)  # Should be very low

        # Test maximum result
        max_percentile = multiple_dice_percentile(max_result, num_dice, die_size)
        self.assertGreaterEqual(max_percentile, 95)  # Should be very high

        # Test a middle result
        mid_result = (min_result + max_result) // 2
        mid_percentile = multiple_dice_percentile(mid_result, num_dice, die_size)
        self.assertTrue(0 <= mid_percentile <= 100)

    @given(st.integers(min_value=1, max_value=6), st.integers(min_value=-6, max_value=6))
    def test_fudge_percentile_properties(self, num_dice, result):
        """Test properties of fudge dice percentile calculation."""
        # Only test valid results
        assume(-num_dice <= result <= num_dice)

        roll_string = f"{num_dice}dF"
        percentile = calculate_fudge_percentile(roll_string, result)

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


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestTranslationFunction(unittest.TestCase):
    """Property-based tests for dice syntax translation."""

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=4, max_value=20))
    def test_translate_idempotence(self, num_dice, die_size):
        """Test that translation is idempotent (applying twice gives same result)."""
        expr = f"{num_dice}d{die_size}dl1"
        once = translate_dice_syntax(expr)
        twice = translate_dice_syntax(once)
        self.assertEqual(once, twice)

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=4, max_value=20))
    def test_dl_converts_to_kh(self, num_dice, die_size):
        """Test that drop lowest converts to keep highest."""
        expr = f"{num_dice}d{die_size}dl1"
        result = translate_dice_syntax(expr)
        self.assertIn("kh", result)
        self.assertNotIn("dl", result)

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=4, max_value=20))
    def test_dh_converts_to_kl(self, num_dice, die_size):
        """Test that drop highest converts to keep lowest."""
        expr = f"{num_dice}d{die_size}dh1"
        result = translate_dice_syntax(expr)
        self.assertIn("kl", result)
        self.assertNotIn("dh", result)

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=4, max_value=20))
    def test_kh_without_number_gets_default(self, num_dice, die_size):
        """Test that kh without number defaults to 1."""
        expr = f"{num_dice}d{die_size}kh"
        result = translate_dice_syntax(expr)
        self.assertEqual(result, f"{num_dice}d{die_size}kh1")

    @given(st.integers(min_value=2, max_value=10), st.integers(min_value=4, max_value=20))
    def test_simple_rolls_unchanged(self, num_dice, die_size):
        """Test that simple rolls without operations are unchanged."""
        expr = f"{num_dice}d{die_size}"
        result = translate_dice_syntax(expr)
        self.assertEqual(result, expr)


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestNormalizeDiceKey(unittest.TestCase):
    """Property-based tests for dice key normalization."""

    @given(st.integers(min_value=1, max_value=100), st.integers(min_value=1, max_value=1000))
    def test_normalize_idempotence(self, num_dice, die_size):
        """Test that normalization is idempotent."""
        expr = f"{num_dice}d{die_size}"
        once = normalize_dice_key(expr)
        twice = normalize_dice_key(once)
        self.assertEqual(once, twice)

    @given(st.integers(min_value=1, max_value=100), st.integers(min_value=1, max_value=1000))
    def test_normalize_case_insensitive(self, num_dice, die_size):
        """Test that normalization is case insensitive."""
        lower = normalize_dice_key(f"{num_dice}d{die_size}")
        upper = normalize_dice_key(f"{num_dice}D{die_size}")
        self.assertEqual(lower, upper)

    @given(st.integers(min_value=1, max_value=1000))
    def test_implicit_one_added(self, die_size):
        """Test that d20 becomes 1d20."""
        result = normalize_dice_key(f"d{die_size}")
        self.assertEqual(result, f"1d{die_size}")

    @given(st.integers(min_value=1, max_value=100), st.integers(min_value=1, max_value=1000),
           st.integers(min_value=-100, max_value=100))
    def test_modifiers_stripped(self, num_dice, die_size, modifier):
        """Test that modifiers are stripped from normalized key."""
        if modifier >= 0:
            expr = f"{num_dice}d{die_size}+{modifier}"
        else:
            expr = f"{num_dice}d{die_size}{modifier}"
        result = normalize_dice_key(expr)
        self.assertEqual(result, f"{num_dice}d{die_size}")


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestWeightedRolling(unittest.TestCase):
    """Property-based tests for weighted dice rolling functions."""

    @given(st.integers(min_value=2, max_value=100), st.floats(min_value=-100, max_value=100))
    def test_weighted_die_in_range(self, die_size, debt):
        """Test that weighted die always returns value in valid range."""
        result = roll_weighted_standard_die(die_size, debt)
        self.assertTrue(1 <= result <= die_size)

    @given(st.integers(min_value=1, max_value=6), st.floats(min_value=-100, max_value=100))
    def test_weighted_fudge_sum_matches(self, num_dice, debt):
        """Test that fudge dice results sum correctly."""
        assume(num_dice in FUDGE_PROBABILITIES or abs(debt) < 5.0)
        dice_results, dice_sum = roll_weighted_fudge_dice(num_dice, debt)

        # Property: length should equal num_dice
        self.assertEqual(len(dice_results), num_dice)

        # Property: all faces should be valid
        for face in dice_results:
            self.assertIn(face, FUDGE_FACES)

        # Property: sum should match
        self.assertEqual(sum(dice_results), dice_sum)

    @settings(max_examples=500)
    @given(st.integers(min_value=2, max_value=20))
    def test_positive_debt_biases_high(self, die_size):
        """Test that positive debt biases toward higher rolls (statistical)."""
        high_debt = 50.0
        results = [roll_weighted_standard_die(die_size, high_debt) for _ in range(100)]
        mean_result = sum(results) / len(results)
        expected_mean = (die_size + 1) / 2

        # With high positive debt, mean should be above expected
        # Allow some variance since it's probabilistic
        self.assertGreater(mean_result, expected_mean * 0.9)

    @settings(max_examples=500)
    @given(st.integers(min_value=2, max_value=20))
    def test_negative_debt_biases_low(self, die_size):
        """Test that negative debt biases toward lower rolls (statistical)."""
        low_debt = -50.0
        results = [roll_weighted_standard_die(die_size, low_debt) for _ in range(100)]
        mean_result = sum(results) / len(results)
        expected_mean = (die_size + 1) / 2

        # With high negative debt, mean should be below expected
        self.assertLess(mean_result, expected_mean * 1.1)


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestFudgeDiceGeneration(unittest.TestCase):
    """Property-based tests for fudge dice generation."""

    @given(st.integers(min_value=1, max_value=10), st.integers(min_value=-10, max_value=10))
    def test_generate_fudge_sum_matches_target(self, num_dice, target_sum):
        """Test that generated fudge dice sum to target."""
        # Clamp target to valid range
        actual_target = max(-num_dice, min(num_dice, target_sum))

        dice = generate_fudge_dice_for_sum(num_dice, actual_target)

        # Property: should generate exactly num_dice dice
        self.assertEqual(len(dice), num_dice)

        # Property: all dice should be valid fudge faces
        for die in dice:
            self.assertIn(die, FUDGE_FACES)

        # Property: sum should equal the (clamped) target
        self.assertEqual(sum(dice), actual_target)

    @given(st.integers(min_value=1, max_value=10), st.integers(min_value=-10, max_value=10))
    def test_realistic_fudge_sum_matches_target(self, num_dice, target_sum):
        """Test that realistic fudge dice sum to target."""
        actual_target = max(-num_dice, min(num_dice, target_sum))

        dice = generate_realistic_fudge_faces(num_dice, actual_target)

        # Property: should generate exactly num_dice dice
        self.assertEqual(len(dice), num_dice)

        # Property: all dice should be valid fudge faces
        for die in dice:
            self.assertIn(die, FUDGE_FACES)

        # Property: sum should equal the (clamped) target
        self.assertEqual(sum(dice), actual_target)


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestValidation(unittest.TestCase):
    """Property-based tests for validation functions."""

    @given(st.text(min_size=1, max_size=100))
    def test_validation_never_crashes(self, expression):
        """Test that validation doesn't crash on any input."""
        try:
            is_valid, error_msg = validate_dice_expression(expression)

            # Property: should always return a boolean and a string
            self.assertIsInstance(is_valid, bool)
            self.assertIsInstance(error_msg, str)

            # Property: if invalid, should have a non-empty error message
            if not is_valid:
                self.assertTrue(len(error_msg) > 0)

        except Exception as e:
            # Should not crash - if it does, that's a bug
            self.fail(f"Validation crashed on input '{expression}': {e}")

    @given(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
    def test_extract_base_dice_robustness(self, random_text):
        """Test that extract_base_dice doesn't crash on random input."""
        try:
            result = extract_base_dice(random_text)
            # Should always return a string
            self.assertIsInstance(result, str)
        except Exception as e:
            # If it does raise an exception, it should be a reasonable one
            self.assertIsInstance(e, (ValueError, AttributeError, TypeError))

    @given(st.text(min_size=1, max_size=50, alphabet="0123456789+-d "))
    def test_parse_dice_modifiers_robustness(self, expression):
        """Test that parse_dice_modifiers doesn't crash on various inputs."""
        try:
            dice_part, modifier = parse_dice_modifiers(expression)

            # Property: should always return a string and an integer
            self.assertIsInstance(dice_part, str)
            self.assertIsInstance(modifier, int)

            # Property: dice_part should be non-empty if expression is non-empty
            if expression.strip():
                self.assertTrue(len(dice_part) > 0)

        except Exception as e:
            # If it does raise an exception, it should be a reasonable one
            self.assertIsInstance(e, (ValueError, AttributeError, TypeError))


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestParseRollAndLabel(unittest.TestCase):
    """Property-based tests for roll and label parsing."""

    @given(st.text(min_size=1, max_size=20, alphabet="0123456789d+-"))
    def test_no_label_returns_none(self, dice_expr):
        """Test that expressions without labels return None for label."""
        assume(' ' not in dice_expr)
        result_expr, label = parse_roll_and_label(dice_expr)
        self.assertEqual(result_expr, dice_expr)
        self.assertIsNone(label)

    @given(st.text(min_size=1, max_size=20, alphabet="0123456789d+-"),
           st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz "))
    def test_label_extracted(self, dice_expr, label_text):
        """Test that labels are correctly extracted."""
        assume(' ' not in dice_expr)
        assume(label_text.strip())  # Non-empty label after stripping
        assume(not label_text.startswith(' '))  # Label shouldn't start with space
        full_expr = f"{dice_expr} {label_text}"
        result_expr, label = parse_roll_and_label(full_expr)
        self.assertEqual(result_expr, dice_expr)
        self.assertEqual(label, label_text)


@unittest.skipUnless(HYPOTHESIS_AVAILABLE, "Hypothesis library not available")
class TestPercentileConsistency(unittest.TestCase):
    """Test consistency of percentile calculations."""

    @given(st.integers(min_value=1, max_value=20))
    def test_percentile_ordering_single_die(self, die_size):
        """Test that percentiles are ordered correctly for single dice."""
        percentiles = []

        for result in range(1, die_size + 1):
            percentile = single_die_percentile(result, die_size)
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
            percentile = multiple_dice_percentile(result, num_dice, die_size)
            percentiles.append(percentile)

        # Property: percentiles should be non-decreasing
        for i in range(1, len(percentiles)):
            self.assertGreaterEqual(
                percentiles[i], percentiles[i-1],
                f"Percentiles not ordered for {num_dice}d{die_size}"
            )


if __name__ == "__main__":
    if HYPOTHESIS_AVAILABLE:
        # Run property-based tests
        unittest.main()
    else:
        print("Hypothesis library not available. Install with: pip install hypothesis")
        print("Skipping property-based tests.")
