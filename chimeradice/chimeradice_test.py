"""
ChimeraDice Test Utilities
Local testing extension for development. Not included in public repository.
"""

import discord
import re
from datetime import datetime
from redbot.core import commands

# Import pure functions from core module
from .chimeradice_core import normalize_dice_key, validate_dice_expression


def setup_test_commands(cog):
    """Set up test command handler for the ChimeraDice cog.

    This sets a handler function that will be called by the fr2 command stub.
    """

    async def test_handler(ctx, args):
        """Local test command for simulating dice results. DM-only."""

        # Silently fail if not in DM
        if not isinstance(ctx.channel, discord.DMChannel):
            return

        if not args:
            return await ctx.send("Usage:\n• `>fr2 1d20 15` (force your own roll)\n• `>fr2 123456789012345678 1d20 15` (force specific user by Discord ID)\nTip: Enable Developer Mode in Discord to copy user IDs")

        parts = args.split()
        if len(parts) < 2:
            return await ctx.send("You must specify dice type and result(s).")

        # Determine if first part is username or dice expression
        target = None
        dice_start_idx = 0

        # Check if first part looks like a dice expression or username
        first_part = parts[0]
        # A dice expression typically has pattern like: XdY, XdF, XdD
        is_dice_expr = bool(re.match(r'\d+d[a-zA-Z0-9]', first_part.lower()))

        if not is_dice_expr and len(parts) >= 3:
            # First part is likely a username since it's not a dice expression and we have enough parts
            target = first_part
            dice_start_idx = 1
        elif len(parts) < 2:
            return await ctx.send("You must specify dice type and result(s).")

        dice_expr = parts[dice_start_idx]
        results_str = parts[dice_start_idx + 1:]

        if not results_str:
            return await ctx.send("You must specify at least one result value.")

        # Validate dice expression
        is_valid, error_msg = cog._validate_dice_expression_with_d20(dice_expr)
        if not is_valid:
            return await ctx.send(f"Invalid dice expression: {error_msg}")

        # Handle negative numbers that got split by Discord parsing
        reconstructed_results = []
        i = 0
        while i < len(results_str):
            if results_str[i] == '-' and i + 1 < len(results_str) and results_str[i + 1].isdigit():
                # Combine - with the next number
                reconstructed_results.append('-' + results_str[i + 1])
                i += 2
            else:
                reconstructed_results.append(results_str[i])
                i += 1

        try:
            results = [int(x) for x in reconstructed_results]
        except ValueError as e:
            return await ctx.send(f"Result values must be integers. Error: {e} (got: {reconstructed_results})")

        # Validate that results are possible for this dice type
        is_valid, error_msg = cog._validate_queued_results(dice_expr, results)
        if not is_valid:
            return await ctx.send(f"Invalid queued results: {error_msg}")

        # Determine target user by username lookup
        user_id = ctx.author.id  # Default to self
        target_name = "your"

        if target:
            found_user = None

            # Try to parse as Discord ID first (for DM usage)
            if target.isdigit() or (target.startswith('<@') and target.endswith('>')):
                try:
                    # Handle both raw ID and mention format
                    if target.startswith('<@'):
                        user_id_str = target.strip('<@!>')
                    else:
                        user_id_str = target

                    target_user_id = int(user_id_str)
                    found_user = cog.bot.get_user(target_user_id)

                    if not found_user:
                        return await ctx.send(f"Could not find user with ID {target_user_id}. Make sure the bot can see this user.")

                except ValueError:
                    return await ctx.send(f"Invalid user ID: {target}")

            # In DMs, only Discord IDs work (no guild context available)
            else:
                return await ctx.send(f"In DMs, you must use a Discord user ID. Example: `>fr2 123456789012345678 1d20 15`\nTo get a user's ID: Enable Developer Mode in Discord, right-click the user, and select 'Copy ID'.")

            if found_user:
                user_id = found_user.id
                target_name = f"{found_user.display_name}'s"

        # Store queued test roll using normalized key
        normalized_key = normalize_dice_key(dice_expr)

        if user_id not in cog.test_queue:
            cog.test_queue[user_id] = {}

        if normalized_key not in cog.test_queue[user_id]:
            cog.test_queue[user_id][normalized_key] = {
                "values": [],
                "timestamp": datetime.now()
            }

        # Add the new results and update timestamp
        cog.test_queue[user_id][normalized_key]["values"].extend(results)
        cog.test_queue[user_id][normalized_key]["timestamp"] = datetime.now()

        await ctx.send(f"✅ Set {target_name} next `{dice_expr}` roll(s): `{', '.join(map(str, results))}`")

    # Set the handler on the cog instance
    cog._test_handler = test_handler
