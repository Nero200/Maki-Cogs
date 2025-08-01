# custodianre.py - Refactored Custodian Cog
import discord
import asyncio
import datetime
import logging
import re
import random
from typing import Literal, Optional, Dict, List, Tuple, Any, Union
from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import box, pagify

# Set up logging
log = logging.getLogger("red.custodian")

# Constants
DEFAULT_BREACH_TYPES = {
    "hand": 1,
    "hound": 2, 
    "mole": 5,
}

CONFIG_IDENTIFIER = 987654321987654321  # More unique identifier

class DataManager:
    """Handles all data operations and caching"""
    
    def __init__(self, config: Config):
        self.config = config
        self._cache = {}
        self._cache_ttl = {}
        self.cache_timeout = 300  # 5 minutes
    
    async def get_cached(self, guild_id: int, key: str, default=None):
        """Get cached data or fetch from config"""
        cache_key = f"{guild_id}:{key}"
        now = datetime.datetime.now()
        
        if cache_key in self._cache:
            if cache_key in self._cache_ttl and now < self._cache_ttl[cache_key]:
                return self._cache[cache_key]
        
        # Cache miss or expired, fetch from config
        guild_config = self.config.guild_from_id(guild_id)
        data = await getattr(guild_config, key)() if hasattr(guild_config, key) else default
        
        # Cache the result
        self._cache[cache_key] = data
        self._cache_ttl[cache_key] = now + datetime.timedelta(seconds=self.cache_timeout)
        
        return data
    
    def invalidate_cache(self, guild_id: int, key: str = None):
        """Invalidate cache for specific key or all keys for guild"""
        if key:
            cache_key = f"{guild_id}:{key}"
            self._cache.pop(cache_key, None)
            self._cache_ttl.pop(cache_key, None)
        else:
            # Clear all cache for guild
            guild_prefix = f"{guild_id}:"
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(guild_prefix)]
            for k in keys_to_remove:
                self._cache.pop(k, None)
                self._cache_ttl.pop(k, None)

class InputValidator:
    """Handles input validation and sanitization"""
    
    @staticmethod
    def validate_thinspace_name(name: str) -> Tuple[bool, str]:
        """Validate thinspace name format"""
        if not name:
            return False, "Thinspace name cannot be empty"
        
        # Normalize the name
        normalized = name.upper().strip()
        
        # Check format (AA-BB)
        if not re.match(r'^[A-Z]{1,3}-[A-Z]{1,3}$', normalized):
            return False, "Thinspace name must be in format AA-BB (letters only)"
        
        return True, normalized
    
    @staticmethod
    def validate_breach_count(count_str: str) -> Tuple[bool, int]:
        """Validate breach count input"""
        try:
            count = int(count_str)
            if count < 0:
                return False, 0
            if count > 100:  # Reasonable upper limit
                return False, 0
            return True, count
        except ValueError:
            return False, 0
    
    @staticmethod
    def sanitize_user_input(text: str, max_length: int = 100) -> str:
        """Sanitize user input for safe display"""
        if not text:
            return ""
        
        # Remove potential formatting exploits
        sanitized = text.replace('`', '').replace('*', '').replace('_', '')
        
        # Truncate if too long
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + "..."
        
        return sanitized

class MessageFormatter:
    """Handles message formatting and display"""
    
    # ANSI color codes
    ANSI_RESET = "\u001b[0m"
    ANSI_RED = "\u001b[0;31m"
    ANSI_GREEN = "\u001b[0;32m"
    ANSI_YELLOW = "\u001b[0;33m"
    ANSI_BLUE = "\u001b[0;34m"
    ANSI_MAGENTA = "\u001b[0;35m"
    ANSI_CYAN = "\u001b[0;36m"
    
    @classmethod
    def format_trio_list(cls, trios: Dict[str, Dict], title: str = "Trio Inventory") -> List[str]:
        """Format trio list for display"""
        if not trios:
            return ["No trios to display."]
        
        lines = []
        for trio_id, trio_data in sorted(trios.items(), key=lambda x: int(x[0])):
            if not isinstance(trio_data, dict):
                lines.append(f"Trio #{trio_id}: {cls.ANSI_RED}Error - Malformed Data{cls.ANSI_RESET}")
                continue
            
            name = trio_data.get("name", f"Trio #{trio_id}")
            abilities = trio_data.get("abilities", ["Unknown"] * 3)
            abilities_padded = (abilities + ["Unknown"] * 3)[:3]
            
            abilities_str = f"[{cls.ANSI_CYAN}{abilities_padded[0]}{cls.ANSI_RESET}, " \
                           f"{cls.ANSI_CYAN}{abilities_padded[1]}{cls.ANSI_RESET}, " \
                           f"{cls.ANSI_CYAN}{abilities_padded[2]}{cls.ANSI_RESET}]"
            
            # Format status
            holder_id = trio_data.get("holder_id")
            holder_name = trio_data.get("holder_name")
            
            if holder_id == "IN_BOWL":
                status = f"{cls.ANSI_MAGENTA}In a Bowl{cls.ANSI_RESET}"
            elif holder_id and holder_name:
                status = f"{cls.ANSI_YELLOW}{holder_name}{cls.ANSI_RESET}"
            else:
                status = f"{cls.ANSI_BLUE}In the Well{cls.ANSI_RESET}"
            
            lines.append(f"{name} {abilities_str} - {status}")
        
        return lines
    
    @classmethod
    def create_paginated_embeds(cls, lines: List[str], title: str, 
                               color: discord.Color, lines_per_page: int = 15) -> List[discord.Embed]:
        """Create paginated embeds from text lines"""
        if not lines:
            embed = discord.Embed(title=title, description="No data to display.", color=color)
            return [embed]
        
        embeds = []
        total_pages = (len(lines) + lines_per_page - 1) // lines_per_page
        
        for i in range(0, len(lines), lines_per_page):
            chunk = lines[i:i + lines_per_page]
            page_num = i // lines_per_page + 1
            
            page_title = title
            if total_pages > 1:
                page_title += f" (Page {page_num}/{total_pages})"
            
            content = '\n'.join(chunk)
            description = f"```ansi\n{content}\n```" if content else "No data for this page."
            
            embed = discord.Embed(title=page_title, description=description, color=color)
            embeds.append(embed)
        
        return embeds

class TrioManager:
    """Manages trio-related operations"""
    
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
    
    async def find_trio_by_identifier(self, guild: discord.Guild, identifier: str) -> Optional[Tuple[str, Dict]]:
        """Find trio by number or ability name"""
        trios = await self.data_manager.get_cached(guild.id, "trios_inventory", {})
        
        # Try numeric lookup first
        try:
            trio_num = str(int(identifier))
            if trio_num in trios:
                return trio_num, trios[trio_num]
        except ValueError:
            pass
        
        # Search by ability name (case-insensitive)
        identifier_lower = identifier.lower()
        for trio_id, trio_data in trios.items():
            if isinstance(trio_data, dict):
                abilities = trio_data.get("abilities", [])
                for ability in abilities:
                    if isinstance(ability, str) and ability.lower() == identifier_lower:
                        return trio_id, trio_data
        
        return None
    
    async def find_user_trio(self, guild: discord.Guild, user_id: int) -> Optional[Tuple[str, Dict]]:
        """Find trio held by specific user"""
        trios = await self.data_manager.get_cached(guild.id, "trios_inventory", {})
        
        for trio_id, trio_data in trios.items():
            if isinstance(trio_data, dict) and trio_data.get("holder_id") == user_id:
                return trio_id, trio_data
        
        return None

class ThinspaceManager:
    """Manages thinspace operations"""
    
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
    
    @staticmethod
    def normalize_thinspace_name(name: str) -> str:
        """Normalize thinspace name to standard format"""
        return name.upper().strip()
    
    async def get_thinspace(self, guild: discord.Guild, space_name: str) -> Optional[Dict]:
        """Get thinspace data"""
        normalized_name = self.normalize_thinspace_name(space_name)
        thinspaces = await self.data_manager.get_cached(guild.id, "thinspaces", {})
        return thinspaces.get(normalized_name)
    
    async def create_thinspace(self, guild: discord.Guild, space_name: str, limit: int = 14) -> bool:
        """Create new thinspace"""
        is_valid, normalized_name = InputValidator.validate_thinspace_name(space_name)
        if not is_valid:
            return False
        
        async with self.data_manager.config.guild(guild).thinspaces() as thinspaces:
            if normalized_name in thinspaces:
                return False
            
            thinspaces[normalized_name] = {
                "pre_gate_breaches": 0,
                "post_gate_breaches": 0,
                "gated": False,
                "limit": limit
            }
        
        self.data_manager.invalidate_cache(guild.id, "thinspaces")
        return True

class ErrorHandler:
    """Centralized error handling"""
    
    @staticmethod
    async def handle_discord_error(ctx: commands.Context, error: Exception, operation: str):
        """Handle Discord API errors gracefully"""
        if isinstance(error, discord.HTTPException):
            log.error(f"Discord HTTP error during {operation}: {error.status} {error.text}")
            await ctx.send(f"❌ Discord API error during {operation}. Please try again later.")
        elif isinstance(error, discord.NotFound):
            log.warning(f"Resource not found during {operation}")
            await ctx.send(f"❌ Resource not found during {operation}.")
        else:
            log.exception(f"Unexpected error during {operation}")
            await ctx.send(f"❌ An unexpected error occurred during {operation}.")

class WeeklyResetManager:
    """Manages weekly reset functionality"""
    
    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager
        self._reset_task = None
    
    async def calculate_next_reset(self, guild: discord.Guild) -> Optional[datetime.datetime]:
        """Calculate next reset datetime"""
        reset_day = await self.data_manager.get_cached(guild.id, "reset_day", 5)
        reset_hour = await self.data_manager.get_cached(guild.id, "reset_hour_utc", 5)
        reset_minute = await self.data_manager.get_cached(guild.id, "reset_minute_utc", 0)
        
        now = datetime.datetime.now(datetime.timezone.utc)
        
        # Find next occurrence of reset day/time
        days_ahead = reset_day - now.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        
        next_reset = now.replace(
            hour=reset_hour, 
            minute=reset_minute, 
            second=0, 
            microsecond=0
        ) + datetime.timedelta(days=days_ahead)
        
        return next_reset
    
    async def perform_reset(self, guild: discord.Guild) -> Tuple[str, str, Optional[datetime.datetime]]:
        """Perform weekly reset and return log messages"""
        try:
            # Reset thinspaces
            async with self.data_manager.config.guild(guild).thinspaces() as thinspaces:
                for space_data in thinspaces.values():
                    space_data["pre_gate_breaches"] = 0
                    space_data["post_gate_breaches"] = 0
                    space_data["gated"] = False
            
            # Reset dreams
            max_dreams = await self.data_manager.get_cached(guild.id, "max_dreams", 3)
            await self.data_manager.config.guild(guild).dreams_left.set(max_dreams)
            
            # Reset artifacts status
            async with self.data_manager.config.guild(guild).weekly_artifacts() as artifacts:
                for artifact_data in artifacts.values():
                    if artifact_data.get("status") == "Used":
                        artifact_data["status"] = "Available"
                        artifact_data.pop("used_by", None)
            
            # Increment cycle
            current_cycle = await self.data_manager.get_cached(guild.id, "cycle_number", 1)
            await self.data_manager.config.guild(guild).cycle_number.set(current_cycle + 1)
            
            # Clear cache
            self.data_manager.invalidate_cache(guild.id)
            
            # Calculate next reset
            next_reset = await self.calculate_next_reset(guild)
            
            log_message = f"Weekly reset completed for {guild.name} (ID: {guild.id})"
            cycle_message = f"🔄 **Weekly Reset Complete!**\nCycle #{current_cycle + 1} has begun."
            
            return log_message, cycle_message, next_reset
            
        except Exception as e:
            log.exception(f"Error during weekly reset for guild {guild.id}")
            error_msg = f"❌ Error during weekly reset: {str(e)}"
            return error_msg, error_msg, None

