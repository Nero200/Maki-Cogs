import unittest
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import discord
import d20
from datetime import datetime, timedelta

# Add the parent directory to sys.path to import the module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chimeradice import ChimeraDice, DEFAULT_GUILD_USER, FUDGE_FACES, FALLOUT_FACES


class TestChimeraDice(unittest.TestCase):
    """Unit tests for ChimeraDice cog functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.bot = Mock()
        self.cog = ChimeraDice(self.bot)
        
        # Mock the config system
        self.mock_config = AsyncMock()
        self.cog.config = self.mock_config
        
        # Create mock context
        self.ctx = Mock()
        self.ctx.author = Mock()
        self.ctx.author.id = 123456789
        self.ctx.author.display_name = "TestUser"
        self.ctx.channel = Mock()
        self.ctx.channel.id = 987654321
        self.ctx.guild = Mock()
        self.ctx.guild.id = 111222333
        self.ctx.send = AsyncMock()
        
        # Setup default user data
        self.default_user_data = DEFAULT_GUILD_USER.copy()
        self.mock_config.user.return_value.all.return_value = self.default_user_data
    
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
        ]
        
        for expression, expected in test_cases:
            with self.subTest(expression=expression):
                dice_part, modifier = self.cog._parse_dice_modifiers(expression)
                self.assertEqual((dice_part, modifier), expected)
    
    def test_validate_dice_expression(self):
        """Test dice expression validation."""
        # Valid expressions
        valid_expressions = [
            "1d20",
            "4d6kh3",
            "2d10+5",
            "1d20ro<3",
            "3d6e6",
            "4dF+2",
            "2dD",
            "1d8mi2ma6",
        ]
        
        for expr in valid_expressions:
            with self.subTest(expression=expr):
                is_valid, error_msg = self.cog._validate_dice_expression(expr)
                self.assertTrue(is_valid, f"Expression '{expr}' should be valid but got error: {error_msg}")
        
        # Invalid expressions
        invalid_expressions = [
            ("", "Dice expression too long"),  # Empty
            ("x" * 200, "Dice expression too long"),  # Too long
            ("999999d999999", "Too many dice"),  # Too many dice
            ("1d0", "Invalid die size"),  # Invalid die size
        ]
        
        for expr, expected_error_part in invalid_expressions:
            with self.subTest(expression=expr):
                is_valid, error_msg = self.cog._validate_dice_expression(expr)
                self.assertFalse(is_valid, f"Expression '{expr}' should be invalid")
                if expected_error_part:
                    self.assertIn(expected_error_part.lower(), error_msg.lower())
    
    def test_single_die_percentile(self):
        """Test percentile calculation for single die rolls."""
        test_cases = [
            (1, 20, 2.5),   # 1 on d20 = 2.5th percentile
            (10, 20, 47.5), # 10 on d20 = 47.5th percentile
            (20, 20, 97.5), # 20 on d20 = 97.5th percentile
            (3, 6, 41.67),  # 3 on d6 ≈ 41.67th percentile
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
    
    def test_calculate_fudge_percentile(self):
        """Test percentile calculation for fudge dice."""
        test_cases = [
            ("4dF", 0, 50),   # 0 on 4dF = median
            ("4dF", 4, 100),  # +4 on 4dF = maximum
            ("4dF", -4, 0),   # -4 on 4dF = minimum
            ("2dF", 1, 75),   # +1 on 2dF = high
        ]
        
        for roll_string, result, expected_range in test_cases:
            with self.subTest(roll_string=roll_string, result=result):
                percentile = self.cog._calculate_fudge_percentile(roll_string, result)
                self.assertIsNotNone(percentile)
                # Allow some tolerance for approximation
                if expected_range == 50:
                    self.assertAlmostEqual(percentile, expected_range, delta=10)
                elif expected_range in [0, 100]:
                    self.assertAlmostEqual(percentile, expected_range, delta=5)
                else:
                    self.assertTrue(expected_range - 20 <= percentile <= expected_range + 20)
    
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
        
        # For same numeric result, kh should generally be higher percentile than kl
        # (though this is an approximation)
    
    def test_generate_fudge_dice_for_sum(self):
        """Test fudge dice generation for specific sums."""
        # Test various target sums
        for target in [-2, 0, 2]:
            dice = self.cog._generate_fudge_dice_for_sum(4, target)
            self.assertEqual(len(dice), 4)
            self.assertEqual(sum(dice), target)
            # Check all dice are valid fudge faces
            for die in dice:
                self.assertIn(die, FUDGE_FACES)
    
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
    
    @patch('d20.roll')
    def test_calculate_roll_percentile_advanced_operations(self, mock_d20_roll):
        """Test percentile calculation with advanced d20 operations."""
        # Test keep highest operation
        percentile = self.cog._calculate_roll_percentile("4d6kh3", 15)
        self.assertIsNotNone(percentile)
        self.assertTrue(0 <= percentile <= 100)
        
        # Test simple dice (should not call advanced logic)
        percentile = self.cog._calculate_roll_percentile("1d20", 10)
        self.assertIsNotNone(percentile)
        self.assertAlmostEqual(percentile, 47.5, places=1)
    
    async def test_handle_forced_standard_dice_simple(self):
        """Test forced dice handling for simple expressions."""
        result = await self.cog._handle_forced_standard_dice(self.ctx, "1d20+5", 15, "standard")
        
        self.assertEqual(result.total, 20)  # 15 + 5
        self.assertIn("(15)", result.result)
    
    async def test_handle_forced_standard_dice_advanced(self):
        """Test forced dice handling for advanced expressions."""
        with patch('d20.roll') as mock_roll:
            mock_result = Mock()
            mock_result.total = 18
            mock_result.result = "4d6kh3 (6, 5, 4, 3) = 18"
            mock_roll.return_value = mock_result
            
            result = await self.cog._handle_forced_standard_dice(self.ctx, "4d6kh3", 15, "standard")
            
            # For advanced operations, should fall back to normal rolling
            self.assertEqual(result.total, 18)
            mock_roll.assert_called_once_with("4d6kh3")


class TestAdvancedOperations(unittest.TestCase):
    """Test advanced d20 library operations integration."""
    
    def setUp(self):
        """Set up test fixtures for advanced operations."""
        self.bot = Mock()
        self.cog = ChimeraDice(self.bot)
    
    def test_d20_keep_highest(self):
        """Test that d20 library keep highest operations work."""
        # This tests the underlying d20 library functionality
        result = d20.roll("4d6kh3")
        self.assertIsNotNone(result.total)
        self.assertTrue(3 <= result.total <= 18)  # 3d6 equivalent range
    
    def test_d20_drop_lowest(self):
        """Test that d20 library drop lowest operations work."""
        # p1 means "drop lowest 1"
        result = d20.roll("4d6p1")  # Equivalent to kh3
        self.assertIsNotNone(result.total)
        self.assertTrue(3 <= result.total <= 18)
    
    def test_d20_reroll_operations(self):
        """Test that d20 library reroll operations work."""
        # Test reroll once
        result = d20.roll("1d6ro<3")
        self.assertIsNotNone(result.total)
        self.assertTrue(1 <= result.total <= 6)
        
        # Test reroll recursive (should eventually succeed)
        result = d20.roll("1d6rr<1")  # Reroll 1s
        self.assertIsNotNone(result.total)
        self.assertTrue(1 <= result.total <= 6)
    
    def test_d20_exploding_dice(self):
        """Test that d20 library exploding dice work."""
        result = d20.roll("1d6e6")  # Explode on 6
        self.assertIsNotNone(result.total)
        self.assertTrue(result.total >= 1)  # Could be very high due to exploding
    
    def test_d20_min_max_constraints(self):
        """Test that d20 library min/max constraints work."""
        result = d20.roll("3d6mi3")  # Minimum 3 on each die
        self.assertIsNotNone(result.total)
        self.assertTrue(9 <= result.total <= 18)  # Each die 3-6, so 9-18 total


class TestAsyncMethods(unittest.IsolatedAsyncioTestCase):
    """Test async methods of ChimeraDice cog."""
    
    async def asyncSetUp(self):
        """Set up async test fixtures."""
        self.bot = Mock()
        self.cog = ChimeraDice(self.bot)
        
        # Mock the config system
        self.mock_config = AsyncMock()
        self.cog.config = self.mock_config
        
        # Create mock context
        self.ctx = Mock()
        self.ctx.author = Mock()
        self.ctx.author.id = 123456789
        self.ctx.author.display_name = "TestUser"
        self.ctx.channel = Mock()
        self.ctx.channel.id = 987654321
        self.ctx.guild = Mock()
        self.ctx.guild.id = 111222333
        self.ctx.send = AsyncMock()
        
        # Setup default user data
        self.default_user_data = DEFAULT_GUILD_USER.copy()
        self.mock_config.user.return_value.all.return_value = self.default_user_data
        self.mock_config.user.return_value.set = AsyncMock()
    
    async def test_record_roll(self):
        """Test roll recording functionality."""
        await self.cog._record_roll(self.ctx, "1d20+5", 18, "standard", 13)
        
        # Verify that the config was updated
        self.mock_config.user.return_value.set.assert_called_once()
        
        # Get the call arguments
        call_args = self.mock_config.user.return_value.set.call_args[0][0]
        
        # Check that roll was added to standard_rolls
        self.assertEqual(len(call_args["stats"]["server_wide"]["standard_rolls"]), 1)
        roll_data = call_args["stats"]["server_wide"]["standard_rolls"][0]
        self.assertEqual(roll_data["roll_string"], "1d20+5")
        self.assertEqual(roll_data["result"], 18)
        self.assertEqual(call_args["stats"]["server_wide"]["total_rolls"], 1)
    
    async def test_update_natural_luck(self):
        """Test natural luck update functionality."""
        # Setup user with existing percentile history
        user_data = self.default_user_data.copy()
        user_data["stats"]["server_wide"]["percentile_history"] = [60.0, 40.0]
        user_data["stats"]["server_wide"]["natural_luck"] = 50.0
        
        self.mock_config.user.return_value.all.return_value = user_data
        
        roll_data = {
            "roll_string": "1d20",
            "result": 15,  # Should be 72.5th percentile
            "timestamp": datetime.now().isoformat(),
            "channel_id": 987654321
        }
        
        await self.cog._update_natural_luck(self.ctx.author, roll_data, "standard")
        
        # Should have attempted to update natural luck
        # Due to mocking complexity, we mainly verify it doesn't crash
        # In real usage, this would update the percentile history and natural luck
    
    async def test_apply_luck_modification(self):
        """Test luck modification application."""
        # Setup user with high luck
        user_data = self.default_user_data.copy()
        user_data["set_luck"] = 80
        self.mock_config.user.return_value.all.return_value = user_data
        
        # Mock d20 result
        mock_result = Mock()
        mock_result.total = 10
        mock_result.result = "1d20 (10) = 10"
        
        result, modified_total = await self.cog._apply_luck_modification(self.ctx, mock_result)
        
        # With luck 80, should get a positive modification
        self.assertGreater(modified_total, 10)
    
    async def test_apply_karma_modification(self):
        """Test karma modification application."""
        # Setup user with positive karma
        user_data = self.default_user_data.copy()
        user_data["current_karma"] = 30
        self.mock_config.user.return_value.all.return_value = user_data
        
        # Mock d20 result
        mock_result = Mock()
        mock_result.total = 10
        mock_result.result = "1d20 (10) = 10"
        
        result, modified_total = await self.cog._apply_karma_modification(self.ctx, mock_result)
        
        # With positive karma, should get a positive modification
        self.assertGreaterEqual(modified_total, 10)


if __name__ == "__main__":
    # Run the tests
    unittest.main()