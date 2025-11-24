import discord
import re
import random
import d20
import statistics
import logging
from datetime import datetime, timedelta
from redbot.core import commands, Config
from typing import List, Dict, Tuple, Optional

log = logging.getLogger("red.chimeradice")

# --- DEFAULT DICTIONARIES ---
DEFAULT_GUILD_USER = {
    "toggles": {
        "luckmode_on": False,
        "karmamode_on": False,
    },
    "set_luck": 50,
    "current_karma": 0,  # Legacy - kept for backward compatibility
    "percentile_debt": 0.0,  # New karma system - accumulated difference from 50th percentile
    "stats": {
        "server_wide": {
            "standard_rolls": [],
            "luck_rolls": [],
            "karma_rolls": [],
            "natural_luck": 50.0,  # Start at 50th percentile
            "percentile_history": [],
            "total_rolls": 0,
        },
        "campaigns": {},
    },
}

DEFAULT_GUILD = {
    "campaigns": {},
    "users": {},
}

# Fallout damage dice faces
FALLOUT_FACES = ["1", "2", "0", "0", "1E", "1E"]

# Fudge dice faces
FUDGE_FACES = [-1, 0, 1]

# Precomputed fudge dice sum probabilities for 1-6 dice
FUDGE_PROBABILITIES = {
    1: {-1: 1/3, 0: 1/3, 1: 1/3},
    2: {-2: 1/9, -1: 2/9, 0: 3/9, 1: 2/9, 2: 1/9},
    3: {-3: 1/27, -2: 3/27, -1: 6/27, 0: 7/27, 1: 6/27, 2: 3/27, 3: 1/27},
    4: {-4: 1/81, -3: 4/81, -2: 10/81, -1: 16/81, 0: 19/81, 1: 16/81, 2: 10/81, 3: 4/81, 4: 1/81},
    5: {-5: 1/243, -4: 5/243, -3: 15/243, -2: 30/243, -1: 45/243, 0: 51/243, 1: 45/243, 2: 30/243, 3: 15/243, 4: 5/243, 5: 1/243},
    6: {-6: 1/729, -5: 6/729, -4: 21/729, -3: 50/729, -2: 90/729, -1: 126/729, 0: 141/729, 1: 126/729, 2: 90/729, 3: 50/729, 4: 21/729, 5: 6/729, 6: 1/729}
}


# Mock result classes for weighted dice rolls that mimic d20.roll() output
class DiceRollResult:
    """Mock result object for weighted dice rolls with individual dice display."""
    def __init__(self, total: int, dice_results: List[int], modifier: int):
        self.total = total
        dice_str = ', '.join(map(str, dice_results))
        if len(dice_results) > 1:
            dice_display = f"({dice_str})"
        else:
            dice_display = str(dice_results[0])

        if modifier != 0:
            modifier_str = f" {modifier:+d}" if modifier < 0 else f" +{modifier}"
            self.result = f"{dice_display}{modifier_str} = {total}"
        else:
            self.result = f"{dice_display} = {total}"


class SimpleRollResult:
    """Mock result object for queued rolls with pre-formatted result string."""
    def __init__(self, total: int, result_str: str):
        self.total = total
        self.result = result_str