# UI Views
# Complete UI Views
class TrioClaimSelectView(discord.ui.View):
    """View for selecting trios to claim"""
    
    def __init__(self, cog, interaction_user: discord.User, available_trios: Dict[str, Dict], timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.interaction_user = interaction_user
        self.available_trios = available_trios
        
        # Create select menu for trios
        options = []
        for trio_id, trio_data in sorted(available_trios.items(), key=lambda x: int(x[0]))[:25]:  # Discord limit
            name = trio_data.get("name", f"Trio #{trio_id}")
            abilities = trio_data.get("abilities", ["Unknown"] * 3)
            description = f"Abilities: {', '.join(abilities[:3])}"
            options.append(discord.SelectOption(
                label=name,
                value=trio_id,
                description=description[:100]  # Discord limit
            ))
        
        if options:
            self.trio_select = discord.ui.Select(
                placeholder="Choose a trio to claim...",
                options=options,
                custom_id="claim_trio_select"
            )
            self.trio_select.callback = self.trio_selected
            self.add_item(self.trio_select)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction_user.id:
            await interaction.response.send_message("This selection is only for the requesting user.", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
    
    async def trio_selected(self, interaction: discord.Interaction):
        """Handle trio selection"""
        await interaction.response.defer()
        
        trio_id = self.trio_select.values[0]
        trio_data = self.available_trios.get(trio_id)
        
        if not trio_data:
            await interaction.followup.send("❌ Selected trio no longer available.", ephemeral=True)
            return
        
        try:
            # Check if user already has a trio
            existing_trio = await self.cog.trio_manager.find_user_trio(interaction.guild, interaction.user.id)
            if existing_trio:
                await interaction.followup.send("❌ You already have a trio. Drop your current trio first.", ephemeral=True)
                return
            
            # Claim the trio
            async with self.cog.config.guild(interaction.guild).trios_inventory() as trios:
                if trio_id in trios and trios[trio_id].get("holder_id") is None:
                    trios[trio_id]["holder_id"] = interaction.user.id
                    trios[trio_id]["holder_name"] = interaction.user.display_name
                else:
                    await interaction.followup.send("❌ This trio is no longer available.", ephemeral=True)
                    return
            
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            await interaction.followup.send(f"✅ You have claimed **{trio_name}**!")
            
            # Disable view and invalidate cache
            for item in self.children:
                item.disabled = True
            await interaction.edit_original_response(view=self)
            
            self.cog.data_manager.invalidate_cache(interaction.guild.id, "trios_inventory")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(interaction, e, "claiming trio")

class UserSelectView(discord.ui.View):
    """View for selecting users - simplified version without user_select"""
    
    def __init__(self, cog, original_user_id: int, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.original_user_id = original_user_id
        
        # Add a button to prompt for user mention instead
        self.user_button = discord.ui.Button(
            label="Click to select user (mention them)",
            style=discord.ButtonStyle.primary,
            custom_id="select_user_prompt"
        )
        self.user_button.callback = self.prompt_user_selection
        self.add_item(self.user_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original_user_id:
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
    
    async def prompt_user_selection(self, interaction: discord.Interaction):
        """Prompt user to mention someone"""
        await interaction.response.send_message(
            "Please use the `trio` command with a user mention instead.\n"
            "Example: `[p]trio @username`",
            ephemeral=True
        )
        
        # Disable view
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

class BowlManagementView(discord.ui.View):
    """View for managing bowl trios"""
    
    def __init__(self, cog, original_user_id: int, bowl_trios: Dict[str, Dict], timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.original_user_id = original_user_id
        self.bowl_trios = bowl_trios
        
        # Create select menu for bowl trios
        options = []
        for trio_id, trio_data in sorted(bowl_trios.items(), key=lambda x: int(x[0]))[:25]:
            name = trio_data.get("name", f"Trio #{trio_id}")
            abilities = trio_data.get("abilities", ["Unknown"] * 3)
            description = f"Abilities: {', '.join(abilities[:3])}"
            options.append(discord.SelectOption(
                label=name,
                value=trio_id,
                description=description[:100]
            ))
        
        if options:
            self.trio_select = discord.ui.Select(
                placeholder="Choose a trio to manage...",
                options=options,
                custom_id="bowl_trio_select"
            )
            self.trio_select.callback = self.trio_selected
            self.add_item(self.trio_select)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original_user_id:
            # Allow admins
            if interaction.guild:
                member = interaction.guild.get_member(interaction.user.id)
                if member and member.guild_permissions.manage_guild:
                    return True
            await interaction.response.send_message("This is not for you.", ephemeral=True)
            return False
        return True
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
    
    async def trio_selected(self, interaction: discord.Interaction):
        """Handle trio selection for bowl management"""
        await interaction.response.defer()
        
        trio_id = self.trio_select.values[0]
        trio_data = self.bowl_trios.get(trio_id)
        
        if not trio_data:
            await interaction.followup.send("❌ Selected trio no longer in bowl.", ephemeral=True)
            return
        
        # Create action buttons for this trio
        view = BowlTrioActionView(self.cog, trio_id, trio_data.get("name", f"Trio #{trio_id}"))
        
        trio_name = trio_data.get("name", f"Trio #{trio_id}")
        abilities = trio_data.get("abilities", ["Unknown"] * 3)
        abilities_str = ", ".join(abilities[:3])
        
        embed = discord.Embed(
            title=f"Bowl Management: {trio_name}",
            description=f"**Abilities:** {abilities_str}\n\nWhat would you like to do with this trio?",
            color=discord.Color.orange()
        )
        
        await interaction.followup.send(embed=embed, view=view)

class BowlTrioActionView(discord.ui.View):
    """Action view for specific bowl trio"""
    
    def __init__(self, cog, trio_id: str, trio_name: str, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.trio_id = trio_id
        self.trio_name = trio_name
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
    
    @discord.ui.button(label="Return to Well", style=discord.ButtonStyle.primary)
    async def return_to_well(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Return trio from bowl to well"""
        await interaction.response.defer()
        
        try:
            async with self.cog.config.guild(interaction.guild).trios_inventory() as trios:
                if self.trio_id in trios and trios[self.trio_id].get("holder_id") == "IN_BOWL":
                    trios[self.trio_id]["holder_id"] = None
                    trios[self.trio_id]["holder_name"] = None
                else:
                    await interaction.followup.send("❌ Trio is no longer in bowl.", ephemeral=True)
                    return
            
            await interaction.followup.send(f"✅ **{self.trio_name}** has been returned to the Well.")
            
            # Disable buttons
            for item in self.children:
                item.disabled = True
            await interaction.edit_original_response(view=self)
            
            self.cog.data_manager.invalidate_cache(interaction.guild.id, "trios_inventory")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(interaction, e, "returning trio to well")

class PersistentTrioControlView(discord.ui.View):
    """Persistent control panel for trio management"""
    
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
    
    @discord.ui.button(label="Manage My Trio", style=discord.ButtonStyle.success, custom_id="persist_trio_mine")
    async def manage_my_trio(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manage user's own trio"""
        await self.cog._execute_trio_mine(interaction, interaction.user)
    
    @discord.ui.button(label="Manage Another's Trio", style=discord.ButtonStyle.primary, custom_id="persist_trio_mine_other")
    async def manage_other_trio(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manage another user's trio"""
        view = UserSelectView(self.cog, interaction.user.id)
        await interaction.response.send_message("Select a user to manage their trio:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Bowl Management", style=discord.ButtonStyle.secondary, custom_id="persist_trio_bowl_manage")
    async def bowl_management(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Manage trios in bowls"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            trios = await self.cog.data_manager.get_cached(interaction.guild.id, "trios_inventory", {})
            bowl_trios = {k: v for k, v in trios.items() if v.get("holder_id") == "IN_BOWL"}
            
            if not bowl_trios:
                await interaction.followup.send("❌ No trios are currently in bowls.", ephemeral=True)
                return
            
            view = BowlManagementView(self.cog, interaction.user.id, bowl_trios)
            await interaction.followup.send("Select a trio to manage:", view=view, ephemeral=True)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(interaction, e, "bowl management")

class TrioActionView(discord.ui.View):
    """View for trio management actions"""
    
    def __init__(self, cog, trio_id: str, trio_name: str, is_locked: bool, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.trio_id = trio_id
        self.trio_name = trio_name
        self.is_locked = is_locked
        self.interaction_user_id = None
        self.message = None
        
        # Add lock/unlock button
        lock_label = "Unlock" if is_locked else "Lock"
        self.lock_button = discord.ui.Button(
            label=lock_label,
            style=discord.ButtonStyle.primary,
            custom_id="trio_toggle_lock"
        )
        self.lock_button.callback = self.toggle_lock
        self.add_item(self.lock_button)
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if user can interact with this view"""
        if self.interaction_user_id is None:
            await interaction.response.send_message("This interaction is not properly initialized.", ephemeral=True)
            return False
        
        # Allow original user
        if interaction.user.id == self.interaction_user_id:
            return True
        
        # Allow server managers
        if interaction.guild:
            member = interaction.guild.get_member(interaction.user.id)
            if member and member.guild_permissions.manage_guild:
                return True
        
        await interaction.response.send_message(
            "These buttons are for the trio holder or server managers only.", 
            ephemeral=True
        )
        return False
    
    async def on_timeout(self):
        """Disable view on timeout"""
        for item in self.children:
            item.disabled = True
        
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass
    
    @discord.ui.button(label="Drop (to Well)", style=discord.ButtonStyle.danger)
    async def drop_trio(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Drop trio to well"""
        await interaction.response.defer()
        
        try:
            async with self.cog.data_manager.config.guild(interaction.guild).trios_inventory() as trios:
                if self.trio_id in trios:
                    trios[self.trio_id]["holder_id"] = None
                    trios[self.trio_id]["holder_name"] = None
                else:
                    await interaction.followup.send(f"❌ Could not find {self.trio_name} to drop.", ephemeral=True)
                    return
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            if self.message:
                await self.message.edit(
                    content=f"✅ You have dropped '{self.trio_name}'. It is now in the Well.",
                    view=self
                )
            
            # Invalidate cache and update lists
            self.cog.data_manager.invalidate_cache(interaction.guild.id, "trios_inventory")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(interaction, e, "dropping trio")
    
    @discord.ui.button(label="Place in Bowl", style=discord.ButtonStyle.secondary)
    async def place_in_bowl(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Place trio in bowl"""
        await interaction.response.defer()
        
        try:
            async with self.cog.data_manager.config.guild(interaction.guild).trios_inventory() as trios:
                if self.trio_id in trios:
                    trios[self.trio_id]["holder_id"] = "IN_BOWL"
                    trios[self.trio_id]["holder_name"] = None
                else:
                    await interaction.followup.send(f"❌ Could not find {self.trio_name} to place in bowl.", ephemeral=True)
                    return
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            if self.message:
                await self.message.edit(
                    content=f"✅ You have placed '{self.trio_name}' in a Bowl.",
                    view=self
                )
            
            # Invalidate cache
            self.cog.data_manager.invalidate_cache(interaction.guild.id, "trios_inventory")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(interaction, e, "placing trio in bowl")
    
    async def toggle_lock(self, interaction: discord.Interaction):
        """Toggle trio lock status"""
        await interaction.response.defer()
        
        try:
            async with self.cog.data_manager.config.guild(interaction.guild).trio_user_locks() as locks:
                user_id_str = str(self.interaction_user_id)
                new_lock_state = not locks.get(user_id_str, False)
                locks[user_id_str] = new_lock_state
            
            # Update button
            self.lock_button.label = "Unlock" if new_lock_state else "Lock"
            
            status = "locked" if new_lock_state else "unlocked"
            await interaction.followup.send(f"✅ Trio access has been {status}.", ephemeral=True)
            
            if self.message:
                await self.message.edit(view=self)
            
            # Invalidate cache
            self.cog.data_manager.invalidate_cache(interaction.guild.id, "trio_user_locks")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(interaction, e, "toggling trio lock")

class CustodianRefactored(commands.Cog):
    """
    Refactored Custodian cog for tracking thinspace breaches, gates, dreams, and weekly cycles.
    
    This version includes:
    - Better error handling and validation
    - Improved performance with caching
    - Cleaner code organization
    - Enhanced security
    """
    
    def __init__(self, bot):
        self.bot = bot
        self._views_reloaded = False
        
        # Initialize config
        self.config = Config.get_conf(self, identifier=CONFIG_IDENTIFIER, force_registration=True)
        
        # Initialize managers
        self.data_manager = DataManager(self.config)
        self.trio_manager = TrioManager(self.data_manager)
        self.thinspace_manager = ThinspaceManager(self.data_manager)
        self.reset_manager = WeeklyResetManager(self.data_manager)
        
        # Message templates
        self.breach_messages = [
            "Breach made:",
            "Space breached:",
            "You tear space:",
            "Inky fingers trace the path:",
            "The crossing is established:",
            "Passage confirmed:",
            "Reality is torn:",
            "Sequence complete:",
        ]
        
        self.gate_apply_messages = [
            "Breachgate established for crossing:",
            "Breach, tamed for your use:",
            "Limit bypassed for:",
            "A stable path secured through:",
        ]
        
        self.gated_breach_messages = [
            "Gate utilized:",
            "Path via gate:",
            "Limit irrelevant:",
            "A gated crossing used:",
        ]
        
        # Register default config
        self._register_default_config()
        
        # Start reset task
        self.reset_manager._reset_task = self.bot.loop.create_task(self._run_weekly_reset_loop())
        
        log.info("Custodian cog initialized successfully")
    
    def _register_default_config(self):
        """Register default configuration"""
        default_guild = {
            "thinspaces": {},
            "breach_types": DEFAULT_BREACH_TYPES.copy(),
            "breachgates_available": 0,
            "max_gates": 4,
            "dreams_left": 3,
            "max_dreams": 3,
            "cycle_number": 1,
            "reset_day": 5,  # Saturday
            "reset_hour_utc": 5,
            "reset_minute_utc": 0,
            "last_reset_log": None,
            "tracking_channel": None,
            "default_limit": 14,
            "trios_inventory": {},
            "trio_user_locks": {},
            "trio_user_titles": {},
            "weekly_artifacts": {},
            "is_reset_paused": False,
            "persistent_trio_list_channel_id": None,
            "persistent_trio_list_message_ids": [],
            "trio_control_panel_message_id": None,
            "trio_control_panel_channel_id": None,
        }
        
        self.config.register_guild(**default_guild)
    
    def cog_unload(self):
        """Clean up when cog is unloaded"""
        if self.reset_manager._reset_task:
            self.reset_manager._reset_task.cancel()
        log.info("Custodian cog unloaded")
    
    async def _run_weekly_reset_loop(self):
        """Background task for weekly resets"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                # Check all guilds for reset time
                all_guilds = await self.config.all_guilds()
                
                for guild_id, guild_data in all_guilds.items():
                    if guild_data.get("is_reset_paused", False):
                        continue
                    
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue
                    
                    next_reset = await self.reset_manager.calculate_next_reset(guild)
                    if not next_reset:
                        continue
                    
                    now = datetime.datetime.now(datetime.timezone.utc)
                    if now >= next_reset:
                        await self._perform_guild_reset(guild)
                
                # Sleep for 1 hour before next check
                await asyncio.sleep(3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception(f"Error in weekly reset loop: {e}")
                await asyncio.sleep(3600)  # Continue despite errors
    
    async def _perform_guild_reset(self, guild: discord.Guild):
        """Perform reset for specific guild"""
        try:
            log_msg, cycle_msg, next_reset = await self.reset_manager.perform_reset(guild)
            
            # Send reset notification
            tracking_channel_id = await self.data_manager.get_cached(guild.id, "tracking_channel")
            if tracking_channel_id:
                channel = guild.get_channel(tracking_channel_id)
                if channel:
                    try:
                        await channel.send(cycle_msg)
                        log.info(f"Reset notification sent to {guild.name}")
                    except discord.HTTPException as e:
                        log.error(f"Failed to send reset notification to {guild.name}: {e}")
            
            log.info(log_msg)
            
        except Exception as e:
            log.exception(f"Failed to perform reset for guild {guild.id}: {e}")
    
    # Helper methods
    async def _execute_trio_mine(self, interaction_or_ctx, user_for_mine: discord.User):
        """Execute trio mine operation for a user"""
        guild = getattr(interaction_or_ctx, 'guild', None)
        if not guild:
            return
        
        try:
            # Find user's trio
            trio_result = await self.trio_manager.find_user_trio(guild, user_for_mine.id)
            
            if not trio_result:
                # Check if user can claim a trio
                trios = await self.data_manager.get_cached(guild.id, "trios_inventory", {})
                available_trios = {k: v for k, v in trios.items() if v.get("holder_id") is None}
                
                if not available_trios:
                    msg = f"❌ {user_for_mine.display_name} doesn't have a trio and none are available to claim."
                else:
                    msg = f"**{user_for_mine.display_name}** doesn't have a trio. Available trios to claim:"
                    view = TrioClaimSelectView(self, user_for_mine, available_trios)
                    
                if hasattr(interaction_or_ctx, 'response'):
                    if available_trios:
                        await interaction_or_ctx.response.send_message(msg, view=view, ephemeral=True)
                    else:
                        await interaction_or_ctx.response.send_message(msg, ephemeral=True)
                else:
                    if available_trios:
                        await interaction_or_ctx.send(msg, view=view)
                    else:
                        await interaction_or_ctx.send(msg)
                return
            
            trio_id, trio_data = trio_result
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            abilities = trio_data.get("abilities", ["Unknown"] * 3)
            
            # Check if user is locked
            locks = await self.data_manager.get_cached(guild.id, "trio_user_locks", {})
            is_locked = locks.get(str(user_for_mine.id), False)
            
            # Create action view
            view = TrioActionView(self, trio_id, trio_name, is_locked)
            view.interaction_user_id = user_for_mine.id
            
            # Create embed
            abilities_str = ", ".join(abilities[:3])
            embed = discord.Embed(
                title=f"Trio Management: {trio_name}",
                description=f"**Holder:** {user_for_mine.display_name}\n**Abilities:** {abilities_str}",
                color=discord.Color.blue()
            )
            
            if is_locked:
                embed.add_field(name="🔒 Status", value="Locked", inline=True)
            
            if hasattr(interaction_or_ctx, 'response'):
                await interaction_or_ctx.response.send_message(embed=embed, view=view, ephemeral=True)
                view.message = await interaction_or_ctx.original_response()
            else:
                message = await interaction_or_ctx.send(embed=embed, view=view)
                view.message = message
                
        except Exception as e:
            await ErrorHandler.handle_discord_error(interaction_or_ctx, e, "trio mine operation")

    async def _update_persistent_trio_list(self, guild: discord.Guild):
        """Update the persistent trio list display"""
        try:
            channel_id = await self.data_manager.get_cached(guild.id, "persistent_trio_list_channel_id")
            if not channel_id:
                return
            
            channel = guild.get_channel(channel_id)
            if not channel:
                return
            
            # Generate new embeds
            embeds = await self._generate_trio_list_embeds(guild)
            
            # Get existing message IDs
            message_ids = await self.data_manager.get_cached(guild.id, "persistent_trio_list_message_ids", [])
            
            # Delete old messages
            for msg_id in message_ids:
                try:
                    old_msg = await channel.fetch_message(msg_id)
                    await old_msg.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
            
            # Send new messages
            new_message_ids = []
            for embed in embeds:
                try:
                    msg = await channel.send(embed=embed)
                    new_message_ids.append(msg.id)
                except discord.HTTPException:
                    break
            
            # Update stored message IDs
            await self.config.guild(guild).persistent_trio_list_message_ids.set(new_message_ids)
            self.data_manager.invalidate_cache(guild.id, "persistent_trio_list_message_ids")
            
        except Exception as e:
            log.exception(f"Error updating persistent trio list for guild {guild.id}: {e}")

    async def _generate_trio_list_embeds(self, guild: discord.Guild, title_prefix: str = "Trio Inventory") -> List[discord.Embed]:
        """Generate embeds for trio list display"""
        trios = await self.data_manager.get_cached(guild.id, "trios_inventory", {})
        user_titles = await self.data_manager.get_cached(guild.id, "trio_user_titles", {})
        
        if not trios:
            embed = discord.Embed(
                title=title_prefix,
                description="No trios have been defined for this server.",
                color=discord.Color.blue()
            )
            return [embed]
        
        # Format trio data with titles
        formatted_trios = {}
        for trio_id, trio_data in trios.items():
            if not isinstance(trio_data, dict):
                continue
            
            formatted_data = trio_data.copy()
            holder_id = trio_data.get("holder_id")
            
            # Apply user titles if available
            if holder_id and holder_id != "IN_BOWL":
                titled_name = user_titles.get(str(holder_id))
                if titled_name:
                    formatted_data["holder_name"] = titled_name
            
            formatted_trios[trio_id] = formatted_data
        
        # Generate formatted lines
        lines = MessageFormatter.format_trio_list(formatted_trios, title_prefix)
        
        # Create embeds
        embeds = MessageFormatter.create_paginated_embeds(
            lines, title_prefix, discord.Color.blue()
        )
        
        return embeds

    # ==========================================
    # CORE GAME COMMANDS
    # ==========================================
    
    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def breach(self, ctx: commands.Context, *, sequence_and_multiplier: str):
        """Make a breach through thinspace"""
        if not sequence_and_multiplier.strip():
            await ctx.send("❌ Please specify a thinspace to breach (e.g., `AA-BB`).")
            return
        
        # Parse input - handle multipliers like "AA-BB x3" or "hand AA-BB"
        parts = sequence_and_multiplier.strip().split()
        
        breach_type = "hand"  # default
        thinspace_name = ""
        multiplier = 1
        
        # Parse different input formats
        for i, part in enumerate(parts):
            if part.lower() in DEFAULT_BREACH_TYPES:
                breach_type = part.lower()
            elif 'x' in part and part.replace('x', '').isdigit():
                multiplier = int(part.replace('x', ''))
            elif '-' in part:
                thinspace_name = part
            elif not thinspace_name and i == len(parts) - 1:
                thinspace_name = part
        
        if not thinspace_name:
            await ctx.send("❌ Please specify a valid thinspace name (e.g., `AA-BB`).")
            return
        
        # Validate thinspace name
        is_valid, normalized_name = InputValidator.validate_thinspace_name(thinspace_name)
        if not is_valid:
            await ctx.send(f"❌ {normalized_name}")
            return
        
        # Check if thinspace exists
        thinspace = await self.thinspace_manager.get_thinspace(ctx.guild, normalized_name)
        if not thinspace:
            await ctx.send(f"❌ Thinspace `{normalized_name}` doesn't exist. Use `{ctx.prefix}thinspace add {normalized_name}` to create it.")
            return
        
        try:
            # Get breach cost
            breach_types = await self.data_manager.get_cached(ctx.guild.id, "breach_types", DEFAULT_BREACH_TYPES)
            breach_cost = breach_types.get(breach_type, 1)
            total_cost = breach_cost * multiplier
            
            # Check if gated
            if thinspace["gated"]:
                # Use gate
                message = f"{random.choice(self.gated_breach_messages)} **{normalized_name}** (gated)"
                if multiplier > 1:
                    message += f" x{multiplier}"
                await ctx.send(message)
                
                # Update post-gate breaches
                async with self.config.guild(ctx.guild).thinspaces() as thinspaces:
                    thinspaces[normalized_name]["post_gate_breaches"] += total_cost
                
            else:
                # Check limit
                current_breaches = thinspace["pre_gate_breaches"]
                limit = thinspace["limit"]
                
                if current_breaches + total_cost > limit:
                    await ctx.send(f"❌ Cannot breach `{normalized_name}` {multiplier} time(s). "
                                 f"Would exceed limit ({current_breaches + total_cost}/{limit}).")
                    return
                
                # Perform breach
                message = f"{random.choice(self.breach_messages)} **{normalized_name}**"
                if multiplier > 1:
                    message += f" x{multiplier}"
                if breach_type != "hand":
                    message += f" ({breach_type})"
                await ctx.send(message)
                
                # Update breaches
                async with self.config.guild(ctx.guild).thinspaces() as thinspaces:
                    thinspaces[normalized_name]["pre_gate_breaches"] += total_cost
            
            # Invalidate cache
            self.data_manager.invalidate_cache(ctx.guild.id, "thinspaces")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "breach operation")

    @commands.command()
    @commands.guild_only()
    async def unbreach(self, ctx: commands.Context, thinspace_name: str, breach_type: str = "hand", multiplier: int = 1):
        """Remove breaches from a thinspace"""
        # Validate inputs
        is_valid, normalized_name = InputValidator.validate_thinspace_name(thinspace_name)
        if not is_valid:
            await ctx.send(f"❌ {normalized_name}")
            return
        
        if multiplier < 1:
            await ctx.send("❌ Multiplier must be at least 1.")
            return
        
        try:
            # Check if thinspace exists
            thinspace = await self.thinspace_manager.get_thinspace(ctx.guild, normalized_name)
            if not thinspace:
                await ctx.send(f"❌ Thinspace `{normalized_name}` doesn't exist.")
                return
            
            # Get breach cost
            breach_types = await self.data_manager.get_cached(ctx.guild.id, "breach_types", DEFAULT_BREACH_TYPES)
            breach_cost = breach_types.get(breach_type.lower(), 1)
            total_cost = breach_cost * multiplier
            
            # Calculate what to remove
            current_breaches = thinspace["pre_gate_breaches"]
            post_gate_breaches = thinspace.get("post_gate_breaches", 0)
            
            # Remove from post-gate first, then pre-gate
            removed_post = min(total_cost, post_gate_breaches)
            remaining_to_remove = total_cost - removed_post
            removed_pre = min(remaining_to_remove, current_breaches)
            
            if removed_post == 0 and removed_pre == 0:
                await ctx.send(f"❌ No breaches to remove from `{normalized_name}`.")
                return
            
            # Apply changes
            async with self.config.guild(ctx.guild).thinspaces() as thinspaces:
                thinspaces[normalized_name]["post_gate_breaches"] -= removed_post
                thinspaces[normalized_name]["pre_gate_breaches"] -= removed_pre
            
            total_removed = removed_post + removed_pre
            await ctx.send(f"✅ Removed {total_removed} breach(es) from `{normalized_name}`.")
            
            # Invalidate cache
            self.data_manager.invalidate_cache(ctx.guild.id, "thinspaces")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "unbreach operation")

    @commands.command()
    @commands.guild_only()
    async def status(self, ctx: commands.Context):
        """Show current status of all systems"""
        try:
            # Get current data
            dreams_left = await self.data_manager.get_cached(ctx.guild.id, "dreams_left", 3)
            max_dreams = await self.data_manager.get_cached(ctx.guild.id, "max_dreams", 3)
            gates_available = await self.data_manager.get_cached(ctx.guild.id, "breachgates_available", 0)
            max_gates = await self.data_manager.get_cached(ctx.guild.id, "max_gates", 4)
            cycle_number = await self.data_manager.get_cached(ctx.guild.id, "cycle_number", 1)
            
            # Calculate next reset
            next_reset = await self.reset_manager.calculate_next_reset(ctx.guild)
            next_reset_str = next_reset.strftime("%Y-%m-%d %H:%M UTC") if next_reset else "Unknown"
            
            # Get thinspace summary
            thinspaces = await self.data_manager.get_cached(ctx.guild.id, "thinspaces", {})
            total_spaces = len(thinspaces)
            gated_spaces = sum(1 for space in thinspaces.values() if space.get("gated", False))
            
            embed = discord.Embed(
                title="📊 Custodian Status",
                color=await ctx.embed_colour(),
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(
                name="🌙 Dreams",
                value=f"{dreams_left}/{max_dreams}",
                inline=True
            )
            
            embed.add_field(
                name="🚪 Breach Gates",
                value=f"{gates_available}/{max_gates}",
                inline=True
            )
            
            embed.add_field(
                name="🔄 Current Cycle",
                value=str(cycle_number),
                inline=True
            )
            
            embed.add_field(
                name="🌌 Thinspaces",
                value=f"{total_spaces} total\n{gated_spaces} gated",
                inline=True
            )
            
            embed.add_field(
                name="⏰ Next Reset",
                value=next_reset_str,
                inline=True
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "status check")

    @commands.group()
    @commands.guild_only()
    async def thinspace(self, ctx: commands.Context):
        """Manage thinspaces"""
        if ctx.invoked_subcommand is None:
            # Show all thinspaces
            try:
                thinspaces = await self.data_manager.get_cached(ctx.guild.id, "thinspaces", {})
                
                if not thinspaces:
                    await ctx.send("No thinspaces have been created yet.")
                    return
                
                lines = []
                for name, data in sorted(thinspaces.items()):
                    pre_breaches = data.get("pre_gate_breaches", 0)
                    post_breaches = data.get("post_gate_breaches", 0)
                    limit = data.get("limit", 14)
                    gated = data.get("gated", False)
                    
                    status = "🚪 Gated" if gated else f"{pre_breaches}/{limit}"
                    post_info = f" (+{post_breaches} post-gate)" if post_breaches > 0 else ""
                    
                    lines.append(f"**{name}**: {status}{post_info}")
                
                embeds = MessageFormatter.create_paginated_embeds(
                    lines, "🌌 Thinspaces", await ctx.embed_colour()
                )
                
                for embed in embeds:
                    await ctx.send(embed=embed)
                    
            except Exception as e:
                await ErrorHandler.handle_discord_error(ctx, e, "listing thinspaces")

    @thinspace.command(name="add")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def thinspace_add(self, ctx: commands.Context, space_name: str, limit: int = 14):
        """Add a new thinspace"""
        try:
            success = await self.thinspace_manager.create_thinspace(ctx.guild, space_name, limit)
            if success:
                await ctx.send(f"✅ Created thinspace `{space_name.upper()}` with limit {limit}.")
            else:
                await ctx.send(f"❌ Thinspace `{space_name.upper()}` already exists or name is invalid.")
                
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "creating thinspace")

    @thinspace.command(name="remove", aliases=["delete"])
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def thinspace_remove(self, ctx: commands.Context, space_name: str):
        """Remove a thinspace"""
        try:
            is_valid, normalized_name = InputValidator.validate_thinspace_name(space_name)
            if not is_valid:
                await ctx.send(f"❌ {normalized_name}")
                return
            
            async with self.config.guild(ctx.guild).thinspaces() as thinspaces:
                if normalized_name in thinspaces:
                    del thinspaces[normalized_name]
                    await ctx.send(f"✅ Removed thinspace `{normalized_name}`.")
                else:
                    await ctx.send(f"❌ Thinspace `{normalized_name}` doesn't exist.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "thinspaces")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "removing thinspace")

    @thinspace.command(name="list")
    @commands.guild_only()
    async def thinspace_list(self, ctx: commands.Context):
        """List all thinspaces with their current status"""
        try:
            thinspaces = await self.data_manager.get_cached(ctx.guild.id, "thinspaces", {})
            
            if not thinspaces:
                await ctx.send("No thinspaces have been configured.")
                return
            
            # Create a formatted list
            embed = discord.Embed(
                title="🌌 Thinspace Registry",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            
            for name, data in sorted(thinspaces.items()):
                breaches = data.get('pre_gate_breaches', 0)
                limit = data.get('limit', 14)
                post_gate_breaches = data.get('post_gate_breaches', 0)
                gated = data.get('gated', False)
                
                status = "🔒 GATED" if gated else "🌌 Open"
                if gated:
                    breach_info = f"{post_gate_breaches}/{limit}"
                else:
                    breach_info = f"{breaches}/{limit}"
                
                embed.add_field(
                    name=f"{name} ({status})",
                    value=f"Breaches: {breach_info}",
                    inline=True
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing thinspaces")

    @thinspace.command(name="status")
    @commands.guild_only()
    async def thinspace_status(self, ctx: commands.Context):
        """Lists thinspaces: non-gated in multi-column, gated separately."""
        try:
            all_guild_spaces = await self.data_manager.get_cached(ctx.guild.id, "thinspaces", {})
            if not all_guild_spaces:
                await ctx.send("No thinspaces have been added yet.")
                return

            default_limit = await self.data_manager.get_cached(ctx.guild.id, "default_limit", 14)
            
            # ANSI color codes
            ANSI_GREEN = "\u001b[32m"
            ANSI_YELLOW = "\u001b[33m"
            ANSI_RED = "\u001b[31m"
            ANSI_CYAN = "\u001b[36m"
            ANSI_MAGENTA = "\u001b[35m"
            ANSI_RESET = "\u001b[0m"
            
            non_gated_items = [] 
            gated_items_formatted = [] 
            sent_any_message = False 

            for name, data in sorted(all_guild_spaces.items()):
                name_str_raw = f"{name}:"
                
                if isinstance(data, dict):
                    pre_breaches = data.get('pre_gate_breaches', 0)  # Use correct field name from migration
                    post_breaches = data.get('post_gate_breaches', 0)
                    limit = data.get('limit', default_limit)
                    gated = data.get('gated', False)

                    if gated:
                        # Gated items formatting
                        colored_pre_value = f"{ANSI_YELLOW}{pre_breaches}{ANSI_RESET}"
                        colored_post_value = f"{ANSI_MAGENTA}{post_breaches}{ANSI_RESET}"
                        
                        colored_pre_label = f"{ANSI_YELLOW}Pre:{ANSI_RESET}"
                        colored_post_label = f"{ANSI_MAGENTA}Post:{ANSI_RESET}"
                        
                        status_display = f"{colored_pre_label} {colored_pre_value}, {colored_post_label} {colored_post_value}"
                        gated_items_formatted.append(f"{name}: {status_display}")
                    else:
                        # Non-gated logic with color coding
                        usage_percent = (pre_breaches / limit * 100) if limit > 0 else 0
                        color = ANSI_GREEN
                        if usage_percent > 66: color = ANSI_RED
                        elif usage_percent > 33: color = ANSI_YELLOW
                        
                        colored_pre = f"{color}{pre_breaches:>2}{ANSI_RESET}"
                        colored_limit = f"{ANSI_CYAN}{limit:>2}{ANSI_RESET}"
                        status_display = f"{colored_pre}/{colored_limit}"
                        non_gated_items.append((name_str_raw, status_display))
                else:
                    status_display = f"{ANSI_RED}Error - Invalid Data{ANSI_RESET}"
                    non_gated_items.append((name_str_raw, status_display))

            # Display Non-Gated Items in multi-column format
            if non_gated_items:
                max_name_len = max(len(item[0]) for item in non_gated_items) if non_gated_items else 10
                COLUMNS = 3 
                
                output_text_lines_non_gated = []
                for i in range(0, len(non_gated_items), COLUMNS):
                    row_items = non_gated_items[i:i+COLUMNS]
                    line_parts = []
                    for name_part, status_part in row_items:
                        line_parts.append(f"{name_part:<{max_name_len + 0}}{status_part}") 
                    output_text_lines_non_gated.append("   ".join(line_parts))

                full_text_non_gated = "\n".join(output_text_lines_non_gated)
                
                LINES_PER_EMBED = 20 
                current_page_lines_ng = []
                embed_num_ng = 1

                for line_num, line in enumerate(full_text_non_gated.splitlines()):
                    current_page_lines_ng.append(line)
                    if (line_num + 1) % LINES_PER_EMBED == 0 or (line_num + 1) == len(full_text_non_gated.splitlines()):
                        title = "Thinspaces"
                        if embed_num_ng > 1 or (len(full_text_non_gated.splitlines()) > LINES_PER_EMBED and len(gated_items_formatted) > 0):
                            title += f" (Page {embed_num_ng})"
                        
                        embed_ng = discord.Embed(title=title, color=await ctx.embed_colour())
                        page_content_ng = "\n".join(current_page_lines_ng)
                        if page_content_ng.strip():
                            embed_ng.description = f"```ansi\n{page_content_ng}\n```"
                            await ctx.send(embed=embed_ng)
                            sent_any_message = True
                        
                        current_page_lines_ng = []
                        embed_num_ng += 1

            # Display Gated Items separately
            if gated_items_formatted:
                gated_text = "\n".join(gated_items_formatted)
                
                current_page_lines_g = []
                embed_num_g = 1
                
                for line_num, line in enumerate(gated_text.splitlines()):
                    current_page_lines_g.append(line)
                    if (line_num + 1) % LINES_PER_EMBED == 0 or (line_num + 1) == len(gated_text.splitlines()):
                        title = "Gated Thinspaces"
                        if embed_num_g > 1:
                            title += f" (Page {embed_num_g})"
                        
                        embed_g = discord.Embed(title=title, color=await ctx.embed_colour())
                        page_content_g = "\n".join(current_page_lines_g)
                        if page_content_g.strip():
                            embed_g.description = f"```ansi\n{page_content_g}\n```"
                            await ctx.send(embed=embed_g)
                            sent_any_message = True
                        
                        current_page_lines_g = []
                        embed_num_g += 1

            if not sent_any_message:
                await ctx.send("No thinspace data to display.")
                
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "showing thinspace status")
    
    def _create_status_bar(self, current: int, maximum: int, length: int = 10) -> str:
        """Create a visual status bar for breach usage"""
        if maximum <= 0:
            return "█" * length
        
        filled = int((current / maximum) * length)
        empty = length - filled
        
        if current >= maximum:
            return "🔴" + "█" * filled + "░" * empty
        elif current >= maximum * 0.8:
            return "🟡" + "█" * filled + "░" * empty
        else:
            return "🟢" + "█" * filled + "░" * empty

    @commands.group()
    @commands.guild_only()
    async def gate(self, ctx: commands.Context):
        """Manage breach gates"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @gate.command(name="apply")
    @commands.guild_only()
    async def gate_apply(self, ctx: commands.Context, space_name: str):
        """Apply a breach gate to a thinspace"""
        try:
            is_valid, normalized_name = InputValidator.validate_thinspace_name(space_name)
            if not is_valid:
                await ctx.send(f"❌ {normalized_name}")
                return
            
            # Check if we have gates available
            gates_available = await self.data_manager.get_cached(ctx.guild.id, "breachgates_available", 0)
            if gates_available <= 0:
                await ctx.send("❌ No breach gates available.")
                return
            
            # Check if thinspace exists
            thinspace = await self.thinspace_manager.get_thinspace(ctx.guild, normalized_name)
            if not thinspace:
                await ctx.send(f"❌ Thinspace `{normalized_name}` doesn't exist.")
                return
            
            if thinspace.get("gated", False):
                await ctx.send(f"❌ Thinspace `{normalized_name}` is already gated.")
                return
            
            # Apply gate
            async with self.config.guild(ctx.guild).thinspaces() as thinspaces:
                thinspaces[normalized_name]["gated"] = True
            
            # Consume a gate
            await self.config.guild(ctx.guild).breachgates_available.set(gates_available - 1)
            
            message = f"{random.choice(self.gate_apply_messages)} **{normalized_name}**"
            await ctx.send(message)
            
            # Invalidate cache
            self.data_manager.invalidate_cache(ctx.guild.id, "thinspaces")
            self.data_manager.invalidate_cache(ctx.guild.id, "breachgates_available")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "applying gate")

    @gate.command(name="give")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def gate_give(self, ctx: commands.Context, amount: int = 1):
        """Give breach gates to the server"""
        try:
            if amount < 1:
                await ctx.send("❌ Amount must be at least 1.")
                return
            
            current_gates = await self.data_manager.get_cached(ctx.guild.id, "breachgates_available", 0)
            max_gates = await self.data_manager.get_cached(ctx.guild.id, "max_gates", 4)
            
            new_total = min(current_gates + amount, max_gates)
            actual_given = new_total - current_gates
            
            await self.config.guild(ctx.guild).breachgates_available.set(new_total)
            
            if actual_given > 0:
                await ctx.send(f"✅ Gave {actual_given} breach gate(s). Total: {new_total}/{max_gates}")
            else:
                await ctx.send(f"❌ Already at maximum gates ({max_gates}).")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "breachgates_available")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "giving gates")

    @gate.command(name="remove")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def gate_remove(self, ctx: commands.Context, space_name: str):
        """Remove a gate from a thinspace (admin only)"""
        try:
            is_valid, normalized_name = InputValidator.validate_thinspace_name(space_name)
            if not is_valid:
                await ctx.send(f"❌ {normalized_name}")
                return
            
            thinspace = await self.thinspace_manager.get_thinspace(ctx.guild, normalized_name)
            if not thinspace:
                await ctx.send(f"❌ Thinspace `{normalized_name}` doesn't exist.")
                return
            
            if not thinspace.get('gated', False):
                await ctx.send(f"❌ Thinspace `{normalized_name}` is not gated.")
                return
            
            # Remove the gate
            async with self.config.guild(ctx.guild).thinspaces() as thinspaces:
                if normalized_name in thinspaces:
                    thinspaces[normalized_name]['gated'] = False
                    # Keep post_gate_breaches for record keeping
            
            # Return a gate to availability
            current_gates = await self.data_manager.get_cached(ctx.guild.id, "breachgates_available", 0)
            max_gates = await self.data_manager.get_cached(ctx.guild.id, "max_gates", 4)
            new_total = min(current_gates + 1, max_gates)
            
            await self.config.guild(ctx.guild).breachgates_available.set(new_total)
            
            await ctx.send(f"✅ Removed gate from `{normalized_name}`. Gate returned to pool: {new_total}/{max_gates}")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "thinspaces")
            self.data_manager.invalidate_cache(ctx.guild.id, "breachgates_available")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "removing gate")

    @gate.command(name="add")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def gate_add(self, ctx: commands.Context, amount: int = 1):
        """Add to gate capacity (admin only)"""
        try:
            if amount < 1:
                await ctx.send("❌ Amount must be at least 1.")
                return
            
            max_gates = await self.data_manager.get_cached(ctx.guild.id, "max_gates", 4)
            new_max = max_gates + amount
            
            await self.config.guild(ctx.guild).max_gates.set(new_max)
            
            await ctx.send(f"✅ Increased gate capacity by {amount}. New maximum: {new_max}")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "max_gates")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "adding gate capacity")

    @gate.command(name="list")
    @commands.guild_only()
    async def gate_list(self, ctx: commands.Context):
        """List gate status and active gates"""
        try:
            available_gates = await self.data_manager.get_cached(ctx.guild.id, "breachgates_available", 0)
            max_gates = await self.data_manager.get_cached(ctx.guild.id, "max_gates", 4)
            thinspaces = await self.data_manager.get_cached(ctx.guild.id, "thinspaces", {})
            
            embed = discord.Embed(
                title="🔒 Gate Status",
                color=discord.Color.gold(),
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(
                name="📊 Gate Availability",
                value=f"Available: {available_gates}/{max_gates}",
                inline=False
            )
            
            # List active gates
            active_gates = []
            for name, data in sorted(thinspaces.items()):
                if data.get('gated', False):
                    post_gate_breaches = data.get('post_gate_breaches', 0)
                    limit = data.get('limit', 14)
                    active_gates.append(f"🔒 **{name}**: {post_gate_breaches}/{limit} breaches")
            
            if active_gates:
                embed.add_field(
                    name="🔒 Active Gates",
                    value="\n".join(active_gates),
                    inline=False
                )
            else:
                embed.add_field(
                    name="🔒 Active Gates",
                    value="No gates currently applied",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing gates")

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def dream(self, ctx: commands.Context):
        """Use a dream"""
        try:
            dreams_left = await self.data_manager.get_cached(ctx.guild.id, "dreams_left", 3)
            max_dreams = await self.data_manager.get_cached(ctx.guild.id, "max_dreams", 3)
            
            if dreams_left <= 0:
                await ctx.send("❌ No dreams remaining for this cycle.")
                return
            
            # Use a dream
            await self.config.guild(ctx.guild).dreams_left.set(dreams_left - 1)
            
            await ctx.send(f"🌙 Dream used by {ctx.author.display_name}. Dreams remaining: {dreams_left - 1}/{max_dreams}")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "dreams_left")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "using dream")

    @dream.command(name="status")
    @commands.guild_only()
    async def dream_status(self, ctx: commands.Context):
        """Check dream status"""
        try:
            dreams_left = await self.data_manager.get_cached(ctx.guild.id, "dreams_left", 3)
            max_dreams = await self.data_manager.get_cached(ctx.guild.id, "max_dreams", 3)
            
            embed = discord.Embed(
                title="🌙 Dream Status",
                description=f"Dreams remaining: **{dreams_left}/{max_dreams}**",
                color=await ctx.embed_colour()
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "checking dream status")

    @dream.command(name="give")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def dream_give(self, ctx: commands.Context, amount: int = 1):
        """Give dreams to the server"""
        try:
            if amount < 1:
                await ctx.send("❌ Amount must be at least 1.")
                return
            
            current_dreams = await self.data_manager.get_cached(ctx.guild.id, "dreams_left", 3)
            max_dreams = await self.data_manager.get_cached(ctx.guild.id, "max_dreams", 3)
            
            new_total = min(current_dreams + amount, max_dreams)
            actual_given = new_total - current_dreams
            
            await self.config.guild(ctx.guild).dreams_left.set(new_total)
            
            if actual_given > 0:
                await ctx.send(f"✅ Gave {actual_given} dream(s). Total: {new_total}/{max_dreams}")
            else:
                await ctx.send(f"❌ Already at maximum dreams ({max_dreams}).")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "dreams_left")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "giving dreams")

    @dream.command(name="use")
    @commands.guild_only()
    async def dream_use(self, ctx: commands.Context):
        """Use a dream charge"""
        try:
            dreams_left = await self.data_manager.get_cached(ctx.guild.id, "dreams_left", 3)
            
            if dreams_left <= 0:
                await ctx.send("❌ No dreams available to use.")
                return
            
            new_total = dreams_left - 1
            await self.config.guild(ctx.guild).dreams_left.set(new_total)
            
            max_dreams = await self.data_manager.get_cached(ctx.guild.id, "max_dreams", 3)
            await ctx.send(f"✅ Used a dream. Remaining: {new_total}/{max_dreams}")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "dreams_left")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "using dream")

    @dream.command(name="undo")
    @commands.guild_only()
    async def dream_undo(self, ctx: commands.Context):
        """Undo the last dream usage"""
        try:
            dreams_left = await self.data_manager.get_cached(ctx.guild.id, "dreams_left", 3)
            max_dreams = await self.data_manager.get_cached(ctx.guild.id, "max_dreams", 3)
            
            if dreams_left >= max_dreams:
                await ctx.send(f"❌ Already at maximum dreams ({max_dreams}).")
                return
            
            new_total = dreams_left + 1
            await self.config.guild(ctx.guild).dreams_left.set(new_total)
            
            await ctx.send(f"✅ Dream usage undone. Current: {new_total}/{max_dreams}")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "dreams_left")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "undoing dream")

    @commands.command(name="quiz")
    @commands.guild_only()
    async def thinspace_quiz(self, ctx: commands.Context):
        """Take a thinspace quiz"""
        try:
            thinspaces = await self.data_manager.get_cached(ctx.guild.id, "thinspaces", {})
            
            if not thinspaces:
                await ctx.send("❌ No thinspaces available for quiz.")
                return
            
            # Pick a random thinspace
            space_name = random.choice(list(thinspaces.keys()))
            space_data = thinspaces[space_name]
            
            current_breaches = space_data.get("pre_gate_breaches", 0)
            limit = space_data.get("limit", 14)
            gated = space_data.get("gated", False)
            
            embed = discord.Embed(
                title="🧠 Thinspace Quiz",
                description=f"What is the current status of thinspace **{space_name}**?",
                color=await ctx.embed_colour()
            )
            
            # Give the answer after a moment
            await ctx.send(embed=embed)
            await asyncio.sleep(3)
            
            if gated:
                answer = f"**{space_name}** is currently gated! 🚪"
            else:
                answer = f"**{space_name}**: {current_breaches}/{limit} breaches used"
            
            await ctx.send(f"📖 Answer: {answer}")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "quiz operation")

    # ==========================================
    # TRIO USER COMMANDS
    # ==========================================
    @commands.group(aliases=["mani"], invoke_without_command=True)
    @commands.guild_only()
    async def trio(self, ctx: commands.Context, *, target_member: discord.Member = None):
        """Manage trios (manifestations)"""
        target_user = target_member or ctx.author
        await self._execute_trio_mine(ctx, target_user)

    @trio.command(name="list")
    @commands.guild_only()
    async def trio_list(self, ctx: commands.Context):
        """Show all trios"""
        try:
            embeds = await self._generate_trio_list_embeds(ctx.guild)
            for embed in embeds:
                await ctx.send(embed=embed)
                
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing trios")

    @trio.command(name="available", aliases=["well"])
    @commands.guild_only()
    async def trio_available(self, ctx: commands.Context):
        """Show available trios in the well"""
        try:
            trios = await self.data_manager.get_cached(ctx.guild.id, "trios_inventory", {})
            available_trios = {k: v for k, v in trios.items() if v.get("holder_id") is None}
            
            lines = MessageFormatter.format_trio_list(available_trios, "Available Trios")
            embeds = MessageFormatter.create_paginated_embeds(
                lines, "🌊 Available Trios (Well)", await ctx.embed_colour()
            )
            
            for embed in embeds:
                await ctx.send(embed=embed)
                
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing available trios")

    @trio.command(name="held")
    @commands.guild_only()
    async def trio_held(self, ctx: commands.Context):
        """Show held trios"""
        try:
            trios = await self.data_manager.get_cached(ctx.guild.id, "trios_inventory", {})
            held_trios = {k: v for k, v in trios.items() 
                         if v.get("holder_id") is not None and v.get("holder_id") != "IN_BOWL"}
            
            lines = MessageFormatter.format_trio_list(held_trios, "Held Trios")
            embeds = MessageFormatter.create_paginated_embeds(
                lines, "👥 Held Trios", await ctx.embed_colour()
            )
            
            for embed in embeds:
                await ctx.send(embed=embed)
                
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing held trios")

    @trio.command(name="boww")
    @commands.guild_only()
    async def trio_bowl(self, ctx: commands.Context):
        """Show trios in bowls"""
        try:
            trios = await self.data_manager.get_cached(ctx.guild.id, "trios_inventory", {})
            bowl_trios = {k: v for k, v in trios.items() if v.get("holder_id") == "IN_BOWL"}
            
            lines = MessageFormatter.format_trio_list(bowl_trios, "Bowl Trios")
            embeds = MessageFormatter.create_paginated_embeds(
                lines, "🥣 Trios in Bowls", await ctx.embed_colour()
            )
            
            for embed in embeds:
                await ctx.send(embed=embed)
                
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing bowl trios")

    # ==========================================
    # DATA MIGRATION
    # ==========================================
    @commands.command(name="debugdata", hidden=True)
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def debug_data(self, ctx: commands.Context):
        """Debug: Show raw thinspace data structure"""
        try:
            thinspaces = await self.config.guild(ctx.guild).thinspaces()
            
            if not thinspaces:
                await ctx.send("No thinspace data found.")
                return
            
            # Show first few thinspaces with their raw data
            debug_info = []
            count = 0
            for name, data in thinspaces.items():
                if count < 3:  # Show first 3 for debugging
                    debug_info.append(f"**{name}**: {data}")
                    count += 1
                else:
                    break
            
            await ctx.send(f"```json\n{chr(10).join(debug_info)}\n```")
            
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @commands.command(name="migratecustodian", hidden=True)
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def migrate_custodian_data(self, ctx: commands.Context):
        """Migrate data from old custodian cog to refactored version"""
        try:
            # Check if old cog data exists
            old_config_id = 9876543210  # Old hardcoded ID
            
            # Try to access old config using direct database access
            # This works even when the old cog is unloaded
            old_config = Config.get_conf(
                None, 
                identifier=old_config_id, 
                force_registration=False,
                cog_name="Custodian"
            )
            
            try:
                old_guild_data = await old_config.guild(ctx.guild).all()
            except Exception as e:
                await ctx.send(f"❌ No data found from old custodian cog to migrate. Error: {e}")
                return
            
            if not old_guild_data:
                await ctx.send("❌ No data found from old custodian cog to migrate.")
                return
            
            # Check if new config already has data
            new_guild_data = await self.config.guild(ctx.guild).all()
            has_new_data = any([
                new_guild_data.get("thinspaces"),
                new_guild_data.get("trios_inventory"),
                new_guild_data.get("cycle_number", 1) > 1
            ])
            
            if has_new_data:
                await ctx.send("⚠️ New custodian cog already has data. Migration would overwrite existing data. "
                             "Use `--force` flag if you want to proceed anyway.")
                return
            
            # Perform migration
            await ctx.send("🔄 Starting data migration...")
            
            # Migrate all data fields
            migration_count = 0
            for key, value in old_guild_data.items():
                if key in new_guild_data:  # Only migrate known fields
                    await getattr(self.config.guild(ctx.guild), key).set(value)
                    migration_count += 1
            
            # Clear cache to ensure fresh data
            self.data_manager.invalidate_cache(ctx.guild.id)
            
            await ctx.send(f"✅ Migration complete! Migrated {migration_count} data fields from old custodian cog.")
            await ctx.send("📋 Migrated data includes:\n"
                         "• Thinspaces and breach counts\n"
                         "• Trio inventory and holders\n" 
                         "• Dreams and breach gates\n"
                         "• Cycle information\n"
                         "• User titles and locks\n"
                         "• Weekly artifacts\n"
                         "• All configuration settings")
            
            log.info(f"Successfully migrated custodian data for guild {ctx.guild.id}")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "data migration")
            log.exception(f"Error during custodian data migration for guild {ctx.guild.id}")

    # ==========================================
    # TRIO ADMIN COMMANDS
    # ==========================================
    @trio.command(name="add")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def trio_add(self, ctx: commands.Context, trio_number: int, ability1: str, ability2: str, ability3: str, *, name: str = None):
        """Add a new trio"""
        try:
            if trio_number < 1:
                await ctx.send("❌ Trio number must be at least 1.")
                return
            
            trio_id = str(trio_number)
            trio_name = name or f"Trio #{trio_number}"
            
            async with self.config.guild(ctx.guild).trios_inventory() as trios:
                if trio_id in trios:
                    await ctx.send(f"❌ Trio #{trio_number} already exists.")
                    return
                
                trios[trio_id] = {
                    "name": trio_name,
                    "abilities": [ability1, ability2, ability3],
                    "holder_id": None,
                    "holder_name": None
                }
            
            await ctx.send(f"✅ Added **{trio_name}** with abilities: {ability1}, {ability2}, {ability3}")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trios_inventory")
            await self._update_persistent_trio_list(ctx.guild)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "adding trio")

    @trio.command(name="remove")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def trio_remove(self, ctx: commands.Context, identifier: str):
        """Remove a trio"""
        try:
            trio_result = await self.trio_manager.find_trio_by_identifier(ctx.guild, identifier)
            if not trio_result:
                await ctx.send(f"❌ Could not find trio matching `{identifier}`.")
                return
            
            trio_id, trio_data = trio_result
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            
            async with self.config.guild(ctx.guild).trios_inventory() as trios:
                del trios[trio_id]
            
            await ctx.send(f"✅ Removed **{trio_name}**")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trios_inventory")
            await self._update_persistent_trio_list(ctx.guild)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "removing trio")

    @trio.command(name="claim")
    @commands.guild_only()
    async def trio_claim(self, ctx: commands.Context, identifier: str, *, target_member: discord.Member = None):
        """Claim a trio"""
        target_user = target_member or ctx.author
        
        try:
            # Check if user already has a trio
            existing_trio = await self.trio_manager.find_user_trio(ctx.guild, target_user.id)
            if existing_trio:
                await ctx.send(f"❌ {target_user.display_name} already has a trio.")
                return
            
            # Find the trio to claim
            trio_result = await self.trio_manager.find_trio_by_identifier(ctx.guild, identifier)
            if not trio_result:
                await ctx.send(f"❌ Could not find trio matching `{identifier}`.")
                return
            
            trio_id, trio_data = trio_result
            
            if trio_data.get("holder_id") is not None:
                await ctx.send(f"❌ This trio is already held by someone else.")
                return
            
            # Claim the trio
            async with self.config.guild(ctx.guild).trios_inventory() as trios:
                trios[trio_id]["holder_id"] = target_user.id
                trios[trio_id]["holder_name"] = target_user.display_name
            
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            await ctx.send(f"✅ **{target_user.display_name}** has claimed **{trio_name}**!")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trios_inventory")
            await self._update_persistent_trio_list(ctx.guild)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "claiming trio")

    @trio.command(name="drop")
    @commands.guild_only()
    async def trio_drop(self, ctx: commands.Context, *, target_member: discord.Member = None):
        """Drop a trio back to the well"""
        target_user = target_member or ctx.author
        
        try:
            # Find user's trio
            trio_result = await self.trio_manager.find_user_trio(ctx.guild, target_user.id)
            if not trio_result:
                await ctx.send(f"❌ {target_user.display_name} doesn't have a trio to drop.")
                return
            
            trio_id, trio_data = trio_result
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            
            # Drop the trio
            async with self.config.guild(ctx.guild).trios_inventory() as trios:
                trios[trio_id]["holder_id"] = None
                trios[trio_id]["holder_name"] = None
            
            await ctx.send(f"✅ **{target_user.display_name}** has dropped **{trio_name}** back to the Well.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trios_inventory")
            await self._update_persistent_trio_list(ctx.guild)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "dropping trio")

    @trio.command(name="info")
    @commands.guild_only()
    async def trio_info(self, ctx: commands.Context, *, identifier: str):
        """Get detailed information about a trio"""
        try:
            trio_result = await self.trio_manager.find_trio_by_identifier(ctx.guild, identifier)
            if not trio_result:
                await ctx.send(f"❌ Could not find trio matching `{identifier}`.")
                return
            
            trio_id, trio_data = trio_result
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            abilities = trio_data.get("abilities", ["Unknown"] * 3)
            holder_id = trio_data.get("holder_id")
            holder_name = trio_data.get("holder_name")
            
            embed = discord.Embed(
                title=f"ℹ️ {trio_name}",
                color=await ctx.embed_colour()
            )
            
            embed.add_field(
                name="📝 Trio ID",
                value=trio_id,
                inline=True
            )
            
            embed.add_field(
                name="✨ Abilities",
                value="\n".join(f"• {ability}" for ability in abilities[:3]),
                inline=True
            )
            
            if holder_id == "IN_BOWL":
                status = "🥣 In a Bowl"
            elif holder_id and holder_name:
                status = f"👤 Held by {holder_name}"
            else:
                status = "🌊 In the Well"
            
            embed.add_field(
                name="📍 Status",
                value=status,
                inline=True
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "getting trio info")

    @trio.command(name="lock")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def trio_lock(self, ctx: commands.Context):
        """Lock the trio system (admin only)"""
        try:
            await self.config.guild(ctx.guild).trio_system_locked.set(True)
            await ctx.send("🔒 Trio system has been locked. No trio operations can be performed.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trio_system_locked")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "locking trio system")

    @trio.command(name="unlock")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def trio_unlock(self, ctx: commands.Context):
        """Unlock the trio system (admin only)"""
        try:
            await self.config.guild(ctx.guild).trio_system_locked.set(False)
            await ctx.send("🔓 Trio system has been unlocked. Trio operations can now be performed.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trio_system_locked")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "unlocking trio system")

    @trio.command(name="bowstore")
    @commands.guild_only()
    async def trio_bowl_store(self, ctx: commands.Context, *, identifier: str):
        """Store a trio in the bowl"""
        try:
            # Check if system is locked
            locked = await self.data_manager.get_cached(ctx.guild.id, "trio_system_locked", False)
            if locked:
                await ctx.send("🔒 The trio system is currently locked.")
                return
            
            # Find the trio
            trio_result = await self.trio_manager.find_trio_by_identifier(ctx.guild, identifier)
            if not trio_result:
                await ctx.send(f"❌ Could not find trio `{identifier}`.")
                return
            
            trio_id, trio_data = trio_result
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            
            # Check if trio is held
            if not trio_data.get("holder_id"):
                await ctx.send(f"❌ **{trio_name}** is not currently held by anyone.")
                return
            
            # Move to bowl
            async with self.config.guild(ctx.guild).trios_inventory() as trios:
                trios[trio_id]["holder_id"] = None
                trios[trio_id]["holder_name"] = None
                trios[trio_id]["in_bowl"] = True
            
            await ctx.send(f"✅ **{trio_name}** has been placed in the bowl.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trios_inventory")
            await self._update_persistent_trio_list(ctx.guild)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "storing trio in bowl")

    @trio.command(name="claimbowl")
    @commands.guild_only()
    async def trio_claim_from_bowl(self, ctx: commands.Context, identifier: str, *, target_member: discord.Member = None):
        """Claim a trio from the bowl"""
        target_user = target_member or ctx.author
        
        try:
            # Check if system is locked
            locked = await self.data_manager.get_cached(ctx.guild.id, "trio_system_locked", False)
            if locked:
                await ctx.send("🔒 The trio system is currently locked.")
                return
            
            # Check if target user already has a trio
            existing_trio = await self.trio_manager.find_user_trio(ctx.guild, target_user.id)
            if existing_trio:
                existing_name = existing_trio[1].get("name", f"Trio #{existing_trio[0]}")
                await ctx.send(f"❌ **{target_user.display_name}** already has **{existing_name}**.")
                return
            
            # Find the trio in bowl
            trio_result = await self.trio_manager.find_trio_by_identifier(ctx.guild, identifier)
            if not trio_result:
                await ctx.send(f"❌ Could not find trio `{identifier}`.")
                return
            
            trio_id, trio_data = trio_result
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            
            # Check if trio is in bowl
            if not trio_data.get("in_bowl", False):
                await ctx.send(f"❌ **{trio_name}** is not in the bowl.")
                return
            
            # Claim from bowl
            async with self.config.guild(ctx.guild).trios_inventory() as trios:
                trios[trio_id]["holder_id"] = target_user.id
                trios[trio_id]["holder_name"] = target_user.display_name
                trios[trio_id]["in_bowl"] = False
            
            await ctx.send(f"✅ **{target_user.display_name}** has claimed **{trio_name}** from the bowl!")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trios_inventory")
            await self._update_persistent_trio_list(ctx.guild)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "claiming trio from bowl")

    @trio.command(name="empty")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def trio_empty_bowl(self, ctx: commands.Context, *, identifier: str):
        """Remove a trio from the bowl (admin only)"""
        try:
            # Find the trio
            trio_result = await self.trio_manager.find_trio_by_identifier(ctx.guild, identifier)
            if not trio_result:
                await ctx.send(f"❌ Could not find trio `{identifier}`.")
                return
            
            trio_id, trio_data = trio_result
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            
            # Check if trio is in bowl
            if not trio_data.get("in_bowl", False):
                await ctx.send(f"❌ **{trio_name}** is not in the bowl.")
                return
            
            # Remove from bowl
            async with self.config.guild(ctx.guild).trios_inventory() as trios:
                trios[trio_id]["in_bowl"] = False
            
            await ctx.send(f"✅ **{trio_name}** has been removed from the bowl.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trios_inventory")
            await self._update_persistent_trio_list(ctx.guild)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "emptying trio from bowl")

    @trio.command(name="listbowl")
    @commands.guild_only()
    async def trio_list_bowl(self, ctx: commands.Context):
        """List all trios currently in the bowl"""
        try:
            trios = await self.data_manager.get_cached(ctx.guild.id, "trios_inventory", {})
            
            bowl_trios = []
            for trio_id, trio_data in trios.items():
                if trio_data.get("in_bowl", False):
                    trio_name = trio_data.get("name", f"Trio #{trio_id}")
                    abilities = trio_data.get("abilities", ["Unknown", "Unknown", "Unknown"])
                    bowl_trios.append(f"**{trio_name}** (`{trio_id}`)\n  ↳ {' • '.join(abilities)}")
            
            if not bowl_trios:
                await ctx.send("🥣 The trio bowl is empty.")
                return
            
            embed = discord.Embed(
                title="🥣 Trio Bowl",
                description="\n\n".join(bowl_trios),
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now()
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing bowl trios")

    @trio.command(name="mine")
    @commands.guild_only()
    async def trio_mine(self, ctx: commands.Context, *, target_member: discord.Member = None):
        """Check your trio or someone else's trio"""
        target_user = target_member or ctx.author
        
        try:
            trio_result = await self.trio_manager.find_user_trio(ctx.guild, target_user.id)
            if not trio_result:
                if target_member:
                    await ctx.send(f"❌ **{target_user.display_name}** doesn't have a trio.")
                else:
                    await ctx.send("❌ You don't have a trio.")
                return
            
            trio_id, trio_data = trio_result
            trio_name = trio_data.get("name", f"Trio #{trio_id}")
            abilities = trio_data.get("abilities", ["Unknown", "Unknown", "Unknown"])
            
            embed = discord.Embed(
                title=f"🔮 {target_user.display_name}'s Trio",
                color=discord.Color.purple(),
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(
                name=trio_name,
                value=f"**ID:** {trio_id}\n**Abilities:** {' • '.join(abilities)}",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "checking trio")

    # ==========================================
    # TRIO TITLE MANAGEMENT
    # ==========================================
    @commands.group(name="triotitle")
    @commands.guild_only()
    async def trio_title(self, ctx: commands.Context):
        """Manage trio titles"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @trio_title.command(name="set")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def trio_title_set(self, ctx: commands.Context, user: discord.Member, *, title: str):
        """Set a user's trio title (admin only)"""
        try:
            if len(title) > 100:
                await ctx.send("❌ Title must be 100 characters or less.")
                return
            
            sanitized_title = InputValidator.sanitize_user_input(title, 100)
            
            async with self.config.guild(ctx.guild).trio_titles() as titles:
                titles[str(user.id)] = sanitized_title
            
            await ctx.send(f"✅ Set **{user.display_name}**'s trio title to: `{sanitized_title}`")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trio_titles")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting trio title")

    @trio_title.command(name="remove")
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def trio_title_remove(self, ctx: commands.Context, user: discord.Member):
        """Remove a user's trio title (admin only)"""
        try:
            async with self.config.guild(ctx.guild).trio_titles() as titles:
                if str(user.id) in titles:
                    del titles[str(user.id)]
                    await ctx.send(f"✅ Removed **{user.display_name}**'s trio title.")
                else:
                    await ctx.send(f"❌ **{user.display_name}** doesn't have a trio title.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "trio_titles")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "removing trio title")

    @trio_title.command(name="list")
    @commands.guild_only()
    async def trio_title_list(self, ctx: commands.Context):
        """List all trio titles"""
        try:
            titles = await self.data_manager.get_cached(ctx.guild.id, "trio_titles", {})
            
            if not titles:
                await ctx.send("No trio titles have been set.")
                return
            
            title_list = []
            for user_id, title in titles.items():
                try:
                    user = ctx.guild.get_member(int(user_id))
                    if user:
                        title_list.append(f"**{user.display_name}**: {title}")
                    else:
                        title_list.append(f"**Unknown User ({user_id})**: {title}")
                except ValueError:
                    continue
            
            if not title_list:
                await ctx.send("No valid trio titles found.")
                return
            
            embed = discord.Embed(
                title="🏆 Trio Titles",
                description="\n".join(title_list),
                color=discord.Color.gold(),
                timestamp=datetime.datetime.now()
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing trio titles")

    # ==========================================
    # ARTIFACT SYSTEM
    # ==========================================
    @commands.group(aliases=["art"])
    @commands.guild_only()
    async def artifact(self, ctx: commands.Context):
        """Manage and use weekly-resettable artifacts"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @artifact.group(name="set")
    @checks.admin_or_permissions(manage_guild=True)
    async def artifact_set(self, ctx: commands.Context):
        """Admin commands for setting up artifacts"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @artifact_set.command(name="add")
    async def artifact_add(self, ctx: commands.Context, item_id: str, *, item_name: str):
        """Add or update a weekly-resettable artifact
        
        The ID should be a short, unique identifier (e.g., DPF).
        Example: [p]artifact set add DPF Dry Palm Frond
        """
        try:
            item_id_upper = item_id.upper()
            
            async with self.config.guild(ctx.guild).weekly_artifacts() as artifacts:
                artifacts[item_id_upper] = {
                    "name": item_name,
                    "status": "Unclaimed"
                }
            
            await ctx.send(f"✅ Added artifact **{item_name}** (ID: {item_id_upper}) with status 'Unclaimed'.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "weekly_artifacts")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "adding artifact")

    @artifact_set.command(name="status")
    async def artifact_set_status(self, ctx: commands.Context, item_id: str, *, new_status: str):
        """Manually set the status of an artifact
        
        Valid statuses are: Unclaimed, Available, Used
        Example: [p]artifact set status DPF Available
        """
        try:
            valid_statuses = ["Unclaimed", "Available", "Used"]
            if new_status not in valid_statuses:
                await ctx.send(f"❌ Invalid status. Valid options: {', '.join(valid_statuses)}")
                return
            
            item_id_upper = item_id.upper()
            
            async with self.config.guild(ctx.guild).weekly_artifacts() as artifacts:
                if item_id_upper not in artifacts:
                    await ctx.send(f"❌ Artifact with ID `{item_id_upper}` not found.")
                    return
                
                old_status = artifacts[item_id_upper].get("status", "Unknown")
                artifacts[item_id_upper]["status"] = new_status
                
                # Clear used_by if changing away from Used
                if new_status != "Used":
                    artifacts[item_id_upper].pop("used_by", None)
            
            artifact_name = artifacts[item_id_upper]["name"]
            await ctx.send(f"✅ Changed **{artifact_name}** status from '{old_status}' to '{new_status}'.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "weekly_artifacts")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting artifact status")

    @artifact_set.command(name="remove", aliases=["delete", "del"])
    async def artifact_remove(self, ctx: commands.Context, item_id: str):
        """Remove an artifact from tracking"""
        try:
            item_id_upper = item_id.upper()
            
            async with self.config.guild(ctx.guild).weekly_artifacts() as artifacts:
                if item_id_upper not in artifacts:
                    await ctx.send(f"❌ Artifact with ID `{item_id_upper}` not found.")
                    return
                
                artifact_name = artifacts[item_id_upper]["name"]
                del artifacts[item_id_upper]
            
            await ctx.send(f"✅ Removed artifact **{artifact_name}** (ID: {item_id_upper}).")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "weekly_artifacts")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "removing artifact")

    @artifact.command(name="status", aliases=["list"])
    async def artifact_status(self, ctx: commands.Context):
        """Display the status of all weekly-resettable artifacts"""
        try:
            artifacts = await self.data_manager.get_cached(ctx.guild.id, "weekly_artifacts", {})
            
            if not artifacts:
                await ctx.send("No artifacts have been defined for this server.")
                return
            
            lines = []
            for item_id, data in sorted(artifacts.items()):
                name = data.get("name", "Unknown")
                status = data.get("status", "Unknown")
                used_by = data.get("used_by", "")
                
                status_emoji = {
                    "Unclaimed": "⚪",
                    "Available": "🟢", 
                    "Used": "🔴"
                }.get(status, "❓")
                
                line = f"{status_emoji} \u001b[1m{name}\u001b[0m (ID: {item_id}) - {status}"
                if status == "Used" and used_by:
                    line += f" by {used_by}"
                
                lines.append(line)
            
            embeds = MessageFormatter.create_paginated_embeds(
                lines, "🏺 Weekly Artifacts", await ctx.embed_colour()
            )
            
            for embed in embeds:
                await ctx.send(embed=embed)
                
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing artifacts")

    @artifact.command(name="claim")
    async def artifact_claim(self, ctx: commands.Context, *, identifier: str):
        """Claim an 'Unclaimed' artifact, making it 'Available' to be used"""
        try:
            async with self.config.guild(ctx.guild).weekly_artifacts() as artifacts:
                found_id = None
                for item_id, data in artifacts.items():
                    if identifier.upper() == item_id or identifier.lower() == data.get("name", "").lower():
                        found_id = item_id
                        break
                
                if not found_id:
                    await ctx.send(f"❌ Could not find an artifact matching `{identifier}`.")
                    return
                
                target_artifact = artifacts[found_id]
                
                if target_artifact.get("status") != "Unclaimed":
                    current_status = target_artifact.get("status", "Unknown")
                    await ctx.send(f"❌ The **{target_artifact['name']}** cannot be claimed. Current status: `{current_status}`.")
                    return
                
                # Claim the artifact
                target_artifact["status"] = "Available"
                
                await ctx.send(f"✅ **{ctx.author.display_name}** has claimed the **{target_artifact['name']}**. It is now available to be used.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "weekly_artifacts")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "claiming artifact")

    @artifact.command(name="use")
    async def artifact_use(self, ctx: commands.Context, *, arguments: str):
        """Use a weekly artifact, marking it as unavailable for the rest of the cycle
        
        You can use the artifact's short ID or its full name.
        To use it for someone else, mention them at the end.
        
        Examples:
        [p]artifact use DPF
        [p]artifact use Dry Palm Frond
        [p]artifact use DPF @username
        """
        try:
            # Parse arguments to extract identifier and optional target user
            parts = arguments.strip().split()
            target_user = ctx.author
            identifier = arguments
            
            # Check if last part is a user mention
            if parts:
                try:
                    # Try to convert last part to member
                    potential_member = await commands.MemberConverter().convert(ctx, parts[-1])
                    target_user = potential_member
                    identifier = " ".join(parts[:-1])
                except commands.BadArgument:
                    # Not a valid member mention, use full string as identifier
                    pass
            
            if not identifier:
                await ctx.send("❌ You need to specify which artifact to use.")
                return
            
            async with self.config.guild(ctx.guild).weekly_artifacts() as artifacts:
                found_id = None
                for item_id, data in artifacts.items():
                    if identifier.upper() == item_id or identifier.lower() == data.get("name", "").lower():
                        found_id = item_id
                        break
                
                if not found_id:
                    await ctx.send(f"❌ Could not find an artifact matching `{identifier}`.")
                    return
                
                target_artifact = artifacts[found_id]
                
                if target_artifact.get("status") != "Available":
                    current_status = target_artifact.get("status", "Unknown")
                    await ctx.send(f"❌ The **{target_artifact['name']}** is not available to be used. Current status: `{current_status}`.")
                    return
                
                # Mark the artifact as used
                target_artifact["status"] = "Used"
                target_artifact["used_by"] = target_user.display_name
                
                await ctx.send(f"✅ **{target_user.display_name}** has used the **{target_artifact['name']}** for this cycle.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "weekly_artifacts")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "using artifact")

    # ==========================================
    # ADMINISTRATIVE CONFIGURATION (CUSTODIANSET)
    # ==========================================
    @commands.group(aliases=["custodianset"])
    @checks.admin_or_permissions(manage_guild=True)
    async def setup(self, ctx: commands.Context):
        """Administrative configuration for the Custodian system"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @setup.command(name="resettime")
    @commands.guild_only()
    async def setup_resettime(self, ctx: commands.Context, day: int, hour: int, minute: int = 0):
        """Set the weekly reset time (day: 0=Monday, 6=Sunday, hour: 0-23 UTC)"""
        try:
            if not (0 <= day <= 6):
                await ctx.send("❌ Day must be 0-6 (0=Monday, 6=Sunday).")
                return
            
            if not (0 <= hour <= 23):
                await ctx.send("❌ Hour must be 0-23 (UTC).")
                return
            
            if not (0 <= minute <= 59):
                await ctx.send("❌ Minute must be 0-59.")
                return
            
            async with self.config.guild(ctx.guild).settings() as settings:
                settings["reset_day"] = day
                settings["reset_hour"] = hour
                settings["reset_minute"] = minute
            
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            await ctx.send(f"✅ Weekly reset set to {day_names[day]} at {hour:02d}:{minute:02d} UTC.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "settings")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting reset time")

    @setup.command(name="channel")
    @commands.guild_only()
    async def setup_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the tracking channel for announcements"""
        try:
            target_channel = channel or ctx.channel
            
            await self.config.guild(ctx.guild).tracking_channel.set(target_channel.id)
            await ctx.send(f"✅ Tracking channel set to {target_channel.mention}.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "tracking_channel")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting tracking channel")

    @setup.command(name="defaultlimit")
    @commands.guild_only()
    async def setup_defaultlimit(self, ctx: commands.Context, limit: int):
        """Set the default breach limit for new thinspaces"""
        try:
            if limit < 1:
                await ctx.send("❌ Limit must be at least 1.")
                return
            
            if limit > 100:
                await ctx.send("❌ Limit must be 100 or less.")
                return
            
            await self.config.guild(ctx.guild).default_limit.set(limit)
            await ctx.send(f"✅ Default thinspace limit set to {limit}.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "default_limit")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting default limit")

    @setup.command(name="alllimits")
    @commands.guild_only()
    async def setup_set_all_limits(self, ctx: commands.Context, new_limit: int):
        """Update all existing thinspace limits"""
        try:
            if new_limit < 1:
                await ctx.send("❌ Limit must be at least 1.")
                return
            
            if new_limit > 100:
                await ctx.send("❌ Limit must be 100 or less.")
                return
            
            async with self.config.guild(ctx.guild).thinspaces() as thinspaces:
                updated_count = 0
                for space_name in thinspaces:
                    thinspaces[space_name]["limit"] = new_limit
                    updated_count += 1
            
            await ctx.send(f"✅ Updated {updated_count} thinspace limits to {new_limit}.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "thinspaces")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "updating all limits")

    @setup.command(name="showsettings")
    @commands.guild_only()
    async def setup_showsettings(self, ctx: commands.Context):
        """Show current configuration settings"""
        try:
            settings = await self.data_manager.get_cached(ctx.guild.id, "settings", {})
            
            embed = discord.Embed(
                title="⚙️ Custodian Configuration",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            
            # Reset settings
            reset_day = settings.get("reset_day", 0)
            reset_hour = settings.get("reset_hour", 12)
            reset_minute = settings.get("reset_minute", 0)
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            
            embed.add_field(
                name="🔄 Reset Schedule",
                value=f"{day_names[reset_day]} at {reset_hour:02d}:{reset_minute:02d} UTC",
                inline=True
            )
            
            # Channel settings
            tracking_channel_id = await self.data_manager.get_cached(ctx.guild.id, "tracking_channel", None)
            if tracking_channel_id:
                tracking_channel = ctx.guild.get_channel(tracking_channel_id)
                channel_name = tracking_channel.mention if tracking_channel else f"Unknown ({tracking_channel_id})"
            else:
                channel_name = "Not set"
            
            embed.add_field(
                name="📢 Tracking Channel",
                value=channel_name,
                inline=True
            )
            
            # Limits and counts
            default_limit = await self.data_manager.get_cached(ctx.guild.id, "default_limit", 14)
            max_dreams = await self.data_manager.get_cached(ctx.guild.id, "max_dreams", 3)
            dreams_left = await self.data_manager.get_cached(ctx.guild.id, "dreams_left", 3)
            max_gates = await self.data_manager.get_cached(ctx.guild.id, "max_gates", 4)
            gates_available = await self.data_manager.get_cached(ctx.guild.id, "breachgates_available", 0)
            
            embed.add_field(
                name="🌌 Default Limit",
                value=str(default_limit),
                inline=True
            )
            
            embed.add_field(
                name="💭 Dreams",
                value=f"{dreams_left}/{max_dreams}",
                inline=True
            )
            
            embed.add_field(
                name="🔒 Gates",
                value=f"{gates_available}/{max_gates}",
                inline=True
            )
            
            # Cycle information
            current_cycle = await self.data_manager.get_cached(ctx.guild.id, "current_cycle", 1)
            reset_paused = await self.data_manager.get_cached(ctx.guild.id, "reset_paused", False)
            
            embed.add_field(
                name="🔄 Current Cycle",
                value=str(current_cycle),
                inline=True
            )
            
            embed.add_field(
                name="⏸️ Reset Status",
                value="Paused" if reset_paused else "Active",
                inline=True
            )
            
            # Next reset
            next_reset = await self.calculate_next_reset(ctx.guild)
            if next_reset:
                embed.add_field(
                    name="⏰ Next Reset",
                    value=f"<t:{int(next_reset.timestamp())}:R>",
                    inline=True
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "showing settings")

    @setup.command(name="setmaxdreams")
    @commands.guild_only()
    async def setup_setmaxdreams(self, ctx: commands.Context, count: int):
        """Set maximum dreams available"""
        try:
            if count < 0:
                await ctx.send("❌ Count must be 0 or greater.")
                return
            
            if count > 20:
                await ctx.send("❌ Count must be 20 or less.")
                return
            
            await self.config.guild(ctx.guild).max_dreams.set(count)
            await ctx.send(f"✅ Maximum dreams set to {count}.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "max_dreams")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting max dreams")

    @setup.command(name="setbreaches")
    @commands.guild_only()
    async def setup_setbreaches(self, ctx: commands.Context, thinspace_name: str, pre_gate: int, post_gate: int = 0):
        """Manually set breach counts for a thinspace"""
        try:
            is_valid, normalized_name = InputValidator.validate_thinspace_name(thinspace_name)
            if not is_valid:
                await ctx.send(f"❌ {normalized_name}")
                return
            
            if pre_gate < 0 or post_gate < 0:
                await ctx.send("❌ Breach counts must be 0 or greater.")
                return
            
            thinspace = await self.thinspace_manager.get_thinspace(ctx.guild, normalized_name)
            if not thinspace:
                await ctx.send(f"❌ Thinspace `{normalized_name}` doesn't exist.")
                return
            
            async with self.config.guild(ctx.guild).thinspaces() as thinspaces:
                thinspaces[normalized_name]["pre_gate_breaches"] = pre_gate
                thinspaces[normalized_name]["post_gate_breaches"] = post_gate
            
            await ctx.send(f"✅ Set `{normalized_name}` breaches: Pre-gate={pre_gate}, Post-gate={post_gate}")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "thinspaces")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting breaches")

    @setup.command(name="setdreams")
    @commands.guild_only()
    async def setup_setdreams(self, ctx: commands.Context, count: int):
        """Set current dreams remaining"""
        try:
            if count < 0:
                await ctx.send("❌ Count must be 0 or greater.")
                return
            
            max_dreams = await self.data_manager.get_cached(ctx.guild.id, "max_dreams", 3)
            if count > max_dreams:
                await ctx.send(f"❌ Count cannot exceed maximum dreams ({max_dreams}).")
                return
            
            await self.config.guild(ctx.guild).dreams_left.set(count)
            await ctx.send(f"✅ Dreams remaining set to {count}/{max_dreams}.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "dreams_left")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting dreams")

    @setup.command(name="setavailablegates")
    @commands.guild_only()
    async def setup_setavailablegates(self, ctx: commands.Context, count: int):
        """Set available gate count"""
        try:
            if count < 0:
                await ctx.send("❌ Count must be 0 or greater.")
                return
            
            max_gates = await self.data_manager.get_cached(ctx.guild.id, "max_gates", 4)
            if count > max_gates:
                await ctx.send(f"❌ Count cannot exceed maximum gates ({max_gates}).")
                return
            
            await self.config.guild(ctx.guild).breachgates_available.set(count)
            await ctx.send(f"✅ Available gates set to {count}/{max_gates}.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "breachgates_available")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting available gates")

    @setup.command(name="setmaxgates")
    @commands.guild_only()
    async def setup_setmaxgates(self, ctx: commands.Context, count: int):
        """Set maximum gate capacity"""
        try:
            if count < 0:
                await ctx.send("❌ Count must be 0 or greater.")
                return
            
            if count > 20:
                await ctx.send("❌ Count must be 20 or less.")
                return
            
            await self.config.guild(ctx.guild).max_gates.set(count)
            await ctx.send(f"✅ Maximum gates set to {count}.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "max_gates")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting max gates")

    @setup.command(name="setcycle")
    @commands.guild_only()
    async def setup_setcycle(self, ctx: commands.Context, number: int):
        """Set the current cycle number"""
        try:
            if number < 1:
                await ctx.send("❌ Cycle number must be 1 or greater.")
                return
            
            await self.config.guild(ctx.guild).current_cycle.set(number)
            await ctx.send(f"✅ Current cycle set to {number}.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "current_cycle")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "setting cycle")

    @setup.command(name="pausereset")
    @commands.guild_only()
    async def setup_pausereset(self, ctx: commands.Context):
        """Pause automatic weekly resets"""
        try:
            await self.config.guild(ctx.guild).reset_paused.set(True)
            await ctx.send("⏸️ Automatic weekly resets have been paused.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "reset_paused")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "pausing reset")

    @setup.command(name="unpausereset")
    @commands.guild_only()
    async def setup_unpausereset(self, ctx: commands.Context):
        """Resume automatic weekly resets"""
        try:
            await self.config.guild(ctx.guild).reset_paused.set(False)
            await ctx.send("▶️ Automatic weekly resets have been resumed.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "reset_paused")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "resuming reset")

    @setup.command(name="manualreset")
    @commands.is_owner()
    async def setup_manualreset(self, ctx: commands.Context):
        """Manually trigger a weekly reset (bot owner only)"""
        try:
            # Perform the reset
            old_cycle, new_cycle, next_reset = await self.perform_reset(ctx.guild)
            
            embed = discord.Embed(
                title="🔄 Manual Reset Completed",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            
            embed.add_field(
                name="Cycle Transition",
                value=f"Cycle {old_cycle} → Cycle {new_cycle}",
                inline=False
            )
            
            if next_reset:
                embed.add_field(
                    name="Next Reset",
                    value=f"<t:{int(next_reset.timestamp())}:R>",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
            # Send notification to tracking channel
            tracking_channel_id = await self.data_manager.get_cached(ctx.guild.id, "tracking_channel", None)
            if tracking_channel_id:
                tracking_channel = ctx.guild.get_channel(tracking_channel_id)
                if tracking_channel and tracking_channel != ctx.channel:
                    await tracking_channel.send(f"🔄 **Manual Reset Triggered** - Cycle {old_cycle} → Cycle {new_cycle}")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "manual reset")

    # ==========================================
    # BREACH TYPE MANAGEMENT
    # ==========================================
    @commands.group(name="breachtype")
    @checks.admin_or_permissions(manage_guild=True)
    async def breachtype(self, ctx: commands.Context):
        """Manage custom breach types"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @breachtype.command(name="add")
    @commands.guild_only()
    async def breachtype_add(self, ctx: commands.Context, name: str, cost: int):
        """Add a custom breach type"""
        try:
            if cost < 1:
                await ctx.send("❌ Cost must be at least 1.")
                return
            
            if cost > 20:
                await ctx.send("❌ Cost must be 20 or less.")
                return
            
            name_clean = name.lower().strip()
            if len(name_clean) > 20:
                await ctx.send("❌ Breach type name must be 20 characters or less.")
                return
            
            async with self.config.guild(ctx.guild).breach_types() as breach_types:
                if name_clean in breach_types:
                    await ctx.send(f"❌ Breach type `{name_clean}` already exists.")
                    return
                
                breach_types[name_clean] = cost
            
            await ctx.send(f"✅ Added breach type `{name_clean}` with cost {cost}.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "breach_types")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "adding breach type")

    @breachtype.command(name="remove")
    @commands.guild_only()
    async def breachtype_remove(self, ctx: commands.Context, name: str):
        """Remove a custom breach type"""
        try:
            name_clean = name.lower().strip()
            
            async with self.config.guild(ctx.guild).breach_types() as breach_types:
                if name_clean in breach_types:
                    del breach_types[name_clean]
                    await ctx.send(f"✅ Removed breach type `{name_clean}`.")
                else:
                    await ctx.send(f"❌ Breach type `{name_clean}` doesn't exist.")
            
            self.data_manager.invalidate_cache(ctx.guild.id, "breach_types")
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "removing breach type")

    @breachtype.command(name="list")
    @commands.guild_only()
    async def breachtype_list(self, ctx: commands.Context):
        """List all available breach types"""
        try:
            # Get custom breach types
            custom_types = await self.data_manager.get_cached(ctx.guild.id, "breach_types", {})
            
            # Combine with default types
            all_types = {**DEFAULT_BREACH_TYPES, **custom_types}
            
            if not all_types:
                await ctx.send("No breach types available.")
                return
            
            embed = discord.Embed(
                title="⚡ Available Breach Types",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now()
            )
            
            default_list = []
            custom_list = []
            
            for name, cost in sorted(all_types.items()):
                type_str = f"**{name}**: {cost} breach(es)"
                
                if name in DEFAULT_BREACH_TYPES:
                    default_list.append(type_str)
                else:
                    custom_list.append(type_str)
            
            if default_list:
                embed.add_field(
                    name="🏭 Default Types",
                    value="\n".join(default_list),
                    inline=False
                )
            
            if custom_list:
                embed.add_field(
                    name="⚙️ Custom Types",
                    value="\n".join(custom_list),
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ErrorHandler.handle_discord_error(ctx, e, "listing breach types")

# This setup function is not used since __init__.py handles setup
# async def setup(bot: commands.Bot):
#     """Setup function for the cog"""
#     await bot.add_cog(CustodianRefactored(bot))