class ChimeraDice(commands.Cog):
    """A dice roller with probability-based luck and karma systems.
    
    Features:
    - Weighted probability luck system (0-100 scale)
    - Percentile debt karma system (auto-balancing)
    - Natural-feeling dice manipulation
    - Support for standard dice, fudge dice, and Fallout dice
    - Campaign statistics and analytics
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=1234567890, force_registration=True
        )
        self.config.register_guild(**DEFAULT_GUILD)
        self.config.register_user(**DEFAULT_GUILD_USER)
        # Test queue for validating luck/karma probability systems.
        # Used by test utilities to run deterministic sequences for system validation.
        self.test_queue = {}

        # Local test handler - will be set by test utilities if available
        self._test_handler = None

        # Load local test utilities if available (not in public repo)
        try:
            from .chimeradice_test import setup_test_commands
            setup_test_commands(self)
        except ImportError:
            pass  # Test utilities not installed, skip silently

    # --- CORE COMMANDS ---

    @commands.command(name="roll", aliases=["r"])
    async def roll(self, ctx: commands.Context, *, roll_string: str):
        """Standard dice rolling with d20 library support."""
        # Check if user has luck or karma mode enabled - if so, use that mode
        user_data = await self.config.user(ctx.author).all()
        
        if user_data["toggles"]["luckmode_on"]:
            await self._execute_roll(ctx, roll_string, "luck")
        elif user_data["toggles"]["karmamode_on"]:
            await self._execute_roll(ctx, roll_string, "karma")
        else:
            await self._execute_roll(ctx, roll_string, "standard")

    @commands.command(name="lroll", aliases=["lr"])
    async def lroll(self, ctx: commands.Context, *, roll_string: str):
        """Luck-modified dice rolling (works without luck mode enabled)."""
        await self._execute_roll(ctx, roll_string, "luck")

    @commands.command(name="kroll", aliases=["kr"])
    async def kroll(self, ctx: commands.Context, *, roll_string: str):
        """Karma-modified dice rolling (works without karma mode enabled)."""
        await self._execute_roll(ctx, roll_string, "karma")

    async def _execute_roll(self, ctx: commands.Context, roll_string: str, roll_type: str):
        """Execute a roll with the specified type (standard, luck, karma)."""
        try:
            # Parse dice expression and optional label
            dice_expr, label = self._parse_roll_and_label(roll_string)

            # Validate dice expression first (only the dice part, not the label)
            is_valid, error_msg = self._validate_dice_expression(dice_expr)
            if not is_valid:
                await ctx.send(f"Invalid dice expression: {error_msg}")
                return

            user_id = ctx.author.id
            queued_result = None

            if user_id in self.test_queue:
                # Clean up expired rolls first
                self._cleanup_expired_test_queue()

                # Normalize the dice expression for consistent lookup
                normalized_key = self._normalize_dice_key(dice_expr)

                if normalized_key in self.test_queue[user_id]:
                    data = self.test_queue[user_id][normalized_key]
                    # Handle both new format (dict) and legacy format (list)
                    if isinstance(data, dict) and "values" in data and data["values"]:
                        queued_result = data["values"].pop(0)
                        # Remove entry if no more values
                        if not data["values"]:
                            del self.test_queue[user_id][normalized_key]
                            # Clean up empty user dict
                            if not self.test_queue[user_id]:
                                del self.test_queue[user_id]
                    elif isinstance(data, list) and data:
                        # Legacy format support
                        queued_result = data.pop(0)
                        if not data:
                            del self.test_queue[user_id][normalized_key]
                            # Clean up empty user dict
                            if not self.test_queue[user_id]:
                                del self.test_queue[user_id]

            # Handle special dice types first
            if 'df' in dice_expr.lower() or 'f' in dice_expr.lower():
                await self._handle_fudge_dice(ctx, dice_expr, roll_type, queued_result, label)
                return
            elif 'dd' in dice_expr.lower():
                await self._handle_fallout_dice(ctx, dice_expr, roll_type, queued_result, label)
                return

            # Use d20 library for standard dice with full support for advanced operations
            if queued_result is not None:
                # For queued results with advanced operations, we need special handling
                result = await self._handle_test_queue_standard_dice(ctx, dice_expr, queued_result, roll_type)
            else:
                # Apply bias for karma/luck rolls, otherwise roll normally
                if roll_type == "karma":
                    result = await self._roll_standard_dice_with_karma(ctx, dice_expr)
                elif roll_type == "luck":
                    result = await self._roll_standard_dice_with_luck(ctx, dice_expr)
                else:
                    # Translate user-friendly syntax to d20 library syntax
                    translated_expression = self._translate_dice_syntax(dice_expr)
                    result = d20.roll(translated_expression)
            
            actual_total = result.total
            display_result = result.result
            
            # Store original result before modifications (for natural luck tracking)
            original_total = actual_total
            
            # Apply roll type modifications (but not if queued)
            if queued_result is None:
                if roll_type == "luck":
                    # Luck bias was already applied during dice generation
                    # No additional modification needed
                    pass
                elif roll_type == "karma":
                    result, modified_total = await self._apply_karma_modification(ctx, result)
                    actual_total = modified_total
                    display_result = f"{result.result.split('=')[0].strip()} = {modified_total}"
            
            # Record the roll (pass both modified and original results)
            await self._record_roll(ctx, dice_expr, actual_total, roll_type, original_total)

            # Format output with visual indicators
            emoji = self._get_roll_emoji(roll_type)
            # Include label in display if provided
            roll_display = f"`{dice_expr}`" if label is None else f"`{dice_expr}` ({label})"
            output = f"{emoji} **{ctx.author.display_name}** rolls {roll_display}...\n"
            output += f"Result: {display_result} = **{actual_total}**"

            if roll_type == "karma":
                debt = await self._get_user_karma(ctx.author, ctx.guild.id, ctx.channel.id)
                output += f" (Debt: {debt:+.1f})"

            await ctx.send(output)

        except Exception as e:
            log.error(f"Roll execution failed for user {ctx.author} ({ctx.author.id}): roll_string='{roll_string}', roll_type='{roll_type}'", exc_info=True)
            await ctx.send(f"Error: {str(e)}")

    @commands.command(name="force")
    async def force_fake(self, ctx: commands.Context, *, args: str = ""):
        """Nice try! This command doesn't exist."""
        responses = [
            "You really thought?",
            "Not an option.",
            "Nope.",
            "Access denied. 🚫",
            "Did you mean to roll dice? Try `>roll`",
            "That's not how this works.",
            "Bold of you to assume.",
            "No cheating! 🎲",
            "The dice gods frown upon this.",
            "Try harder. Or don't.",
            "Dad says no.",
            "I'm telling dad!",
            "Nada.",
            "Take -2 to your next roll.",
        ]
        await ctx.send(random.choice(responses))

    @commands.command(name="forcedice")
    async def forcedice_fake(self, ctx: commands.Context, *, args: str = ""):
        """Nice try! This command doesn't exist."""
        responses = [
            "You really thought?",
            "Not an option.",
            "Nope.",
            "Access denied. 🚫",
            "Did you mean to roll dice? Try `>roll`",
            "That's not how this works.",
            "Bold of you to assume.",
            "No cheating! 🎲",
            "The dice gods frown upon this.",
            "Try harder. Or don't.",
            "Dad says no.",
            "I'm telling dad!",
            "Nada.",
            "Take -2 to your next roll.",
        ]
        await ctx.send(random.choice(responses))

    @commands.command(name="setresult")
    async def setresult_fake(self, ctx: commands.Context, *, args: str = ""):
        """Nice try! This command doesn't exist."""
        responses = [
            "You really thought?",
            "Not an option.",
            "Nope.",
            "Access denied. 🚫",
            "Did you mean to roll dice? Try `>roll`",
            "That's not how this works.",
            "Bold of you to assume.",
            "No cheating! 🎲",
            "The dice gods frown upon this.",
            "Try harder. Or don't.",
            "Dad says no.",
            "I'm telling dad!",
            "Nada.",
            "Take -2 to your next roll.",
        ]
        await ctx.send(random.choice(responses))

    @commands.command(name="fr2", hidden=True)
    async def fr2(self, ctx: commands.Context, *, args: str = ""):
        """Local test roll command - requires test utilities."""
        if self._test_handler:
            await self._test_handler(ctx, args)
        # Silently do nothing if test utilities not loaded

    @commands.command(name="fdice")
    async def fdice_fake(self, ctx: commands.Context, *, args: str = ""):
        """Nice try! This command doesn't exist."""
        responses = [
            "You really thought?",
            "Not an option.",
            "Nope.",
            "Access denied. 🚫",
            "Did you mean to roll dice? Try `>roll`",
            "That's not how this works.",
            "Bold of you to assume.",
            "No cheating! 🎲",
            "The dice gods frown upon this.",
            "Try harder. Or don't.",
            "Dad says no.",
            "I'm telling dad!",
            "Nada.",
            "Take -2 to your next roll.",
        ]
        await ctx.send(random.choice(responses))

    # --- ADMIN COMMANDS ---
    
    @commands.command(name="enable_luck")
    @commands.has_permissions(administrator=True)
    async def enable_luck(self, ctx: commands.Context, user: discord.Member):
        """Enable luck mode for a user in this channel."""
        await self.config.user(user).toggles.luckmode_on.set(True)
        log.info(f"Admin {ctx.author} ({ctx.author.id}) enabled luck mode for {user} ({user.id})")
        await ctx.send(f"🍀 Luck mode enabled for {user.display_name}")
    
    @commands.command(name="disable_luck")
    @commands.has_permissions(administrator=True)
    async def disable_luck(self, ctx: commands.Context, user: discord.Member):
        """Disable luck mode for a user in this channel."""
        await self.config.user(user).toggles.luckmode_on.set(False)
        log.info(f"Admin {ctx.author} ({ctx.author.id}) disabled luck mode for {user} ({user.id})")
        await ctx.send(f"❌ Luck mode disabled for {user.display_name}")
    
    @commands.command(name="enable_karma")
    @commands.has_permissions(administrator=True)
    async def enable_karma(self, ctx: commands.Context, user: discord.Member):
        """Enable karma mode for a user in this channel."""
        await self.config.user(user).toggles.karmamode_on.set(True)
        log.info(f"Admin {ctx.author} ({ctx.author.id}) enabled karma mode for {user} ({user.id})")
        await ctx.send(f"⚖️ Karma mode enabled for {user.display_name}")

    @commands.command(name="disable_karma")
    @commands.has_permissions(administrator=True)
    async def disable_karma(self, ctx: commands.Context, user: discord.Member):
        """Disable karma mode for a user in this channel."""
        await self.config.user(user).toggles.karmamode_on.set(False)
        log.info(f"Admin {ctx.author} ({ctx.author.id}) disabled karma mode for {user} ({user.id})")
        await ctx.send(f"❌ Karma mode disabled for {user.display_name}")
    
    @commands.command(name="set_luck")
    @commands.has_permissions(administrator=True)
    async def set_luck(self, ctx: commands.Context, user: discord.Member, luck_value: int):
        """Set a user's luck value (0-100)."""
        if not 0 <= luck_value <= 100:
            await ctx.send("Luck value must be between 0 and 100.")
            return

        await self.config.user(user).set_luck.set(luck_value)
        log.info(f"Admin {ctx.author} ({ctx.author.id}) set luck for {user} ({user.id}) to {luck_value}")
        await ctx.send(f"🎲 Set {user.display_name}'s luck to {luck_value}")
    
    @commands.command(name="reset_karma")
    @commands.has_permissions(administrator=True)
    async def reset_karma(self, ctx: commands.Context, user: discord.Member):
        """Reset a user's percentile debt to 0."""
        await self.config.user(user).current_karma.set(0)
        await self.config.user(user).percentile_debt.set(0.0)
        log.info(f"Admin {ctx.author} ({ctx.author.id}) reset karma for {user} ({user.id})")
        await ctx.send(f"⚖️ Reset {user.display_name}'s karma and percentile debt to 0")

    @commands.command(name="set_debt")
    @commands.has_permissions(administrator=True)
    async def set_debt(self, ctx: commands.Context, user: discord.Member, debt_value: float):
        """Set a user's percentile debt value (-100 to +100)."""
        if not -100 <= debt_value <= 100:
            await ctx.send("Percentile debt must be between -100 and +100.")
            return

        await self.config.user(user).percentile_debt.set(debt_value)
        log.info(f"Admin {ctx.author} ({ctx.author.id}) set debt for {user} ({user.id}) to {debt_value:+.1f}")
        await ctx.send(f"⚖️ Set {user.display_name}'s percentile debt to {debt_value:+.1f}")
    
    @commands.command(name="fix_luck_data")
    @commands.has_permissions(administrator=True)
    async def fix_luck_data(self, ctx: commands.Context, user: discord.Member = None):
        """Fix user's luck data structure (admin only)."""
        target_user = user or ctx.author
        user_data = await self.config.user(target_user).all()
        
        # Ensure percentile_history exists and reset natural luck if needed
        fixed = False
        if "percentile_history" not in user_data["stats"]["server_wide"]:
            user_data["stats"]["server_wide"]["percentile_history"] = []
            fixed = True
        
        # Reset natural luck to 50.0 if it's still 0.0 and no percentile history
        if (user_data["stats"]["server_wide"]["natural_luck"] == 0.0 and 
            len(user_data["stats"]["server_wide"].get("percentile_history", [])) == 0):
            user_data["stats"]["server_wide"]["natural_luck"] = 50.0
            fixed = True
        
        if fixed:
            await self.config.user(target_user).set(user_data)
            log.info(f"Admin {ctx.author} ({ctx.author.id}) fixed luck data for {target_user} ({target_user.id})")
            await ctx.send(f"✅ Fixed {target_user.display_name}'s luck data structure")
        else:
            await ctx.send(f"✅ {target_user.display_name}'s luck data is already correct")
        
        # Show current values
        natural_luck = user_data["stats"]["server_wide"]["natural_luck"]
        percentile_count = len(user_data["stats"]["server_wide"].get("percentile_history", []))
        await ctx.send(f"Natural luck: {natural_luck:.1f}, Percentile history: {percentile_count} rolls")

    def _get_roll_emoji(self, roll_type: str) -> str:
        """Get emoji for roll type."""
        emojis = {
            "standard": "🎲",
            "luck": "🍀",
            "karma": "⚖️"
        }
        return emojis.get(roll_type, "🎲")
    
    async def _apply_luck_modification(self, ctx: commands.Context, result) -> tuple:
        """Apply luck modification to a roll result using weighted probability."""
        # Note: This function is now primarily called for display purposes
        # The actual luck bias is applied during dice generation in _execute_roll
        # No debt tracking needed for luck system
        
        # Return the unmodified result since luck was applied during generation
        return result, result.total
    
    async def _apply_karma_modification(self, ctx: commands.Context, result) -> tuple:
        """Apply karma modification to a roll result using weighted probability."""
        # Note: This function is now primarily called for display purposes
        # The actual karma bias is applied during dice generation in _execute_roll
        # We just need to update the debt tracking here
        
        await self._update_percentile_debt(ctx, result.total, result.total)
        
        # Return the unmodified result since karma was applied during generation
        return result, result.total
    
    async def _update_percentile_debt(self, ctx: commands.Context, original_result: int, modified_result: int):
        """Update user's percentile debt based on roll outcome."""
        # Calculate the percentile for the original roll result
        roll_string = ctx.message.content.split(maxsplit=1)[1] if len(ctx.message.content.split()) > 1 else "1d20"
        percentile = self._calculate_roll_percentile(roll_string, original_result)
        
        if percentile is not None:
            user_data = await self.config.user(ctx.author).all()
            current_debt = user_data.get("percentile_debt", 0.0)
            
            # Calculate how much we deviated from the 50th percentile
            deviation = 50.0 - percentile
            
            # Add this deviation to our debt (positive debt = owed good luck)
            new_debt = current_debt + deviation

            # Note: No decay factor - karma is purely self-correcting
            # Good rolls naturally reduce positive debt, bad rolls reduce negative debt

            # Cap debt at reasonable limits (-100 to +100 percentile points)
            if new_debt < -100 or new_debt > 100:
                log.warning(f"Debt capped for user {ctx.author.id}: {new_debt:.1f} -> {max(-100, min(100, new_debt)):.1f}")
            new_debt = max(-100, min(100, new_debt))

            await self.config.user(ctx.author).percentile_debt.set(new_debt)
    
    async def _get_user_karma(self, user: discord.Member, guild_id: int, channel_id: int) -> float:
        """Get user's current percentile debt value."""
        user_data = await self.config.user(user).all()
        return user_data.get("percentile_debt", 0.0)
    
    async def _record_roll(self, ctx: commands.Context, roll_string: str, result: int, roll_type: str, original_result: int = None):
        """Record a roll in the user's statistics."""
        user_data = await self.config.user(ctx.author).all()
        
        roll_data = {
            "timestamp": datetime.now().isoformat(),
            "roll_string": roll_string,
            "result": result,
            "channel_id": ctx.channel.id
        }
        
        # Add to appropriate roll type list
        if roll_type == "standard":
            user_data["stats"]["server_wide"]["standard_rolls"].append(roll_data)
        elif roll_type == "luck":
            user_data["stats"]["server_wide"]["luck_rolls"].append(roll_data)
        elif roll_type == "karma":
            user_data["stats"]["server_wide"]["karma_rolls"].append(roll_data)
        
        user_data["stats"]["server_wide"]["total_rolls"] += 1
        
        # Save the updated user data first
        await self.config.user(ctx.author).set(user_data)
        
        # Update natural luck calculation (after saving user_data)
        # Use original_result for natural luck if available (for luck/karma rolls)
        luck_roll_data = roll_data.copy()
        if original_result is not None:
            luck_roll_data["result"] = original_result
        await self._update_natural_luck(ctx.author, luck_roll_data, roll_type)
    
    async def _update_natural_luck(self, user: discord.Member, roll_data: dict, roll_type: str):
        """Update user's natural luck rating using percentile rank system."""
        # Track natural luck for all roll types, but use unmodified results for luck/karma
        if roll_type not in ["standard", "luck", "karma"]:
            return
        
        # Calculate percentile for this roll
        percentile = self._calculate_roll_percentile(roll_data["roll_string"], roll_data["result"])

        if percentile is not None:
            log.debug(f"Percentile calculated: {roll_data['roll_string']} = {roll_data['result']} -> {percentile:.1f}%")
            # Get fresh user data to avoid conflicts
            fresh_user_data = await self.config.user(user).all()
            current_percentiles = fresh_user_data["stats"]["server_wide"].get("percentile_history", [])
            
            # Add new percentile to history
            current_percentiles.append(percentile)

            # Warn if percentile history is getting large
            if len(current_percentiles) > 1000 and len(current_percentiles) % 100 == 0:
                log.warning(f"Large percentile history for user {user.id}: {len(current_percentiles)} entries")

            # Calculate new natural luck as average of all percentiles
            natural_luck = sum(current_percentiles) / len(current_percentiles)
            
            # Update stored data
            try:
                await self.config.user(user).stats.server_wide.natural_luck.set(natural_luck)
                await self.config.user(user).stats.server_wide.percentile_history.set(current_percentiles)
            except Exception as e:
                # Fallback: update fresh data and save everything
                log.warning(f"Failed to save natural_luck/percentile_history for user {user.id}, using fallback method: {e}")
                fresh_user_data["stats"]["server_wide"]["percentile_history"] = current_percentiles
                fresh_user_data["stats"]["server_wide"]["natural_luck"] = natural_luck
                await self.config.user(user).set(fresh_user_data)
    
    def _calculate_roll_percentile(self, roll_string: str, result: int) -> float:
        """Calculate percentile rank for a roll result."""
        try:
            # Handle special dice types
            if 'df' in roll_string.lower():
                return self._calculate_fudge_percentile(roll_string, result)
            elif 'dd' in roll_string.lower():
                log.debug(f"Skipping percentile for Fallout dice: {roll_string}")
                return None  # Skip Fallout dice for now (complex distribution)
            
            # Check if this uses advanced d20 operations
            import re
            has_advanced = bool(re.search(r'(kh|kl|dh|dl|ro|rr|ra|e|mi|ma|p)\d*', roll_string.lower()))
            
            if has_advanced:
                # For advanced operations, we'll use a simplified approach
                # Extract the base dice and use broad estimates
                base_dice = self._extract_base_dice(roll_string)
                match = re.match(r'(\d+)d(\d+)', base_dice.lower())
                if match:
                    num_dice = int(match.group(1))
                    die_size = int(match.group(2))
                    
                    # For operations like kh3 on 4d6, estimate based on modified range
                    if 'kh' in roll_string.lower() or 'kl' in roll_string.lower():
                        # Keep operations - approximate the new range
                        return self._estimate_keep_percentile(roll_string, result, num_dice, die_size)
                    else:
                        # Other advanced operations - use basic calculation as fallback
                        if num_dice == 1:
                            return self._single_die_percentile(result, die_size)
                        else:
                            return self._multiple_dice_percentile(result, num_dice, die_size)
            
            # Simple regex parsing for standard dice (more reliable than d20 library parsing)
            # Match patterns like: 1d20, 3d6, 5d20+2, 2d10-1
            match = re.match(r'(\d+)d(\d+)(?:[+-]\d+)?', roll_string.lower())
            
            if match:
                num_dice = int(match.group(1))
                die_size = int(match.group(2))
                
                # Calculate percentile for single die
                if num_dice == 1:
                    return self._single_die_percentile(result, die_size)
                # Calculate percentile for multiple dice (sum)
                elif num_dice > 1:
                    return self._multiple_dice_percentile(result, num_dice, die_size)
            
            return None

        except Exception as e:
            log.debug(f"Percentile calculation failed for roll_string='{roll_string}', result={result}: {e}")
            return None
    
    def _single_die_percentile(self, result: int, die_size: int) -> float:
        """Calculate percentile for a single die roll."""
        if result < 1 or result > die_size:
            return None
        
        # For a single die, percentile is (result - 0.5) / die_size * 100
        # Subtract 0.5 to get midpoint of the result's range
        return ((result - 0.5) / die_size) * 100
    
    def _multiple_dice_percentile(self, result: int, num_dice: int, die_size: int) -> float:
        """Calculate percentile for multiple dice of same type."""
        min_result = num_dice
        max_result = num_dice * die_size
        
        if result < min_result or result > max_result:
            return None
        
        # For multiple dice, approximate using normal distribution
        # This is an approximation - true calculation would require probability tables
        mean = num_dice * (die_size + 1) / 2
        
        # Rough approximation of percentile
        if result <= mean:
            # Below average
            percentile = ((result - min_result) / (mean - min_result)) * 50
        else:
            # Above average  
            percentile = 50 + ((result - mean) / (max_result - mean)) * 50
        
        return max(0, min(100, percentile))
    
    def _calculate_fudge_percentile(self, roll_string: str, result: int) -> float:
        """Calculate percentile for fudge dice results."""
        # Extract number of dice from roll string
        match = re.match(r'(\d+)df?', roll_string.lower().split('+')[0].split('-')[0])
        if not match:
            return None
        
        num_dice = int(match.group(1))
        min_result = -num_dice
        max_result = num_dice
        
        if result < min_result or result > max_result:
            return None
        
        # Fudge dice follow a triangular/binomial distribution
        # For 4dF: -4(1.2%), -3(4.9%), -2(12.3%), -1(19.8%), 0(23.5%), +1(19.8%), +2(12.3%), +3(4.9%), +4(1.2%)
        # Approximate percentile calculation
        range_size = max_result - min_result
        position = (result - min_result) / range_size
        
        # Adjust for bell curve distribution (fudge dice are more likely to be near 0)
        if result == 0:
            percentile = 50  # Exactly at median
        elif result > 0:
            # Positive results
            percentile = 50 + (position - 0.5) * 100 * 0.8  # Slightly compressed
        else:
            # Negative results
            percentile = position * 100 * 0.8  # Slightly compressed
        
        return max(0, min(100, percentile))
    
    def _estimate_keep_percentile(self, roll_string: str, result: int, num_dice: int, die_size: int) -> float:
        """Estimate percentile for keep highest/lowest operations."""
        import re

        # Extract keep/drop parameters (numbers are optional, default to 1)
        kh_match = re.search(r'kh(\d*)', roll_string.lower())
        kl_match = re.search(r'kl(\d*)', roll_string.lower())
        dh_match = re.search(r'dh(\d*)', roll_string.lower())
        dl_match = re.search(r'dl(\d*)', roll_string.lower())
        
        if kh_match:
            # Keep highest X dice (default to 1 if not specified)
            keep_count = int(kh_match.group(1)) if kh_match.group(1) else 1
            # For keep highest, the range is from keep_count to keep_count * die_size
            min_result = keep_count
            max_result = keep_count * die_size

            # Approximate percentile (keep highest skews toward higher values)
            if result < min_result or result > max_result:
                return None

            # Keep highest operations have higher probability for higher results
            range_position = (result - min_result) / (max_result - min_result)
            # Apply a power curve to account for the bias toward higher values
            percentile = (range_position ** 0.7) * 100

        elif kl_match:
            # Keep lowest X dice (default to 1 if not specified)
            keep_count = int(kl_match.group(1)) if kl_match.group(1) else 1
            min_result = keep_count
            max_result = keep_count * die_size

            if result < min_result or result > max_result:
                return None

            # Keep lowest operations have higher probability for lower results
            range_position = (result - min_result) / (max_result - min_result)
            # Apply an inverse power curve to account for the bias toward lower values
            percentile = (range_position ** 1.4) * 100

        elif dh_match:
            # Drop highest X dice (default to 1 if not specified)
            # Equivalent to keep lowest Y where Y = num_dice - X
            drop_count = int(dh_match.group(1)) if dh_match.group(1) else 1
            keep_count = num_dice - drop_count
            min_result = keep_count
            max_result = keep_count * die_size

            if result < min_result or result > max_result:
                return None

            # Drop highest = keep lowest, so bias toward lower results
            range_position = (result - min_result) / (max_result - min_result)
            percentile = (range_position ** 1.4) * 100

        elif dl_match:
            # Drop lowest X dice (default to 1 if not specified)
            # Equivalent to keep highest Y where Y = num_dice - X
            drop_count = int(dl_match.group(1)) if dl_match.group(1) else 1
            keep_count = num_dice - drop_count
            min_result = keep_count
            max_result = keep_count * die_size

            if result < min_result or result > max_result:
                return None

            # Drop lowest = keep highest, so bias toward higher results
            range_position = (result - min_result) / (max_result - min_result)
            percentile = (range_position ** 0.7) * 100
            
        else:
            # Fallback for other operations
            return self._multiple_dice_percentile(result, num_dice, die_size)
        
        return max(0, min(100, percentile))
    
    def _cleanup_expired_test_queue(self):
        """Remove queued test rolls older than 12 hours."""
        current_time = datetime.now()
        expiry_time = timedelta(hours=12)

        expired_count = 0
        users_to_remove = []
        for user_id, user_test_queue in self.test_queue.items():
            dice_exprs_to_remove = []

            for dice_expr, data in user_test_queue.items():
                if isinstance(data, dict) and "timestamp" in data:
                    if current_time - data["timestamp"] > expiry_time:
                        dice_exprs_to_remove.append(dice_expr)
                        expired_count += 1
                elif isinstance(data, list):
                    # Legacy format - remove it
                    dice_exprs_to_remove.append(dice_expr)
                    expired_count += 1

            # Remove expired dice expressions
            for dice_expr in dice_exprs_to_remove:
                del user_test_queue[dice_expr]

            # Mark user for removal if no queued rolls left
            if not user_test_queue:
                users_to_remove.append(user_id)

        # Remove users with no queued rolls
        for user_id in users_to_remove:
            del self.test_queue[user_id]

        if expired_count > 0:
            log.debug(f"Cleaned up {expired_count} expired queued roll(s)")

    def _estimate_complex_percentile(self, roll_string: str, result: int) -> float:
        """Estimate percentile for complex expressions."""
        # This is a fallback for complex expressions we can't parse easily
        # For now, return None to skip tracking these rolls
        return None
    
    def _parse_dice_modifiers(self, expression: str) -> tuple:
        """Parse dice expression with multiple modifiers.
        
        Examples:
        - "4df+5+2-1" -> ("4df", 6)
        - "1d20+3-2+1" -> ("1d20", 2)
        - "4df" -> ("4df", 0)
        """
        import re
        
        # Find the dice part (everything before first + or -)
        dice_match = re.match(r'([^+-]+)', expression)
        if not dice_match:
            return expression, 0
            
        dice_part = dice_match.group(1)
        modifier_part = expression[len(dice_part):]
        
        if not modifier_part:
            return dice_part, 0
        
        # Parse all modifiers using regex
        # This finds patterns like +5, -3, +2, etc.
        modifier_matches = re.findall(r'([+-])(\d+)', modifier_part)
        
        total_modifier = 0
        for sign, value in modifier_matches:
            if sign == '+':
                total_modifier += int(value)
            else:  # sign == '-'
                total_modifier -= int(value)
        
        return dice_part, total_modifier
    
    def _validate_dice_expression(self, expression: str) -> tuple:
        """Validate dice expression for safety and sanity.
        
        Returns (is_valid, error_message)
        """
        if not expression or len(expression) > 150:  # Increased for advanced operations
            return False, "Dice expression too long (max 150 characters)"
        
        # Check for basic safety limits
        import re
        
        # Find all numbers in the expression (but exclude those in advanced operators)
        # Remove advanced operation patterns first to avoid false positives
        temp_expr = expression
        for pattern in [r'[<>]\d+', r'(kh|kl|dh|dl|ro|rr|ra|e|mi|ma|p)\d*']:
            temp_expr = re.sub(pattern, '', temp_expr, flags=re.IGNORECASE)
        
        numbers = re.findall(r'\d+', temp_expr)
        
        for num_str in numbers:
            num = int(num_str)
            
            # Reasonable limits to prevent abuse
            if num > 1000:
                return False, f"Number too large: {num} (max 1000)"
            if num < 0:
                return False, f"Negative numbers not allowed: {num}"
        
        # Check for reasonable dice patterns
        dice_patterns = re.findall(r'(\d+)d(\d+)', expression.lower())
        for num_dice, die_size in dice_patterns:
            num_dice, die_size = int(num_dice), int(die_size)
            
            if num_dice > 100:
                return False, f"Too many dice: {num_dice} (max 100)"
            if die_size > 1000:
                return False, f"Die size too large: {die_size} (max 1000)"
            if die_size < 1:
                return False, f"Invalid die size: {die_size} (min 1)"
        
        # Check for fudge dice
        fudge_patterns = re.findall(r'(\d+)df?', expression.lower())
        for num_dice in fudge_patterns:
            if int(num_dice) > 100:
                return False, f"Too many fudge dice: {num_dice} (max 100)"
        
        # Check for fallout dice  
        fallout_patterns = re.findall(r'(\d+)dd?', expression.lower())
        for num_dice in fallout_patterns:
            if int(num_dice) > 100:
                return False, f"Too many fallout dice: {num_dice} (max 100)"
        
        # Validate d20 expression by attempting to parse it
        # Skip validation for our custom dice types
        if not ('df' in expression.lower() or 'dd' in expression.lower()):
            try:
                # Translate user-friendly syntax to d20 library syntax before testing
                translated_expression = self._translate_dice_syntax(expression)
                # Test if d20 can parse the translated expression
                d20.roll(translated_expression)
            except Exception as e:
                return False, f"Invalid d20 expression: {str(e)}"
        
        return True, ""

    def _validate_queued_results(self, dice_expr: str, results: List[int]) -> tuple:
        """Validate that queued test results are possible for the given dice expression.

        Returns (is_valid, error_message)
        """
        import re

        # Parse the dice expression to determine type and bounds
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
            # Fallout dice: each die shows 0, 0, 1, 1E, 2, or 1E
            # Max possible is if all show "2": num_dice * 2
            # We'll validate: 0 <= result <= num_dice * 2
            max_result = num_dice * 2
            for result in results:
                if result < 0 or result > max_result:
                    return False, f"{result} is impossible for {dice_expr} (range: 0 to {max_result})"
            return True, ""

        # Check for standard dice (XdY) - check last since it's most general
        # Match pattern like "1d20" or "2d6" at the start
        standard_match = re.match(r'(\d+)d(\d+)', dice_expr_lower)
        if standard_match:
            num_dice = int(standard_match.group(1))
            die_size = int(standard_match.group(2))

            # For queued results, we're setting the dice result before modifiers
            # So validate against the dice range, not the final result range
            min_result = num_dice
            max_result = num_dice * die_size

            for result in results:
                if result < min_result or result > max_result:
                    return False, f"{result} is impossible for {standard_match.group(0)} (range: {min_result} to {max_result})"
            return True, ""

        # If we can't parse it, allow it (validation already happened earlier)
        return True, ""

    def _normalize_dice_key(self, dice_expr: str) -> str:
        """Normalize a dice expression to a consistent lookup key.

        Examples:
        - "1D20" -> "1d20"
        - "d20" -> "1d20" (adds implicit 1)
        - "1d20+5" -> "1d20"
        - "4DF" -> "4df"
        - "dF" -> "1df" (adds implicit 1)
        - "3dD" -> "3dd"
        """
        # Extract just the dice part (no modifiers)
        dice_part, _ = self._parse_dice_modifiers(dice_expr)
        # Lowercase everything for consistency
        dice_part = dice_part.lower()

        # Add implicit "1" if dice expression starts with "d"
        if dice_part.startswith('d'):
            dice_part = '1' + dice_part

        return dice_part

    async def _handle_fudge_dice(self, ctx: commands.Context, roll_string: str, roll_type: str, queued_result: int = None, label: str = None):
        """Handle fudge dice rolling with outcome manipulation."""
        # Parse fudge dice (XdF+N or XdF-N format)
        original_string = roll_string
        bonus = 0

        # Extract all modifiers (e.g., 4df+5+2-1)
        dice_part, bonus = self._parse_dice_modifiers(roll_string)
        roll_string = dice_part
        
        match = re.match(r'(\d+)df?', roll_string.lower())
        if not match:
            await ctx.send("Invalid fudge dice format. Use XdF with optional modifiers (e.g., 4dF+2, 4dF+5+2-1)")
            return
        
        num_dice = int(match.group(1))
        
        # Calculate target outcome based on roll type
        dice_results = None
        dice_total = 0
        
        if queued_result is not None:
            # Set the dice result directly (before adding bonus)
            dice_results = self._generate_fudge_dice_for_sum(num_dice, queued_result)
            dice_total = sum(dice_results)
        elif roll_type == "standard":
            # For standard rolls, generate truly random fudge dice
            dice_results = [random.choice(FUDGE_FACES) for _ in range(num_dice)]
            dice_total = sum(dice_results)
        elif roll_type == "luck":
            user_data = await self.config.user(ctx.author).all()
            luck_value = user_data["set_luck"]
            # Convert luck (0-100) to debt-like value (-50 to +50)
            luck_debt = (luck_value - 50.0)
            
            # Use new weighted system for fudge dice
            dice_results, dice_total = self._roll_weighted_fudge_dice(num_dice, luck_debt)
        elif roll_type == "karma":
            user_data = await self.config.user(ctx.author).all()
            percentile_debt = user_data.get("percentile_debt", 0.0)
            
            # Use new weighted system for fudge dice
            dice_results, dice_total = self._roll_weighted_fudge_dice(num_dice, percentile_debt)
        
        # Check for all positives or all negatives bonus
        all_positive = all(d == 1 for d in dice_results)
        all_negative = all(d == -1 for d in dice_results)
        
        fudge_bonus = 0
        if all_positive:
            fudge_bonus = (num_dice + 1) // 2  # Half number of dice, rounded up
            dice_total += fudge_bonus
        elif all_negative:
            fudge_bonus = -((num_dice + 1) // 2)  # Negative half, rounded up
            dice_total += fudge_bonus
        
        final_total = dice_total + bonus
        dice_str = ', '.join(['**+**' if d == 1 else '☐' if d == 0 else '**-**' for d in dice_results])

        emoji = self._get_roll_emoji(roll_type)
        # Include label in display if provided
        roll_display = f"`{original_string}`" if label is None else f"`{original_string}` ({label})"
        output = f"{emoji} **{ctx.author.display_name}** rolls {roll_display}...\n"
        output += f"Result: ({dice_str})"
        
        # Show fudge bonus if applicable
        if fudge_bonus != 0:
            fudge_text = " (all +)" if all_positive else " (all -)"
            output += f" {fudge_bonus:+d}{fudge_text}"
        
        # Show regular bonus if applicable
        if bonus != 0:
            bonus_str = f" {bonus:+d}" if bonus < 0 else f" +{bonus}"
            output += f"{bonus_str}"
        
        output += f" = **{final_total:+d}**"
        
        await ctx.send(output)
        await self._record_roll(ctx, original_string, final_total, roll_type)
    
    def _generate_fudge_dice_for_sum(self, num_dice: int, target_sum: int) -> List[int]:
        """Generate fudge dice that sum to approximately the target."""
        # Clamp target to possible range
        target_sum = max(-num_dice, min(num_dice, target_sum))
        
        # Start with all zeros
        dice = [0] * num_dice
        current_sum = 0
        
        # Adjust dice to reach target sum
        remaining = target_sum - current_sum
        for i in range(num_dice):
            if remaining > 0:
                dice[i] = 1
                remaining -= 1
            elif remaining < 0:
                dice[i] = -1
                remaining += 1
        
        # Randomize the order
        random.shuffle(dice)
        return dice
    
    async def _handle_fallout_dice(self, ctx: commands.Context, roll_string: str, roll_type: str, queued_result: int = None, label: str = None):
        """Handle Fallout damage dice rolling."""
        # Parse fallout dice (XdD format)
        match = re.match(r'(\d+)dd?', roll_string.lower())
        if not match:
            await ctx.send("Invalid Fallout dice format. Use XdD (e.g., 3dD)")
            return
        
        num_dice = int(match.group(1))
        
        if queued_result is not None:
            # For queued results on Fallout dice, just use the queued damage value
            # Generate random-looking dice that could sum to that damage
            total_damage = queued_result
            total_effects = 0
            dice_results = []
            
            # Simple approach: generate dice that sum to the target
            remaining_damage = total_damage
            for i in range(num_dice):
                if remaining_damage > 2:
                    face = "2"
                    remaining_damage -= 2
                elif remaining_damage > 0:
                    face = str(remaining_damage)
                    remaining_damage = 0
                else:
                    face = "0"
                dice_results.append(face)
        else:
            dice_results = []
            total_damage = 0
            total_effects = 0
            
            for _ in range(num_dice):
                face = random.choice(FALLOUT_FACES)
                dice_results.append(face)
                
                if face.endswith('E'):
                    total_effects += 1
                    total_damage += int(face[0])  # Get the number part
                else:
                    total_damage += int(face)
        
        dice_str = ', '.join(dice_results)

        emoji = self._get_roll_emoji(roll_type)
        # Include label in display if provided
        roll_display = f"`{roll_string}`" if label is None else f"`{roll_string}` ({label})"
        output = f"{emoji} **{ctx.author.display_name}** rolls {roll_display}...\n"
        output += f"Result: [{dice_str}] = **{total_damage} damage, {total_effects} effects**"
        
        await ctx.send(output)
        await self._record_roll(ctx, roll_string, total_damage, roll_type)

    # --- STATISTICS COMMANDS ---
    
    @commands.command(name="stats")
    async def stats(self, ctx: commands.Context, user: discord.Member = None):
        """Show user statistics for current channel."""
        target_user = user or ctx.author
        user_data = await self.config.user(target_user).all()
        
        embed = discord.Embed(
            title=f"Dice Statistics - {target_user.display_name}",
            color=discord.Color.blue()
        )
        
        stats = user_data["stats"]["server_wide"]
        
        embed.add_field(
            name="Total Rolls",
            value=stats["total_rolls"],
            inline=True
        )
        
        embed.add_field(
            name="Natural Luck",
            value=f"{stats['natural_luck']:.1f}",
            inline=True
        )

        embed.add_field(
            name="Karma",
            value=f"{user_data.get('percentile_debt', 0.0):+.1f}",
            inline=True
        )
        
        embed.add_field(
            name="Set Luck",
            value=user_data["set_luck"],
            inline=True
        )
        
        standard_count = len(stats["standard_rolls"])
        luck_count = len(stats["luck_rolls"])
        karma_count = len(stats["karma_rolls"])
        
        embed.add_field(
            name="Roll Breakdown",
            value=f"Standard: {standard_count}\nLuck: {luck_count}\nKarma: {karma_count}",
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="globalstats")
    async def globalstats(self, ctx: commands.Context, user: discord.Member = None):
        """Show user's global (server-wide) statistics."""
        # This would be the same as stats for now, but could be expanded
        await self.stats(ctx, user)
    
    @commands.command(name="campaignstats")
    async def campaignstats(self, ctx: commands.Context):
        """Show statistics overview for current channel."""
        guild_data = await self.config.guild(ctx.guild).all()
        
        embed = discord.Embed(
            title=f"Campaign Statistics - #{ctx.channel.name}",
            color=discord.Color.green()
        )
        
        # Get all users who have rolled in this channel
        all_users = await self.config.all_users()
        channel_users = []
        
        for user_id, user_data in all_users.items():
            user = ctx.guild.get_member(user_id)
            if user:
                channel_rolls = [roll for roll in user_data["stats"]["server_wide"]["standard_rolls"] 
                               if roll["channel_id"] == ctx.channel.id]
                if channel_rolls:
                    channel_users.append((user, len(channel_rolls)))
        
        if channel_users:
            channel_users.sort(key=lambda x: x[1], reverse=True)
            user_list = "\n".join([f"{user.display_name}: {count} rolls" 
                                 for user, count in channel_users[:10]])
            embed.add_field(
                name="Most Active Rollers",
                value=user_list or "No data",
                inline=False
            )
        else:
            embed.add_field(
                name="Activity",
                value="No rolls recorded in this channel",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="recent_luck")
    async def recent_luck(self, ctx: commands.Context, hours: int = 24, user: discord.Member = None):
        """Show luck trend over the last X hours (max 24)."""
        if not 1 <= hours <= 24:
            await ctx.send("Hours must be between 1 and 24.")
            return
        
        target_user = user or ctx.author
        user_data = await self.config.user(target_user).all()
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_rolls = []
        for roll_type in ["standard_rolls", "luck_rolls", "karma_rolls"]:
            for roll in user_data["stats"]["server_wide"][roll_type]:
                roll_time = datetime.fromisoformat(roll["timestamp"])
                if roll_time >= cutoff_time:
                    recent_rolls.append(roll)
        
        if not recent_rolls:
            await ctx.send(f"No rolls found in the last {hours} hours.")
            return
        
        # Calculate recent luck using percentiles for meaningful comparison
        recent_percentiles = []
        for roll in recent_rolls:
            percentile = self._calculate_roll_percentile(roll["roll_string"], roll["result"])
            if percentile is not None:
                recent_percentiles.append(percentile)
        
        embed = discord.Embed(
            title=f"Recent Luck Trend - {target_user.display_name}",
            description=f"Last {hours} hours",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="Recent Rolls",
            value=len(recent_rolls),
            inline=True
        )
        
        if recent_percentiles:
            recent_luck = sum(recent_percentiles) / len(recent_percentiles)
            embed.add_field(
                name="Recent Luck",
                value=f"{recent_luck:.1f}",
                inline=True
            )
        else:
            embed.add_field(
                name="Recent Luck",
                value="No trackable rolls",
                inline=True
            )
        
        embed.add_field(
            name="Overall Luck",
            value=f"{user_data['stats']['server_wide']['natural_luck']:.1f}",
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    # --- ADMIN EXPORT COMMANDS ---
    
    @commands.command(name="admin_stats")
    @commands.has_permissions(administrator=True)
    async def admin_stats(self, ctx: commands.Context, user: discord.Member):
        """Admin view of complete user statistics."""
        user_data = await self.config.user(user).all()
        
        embed = discord.Embed(
            title=f"Admin Statistics - {user.display_name}",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="Toggles",
            value=f"Luck: {user_data['toggles']['luckmode_on']}\nKarma: {user_data['toggles']['karmamode_on']}",
            inline=True
        )
        
        embed.add_field(
            name="Settings",
            value=f"Set Luck: {user_data['set_luck']}\nKarma: {user_data.get('percentile_debt', 0.0):+.1f}",
            inline=True
        )
        
        stats = user_data["stats"]["server_wide"]
        embed.add_field(
            name="Roll Counts",
            value=f"Standard: {len(stats['standard_rolls'])}\nLuck: {len(stats['luck_rolls'])}\nKarma: {len(stats['karma_rolls'])}",
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name="export_user")
    @commands.has_permissions(administrator=True)
    async def export_user(self, ctx: commands.Context, user: discord.Member):
        """Export user's complete roll history."""
        user_data = await self.config.user(user).all()
        
        # Create export data
        export_lines = [f"Roll History Export for {user.display_name}"]
        export_lines.append(f"Generated: {datetime.now().isoformat()}")
        export_lines.append("")
        
        for roll_type in ["standard_rolls", "luck_rolls", "karma_rolls"]:
            rolls = user_data["stats"]["server_wide"][roll_type]
            if rolls:
                export_lines.append(f"=== {roll_type.replace('_', ' ').title()} ===")
                for roll in rolls:
                    export_lines.append(f"{roll['timestamp']}: {roll['roll_string']} = {roll['result']}")
                export_lines.append("")
        
        # Send as file
        export_text = "\n".join(export_lines)
        file = discord.File(
            fp=discord.utils.BytesIO(export_text.encode()),
            filename=f"{user.display_name}_roll_history.txt"
        )
        
        await ctx.send(f"Roll history export for {user.display_name}:", file=file)

    # --- WEIGHTED ROLLING FUNCTIONS ---
    
    def _roll_weighted_standard_die(self, die_size: int, debt: float) -> int:
        """Roll a single standard die with karma/luck bias using weighted probabilities."""
        if abs(debt) < 5.0:  # Activation threshold - no significant debt, roll normally
            return random.randint(1, die_size)
        
        # Create weights for each face
        weights = [1.0] * die_size
        
        # Calculate bias strength (0 to 1)
        bias_strength = min(abs(debt) / 50.0, 1.0)
        
        # Apply bias to weights
        midpoint = (die_size + 1) / 2
        for i in range(die_size):
            face_value = i + 1
            
            if debt > 0:  # Owed good luck - bias toward higher values
                if face_value > midpoint:
                    weights[i] *= (1.0 + bias_strength * 0.4)  # Boost good faces
                else:
                    weights[i] *= (1.0 - bias_strength * 0.2)  # Reduce bad faces
            else:  # Owed bad luck - bias toward lower values
                if face_value < midpoint:
                    weights[i] *= (1.0 + bias_strength * 0.4)  # Boost bad faces
                else:
                    weights[i] *= (1.0 - bias_strength * 0.2)  # Reduce good faces
        
        # Roll using weighted probabilities
        return random.choices(range(1, die_size + 1), weights=weights)[0]
    
    def _roll_weighted_fudge_dice(self, num_dice: int, debt: float) -> tuple:
        """Roll fudge dice with karma/luck bias using weighted sum distribution."""
        if abs(debt) < 5.0 or num_dice not in FUDGE_PROBABILITIES:
            # Activation threshold - no significant debt or unsupported dice count, roll normally
            dice_results = [random.choice(FUDGE_FACES) for _ in range(num_dice)]
            return dice_results, sum(dice_results)
        
        # Get natural probabilities for this number of dice
        natural_probs = FUDGE_PROBABILITIES[num_dice].copy()
        
        # Apply bias to probabilities
        bias_strength = min(abs(debt) / 75.0, 0.8)  # Max 80% bias for fudge
        
        for sum_value in natural_probs:
            if debt > 0:  # Owed good luck - bias toward positive sums
                if sum_value > 0:
                    natural_probs[sum_value] *= (1.0 + bias_strength * 0.5)
                elif sum_value < 0:
                    natural_probs[sum_value] *= (1.0 - bias_strength * 0.3)
            else:  # Owed bad luck - bias toward negative sums
                if sum_value < 0:
                    natural_probs[sum_value] *= (1.0 + bias_strength * 0.5)
                elif sum_value > 0:
                    natural_probs[sum_value] *= (1.0 - bias_strength * 0.3)
        
        # Normalize probabilities
        total_prob = sum(natural_probs.values())
        for sum_value in natural_probs:
            natural_probs[sum_value] /= total_prob
        
        # Roll weighted sum
        sums = list(natural_probs.keys())
        weights = list(natural_probs.values())
        target_sum = random.choices(sums, weights=weights)[0]
        
        # Generate realistic-looking dice faces that sum to target
        dice_results = self._generate_realistic_fudge_faces(num_dice, target_sum)
        
        return dice_results, target_sum
    
    def _generate_realistic_fudge_faces(self, num_dice: int, target_sum: int) -> list:
        """Generate realistic fudge dice faces that sum to target while looking natural."""
        # Clamp target to possible range
        target_sum = max(-num_dice, min(num_dice, target_sum))
        
        # Start with all zeros
        dice = [0] * num_dice
        remaining = target_sum
        
        # First pass: distribute the sum efficiently
        for i in range(num_dice):
            if remaining > 0:
                # Add positive faces, but don't exceed what we need
                add_amount = min(1, remaining)
                dice[i] = add_amount
                remaining -= add_amount
            elif remaining < 0:
                # Add negative faces
                subtract_amount = max(-1, remaining)
                dice[i] = subtract_amount
                remaining -= subtract_amount
        
        # Second pass: randomize the distribution while maintaining sum
        # This makes the faces look more natural by spreading values around
        for _ in range(num_dice * 2):  # Multiple randomization passes
            # Pick two random dice
            i, j = random.sample(range(num_dice), 2)
            
            # Try to transfer value from one to another (keeping sum constant)
            if dice[i] > -1 and dice[j] < 1:  # Can transfer from i to j
                if random.random() < 0.3:  # 30% chance to make this swap
                    dice[i] -= 1
                    dice[j] += 1
            elif dice[i] < 1 and dice[j] > -1:  # Can transfer from j to i
                if random.random() < 0.3:
                    dice[i] += 1
                    dice[j] -= 1
        
        # Final shuffle to randomize position
        random.shuffle(dice)
        
        return dice
    
    async def _roll_standard_dice_with_karma(self, ctx: commands.Context, roll_string: str):
        """Roll standard dice with karma bias applied."""
        import re
        
        user_data = await self.config.user(ctx.author).all()
        debt = user_data.get("percentile_debt", 0.0)
        
        # Check if this is a simple single die roll we can bias
        simple_match = re.match(r'^(\d+)d(\d+)(?:([+-])(\d+))?$', roll_string.lower())
        
        if simple_match and abs(debt) > 5.0:
            num_dice = int(simple_match.group(1))
            die_size = int(simple_match.group(2))
            modifier_sign = simple_match.group(3)
            modifier_value = int(simple_match.group(4)) if simple_match.group(4) else 0
            
            if modifier_sign == '-':
                modifier_value = -modifier_value
            
            # Only apply bias to simple rolls without advanced operations
            if num_dice <= 10:  # Reasonable limit
                # Roll each die with karma bias
                dice_results = []
                for _ in range(num_dice):
                    die_result = self._roll_weighted_standard_die(die_size, debt)
                    dice_results.append(die_result)

                dice_total = sum(dice_results)
                final_total = dice_total + modifier_value

                return DiceRollResult(final_total, dice_results, modifier_value)
        
        # Fall back to normal d20 library for complex expressions or low debt
        translated_expression = self._translate_dice_syntax(roll_string)
        return d20.roll(translated_expression)
    
    async def _roll_standard_dice_with_luck(self, ctx: commands.Context, roll_string: str):
        """Roll standard dice with luck bias applied."""
        import re
        
        user_data = await self.config.user(ctx.author).all()
        luck_value = user_data["set_luck"]
        
        # Convert luck (0-100) to debt-like value (-50 to +50)
        luck_debt = (luck_value - 50.0)
        
        # Check if this is a simple single die roll we can bias
        simple_match = re.match(r'^(\d+)d(\d+)(?:([+-])(\d+))?$', roll_string.lower())

        if simple_match and abs(luck_debt) > 5.0:  # Activation threshold
            num_dice = int(simple_match.group(1))
            die_size = int(simple_match.group(2))
            modifier_sign = simple_match.group(3)
            modifier_value = int(simple_match.group(4)) if simple_match.group(4) else 0
            
            if modifier_sign == '-':
                modifier_value = -modifier_value
            
            # Only apply bias to simple rolls without advanced operations
            if num_dice <= 10:  # Reasonable limit
                # Roll each die with luck bias
                dice_results = []
                for _ in range(num_dice):
                    die_result = self._roll_weighted_standard_die(die_size, luck_debt)
                    dice_results.append(die_result)

                dice_total = sum(dice_results)
                final_total = dice_total + modifier_value

                return DiceRollResult(final_total, dice_results, modifier_value)
        
        # Fall back to normal d20 library for complex expressions or neutral luck
        translated_expression = self._translate_dice_syntax(roll_string)
        return d20.roll(translated_expression)
    
    # --- HELPER FUNCTIONS ---

    def _parse_roll_and_label(self, roll_string: str) -> tuple:
        """Parse roll string into dice expression and optional label.

        Examples:
        - "1d20+5" -> ("1d20+5", None)
        - "1d20+5 perception" -> ("1d20+5", "perception")
        - "2d6 fireball damage" -> ("2d6", "fireball damage")

        Returns:
            tuple: (dice_expression, label or None)
        """
        parts = roll_string.split(None, 1)  # Split on first whitespace
        if len(parts) == 1:
            return parts[0], None
        return parts[0], parts[1]

    def _translate_dice_syntax(self, expression: str) -> str:
        """Translate user-friendly dice syntax to d20 library syntax.

        Supports optional numbers (defaults to 1):
        - "2d20dl" -> "2d20kh1" (drop lowest 1 = keep highest 1)
        - "2d20dl1" -> "2d20kh1" (explicit drop lowest 1 = keep highest 1)
        - "4d6dl" -> "4d6kh3" (drop lowest 1 from 4d6 = keep highest 3)
        - "3d20dh" -> "3d20kl2" (drop highest 1 from 3d20 = keep lowest 2)
        - "2d20kh" -> "2d20kh1" (keep highest 1)
        - "2d20kl" -> "2d20kl1" (keep lowest 1)
        """
        import re

        # Handle drop lowest (dl) -> convert to keep highest (kh)
        # Match patterns like: 2d20dl, 2d20dl1, 4d6dl1+5, 3d8dl2-1
        dl_pattern = r'(\d+)d(\d+)dl(\d*)'
        def dl_to_kh(match):
            num_dice = int(match.group(1))
            die_size = match.group(2)
            drop_count = int(match.group(3)) if match.group(3) else 1  # Default to 1
            keep_count = num_dice - drop_count
            if keep_count <= 0:
                # Can't drop more dice than we have, fall back to original
                return match.group(0)
            return f"{num_dice}d{die_size}kh{keep_count}"

        expression = re.sub(dl_pattern, dl_to_kh, expression)

        # Handle drop highest (dh) -> convert to keep lowest (kl)
        # Match patterns like: 3d20dh, 3d20dh1, 5d8dh2+3
        dh_pattern = r'(\d+)d(\d+)dh(\d*)'
        def dh_to_kl(match):
            num_dice = int(match.group(1))
            die_size = match.group(2)
            drop_count = int(match.group(3)) if match.group(3) else 1  # Default to 1
            keep_count = num_dice - drop_count
            if keep_count <= 0:
                # Can't drop more dice than we have, fall back to original
                return match.group(0)
            return f"{num_dice}d{die_size}kl{keep_count}"

        expression = re.sub(dh_pattern, dh_to_kl, expression)

        # Handle keep highest (kh) with optional number
        # Match patterns like: 2d20kh, 2d20kh1, 4d6kh3+5
        kh_pattern = r'(\d+)d(\d+)kh(\d*)'
        def kh_explicit(match):
            num_dice = match.group(1)
            die_size = match.group(2)
            keep_count = match.group(3) if match.group(3) else '1'  # Default to 1
            return f"{num_dice}d{die_size}kh{keep_count}"

        expression = re.sub(kh_pattern, kh_explicit, expression)

        # Handle keep lowest (kl) with optional number
        # Match patterns like: 2d20kl, 2d20kl1, 4d6kl2+3
        kl_pattern = r'(\d+)d(\d+)kl(\d*)'
        def kl_explicit(match):
            num_dice = match.group(1)
            die_size = match.group(2)
            keep_count = match.group(3) if match.group(3) else '1'  # Default to 1
            return f"{num_dice}d{die_size}kl{keep_count}"

        expression = re.sub(kl_pattern, kl_explicit, expression)

        return expression
    
    def _extract_base_dice(self, expression: str) -> str:
        """Extract the base dice notation from a complex expression.
        
        Examples:
        - "4d6kh3+2" -> "4d6"
        - "1d20ro<3+5" -> "1d20"
        - "2d10e10mi2" -> "2d10"
        """
        import re
        
        # Match basic dice pattern at the start
        match = re.match(r'(\d+d\d+)', expression.lower())
        if match:
            return match.group(1)
        
        # Fallback to parsing dice modifiers for simple cases
        dice_part, _ = self._parse_dice_modifiers(expression)
        return dice_part
    
    async def _handle_test_queue_standard_dice(self, ctx: commands.Context, roll_string: str, queued_result: int, roll_type: str):
        """Handle queued test results for standard dice with advanced operations."""
        import re
        
        # Check if this has advanced operations
        has_advanced = bool(re.search(r'(kh|kl|dh|dl|ro|rr|ra|e|mi|ma|p)\d*', roll_string.lower()))
        
        if not has_advanced:
            # Simple case - just set the basic dice result
            dice_part, modifier = self._parse_dice_modifiers(roll_string)

            actual_total = queued_result + modifier
            modifier_str = ""
            if modifier > 0:
                modifier_str = f"+{modifier}"
            elif modifier < 0:
                modifier_str = str(modifier)

            display_result = f"{dice_part} ({queued_result}){modifier_str}"
            return SimpleRollResult(actual_total, display_result)
        else:
            # Complex case - we can't easily set the result with advanced operations
            # So we'll just roll normally and note it in the output
            translated_expression = self._translate_dice_syntax(roll_string)
            result = d20.roll(translated_expression)
            return result