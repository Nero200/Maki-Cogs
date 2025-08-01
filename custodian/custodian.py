# custodian.py
import discord
import asyncio
import datetime
import random
import re # For parsing complex breach commands
from typing import Literal
from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import box, pagify

# Define breach types
DEFAULT_BREACH_TYPES = {
    "hand": 1, # Default type if none specified
    "hound": 2,
    "mole": 5,
}

class Custodian(commands.Cog):
    ANSI_RESET = "\u001b[0m"
    ANSI_RED = "\u001b[0;31m"
    ANSI_GREEN = "\u001b[0;32m"
    ANSI_YELLOW = "\u001b[0;33m"
    ANSI_BLUE = "\u001b[0;34m"
    ANSI_MAGENTA = "\u001b[0;35m"
    ANSI_CYAN = "\u001b[0;36m"
    
    # Trio List and Buttons ---

    class TrioMineActionView(discord.ui.View):
        def __init__(self, cog_instance, held_trio_id: str, held_trio_name: str, 
                     is_locked: bool, timeout=180.0):
            super().__init__(timeout=timeout)
            self.cog = cog_instance 
            self.held_trio_id = held_trio_id
            self.held_trio_name = held_trio_name
            self.is_locked = is_locked 
            self.interaction_user_id = None 
            self.message = None

            lock_button_label = "Unlock" if self.is_locked else "Lock"
            self.toggle_lock_button = discord.ui.Button(
                label=lock_button_label,
                style=discord.ButtonStyle.primary,
                custom_id="trio_mine_toggle_lock"
            )
            self.toggle_lock_button.callback = self.toggle_lock_callback
            self.add_item(self.toggle_lock_button)

            # Add other buttons (Drop, Place in Bowl) as they were
            # Ensure their decorators and method names are correct as per your file

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            # ... (this should be the version that allows admin override) ...
            if self.interaction_user_id is None:
                await interaction.response.send_message("This interaction is not properly initialized.", ephemeral=True)
                return False
            if interaction.user.id == self.interaction_user_id:
                return True
            if interaction.guild: 
                interactor_as_member = interaction.guild.get_member(interaction.user.id)
                if interactor_as_member and interactor_as_member.guild_permissions.manage_guild:
                    return True
            await interaction.response.send_message(
                "These buttons are for the user whose Trio is being displayed, or for server managers.", 
                ephemeral=True
            )
            return False

        async def on_timeout(self):
            for item in self.children:
                item.disabled = True
            if self.message:
                try: await self.message.edit(view=self)
                except discord.NotFound: pass
                except discord.HTTPException as e: print(f"Error editing message on timeout for TrioMineActionView: {e}")

        @discord.ui.button(label="Drop (to Well)", style=discord.ButtonStyle.danger, custom_id="trio_mine_drop")
        async def drop_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer() 
            successful_action = False
            async with self.cog.config.guild(interaction.guild).trios_inventory() as trios_inv:
                if self.held_trio_id in trios_inv:
                    trios_inv[self.held_trio_id]["holder_id"] = None
                    trios_inv[self.held_trio_id]["holder_name"] = None
                    successful_action = True
                else:
                    if self.message: await self.message.edit(content=f"Error: Could not find {self.held_trio_name} to drop.", view=None)
                    else: await interaction.followup.send(f"Error: Could not find {self.held_trio_name} to drop.", ephemeral=True)
                    return

            for item in self.children: item.disabled = True
            if self.message:
                await self.message.edit(
                    content=f"You have dropped '{self.held_trio_name}'. It is now in the Well.", 
                    view=self
                )
            
            if successful_action:
                await self.cog._update_persistent_trio_list(interaction.guild)
                
            # THE FIX: Get the original target user object from the stored ID
            target_user_for_claim = interaction.guild.get_member(self.interaction_user_id)
            if target_user_for_claim:
                await self.cog._display_trio_claim_options(interaction, target_user_for_claim=target_user_for_claim, followup=True)

        @discord.ui.button(label="Place in Bowl", style=discord.ButtonStyle.secondary, custom_id="trio_mine_bowl")
        async def bowl_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer() 
            successful_action = False
            async with self.cog.config.guild(interaction.guild).trios_inventory() as trios_inv:
                if self.held_trio_id in trios_inv:
                    trios_inv[self.held_trio_id]["holder_id"] = "IN_BOWL"
                    trios_inv[self.held_trio_id]["holder_name"] = "In a Bowl"
                    successful_action = True
                else:
                    if self.message: await self.message.edit(content=f"Error: Could not find {self.held_trio_name} to place in bowl.", view=None)
                    else: await interaction.followup.send(f"Error: Could not find {self.held_trio_name} to place in bowl.",ephemeral=True)
                    return

            for item in self.children: item.disabled = True
            if self.message:
                await self.message.edit(
                    content=f"You have placed '{self.held_trio_name}' into a Bowl.",
                    view=self
                )

            if successful_action:
                await self.cog._update_persistent_trio_list(interaction.guild)

            # THE FIX: Get the original target user object from the stored ID
            target_user_for_claim = interaction.guild.get_member(self.interaction_user_id)
            if target_user_for_claim:
                await self.cog._display_trio_claim_options(interaction, target_user_for_claim=target_user_for_claim, followup=True)

        async def toggle_lock_callback(self, interaction: discord.Interaction): # Assuming this callback exists and is correctly defined
            await interaction.response.defer() 
            user_id_str = str(self.interaction_user_id)
            action_message = ""
            new_lock_state = False

            async with self.cog.config.guild(interaction.guild).trio_user_locks() as user_locks:
                current_lock_state = user_locks.get(user_id_str, False)
                # Ensure you fetch the user object correctly to get the mention/name
                locked_user = self.cog.bot.get_user(self.interaction_user_id) or interaction.guild.get_member(self.interaction_user_id)
                locked_user_name = locked_user.mention if locked_user else f"User ID {user_id_str}" # Fallback

                if current_lock_state: 
                    user_locks[user_id_str] = False
                    new_lock_state = False
                    action_message = f"{locked_user_name}'s Trio status is now **unlocked**."
                else: 
                    user_locks[user_id_str] = True
                    new_lock_state = True
                    action_message = f"{locked_user_name}'s Trio status is now **locked**."
            
            self.is_locked = new_lock_state
            self.toggle_lock_button.label = "Unlock" if self.is_locked else "Lock"
            
            if self.message:
                try: await self.message.edit(view=self)
                except discord.HTTPException as e: print(f"Error editing message in toggle_lock_callback: {e}")
            
            await interaction.followup.send(action_message, ephemeral=False)
            
    class TrioClaimOptionsView(discord.ui.View):
        def __init__(self, cog_instance, interaction_user: discord.User, 
                     well_trios: dict, bowl_trios: dict, timeout=180.0):
            super().__init__(timeout=timeout)
            self.cog = cog_instance
            self.interaction_user = interaction_user
            self.message = None 

            select_menus_added = 0

            if well_trios:
                well_options = []
                for trio_id, data in sorted(well_trios.items(), key=lambda item: int(item[0]))[:25]: # Max 25 options
                    name = data.get("name", f"Trio #{trio_id}")
                    abilities_list = data.get("abilities", ["Unknown", "Unknown", "Unknown"])[:3]
                    abilities_display_str = ", ".join(abilities_list)
                    if len(abilities_display_str) > 100: # SelectOption description limit
                        abilities_display_str = abilities_display_str[:97] + "..."
                    
                    well_options.append(discord.SelectOption(
                        label=f"{name} (Well)", 
                        value=f"claim_well_{trio_id}",
                        description=abilities_display_str 
                    ))
                if well_options:
                    well_select = discord.ui.Select(placeholder="Choose a Trio from the Well...", options=well_options, custom_id="trio_claim_well_select")
                    well_select.callback = self.select_callback
                    self.add_item(well_select)
                    select_menus_added += 1

            if bowl_trios:
                bowl_options = []
                for trio_id, data in sorted(bowl_trios.items(), key=lambda item: int(item[0]))[:25]: # Max 25 options
                    name = data.get("name", f"Trio #{trio_id}")
                    # --- MODIFIED ABILITIES DISPLAY FOR SELECT MENU ---
                    abilities_list = data.get("abilities", ["Unknown", "Unknown", "Unknown"])[:3]
                    abilities_display_str = ", ".join(abilities_list)
                    if len(abilities_display_str) > 100: # SelectOption description limit
                        abilities_display_str = abilities_display_str[:97] + "..."
                    # --- END MODIFICATION ---

                    bowl_options.append(discord.SelectOption(
                        label=f"{name} (Bowl)",
                        value=f"claim_bowl_{trio_id}",
                        description=abilities_display_str
                    ))
                if bowl_options:
                    bowl_select = discord.ui.Select(placeholder="Choose a Trio from a Bowl...", options=bowl_options, custom_id="trio_claim_bowl_select")
                    bowl_select.callback = self.select_callback
                    self.add_item(bowl_select)
                    select_menus_added += 1
        
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            # self.interaction_user is the user for whom the claim options are being displayed
            if self.interaction_user is None: 
                await interaction.response.send_message("This interaction is not properly initialized.", ephemeral=True)
                return False

            # Allow interaction if the user is the one for whom the claim is intended
            if interaction.user.id == self.interaction_user.id:
                return True
            
            # OR if the interactor (the one who clicked) has 'Manage Server' permissions
            if interaction.guild: 
                interactor_as_member = interaction.guild.get_member(interaction.user.id)
                if interactor_as_member and interactor_as_member.guild_permissions.manage_guild:
                    # Optional: Send a quick ephemeral confirmation of override for the click itself
                    # await interaction.response.send_message("Admin interaction with select menu.", ephemeral=True, delete_after=2)
                    return True # Allow manager to interact

            # If neither of the above, deny interaction
            await interaction.response.send_message(
                "These selection options are for the user the claim is being made for, or for server managers.", 
                ephemeral=True
            )
            return False

        async def on_timeout(self):
            for item in self.children: item.disabled = True
            if self.message:
                try: await self.message.edit(content="Trio claiming selection timed out.", view=self)
                except discord.NotFound: pass
                except discord.HTTPException as e: print(f"Error editing message on timeout for TrioClaimOptionsView: {e}")

        # Inside your Custodian class, within TrioClaimOptionsView:

        async def select_callback(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True) 

            for item in self.children:
                item.disabled = True
            if self.message: 
                try:
                    await self.message.edit(view=self) 
                except discord.NotFound: 
                    pass 
                except discord.HTTPException as e:
                    print(f"Error editing original message in select_callback: {e}")

            selected_value = interaction.data["values"][0]
            action_type = ""
            trio_id_to_claim = ""

            if selected_value.startswith("claim_well_"):
                action_type = "Well"
                trio_id_to_claim = selected_value.replace("claim_well_", "")
            elif selected_value.startswith("claim_bowl_"):
                action_type = "Bowl"
                trio_id_to_claim = selected_value.replace("claim_bowl_", "")
            else:
                await interaction.followup.send("Invalid selection.", ephemeral=True)
                return

            user_trio_info = await self.cog._find_user_trio(interaction.guild, self.interaction_user.id)
            if user_trio_info is not None:
                await interaction.followup.send(
                    f"{self.interaction_user.mention}, it seems you already acquired a Trio while deciding. Action cancelled.", 
                    ephemeral=False 
                )
                return

            # --- Initialize claim_successful and message variables here ---
            trio_name_display_for_msg = f"Trio #{trio_id_to_claim}" # Default name
            abilities_list_str_for_msg = "Unknown Manifestations" # Default abilities
            claim_successful = False # <<< ENSURE THIS IS INITIALIZED TO FALSE
            # --- End initialization ---

            async with self.cog.config.guild(interaction.guild).trios_inventory() as trios_inv:
                if trio_id_to_claim in trios_inv:
                    trio_data = trios_inv[trio_id_to_claim]
                    # Update display names if found
                    trio_name_display_for_msg = trio_data.get("name", f"Trio #{trio_id_to_claim}")
                    abilities_list_str_for_msg = ", ".join(trio_data.get("abilities", ["Unknown Manifestations"]))
                    
                    expected_holder_id = None if action_type == "Well" else "IN_BOWL"
                    if trio_data.get("holder_id") != expected_holder_id:
                        await interaction.followup.send(
                            f"'{trio_name_display_for_msg}' is no longer in the {action_type}. "
                            "Someone else might have claimed it or moved it.", 
                            ephemeral=False 
                        )
                        return # claim_successful remains False

                    # All checks passed, perform the claim
                    trio_data["holder_id"] = self.interaction_user.id
                    trio_data["holder_name"] = self.interaction_user.display_name
                    claim_successful = True # Set to True because the claim happened
                else:
                    await interaction.followup.send(
                        f"Error: Trio #{trio_id_to_claim} could not be found in the inventory to complete the claim. "
                        "This might be an internal error.", 
                        ephemeral=True
                    )
                    return # claim_successful remains False
            
            # This block is now only reached if no early return occurred
            if claim_successful: 
                await interaction.followup.send(
                    f"{self.interaction_user.mention} has claimed '{trio_name_display_for_msg}' from the {action_type}!\n"
                    f"Manifestations Available: {abilities_list_str_for_msg}",
                    ephemeral=False 
                )
                await self.cog._update_persistent_trio_list(interaction.guild)

    async def _execute_trio_mine(self, interaction_or_ctx, user_for_mine: discord.User):
        """
        Core logic for 'trio mine'. Displays held Trio with actions, or claim options.
        Responds via interaction followup (if interaction) or ctx.send (if command).
        """
        guild = interaction_or_ctx.guild
        is_interaction = isinstance(interaction_or_ctx, discord.Interaction)

        user_trio_info = await self._find_user_trio(guild, user_for_mine.id)

        if user_trio_info: # User IS holding a Trio
            trio_id_str, trio_data = user_trio_info
            name = trio_data.get("name", f"Trio #{trio_id_str}")
            abilities = trio_data.get("abilities", [])
            abilities_str = ", ".join(abilities) if abilities else "None defined."

            embed = discord.Embed(
                title=f"Trio Status for {user_for_mine.display_name}",
                description=f"Currently holding: **{name}**",
                color=await self.bot.get_embed_colour(guild)
            )
            embed.add_field(name="Manifestations Available", value=abilities_str, inline=False)
            
            user_locks = await self.config.guild(guild).trio_user_locks()
            is_currently_locked = user_locks.get(str(user_for_mine.id), False)

            view = self.TrioMineActionView(self, trio_id_str, name, is_currently_locked)
            view.interaction_user_id = user_for_mine.id 
            
            if is_interaction:
                view.message = await interaction_or_ctx.followup.send(embed=embed, view=view, ephemeral=True)
            else: # commands.Context
                view.message = await interaction_or_ctx.send(embed=embed, view=view)
        
        else: # User is NOT holding a Trio
            message_content = f"{user_for_mine.mention} is not currently holding any Trio."
            if is_interaction:
                await interaction_or_ctx.followup.send(message_content, ephemeral=True)
                # For _display_trio_claim_options, it will also use followup if interaction is passed
                await self._display_trio_claim_options(interaction_or_ctx, target_user_for_claim=user_for_mine, followup=True)
            else: # commands.Context
                await interaction_or_ctx.send(message_content)
                await self._display_trio_claim_options(interaction_or_ctx, target_user_for_claim=user_for_mine, followup=False)
                
    async def _display_trio_claim_options(self, interaction_or_ctx, target_user_for_claim: discord.User, followup: bool = False):
        """Fetches available Trios and presents them in Select Menus for the target_user_for_claim."""
        guild = interaction_or_ctx.guild
        
        # NEW: Determine who is performing the interaction vs. who the claim is for.
        interactor = interaction_or_ctx.user
        user_to_claim = target_user_for_claim 

        all_trios_inv = await self.config.guild(guild).trios_inventory()
        
        available_well_trios = {
            tid: data for tid, data in all_trios_inv.items()
            if isinstance(data, dict) and data.get("holder_id") is None
        }
        available_bowl_trios = {
            tid: data for tid, data in all_trios_inv.items()
            if isinstance(data, dict) and data.get("holder_id") == "IN_BOWL"
        }
        
        if not available_well_trios and not available_bowl_trios:
            message_content = "There are currently no Trios available to claim from the Well or a Bowl."
            is_interaction = isinstance(interaction_or_ctx, discord.Interaction)
            
            # This logic remains the same, just for context
            if followup and is_interaction:
                await interaction_or_ctx.followup.send(message_content, ephemeral=True)
            elif isinstance(interaction_or_ctx, commands.Context):
                await interaction_or_ctx.send(message_content)
            elif hasattr(interaction_or_ctx, 'channel') and interaction_or_ctx.channel:
                await interaction_or_ctx.channel.send(message_content)
            else:
                print(f"Could not send 'no trios available' message for {user_to_claim.id} in _display_trio_claim_options")
            return

        # NEW: Check if the interactor is acting on behalf of someone else and set message accordingly.
        if interactor.id != user_to_claim.id:
            message_content = f"Choose a new Trio for {user_to_claim.mention} to claim from the options below:"
        else:
            message_content = f"{user_to_claim.mention}, you are free to claim a new Trio. Choose from the options below:"

        # The view is always initialized for the person who will receive the Trio.
        view = self.TrioClaimOptionsView(self, user_to_claim, available_well_trios, available_bowl_trios)
        
        target_to_send = None
        is_interaction = isinstance(interaction_or_ctx, discord.Interaction)
        is_interaction_followup = followup and is_interaction

        if is_interaction_followup:
            target_to_send = interaction_or_ctx.followup
        elif isinstance(interaction_or_ctx, commands.Context):
            target_to_send = interaction_or_ctx
        elif hasattr(interaction_or_ctx, 'channel') and interaction_or_ctx.channel:
             target_to_send = interaction_or_ctx.channel
        
        if target_to_send:
            # MODIFIED: When an admin acts for another, the claim options should be ephemeral to the admin.
            # A normal user claiming for themselves also gets an ephemeral response. This is good.
            ephemeral_setting = True if is_interaction else discord.utils.MISSING
            
            if hasattr(target_to_send, 'send'):
                try:
                    sent_message = await target_to_send.send(message_content, view=view, ephemeral=ephemeral_setting)
                    if view:
                        view.message = sent_message 
                except Exception as e_send:
                    print(f"[ERROR _display_trio_claim_options] Failed to send message with view: {e_send}")
                    origin_channel = interaction_or_ctx.channel if hasattr(interaction_or_ctx, 'channel') else None
                    if origin_channel:
                         await origin_channel.send("Failed to display Trio claim options. Check console.")
            else:
                 print(f"Could not send claim options message for {user_to_claim.id} - target_to_send has no send method.")
        else:
            print(f"Could not determine where to send claim options message for {user_to_claim.id}")
    
    async def _generate_trio_list_embeds(self, guild: discord.Guild, title_prefix: str = "Trio Inventory") -> list[discord.Embed]:
        """Generates a list of embeds for displaying all Trios."""
        trios_inv = await self.config.guild(guild).trios_inventory()
        embed_color = await self.bot.get_embed_colour(guild) # Get embed color once

        if not trios_inv:
            embed = discord.Embed(title=title_prefix, description="No Trios have been defined yet.", color=embed_color)
            return [embed]

        output_lines = []
        for trio_id_str, trio_data in sorted(trios_inv.items(), key=lambda item: int(item[0])):
            if not isinstance(trio_data, dict):
                output_lines.append(f"Trio #{trio_id_str}: {self.ANSI_RED}Error - Malformed Data{self.ANSI_RESET}")
                continue

            name = trio_data.get("name", f"Trio #{trio_id_str}")
            abilities = trio_data.get("abilities", ["Unknown", "Unknown", "Unknown"])
            abilities_padded = (abilities + ["Unknown"] * 3)[:3]
            abilities_str = f"[{abilities_padded[0]}, {abilities_padded[1]}, {abilities_padded[2]}]" # No color here for now
            
            holder_id = trio_data.get("holder_id")
            holder_name = trio_data.get("holder_name")
            status_str = ""

            if holder_id == "IN_BOWL":
                status_str = f"{self.ANSI_MAGENTA}In a Bowl{self.ANSI_RESET}"
            elif holder_id is not None and holder_name is not None:
                status_str = f"{self.ANSI_YELLOW}{holder_name}{self.ANSI_RESET}"
            else: 
                status_str = f"{self.ANSI_BLUE}In the Well{self.ANSI_RESET}"
            
            output_lines.append(f"{name} {abilities_str} - {status_str}")
        
        if not output_lines: # Should not happen if trios_inv was not empty
            embed = discord.Embed(title=title_prefix, description="No Trios to display after formatting.", color=embed_color)
            return [embed]

        generated_embeds = []
        MAX_LINES_PER_EMBED = 15 
        for i in range(0, len(output_lines), MAX_LINES_PER_EMBED):
            chunk = output_lines[i:i+MAX_LINES_PER_EMBED]
            current_page_title = title_prefix
            if len(output_lines) > MAX_LINES_PER_EMBED:
                current_page_title += f" (Page {i//MAX_LINES_PER_EMBED + 1})"
            
            page_text_content = '\n'.join(chunk)
            description_content = f"```ansi\n{page_text_content}\n```"

            embed_page = discord.Embed(title=current_page_title, description=description_content, color=embed_color)
            generated_embeds.append(embed_page)
            
        return generated_embeds
        
    async def _update_persistent_trio_list(self, guild: discord.Guild):
        guild_config = self.config.guild(guild)
        channel_id = await guild_config.persistent_trio_list_channel_id()
        
        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            await guild_config.persistent_trio_list_channel_id.set(None)
            await guild_config.persistent_trio_list_message_ids.set([])
            return

        perms = channel.permissions_for(guild.me)
        if not (perms.send_messages and perms.embed_links and perms.manage_messages and perms.read_message_history):
            return

        old_message_ids = await guild_config.persistent_trio_list_message_ids()

        new_embeds_list = await self._generate_trio_list_embeds(guild, "Trio Tracking")
        if not new_embeds_list: # Should contain at least one "No Trios" embed if empty
            return
        if len(new_embeds_list) == 1 and ("No Trios have been defined yet." in new_embeds_list[0].description or "No Trios to display after formatting." in new_embeds_list[0].description):
             print("[DEBUG UPDATE_LIST] New embed list is effectively empty (e.g., 'No Trios defined').")
        
        can_edit = (len(new_embeds_list) == len(old_message_ids)) and old_message_ids and len(new_embeds_list) > 0
        
        if can_edit:
            edits_successful = True
            for i, msg_id in enumerate(old_message_ids):
                try:
                    message_to_edit = await channel.fetch_message(msg_id)
                    await message_to_edit.edit(embed=new_embeds_list[i])
                except discord.NotFound:
                    edits_successful = False; break
                except discord.Forbidden:
                    edits_successful = False; break
                except Exception as e:
                    import traceback; traceback.print_exc()
                    edits_successful = False; break
            
            if edits_successful:
                return # Edits done, work finished
        
        # Delete Old Messages
        if old_message_ids:
            for msg_id in old_message_ids:
                try:
                    message_to_delete = await channel.fetch_message(msg_id)
                    await message_to_delete.delete()
                except discord.NotFound: print(f"[DEBUG UPDATE_LIST] Old message {msg_id} was already gone.")
                except discord.Forbidden: print(f"[DEBUG UPDATE_LIST] FORBIDDEN to delete old message {msg_id}.")
                except Exception as e: print(f"[DEBUG UPDATE_LIST] Error deleting old message {msg_id}: {e}")
        
        await guild_config.persistent_trio_list_message_ids.set([]) # Clear IDs before adding new ones

        new_message_ids_to_store = []
        
        for i, embed_to_post in enumerate(new_embeds_list):
            try:
                msg = await channel.send(embed=embed_to_post)
                new_message_ids_to_store.append(msg.id)
                # THE FIX: Save the growing list of IDs back to config after each message is sent.
                await guild_config.persistent_trio_list_message_ids.set(new_message_ids_to_store)
            except discord.Forbidden:
                break 
            except Exception as e:
                import traceback; traceback.print_exc()
                break 
        
    async def _delete_message_after_delay(self, message: discord.Message, delay: int):
        """Waits for a delay and then attempts to delete the given message."""
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except discord.NotFound:
            # Message was already deleted by someone else or a previous attempt
            print(f"[AutoDelete] Message {message.id} already deleted.")
        except discord.Forbidden:
            print(f"[AutoDelete] Lacking 'Manage Messages' permission to delete message {message.id} in #{message.channel.name}.")
            # Optionally, you could try to notify an admin or log this more formally if it happens often.
        except Exception as e:
            print(f"[AutoDelete] Error deleting message {message.id}: {e}")
            import traceback
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild: return

        guild_config = self.config.guild(message.guild)
        auto_delete_channel_id = await guild_config.persistent_trio_list_channel_id() 

        if not (auto_delete_channel_id and message.channel.id == auto_delete_channel_id):
            return

        # Add a small delay for bot's own messages to allow config to potentially settle from a command
        # This is a pragmatic attempt to reduce race conditions.
        if message.author.id == self.bot.user.id:
            await asyncio.sleep(0.2) # Very short delay

        persistent_list_msg_ids = await guild_config.persistent_trio_list_message_ids()
        if message.id in persistent_list_msg_ids:
            return 

        control_panel_msg_id = await guild_config.trio_control_panel_message_id()
        # This check is now more critical: if control_panel_msg_id is None (because we just cleared it before posting a new one),
        # this message (if it's the new panel) won't match here.
        if message.id == control_panel_msg_id: 
            return
        
        # If it's our bot's message, and it didn't match any of the above protected IDs
        if message.author.id == self.bot.user.id:
            # At this point, if control_panel_msg_id was None, and this is the new panel message,
            # it would be caught here. This means the config set for the NEW panel ID must happen *fast*.
            # The asyncio.sleep(0.2) above is to give the 'postcontrolpanel' command a chance to save the new ID.
            delay = 30 
            self.bot.loop.create_task(self._delete_message_after_delay(message, delay))
        elif not message.author.bot: # Human user
            delay = 30 
            self.bot.loop.create_task(self._delete_message_after_delay(message, delay))

    class TargetUserSelectView(discord.ui.View):
        def __init__(self, cog_instance, original_interactor_id: int):
            super().__init__(timeout=180.0)
            self.cog = cog_instance
            self.original_interactor_id = original_interactor_id
            # self.message is not needed here as we use interaction.edit_original_response()

            user_select = discord.ui.UserSelect(
                custom_id="trio_target_user_select",
                placeholder="Select a user to manage their Trio...",
                min_values=1,
                max_values=1,
            )
            user_select.callback = self.user_select_callback
            self.add_item(user_select)

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.original_interactor_id:
                await interaction.response.send_message("This selection is not for you.", ephemeral=True)
                return False
            return True
        
        async def on_timeout(self):
            for item in self.children: 
                item.disabled = True
            # Attempt to edit the original message this view was attached to
            # This requires the interaction that sent the view to be available or its message
            # For simplicity, we'll just disable. A persistent message might need better handling.
            # If interaction.message was stored on self, we could use it.
            # Since we're using interaction.edit_original_response in callbacks,
            # we need to ensure this view knows *which* original interaction to edit for timeout.
            # This is complex if the original interaction isn't stored.
            # For now, let's assume visual disabling is enough for timeout.
            # If self.message was set by interaction.response.send_message, then:
            if hasattr(self, '_original_interaction_message_id') and self._original_interaction_message_id and interaction.channel:
                try:
                    msg_to_edit = await interaction.channel.fetch_message(self._original_interaction_message_id)
                    await msg_to_edit.edit(content="User selection timed out.", view=self)
                except: pass # Best effort


        async def user_select_callback(self, interaction: discord.Interaction):
            print(f"[DEBUG TargetUserSelectView] user_select_callback entered by {interaction.user.name} ({interaction.user.id})")
            # Defer ephemerally, as _execute_trio_mine will send its own ephemeral followups
            await interaction.response.defer(ephemeral=True, thinking=False) 
            
            selected_user_id_str = interaction.data["values"][0] 
            print(f"[DEBUG TargetUserSelectView] Selected user ID string: {selected_user_id_str}")
            
            target_user_obj = None
            try:
                target_user_obj = await self.cog.bot.fetch_user(int(selected_user_id_str))
                print(f"[DEBUG TargetUserSelectView] Fetched target_user_obj: {target_user_obj.name if target_user_obj else 'None'}")
            except ValueError:
                print(f"[DEBUG TargetUserSelectView] ValueError fetching user ID: {selected_user_id_str}")
                await interaction.followup.send("Invalid user ID format received.", ephemeral=True)
                return
            except discord.NotFound:
                print(f"[DEBUG TargetUserSelectView] User ID not found: {selected_user_id_str}")
                await interaction.followup.send("Could not fetch user details for the selected ID (user not found).", ephemeral=True)
                return
            except Exception as e:
                print(f"[DEBUG TargetUserSelectView] Other error fetching user: {e}")
                await interaction.followup.send("An error occurred trying to fetch user details.", ephemeral=True)
                return

            if not target_user_obj:
                print(f"[DEBUG TargetUserSelectView] target_user_obj is None after fetch attempt.")
                await interaction.followup.send("Could not find that user object.", ephemeral=True)
                return

            invoker_can_manage = interaction.user.guild_permissions.manage_guild
            print(f"[DEBUG TargetUserSelectView] Invoker ({interaction.user.name}) manage_guild: {invoker_can_manage}")
            
            can_proceed = False
            if target_user_obj.id == interaction.user.id: 
                print(f"[DEBUG TargetUserSelectView] Target user ({target_user_obj.name}) is self. Proceeding.")
                can_proceed = True
            elif invoker_can_manage: 
                print(f"[DEBUG TargetUserSelectView] Invoker ({interaction.user.name}) has manage_guild. Proceeding.")
                can_proceed = True
            else: 
                user_locks = await self.cog.config.guild(interaction.guild).trio_user_locks()
                is_target_locked = user_locks.get(str(target_user_obj.id), False)
                print(f"[DEBUG TargetUserSelectView] Target user ({target_user_obj.name}) is locked: {is_target_locked}. Invoker is not manager.")
                if not is_target_locked: 
                    print(f"[DEBUG TargetUserSelectView] Target ({target_user_obj.name}) is not locked by them. Proceeding.")
                    can_proceed = True
            
            print(f"[DEBUG TargetUserSelectView] Final 'can_proceed' value: {can_proceed}")
            if can_proceed:
                for item in self.children: 
                    item.disabled = True
                try:
                    await interaction.edit_original_response(
                        content=f"Proceeding to manage Trios for {target_user_obj.display_name}...", 
                        view=self 
                    )
                    print(f"[DEBUG TargetUserSelectView] Edited original response. Calling _execute_trio_mine for {target_user_obj.name}")
                except discord.HTTPException as e: 
                    print(f"[DEBUG TargetUserSelectView] Error editing original select message: {e}")
                
                await self.cog._execute_trio_mine(interaction, target_user_obj)
            else:
                print(f"[DEBUG TargetUserSelectView] Cannot proceed. Sending lock message for {target_user_obj.name}")
                await interaction.followup.send(
                    f"{target_user_obj.display_name} has locked their Trio status, and you lack 'Manage Server' permission to override.", 
                    ephemeral=True
                )

    class BowlManagementSelectView(discord.ui.View):
        def __init__(self, cog_instance, original_interactor_id: int, all_trios_inv: dict):
            super().__init__(timeout=180.0)
            self.cog = cog_instance
            self.original_interactor_id = original_interactor_id
            self.message = None

            trio_options = []
            if all_trios_inv:
                for trio_id, data in sorted(all_trios_inv.items(), key=lambda item: int(item[0]))[:25]: # Max 25
                    name = data.get("name", f"Trio #{trio_id}")
                    holder_id = data.get("holder_id")
                    current_status = "In Well"
                    if holder_id == "IN_BOWL": current_status = "In Bowl"
                    elif holder_id: current_status = f"Held by {data.get('holder_name', 'Someone')}"
                    
                    trio_options.append(discord.SelectOption(
                        label=f"{name} ({current_status})",
                        value=str(trio_id),
                        description=f"Manifestations: {', '.join(data.get('abilities', [])[:2])}"[:100]
                    ))
            
            if trio_options:
                trio_select = discord.ui.Select(
                    custom_id="trio_bowl_manage_select",
                    placeholder="Select a Trio to place into a Bowl...",
                    options=trio_options
                )
                trio_select.callback = self.trio_select_callback
                self.add_item(trio_select)
            else:
                # No trios to manage, perhaps add a disabled placeholder or this view shouldn't be sent
                pass 

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.original_interactor_id:
                await interaction.response.send_message("This selection is not for you.", ephemeral=True)
                return False
            return True

        async def on_timeout(self):
            for item in self.children: item.disabled = True
            if self.message:
                try: await self.message.edit(content="Bowl management selection timed out.", view=self)
                except: pass

        async def trio_select_callback(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False) # Public defer for potential public followup
            selected_trio_id = interaction.data["values"][0]
            
            invoker_can_override_lock = interaction.user.guild_permissions.manage_guild
            action_performed_message = "" # To build the final message

            async with self.cog.config.guild(interaction.guild).trios_inventory() as trios_inv:
                if selected_trio_id not in trios_inv:
                    await interaction.followup.send("Selected Trio not found.", ephemeral=True) # Keep this ephemeral as it's an error for the clicker
                    return
                
                trio_data = trios_inv[selected_trio_id]
                trio_name_display = trio_data.get("name", f"Trio #{selected_trio_id}")
                current_holder_id = trio_data.get("holder_id")
                original_holder_name = trio_data.get("holder_name", "the Well") # For message context

                if current_holder_id == "IN_BOWL":
                    # Action: Empty from Bowl to Well
                    trios_inv[selected_trio_id]["holder_id"] = None
                    trios_inv[selected_trio_id]["holder_name"] = None
                    action_performed_message = f"'{trio_name_display}' has been emptied from the Bowl and is now in the Well."
                else:
                    # Action: Move to Bowl (from Well or Player)
                    if current_holder_id is not None: # Held by a player, check lock
                        # Lock check only if invoker is not the holder and lacks override perms
                        if current_holder_id != interaction.user.id and not invoker_can_override_lock:
                            user_locks = await self.cog.config.guild(interaction.guild).trio_user_locks()
                            if user_locks.get(str(current_holder_id), False):
                                holder = interaction.guild.get_member(current_holder_id)
                                holder_name_for_msg = holder.display_name if holder else "its current holder"
                                await interaction.followup.send(f"Cannot move '{trio_name_display}' to a Bowl. {holder_name_for_msg} has locked their Trio status.", ephemeral=True)
                                return
                    
                    source_message = "from the Well"
                    if current_holder_id is not None and current_holder_id != "IN_BOWL": # Was held by a player
                        source_message = f"(was held by {original_holder_name})"
                    
                    trios_inv[selected_trio_id]["holder_id"] = "IN_BOWL"
                    trios_inv[selected_trio_id]["holder_name"] = "In a Bowl"
                    action_performed_message = f"'{trio_name_display}' {source_message} has been placed into a Bowl."
            
            if action_performed_message: # If an action was actually performed and config saved
                await interaction.followup.send(action_performed_message, ephemeral=False) # Public confirmation
                await self.cog._update_persistent_trio_list(interaction.guild)
            
            # Disable this select view after action
            for item in self.children: item.disabled = True
            if self.message:
                try: await self.message.edit(view=self)
                except: pass # Original message might have been deleted or view already changed

    class PersistentTrioControlView(discord.ui.View):
        def __init__(self, cog_instance):
            super().__init__(timeout=None)
            self.cog = cog_instance

        @discord.ui.button(label="Manage My Trio", style=discord.ButtonStyle.success, custom_id="persist_trio_mine")
        async def manage_my_trio_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
            # This deferral is already ephemeral, which is good as a quick ack.
            await interaction.response.defer(ephemeral=True, thinking=False) 
            await self.cog._execute_trio_mine(interaction, interaction.user)

        @discord.ui.button(label="Manage Another's Trio", style=discord.ButtonStyle.primary, custom_id="persist_trio_mine_other")
        async def manage_other_trio_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
            view = self.cog.TargetUserSelectView(self.cog, interaction.user.id)
            # Send initial response ephemerally
            await interaction.response.send_message("Select the user whose Trio you want to manage:", view=view, ephemeral=True)
            # view.message is not explicitly set here, TargetUserSelectView will use interaction.edit_original_response

        @discord.ui.button(label="Bowl Management", style=discord.ButtonStyle.secondary, custom_id="persist_trio_bowl_manage")
        async def bowl_management_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
            all_trios_inv = await self.cog.config.guild(interaction.guild).trios_inventory()
            if not all_trios_inv:
                await interaction.response.send_message("No Trios defined to manage for bowl storage.", ephemeral=True)
                return
            
            view = self.cog.BowlManagementSelectView(self.cog, interaction.user.id, all_trios_inv)
            # Send initial response ephemerally
            await interaction.response.send_message("Select a Trio to interact with Bowl storage:", view=view, ephemeral=True)

            
    """Custodian Cog - Tracks thinspaces, breaches, gates, and cycles."""

    def __init__(self, bot):
        print("!!! [Custodian Cog] __init__ method entered !!!")
        self.bot = bot
        self._views_reloaded = False 
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        
        # --- Breach Message List ---
        self.breach_success_messages = [
            "Breach made:",
            "Space breached:",
            "You tear space:",
            "Inky fingers trace the path:",
            "The crossing is established:",
            "Passage confirmed:",
            "Reality is torn:",
            "Sequence complete:",
            "Path traversed:",
            "The thinspace tears:",
            "Crossing completed:",
            "They've been your hands for as long as you can remember:",
            "Your hands, as long as you remember:",
            "Purchase is found on the space:",
            "The ring of a dolorous bell:",
            "Sea of unknowns. Sky of unknowns. Threshold of the unknown. Incomprehensible sights. Exhilarating possibilities:",
            "Fingers work on the air:",
            "Desire breaks the world:",
            "Between worlds:",
        ]
        
        # --- Gate Apply Message List ---
        self.gate_apply_messages = [
            "Breachgate established for crossing:",
            "Breach, tamed for your use:",
            "Limit bypassed for:",
            "A stable path secured through:",
            "The power of the Breach Manifestation is put to use:",
            "A gift of passage is deployed:",
            "A stable crossing:",
        ]
        
        # --- Gate Use Message List --- 
        self.gated_breach_messages = [
            "Gate utilized:",
            "Path via gate:",
            "Limit irrelevant:",
            "A gated crossing used:",
            "Gate sequence complete:",
            "Passage secured via gate:",
        ]


        # Define default guild settings
        default_guild = {
            "thinspaces": {}, # Stores { "AA-BB": {"pre_gate_breaches": 0, "post_gate_breaches": 0, "gated": False, "limit": 14} }
            "breach_types": DEFAULT_BREACH_TYPES.copy(), # Allow per-guild overrides/additions
            "breachgates_available": 0,
            "max_gates": 4,
            "dreams_left": 3,
            "max_dreams": 3,
            "cycle_number": 1,
            "reset_day": 5, # 0=Mon, 1=Tue, ..., 5=Sat, 6=Sun
            "reset_hour_utc": 5, # 5 AM UTC
            "reset_minute_utc": 0,
            "last_reset_log": None, # Stores the message ID of the last reset log
            "tracking_channel": None, # Channel ID for reset logs and updates
            "default_limit": 14, # Default limit for new thinspaces
            "trios_inventory": {}, # Stores { "number_str": {"abilities": ["ab1", "ab2", "ab3"], "holder_id": null, "holder_name": null} }
            "trio_user_locks": {},  # Stores { "user_id_str": True } for locked users
            "trio_user_titles": {}, # User Titles
            "weekly_artifacts": {}, # <-- ADD THIS LINE
            "is_reset_paused": False, # <-- ADD THIS LINE
            "persistent_trio_list_channel_id": None, # Stores the ID of the channel for the list
            "persistent_trio_list_message_ids": [],   # Stores a list of message IDs for the list
            "trio_control_panel_message_id": None,
            "trio_control_panel_channel_id": None,
            
            
        }

        self.config.register_guild(**default_guild)

        self.weekly_reset_task = self.bot.loop.create_task(self.run_weekly_reset_loop())
        
    @commands.Cog.listener()
    async def on_ready(self):
        # We use a flag to ensure this only runs once, on the first ready event.
        if self._views_reloaded:
            return

        all_guild_configs = await self.config.all_guilds()
        print(f"!!! [Custodian on_ready] Found {len(all_guild_configs)} guild configs to check for views.")

        for guild_id, guild_data in all_guild_configs.items():
            # The guild cache is now guaranteed to be available.
            guild = self.bot.get_guild(guild_id)
            if not guild:
                print(f"!!! [Custodian on_ready] Guild {guild_id} not found, skipping.")
                continue

            panel_message_id = guild_data.get("trio_control_panel_message_id")

            if panel_message_id:
                try:
                    view_instance = self.PersistentTrioControlView(self) 
                    self.bot.add_view(view_instance, message_id=panel_message_id)
                    print(f"!!! [Custodian on_ready] Successfully re-registered persistent view for message {panel_message_id} in guild {guild.name}.")
                except Exception as e:
                    print(f"!!! [Custodian on_ready] FAILED to re-register view for message {panel_message_id} in guild {guild.name}. Error: {e}")

        self._views_reloaded = True # Set the flag to True to prevent this from running again.

    def cog_unload(self):
        self.weekly_reset_task.cancel()


    # --- Helper Functions ---

    def _normalize_thinspace(self, space_name: str) -> str:
        """Ensures thinspace names are consistent (e.g., AA-BB becomes AA-BB, BB-AA becomes AA-BB)."""
        # Use user's provided version
        parts = sorted(space_name.upper().split('-'))
        if len(parts) != 2:
            raise ValueError("Invalid thinspace format. Use AA-BB.")
        return f"{parts[0]}-{parts[1]}"
    
    async def _calculate_next_reset_dt(self, guild: discord.Guild) -> datetime.datetime | None:
        """Calculates the next scheduled reset datetime based on current time and config."""
        # Fetch config values directly from the guild's config group
        guild_config = self.config.guild(guild)
        reset_day = await guild_config.reset_day()
        reset_hour = await guild_config.reset_hour_utc()
        reset_minute = await guild_config.reset_minute_utc()

        if reset_day is None or reset_hour is None or reset_minute is None:
            print(f"[Calculate Next Reset] Reset time config missing or incomplete for Guild {guild.id}")
            return None

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        today_reset_dt = now_utc.replace(hour=reset_hour, minute=reset_minute, second=0, microsecond=0)
        days_until_reset = (reset_day - now_utc.weekday() + 7) % 7

        if days_until_reset == 0 and now_utc >= today_reset_dt:
            # If it's reset day but the time has passed, aim for next week
            next_reset_dt = today_reset_dt + datetime.timedelta(weeks=1)
        else:
            # Otherwise, aim for the reset day in the current or next week
            next_reset_dt = today_reset_dt + datetime.timedelta(days=days_until_reset)

        return next_reset_dt

    async def _get_thinspace(self, guild: discord.Guild, space_name: str):
        """Gets thinspace data, handling normalization."""
        normalized_name = self._normalize_thinspace(space_name)
        spaces = await self.config.guild(guild).thinspaces()
        return spaces.get(normalized_name) # Returns None if not found

    async def _show_dream_status(self, ctx: commands.Context):
        dreams = await self.config.guild(ctx.guild).dreams_left()
        max_dreams = await self.config.guild(ctx.guild).max_dreams() # Fetch max
        await ctx.send(f"Dreams left: {dreams}/{max_dreams}.") # Use max
    
    async def _find_user_trio(self, guild: discord.Guild, user_id: int) -> tuple[str, dict] | None:
        """Finds the Trio ID and data held by a specific user in a guild.

        Returns:
            A tuple (trio_id_str, trio_data) if found, otherwise None.
        """
        trios_inv = await self.config.guild(guild).trios_inventory()
        for trio_id_str, trio_data in trios_inv.items():
            if isinstance(trio_data, dict) and trio_data.get("holder_id") == user_id:
                return trio_id_str, trio_data
        return None

    async def _find_trio_by_identifier(self, guild: discord.Guild, identifier: str) -> tuple[str, dict] | None:
        """Finds a Trio by its number or one of its unique ability names.

        Args:
            guild: The guild object.
            identifier: The Trio number (as a string or int) or an ability name (string).

        Returns:
            A tuple (trio_id_str, trio_data) if found, otherwise None.
        """
        trios_inv = await self.config.guild(guild).trios_inventory()
        
        # Try to find by number first
        try:
            trio_num_lookup = str(int(identifier)) # Ensure it's a string key if identifier is int-like
            if trio_num_lookup in trios_inv:
                return trio_num_lookup, trios_inv[trio_num_lookup]
        except ValueError:
            # Identifier is not purely numeric, so treat as ability name
            pass

        # If not found by number, search by ability name (case-insensitive)
        # Since abilities are unique, this will find at most one.
        identifier_lower = identifier.lower()
        for trio_id_str, trio_data in trios_inv.items():
            if isinstance(trio_data, dict):
                abilities = trio_data.get("abilities", [])
                for ability in abilities:
                    if isinstance(ability, str) and ability.lower() == identifier_lower:
                        return trio_id_str, trio_data
        return None

    async def _display_trios_list(self, ctx: commands.Context, trios_to_display: dict, title_prefix: str):
        """Helper function to display a list of trios in a paginated embed format with ANSI colors."""
        if not trios_to_display:
            if "Available" in title_prefix or "Well" in title_prefix:
                await ctx.send("No Trios are currently in the Well.")
            elif "Held" in title_prefix:
                await ctx.send("No Trios are currently held by players.")
            elif "Bowl" in title_prefix:
                await ctx.send("No Trios are currently in a Bowl.")
            else: 
                await ctx.send("No Trios to display.")
            return

        output_lines = []
        for trio_id_str, trio_data in sorted(trios_to_display.items(), key=lambda item: int(item[0])):
            if not isinstance(trio_data, dict):
                output_lines.append(f"Trio #{trio_id_str}: {self.ANSI_RED}Error - Malformed Data{self.ANSI_RESET}")
                continue

            name = trio_data.get("name", f"Trio #{trio_id_str}")
            abilities = trio_data.get("abilities", ["Unknown", "Unknown", "Unknown"])
            abilities_padded = (abilities + ["Unknown"] * 3)[:3] 
            # Manifestations are colored, and no Markdown here
            abilities_str = f"[{self.ANSI_CYAN}{abilities_padded[0]}{self.ANSI_RESET}, {self.ANSI_CYAN}{abilities_padded[1]}{self.ANSI_RESET}, {self.ANSI_CYAN}{abilities_padded[2]}{self.ANSI_RESET}]"
            
            holder_id = trio_data.get("holder_id")
            holder_name = trio_data.get("holder_name")
            status = ""

            if holder_id == "IN_BOWL":
                status = f"{self.ANSI_MAGENTA}In a Bowl{self.ANSI_RESET}"
            elif holder_id is not None and holder_name is not None:
                status = f"{self.ANSI_YELLOW}{holder_name}{self.ANSI_RESET}"
            else: 
                status = f"{self.ANSI_BLUE}In the Well{self.ANSI_RESET}"
            
            output_lines.append(f"{name} {abilities_str} - {status}") 
            
        if not output_lines: # Should be covered by the initial check, but as a safeguard
            await ctx.send(f"No {title_prefix.lower()} to display after formatting.")
            return

        MAX_LINES_PER_EMBED = 15 # Adjust as needed
        for i in range(0, len(output_lines), MAX_LINES_PER_EMBED):
            chunk = output_lines[i:i+MAX_LINES_PER_EMBED]
            
            current_page_title = title_prefix
            if len(output_lines) > MAX_LINES_PER_EMBED:
                current_page_title += f" (Page {i//MAX_LINES_PER_EMBED + 1})"

            page_text_content = '\n'.join(chunk)
            description_content = f"```ansi\n{page_text_content}\n```"

            embed_page = discord.Embed(
                title=current_page_title,
                description=description_content if page_text_content.strip() else "No details for this page.", # Check page_text_content
                color=await ctx.embed_colour()
            )
            try:
                await ctx.send(embed=embed_page)
            except discord.HTTPException as e:
                print(f"Discord HTTP Error sending embed in _display_trios_list: {e.status} {e.text}")
                await ctx.send(f"Error displaying Trio list: Discord API error (code: {e.status}). Check console.")
                return 
            except Exception as e:
                print(f"Generic error sending embed in _display_trios_list: {e}")
                import traceback
                traceback.print_exc()
                await ctx.send("An unexpected error occurred while displaying the Trio list. Please check console logs.")
                return
    
    async def _display_trios_list_with_titles(self, ctx: commands.Context):
        """Helper function to display the main trio list but substitutes holder names with their set titles."""
        all_trios_inv = await self.config.guild(ctx.guild).trios_inventory()
        user_titles = await self.config.guild(ctx.guild).trio_user_titles()

        if not all_trios_inv:
            await ctx.send("No Trios have been defined for this server yet.")
            return

        output_lines = []
        for trio_id_str, trio_data in sorted(all_trios_inv.items(), key=lambda item: int(item[0])):
            if not isinstance(trio_data, dict):
                output_lines.append(f"Trio #{trio_id_str}: {self.ANSI_RED}Error - Malformed Data{self.ANSI_RESET}")
                continue

            name = trio_data.get("name", f"Trio #{trio_id_str}")
            abilities = trio_data.get("abilities", ["Unknown"] * 3)
            abilities_padded = (abilities + ["Unknown"] * 3)[:3]
            abilities_str = f"[{self.ANSI_CYAN}{abilities_padded[0]}{self.ANSI_RESET}, {self.ANSI_CYAN}{abilities_padded[1]}{self.ANSI_RESET}, {self.ANSI_CYAN}{abilities_padded[2]}{self.ANSI_RESET}]"
            
            holder_id = trio_data.get("holder_id")
            holder_name = trio_data.get("holder_name") # Keep original name for fallback
            status = ""

            if holder_id == "IN_BOWL":
                status = f"{self.ANSI_MAGENTA}In a Bowl{self.ANSI_RESET}"
            elif holder_id is not None and holder_name is not None:
                # NEW LOGIC: Check for a title first
                titled_name = user_titles.get(str(holder_id))
                display_name = titled_name if titled_name else holder_name
                status = f"{self.ANSI_YELLOW}{display_name}{self.ANSI_RESET}"
            else: 
                status = f"{self.ANSI_BLUE}In the Well{self.ANSI_RESET}"
            
            output_lines.append(f"{name} {abilities_str} - {status}")

        title_prefix = "Trio Inventory (with Titles)"
        MAX_LINES_PER_EMBED = 15
        for i in range(0, len(output_lines), MAX_LINES_PER_EMBED):
            chunk = output_lines[i:i+MAX_LINES_PER_EMBED]
            current_page_title = title_prefix
            if len(output_lines) > MAX_LINES_PER_EMBED:
                current_page_title += f" (Page {i//MAX_LINES_PER_EMBED + 1})"

            page_text_content = '\n'.join(chunk)
            description_content = f"```ansi\n{page_text_content}\n```"

            embed_page = discord.Embed(
                title=current_page_title,
                description=description_content,
                color=await ctx.embed_colour()
            )
            await ctx.send(embed=embed_page)
            
    async def _perform_reset(self, guild: discord.Guild):
        """
        Performs the actual weekly reset logic for a given guild.
        Resets thinspaces, dreams, increments cycle.
        Returns tuple: (log_message_content, cycle_message_content, next_reset_datetime)
        """
        # Fetch config values directly using their registered paths
        # This ensures registered defaults are used if a key is somehow missing
        guild_config = self.config.guild(guild)
        cycle = await guild_config.cycle_number()
        reset_hour = await guild_config.reset_hour_utc()
        reset_minute = await guild_config.reset_minute_utc()
        reset_day = await guild_config.reset_day()
        max_dreams = await guild_config.max_dreams()
        max_gates = await guild_config.max_gates() # <-- Fetching directly

        print(f"Executing reset logic for Guild ID: {guild.id} (Cycle {cycle})")

        # --- Reset Thinspaces ---
        # Fetch thinspaces separately as it's a dictionary we'll modify
        thinspaces = await guild_config.thinspaces()
        log_output_lines = [f"**Cycle {cycle} End Report**", "Final Breach Counts:"]
        if not thinspaces:
            log_output_lines.append("- No thinspaces tracked this cycle.")
        else:
            for name, data in sorted(thinspaces.items()): # Iterate directly on fetched dict for modification
                if isinstance(data, dict):
                    pre_breaches = data.get('pre_gate_breaches', 0)
                    post_breaches = data.get('post_gate_breaches', 0)
                    was_gated = data.get('gated', False)

                    if was_gated or post_breaches > 0:
                        log_line = f"- {name}: Pre: {pre_breaches}"
                        if post_breaches > 0:
                            log_line += f", Post: {post_breaches}"
                        if was_gated:
                             log_line += " (Gate Active)"
                    else:
                        log_line = f"- {name}: {pre_breaches}"
                    log_output_lines.append(log_line)

                    # Reset values in the 'data' dict (which is a reference to part of 'thinspaces')
                    data["pre_gate_breaches"] = 0
                    data["post_gate_breaches"] = 0
                    data["gated"] = False
                else:
                    log_output_lines.append(f"- {name}: Error - Invalid data format.")
                    print(f"Warning: Invalid data format for thinspace '{name}' in Guild {guild.id}")
        
        # --- Reset Weekly Artifacts ---
        async with self.config.guild(guild).weekly_artifacts() as artifacts:
            if artifacts:
                reset_count = 0
                for item_data in artifacts.values():
                    # If an item was 'Used', it becomes 'Unclaimed'.
                    # 'Available' and 'Unclaimed' items remain as they are.
                    if item_data.get("status") == "Used":
                        item_data["status"] = "Unclaimed"
                        item_data["used_by"] = None
                        reset_count += 1
                log_output_lines.append(f"\n- Reset {reset_count} 'Used' artifact(s) to 'Unclaimed'.")
        
        log_message_content = "\n".join(log_output_lines)

        new_cycle = cycle + 1
        await guild_config.thinspaces.set(thinspaces) # Save modified thinspaces
        await guild_config.dreams_left.set(max_dreams)
        await guild_config.breachgates_available.set(max_gates) # Refill gates to the correctly fetched max_gates
        await guild_config.cycle_number.set(new_cycle)

        # --- Prepare Cycle Message ---
        # Use the _calculate_next_reset_dt helper
        next_reset_dt = await self._calculate_next_reset_dt(guild)
        if next_reset_dt:
            next_reset_unix = int(next_reset_dt.timestamp())
            cycle_message_content = (
                f"**Cycle {new_cycle} Started**\n"
                f"Next reset: <t:{next_reset_unix}:F> (<t:{next_reset_unix}:R>)"
            )
        else:
            cycle_message_content = f"**Cycle {new_cycle} Started**\nNext Reset: Calculation Error (Config missing?)"


        return log_message_content, cycle_message_content, next_reset_dt

# --- Weekly Reset Loop (CORRECTED Trigger Logic) ---

    async def run_weekly_reset_loop(self):
        await self.bot.wait_until_ready()
        while True:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            check_interval = 3600

            try:
                guild_configs = await self.config.all_guilds()
                processed_guild_in_loop = False

                # --- Find the soonest reset time across all guilds ---
                soonest_reset_dt = None
                guild_count = 0
                # Use a temporary copy of keys to avoid issues if config changes during iteration
                guild_ids = list(guild_configs.keys())
                for gid_interval in guild_ids:
                    cfg_interval = await self.config.guild_from_id(gid_interval).all() # Fetch fresh per guild
                    guild_for_check = self.bot.get_guild(gid_interval)
                    if not guild_for_check: continue
                    guild_count += 1

                    rst_day = cfg_interval.get("reset_day")
                    rst_hr = cfg_interval.get("reset_hour_utc")
                    rst_min = cfg_interval.get("reset_minute_utc")
                    if rst_day is None or rst_hr is None or rst_min is None: continue

                    temp_today_reset = now_utc.replace(hour=rst_hr, minute=rst_min, second=0, microsecond=0)
                    days_to_rst = (rst_day - now_utc.weekday() + 7) % 7
                    if days_to_rst == 0 and now_utc >= temp_today_reset:
                        temp_next_reset = temp_today_reset + datetime.timedelta(weeks=1)
                    else:
                        temp_next_reset = temp_today_reset + datetime.timedelta(days=days_to_rst)
                    if soonest_reset_dt is None or temp_next_reset < soonest_reset_dt:
                        soonest_reset_dt = temp_next_reset

                # --- Iterate through guilds to check for resets ---
                for guild_id in guild_ids: # Iterate using the key list
                    config = await self.config.guild_from_id(guild_id).all() # Fetch fresh config
                    guild = self.bot.get_guild(guild_id)
                    if not guild: continue
                    
                    if config.get("is_reset_paused", False):
                        continue

                    reset_day = config.get("reset_day")
                    reset_hour = config.get("reset_hour_utc")
                    reset_minute = config.get("reset_minute_utc")
                    tracking_channel_id = config.get("tracking_channel")

                    if reset_day is None or reset_hour is None or reset_minute is None: continue

                    # --- !!! CORRECTED TRIGGER LOGIC !!! ---
                    # Check if today IS the configured reset day
                    if now_utc.weekday() == reset_day:
                        # Calculate the target reset time for TODAY
                        today_reset_target = now_utc.replace(hour=reset_hour, minute=reset_minute, second=0, microsecond=0)
                        # Calculate difference between now and TODAY's target time
                        time_since_reset_today = now_utc - today_reset_target
                        diff_seconds = time_since_reset_today.total_seconds()

                        # Check if we are within the trigger window (0-10 minutes *past* scheduled time for TODAY)
                        if 0 <= diff_seconds < 600:

                            # --- Call the Helper Function ---
                            try:
                                log_msg, cycle_msg, _ = await self._perform_reset(guild)
                            except Exception as reset_e:
                                import traceback; traceback.print_exc()
                                continue # Skip to next guild or interval calculation on error

                            # --- Post Messages ---
                            channel = None
                            if tracking_channel_id:
                                channel = guild.get_channel(tracking_channel_id)
                                if channel:
                                    try:
                                        for page in pagify(log_msg): await channel.send(page)
                                        await channel.send(cycle_msg)
                                    except Exception as post_e: print(f"Error posting reset message: {post_e}")
                                else: print(f"Tracking channel not found: {tracking_channel_id}")

                            processed_guild_in_loop = True
                            # Reset check interval after processing to ensure accurate sleep calculation
                            check_interval = 3600
                            break # Only reset one guild per outer loop iteration
                    # else: # Optional logging if today is not the reset day
                    #    print(f"[Custodian Reset Loop] G:{guild_id} - Today ({now_utc.weekday()}) is not reset day ({reset_day}).")
                    # --- !!! END CORRECTED TRIGGER LOGIC !!! ---

            except asyncio.CancelledError:
                 print("[Custodian Reset Loop] Task cancelled.")
                 return # Stop loop
            except Exception as e:
                print(f"[Custodian Reset Loop] !!! UNEXPECTED ERROR in main loop: {e} !!!") # Log errors
                import traceback; traceback.print_exc()

            # --- REFINED DYNAMIC INTERVAL CALCULATION ---
            now_utc_after_check = datetime.datetime.now(datetime.timezone.utc)
            calculated_check_interval = 3600 # Default fallback 1 hour if no specific rules match

            if soonest_reset_dt: # Use the 'soonest_reset_dt' calculated at the start of this loop iteration
                 time_until_soonest = (soonest_reset_dt - now_utc_after_check).total_seconds()

                 if time_until_soonest > 0:
                     if time_until_soonest > 24 * 3600: # More than 1 day away
                         calculated_check_interval = 6 * 3600 # Check every 6 hours
                     elif time_until_soonest > 6 * 3600: # More than 6 hours away
                         calculated_check_interval = 1 * 3600 # Check every 1 hour
                     elif time_until_soonest > 1 * 3600: # More than 1 hour away
                         calculated_check_interval = 15 * 60 # Check every 15 minutes
                     elif time_until_soonest > 300: # 5 minutes to 1 hour away
                         calculated_check_interval = 60 # Check every 1 minute
                     else: # Less than 5 minutes away
                         # Sleep until just *after* the reset time to guarantee hitting the window
                         sleep_needed = time_until_soonest + 5 # Aim for 5s past reset
                         calculated_check_interval = max(5.0, sleep_needed) # Ensure minimum sleep of 5s
                 else:
                     # If the soonest reset is somehow in the past (e.g., due to clock changes or extended downtime)
                     calculated_check_interval = 60 # Check again in 1 minute
                 
                 # Ensure a minimum reasonable sleep time overall
                 check_interval = max(10.0, calculated_check_interval) # Min sleep 10s
            else: # No valid soonest_reset_dt could be determined (e.g., no guilds with cog or no valid settings)
                check_interval = 3600

            await asyncio.sleep(check_interval)

    # --- Commands ---

    # Inside the Custodian class

    @commands.group(invoke_without_command=True)
    @commands.guild_only()
    async def breach(self, ctx: commands.Context, *, sequence_and_multiplier: str):
        """
        Records a breach sequence along thinspaces, optionally repeated multiple times.

        The multiplier applies to the *entire* sequence.
        Format: START>TYPE>MIDDLE>TYPE>END... [multiplier]
        """
        parts = sequence_and_multiplier.split()
        sequence_str = parts[0]
        multiplier = 1

        if len(parts) > 1 and parts[-1].isdigit():
            try:
                multiplier = int(parts[-1])
                if multiplier <= 0:
                    await ctx.send("Multiplier must be a positive number.")
                    return
                sequence_str = " ".join(parts[:-1])
            except ValueError:
                await ctx.send("Invalid multiplier provided.")
                return

        # --- Parse the sequence into distinct steps ---
        raw_steps = [part.strip().upper() for part in re.split(r'>', sequence_str.strip()) if part.strip()]
        if len(raw_steps) < 2:
            await ctx.send("Invalid breach format. Use at least START>END, separated by '>'.")
            return

        guild_types = await self.config.guild(ctx.guild).breach_types()
        default_breach_type = "hand"
        parsed_steps = [] # Will store tuples of (start_loc, end_loc, type_name, type_cost)

        current_loc = raw_steps[0]
        i = 1
        while i < len(raw_steps):
            potential_type = raw_steps[i].lower()
            step_type = default_breach_type
            step_cost = guild_types.get(default_breach_type, 1)
            next_loc = ""

            if potential_type in guild_types:
                # Found a type, next part must be location
                if i + 1 < len(raw_steps):
                    step_type = potential_type
                    step_cost = guild_types[step_type]
                    next_loc = raw_steps[i+1]
                    i += 2 # Consume type and location
                else:
                    # Error: Sequence ended with a type name
                    await ctx.send(f"Invalid sequence: Breach type '{potential_type}' found without a following location.")
                    return
            else:
                # Did not find a type, this part is the next location
                next_loc = raw_steps[i]
                i += 1 # Consume location

            # Add the parsed step instruction
            parsed_steps.append((current_loc, next_loc, step_type, step_cost))
            current_loc = next_loc # Update current location for next step parse

        if not parsed_steps: # Should be caught earlier, but safety check
             await ctx.send("Failed to parse any valid steps from the sequence.")
             return

        # --- Execute the parsed steps, handling multiplier ---
        default_limit = await self.config.guild(ctx.guild).default_limit()
        initial_spaces = await self.config.guild(ctx.guild).thinspaces()
        current_spaces_copy = initial_spaces.copy() # Work on copy for atomicity

        processed_successfully = True
        gate_was_used_in_sequence = False
        final_results_summary = []

        # --- Outer loop for multiplier ---
        for iteration in range(multiplier):
            if not processed_successfully: break

            iteration_results = []

            # --- Inner loop iterating through PRE-PARSED steps ---
            for step_num, (start_loc, end_loc, type_name, type_cost) in enumerate(parsed_steps):
                # Process the thinspace step
                try:
                    thinspace_name = self._normalize_thinspace(f"{start_loc}-{end_loc}")
                except ValueError:
                     await ctx.send(f"Invalid thinspace format in step {step_num + 1}: {start_loc}-{end_loc} (Iteration {iteration + 1}). Halting.")
                     processed_successfully = False
                     break # Break inner step loop

                # Check existence using the working copy
                if thinspace_name not in current_spaces_copy:
                    await ctx.send(f"Thinspace '{thinspace_name}' does not exist (step {step_num + 1}, Iteration {iteration + 1}). Halting.")
                    processed_successfully = False
                    break

                # Get data from working copy
                space_data = current_spaces_copy[thinspace_name]
                limit = space_data.get("limit", default_limit)
                is_gated = space_data.get("gated", False)

                step_result_str = ""
                if is_gated:
                    gate_was_used_in_sequence = True
                    # Increment POST count in working copy
                    post_count = space_data.get("post_gate_breaches", 0) + type_cost
                    current_spaces_copy[thinspace_name]["post_gate_breaches"] = post_count
                    # Report Gate status and maybe new post-gate count
                    step_result_str = f"{thinspace_name}: Gate (Post: {post_count})"
                else:
                    # Check against PRE count and limit
                    pre_breaches = space_data.get("pre_gate_breaches", 0)
                    if pre_breaches + type_cost > limit:
                        await ctx.send(
                            f"Path rejected at step {step_num + 1} ({thinspace_name}) on Iteration {iteration + 1}. "
                            f"Limit reached ({pre_breaches}/{limit}, tried to add {type_cost}). Halting."
                        )
                        processed_successfully = False
                        break # Break inner step loop
                    else:
                        # Increment PRE count in working copy
                        new_pre_count = pre_breaches + type_cost
                        current_spaces_copy[thinspace_name]["pre_gate_breaches"] = new_pre_count
                        # Report Pre count / limit
                        step_result_str = f"{thinspace_name}: {new_pre_count}/{limit}"

                iteration_results.append(step_result_str)
            # --- End inner step loop ---

            if not processed_successfully: break # Break outer multiplier loop

            # Store results of the last successful iteration for display
            if iteration == multiplier - 1:
                 final_results_summary = iteration_results

        # --- End outer multiplier loop ---

        # --- Save and Send Message ---
        if processed_successfully:
            # Save the modified copy back to config
            await self.config.guild(ctx.guild).thinspaces.set(current_spaces_copy)

            details = " -> ".join(final_results_summary)
            prefix = random.choice(self.breach_success_messages)
            if gate_was_used_in_sequence:
                gate_phrase = random.choice(self.gated_breach_messages)
                final_prefix = f"{prefix} {gate_phrase}"
            else:
                final_prefix = prefix

            multiplier_text = f" (x{multiplier})" if multiplier > 1 else ""
            await ctx.send(f"{final_prefix}{multiplier_text} {details}")
        else:
             await ctx.send("Breach sequence halted due to rejection or error. No changes were saved.")

    @commands.command()
    @commands.guild_only()
    async def unbreach(
        self, ctx: commands.Context,
        thinspace: str,
        amount: int = 1,
        counter_type: Literal["pre", "post"] = "pre" # Optional: target pre or post counter
    ):
        """
        Manually subtracts breaches from a thinspace's pre-gate or post-gate counter.

        Defaults to affecting the 'pre' counter.
        Example: [p]unbreach AA-BB 2 post
        """

        if amount <= 0:
            print("[DEBUG unbreach] Amount <= 0, sending error.")
            await ctx.send("Amount must be positive.")
            return
        print(f"[DEBUG unbreach] Amount validation passed ({amount}).")

        try:
            normalized_name = self._normalize_thinspace(thinspace)
            print(f"[DEBUG unbreach] Normalized name: '{normalized_name}'")
        except ValueError:
            await ctx.send(f"Invalid thinspace format: {thinspace}. Use AA-BB.")
            return

        status_message = "" # This will be populated later
        key_to_modify = f"{counter_type}_gate_breaches"

        # Initialize a flag to see if we entered the config block successfully
        config_accessed_successfully = False
        try:
            async with self.config.guild(ctx.guild).thinspaces() as spaces:
                config_accessed_successfully = True

                if normalized_name not in spaces:
                    await ctx.send(f"Thinspace '{normalized_name}' does not exist.")
                    return

                space_data = spaces[normalized_name]

                # Ensure data structure is correct
                if not isinstance(space_data, dict) or key_to_modify not in space_data:
                    await ctx.send(f"Data error for thinspace '{normalized_name}'. Cannot find '{key_to_modify}'.")
                    return

                current = space_data.get(key_to_modify, 0)
                new_amount = max(0, current - amount)
                space_data[key_to_modify] = new_amount

                # Determine overall status for confirmation message
                pre_count = space_data.get("pre_gate_breaches", 0)
                post_count = space_data.get("post_gate_breaches", 0)
                limit = space_data.get("limit", await self.config.guild(ctx.guild).default_limit())
                gated = space_data.get("gated", False)
                if gated:
                    status_message = f"Gate (Pre: {pre_count}, Post: {post_count})"
                else:
                    status_message = f"Pre: {pre_count}/{limit}"
                    if post_count > 0: # Only add post_count if it's relevant
                        status_message += f", Post: {post_count}"

            # Config is saved automatically upon exiting 'async with' if no unhandled exceptions occurred within it.

        except Exception as e_config:
            import traceback
            traceback.print_exc() # Print full traceback to console
            await ctx.send("An unexpected error occurred while accessing data. Please check the console.")
            return

        # If config was never accessed successfully (e.g., an error before 'async with'), 
        # it might mean an issue with self.config itself.
        if not config_accessed_successfully and not ctx.guild: # ctx.guild check is very basic
            # This part might not be reached if earlier errors send messages.
            await ctx.send("A very early error occurred. Check console.")
            return
            
        try:
            await ctx.send(
                f"Reduced '{counter_type}' breach count for {normalized_name} by {amount}. "
                f"New status: {status_message}"
            )
        except Exception as e_send:
            import traceback
            traceback.print_exc()
            # If sending fails, we can't notify in Discord.

    @commands.group()
    @commands.guild_only()
    async def thinspace(self, ctx: commands.Context):
        """Manage thinspaces."""
        pass

    @thinspace.command(name="add")
    async def thinspace_add(self, ctx: commands.Context, name: str, limit: int = None):
        """
        Adds a new thinspace (e.g., EX-SY).
        Accepts AA-BB or BB-AA format. Optionally sets a custom limit.
        """
        try:
            normalized_name = self._normalize_thinspace(name)
        except ValueError:
            await ctx.send(f"Invalid thinspace format: {name}. Use AA-BB.")
            return

        # Open the config context manager ONCE
        async with self.config.guild(ctx.guild).thinspaces() as spaces:
            # 1. Check if it already exists
            if normalized_name in spaces:
                await ctx.send(f"Thinspace '{normalized_name}' already exists.")
                return # Exit if it exists

            # 2. Determine and validate the limit
            if limit is None:
                limit = await self.config.guild(ctx.guild).default_limit()
            elif limit <= 0:
                await ctx.send("Limit must be positive.")
                return # Exit if limit is invalid

            # 3. If it doesn't exist and limit is valid, add it
            spaces[normalized_name] = {
                "pre_gate_breaches": 0,
                "post_gate_breaches": 0,
                "gated": False,
                "limit": limit
            }
            # Data will be saved automatically when exiting the 'async with' block here

        # 4. Send confirmation message AFTER data is saved
        await ctx.send(f"Thinspace '{normalized_name}' added with limit {limit}.")


    @thinspace.command(name="remove", aliases=["delete", "del"])
    @checks.admin_or_permissions(manage_guild=True)
    async def thinspace_remove(self, ctx: commands.Context, name: str):
        """Removes a thinspace."""
        try:
            normalized_name = self._normalize_thinspace(name)
        except ValueError:
             await ctx.send(f"Invalid thinspace format: {name}. Use AA-BB.")
             return

        async with self.config.guild(ctx.guild).thinspaces() as spaces:
            if normalized_name not in spaces:
                await ctx.send(f"Thinspace '{normalized_name}' does not exist.")
                return
            del spaces[normalized_name]
        await ctx.send(f"Thinspace '{normalized_name}' removed.")

    @thinspace.command(name="list")
    async def thinspace_list(self, ctx: commands.Context):
        """Lists all thinspaces and their current status."""
        spaces = await self.config.guild(ctx.guild).thinspaces()
        if not spaces:
            await ctx.send("No thinspaces have been added yet.")
            return

        default_limit = await self.config.guild(ctx.guild).default_limit()
        output_lines = ["**Current Thinspace Status:**"]
        # Sort by name for consistent listing
        sorted_spaces = sorted(spaces.items())

        for name, data in sorted_spaces:
            if isinstance(data, dict): # Check format
                # Fetch counts regardless of gated status
                pre_breaches = data.get('pre_gate_breaches', 0)
                post_breaches = data.get('post_gate_breaches', 0)
                limit = data.get('limit', default_limit)
                gated = data.get('gated', False)

                # Determine status string based on gated status
                if gated:
                    # If gated, show Gate status and post-gate count
                    status = f"Gate (Post: {post_breaches})"
                else:
                    # If not gated, show ONLY pre-gate count / limit
                    status = f"{pre_breaches}/{limit}" # <-- Removed "Pre: " prefix here
                output_lines.append(f"- {name}: {status}")
            else:
                 output_lines.append(f"- {name}: Error - Invalid Data")

        # Send the message using pagify for potentially long lists
        for page in pagify("\n".join(output_lines), shorten_by=10):
            await ctx.send(page)

    @thinspace.command(name="status")
    async def thinspace_status(self, ctx: commands.Context):
        """Lists thinspaces: non-gated in multi-column, gated separately."""
        all_guild_spaces = await self.config.guild(ctx.guild).thinspaces()
        if not all_guild_spaces:
            await ctx.send("No thinspaces have been added yet.")
            return

        default_limit = await self.config.guild(ctx.guild).default_limit()
        
        non_gated_items = [] 
        gated_items_formatted = [] 
        sent_any_message = False 

        for name, data in sorted(all_guild_spaces.items()):
            name_str_raw = f"{name}:" # For non-gated column width calculation
            
            if isinstance(data, dict):
                pre_breaches = data.get('pre_gate_breaches', 0)
                post_breaches = data.get('post_gate_breaches', 0)
                limit = data.get('limit', default_limit)
                gated = data.get('gated', False)

                if gated:
                    # --- MODIFIED SECTION FOR GATED ITEM NUMBER PADDING ---
                    # Color pre_breaches number WITHOUT :>2 padding
                    colored_pre_value = f"{self.ANSI_YELLOW}{pre_breaches}{self.ANSI_RESET}"
                    # Color post_breaches number WITHOUT :>2 padding
                    colored_post_value = f"{self.ANSI_MAGENTA}{post_breaches}{self.ANSI_RESET}"
                    
                    colored_pre_label = f"{self.ANSI_YELLOW}Pre:{self.ANSI_RESET}"
                    colored_post_label = f"{self.ANSI_MAGENTA}Post:{self.ANSI_RESET}"
                    
                    # This will now result in "Pre: 7" or "Pre: 10" (one space after label)
                    status_display = f"{colored_pre_label} {colored_pre_value}, {colored_post_label} {colored_post_value}"
                    gated_items_formatted.append(f"{name}: {status_display}")
                    # --- END MODIFIED SECTION ---
                else:
                    # Non-gated logic (keeps :>2 padding for numbers for internal alignment)
                    usage_percent = (pre_breaches / limit * 100) if limit > 0 else 0
                    color = self.ANSI_GREEN
                    if usage_percent > 66: color = self.ANSI_RED
                    elif usage_percent > 33: color = self.ANSI_YELLOW
                    
                    colored_pre = f"{color}{pre_breaches:>2}{self.ANSI_RESET}" # Keep padding here
                    colored_limit = f"{self.ANSI_CYAN}{limit:>2}{self.ANSI_RESET}" # Keep padding here
                    status_display = f"{colored_pre}/{colored_limit}"
                    non_gated_items.append((name_str_raw, status_display))
            else:
                status_display = f"{self.ANSI_RED}Error - Invalid Data{self.ANSI_RESET}"
                non_gated_items.append((name_str_raw, status_display))

        # --- Display Non-Gated Items ---
        if non_gated_items:
            max_name_len = max(len(item[0]) for item in non_gated_items) if non_gated_items else 10
            COLUMNS = 3 
            
            output_text_lines_non_gated = []
            for i in range(0, len(non_gated_items), COLUMNS):
                row_items = non_gated_items[i:i+COLUMNS]
                line_parts = []
                for name_part, status_part in row_items:
                    # This padding for the name part remains
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
        
        # --- Display Gated Items (minor change in how lines are added) ---
        if gated_items_formatted:
            LINES_PER_EMBED_GATED = 20 
            current_page_lines_g = []
            embed_num_g = 1
            
            for line_num, formatted_line_for_gated in enumerate(gated_items_formatted): # iterate over pre-formatted lines
                current_page_lines_g.append(formatted_line_for_gated) # Directly use the formatted line
                if (line_num + 1) % LINES_PER_EMBED_GATED == 0 or (line_num + 1) == len(gated_items_formatted):
                    title_g = "Gates"
                    if embed_num_g > 1 or len(gated_items_formatted) > LINES_PER_EMBED_GATED:
                        title_g += f" (Page {embed_num_g})"

                    embed_g = discord.Embed(title=title_g, color=await ctx.embed_colour())
                    page_content_g = "\n".join(current_page_lines_g)
                    if page_content_g.strip():
                        embed_g.description = f"```ansi\n{page_content_g}\n```"
                        await ctx.send(embed=embed_g)
                        sent_any_message = True
                    current_page_lines_g = []
                    embed_num_g += 1
        
        if not sent_any_message:
             await ctx.send("No thinspaces found to display (or lists were empty after formatting).")
            
    @commands.group()
    @commands.guild_only()
    async def gate(self, ctx: commands.Context):
        """Manage Breachgates."""
        pass

    @gate.command(name="apply")
    async def gate_apply(self, ctx: commands.Context, thinspace: str):
        """
        Applies a Breachgate to a thinspace, consuming one available gate.
        Removes the breach limit for the rest of the week.
        """
        gates_available = await self.config.guild(ctx.guild).breachgates_available()
        if gates_available <= 0:
            await ctx.send("No breachgates left at the Well.")
            return

        try:
            normalized_name = self._normalize_thinspace(thinspace)
        except ValueError:
             await ctx.send(f"Invalid thinspace format: {thinspace}. Use AA-BB.")
             return

        async with self.config.guild(ctx.guild).thinspaces() as spaces:
            if normalized_name not in spaces:
                await ctx.send(f"Thinspace '{normalized_name}' does not exist.")
                return
            if spaces[normalized_name].get("gated", False):
                 # Use user's preferred message
                await ctx.send(f"Thinspace '{normalized_name}' already has a gate established.")
                return

            spaces[normalized_name]["gated"] = True
            # Decrement gates *after* applying successfully
            # Calculate the new count and assign it to the variable
            new_gate_count = gates_available - 1
            # Save the new count using the variable
            await self.config.guild(ctx.guild).breachgates_available.set(new_gate_count)
            # Use user's preferred message
            prefix = random.choice(self.gate_apply_messages)
            await ctx.send(f"{prefix} '{normalized_name}'. Gates remaining: {new_gate_count}.")

    @gate.command(name="remove")
    @checks.admin_or_permissions(manage_guild=True)
    async def gate_remove(self, ctx: commands.Context, thinspace: str):
        """
        Manually removes an applied Breachgate from a thinspace
        and returns it to the available pool.
        """
        try:
            normalized_name = self._normalize_thinspace(thinspace)
        except ValueError:
             await ctx.send(f"Invalid thinspace format: {thinspace}. Use AA-BB.")
             return

        async with self.config.guild(ctx.guild).thinspaces() as spaces:
            if normalized_name not in spaces:
                await ctx.send(f"Thinspace '{normalized_name}' does not exist.")
                return
            if not spaces[normalized_name].get("gated", False):
                await ctx.send(f"Thinspace '{normalized_name}' does not have a gate applied.")
                return
            spaces[normalized_name]["gated"] = False # Remove gate

        # Refund gate
        current_gates = await self.config.guild(ctx.guild).breachgates_available()
        new_total = current_gates + 1
        await self.config.guild(ctx.guild).breachgates_available.set(new_total)
        # Use user's preferred message
        await ctx.send(f"Breachgate manually removed from '{normalized_name}' and returned to the well. Gates available: {new_total}.")

    @gate.command(name="add")
    @checks.admin_or_permissions(manage_guild=True)
    async def gate_add(self, ctx: commands.Context, amount: int = 1):
        """Increases max gate capacity AND adds to current available gates.""" # Updated docstring
        if amount <= 0:
             await ctx.send("Amount must be positive.")
             return

        # Update Maximum Gates
        current_max = await self.config.guild(ctx.guild).max_gates()
        new_max = current_max + amount
        await self.config.guild(ctx.guild).max_gates.set(new_max)

        current_available = await self.config.guild(ctx.guild).breachgates_available()
        new_available = current_available + amount 
        await self.config.guild(ctx.guild).breachgates_available.set(new_available)

        await ctx.send(
            f"Increased maximum breachgate capacity by {amount} (New Max: {new_max}).\n"
            f"Added {amount} to the available pool (Currently Available: {new_available})."
        )
        
    @gate.command(name="list", aliases=["show", "used"])
    async def gate_list(self, ctx: commands.Context):
         """Shows active gates, available gates, and max gate capacity."""
         spaces = await self.config.guild(ctx.guild).thinspaces()
         gated_spaces = sorted([name for name, data in spaces.items() if data.get("gated", False)])

         output_lines = []
         if not gated_spaces:
              output_lines.append("No breachgates are currently applied to thinspaces.")
         else:
              output_lines.append("**Active Breachgates (this cycle):**")
              output_lines.extend([f"- {name}" for name in gated_spaces])

         gates_available = await self.config.guild(ctx.guild).breachgates_available()
         max_gates = await self.config.guild(ctx.guild).max_gates() # Fetch max
         # Update display format
         output_lines.append(f"\n**Gates Available / Max:** {gates_available} / {max_gates}")

         await ctx.send("\n".join(output_lines))

    @commands.group(invoke_without_command=True) # Use user's version
    @commands.guild_only()
    async def dream(self, ctx: commands.Context):
        """Manage or check Dream charges."""
        if ctx.invoked_subcommand is None:
            await self._show_dream_status(ctx)

    @dream.command(name="use")
    async def dream_use(self, ctx: commands.Context):
        """
        Uses a Dream charge for the week.
        """
        dreams = await self.config.guild(ctx.guild).dreams_left()

        if dreams <= 0:
            await ctx.send("There are no dreams left to dream. Time still passes, I suppose.")
            return

        new_count = dreams - 1
        await self.config.guild(ctx.guild).dreams_left.set(new_count)
        max_dreams = await self.config.guild(ctx.guild).max_dreams()
        await ctx.send(f"A dream was dreamt. Dreams left: {new_count}/{max_dreams}.")

    @dream.command(name="status", aliases=["check", "show"])
    async def _show_dream_status(self, ctx: commands.Context):
        dreams = await self.config.guild(ctx.guild).dreams_left()
        max_dreams = await self.config.guild(ctx.guild).max_dreams() # <-- Fetch max_dreams
        await ctx.send(f"Dreams left: {dreams}/{max_dreams}.") # <-- MODIFIED LINE

    @dream.command(name="undo")
    async def dream_undo(self, ctx: commands.Context):
        current_dreams = await self.config.guild(ctx.guild).dreams_left()
        max_dreams = await self.config.guild(ctx.guild).max_dreams() # <-- Fetch max_dreams instead of hardcoding

        if current_dreams >= max_dreams:
                                                            # Use fetched max_dreams
            await ctx.send(f"Dreams are already full ({current_dreams}/{max_dreams}). Cannot undo.")
            return

        new_count = current_dreams + 1
        await self.config.guild(ctx.guild).dreams_left.set(new_count)
                                                    # Use fetched max_dreams
        await ctx.send(f"Dream undone. Dreams left: {new_count}/{max_dreams}.")

    @commands.command(name="quiz")
    @commands.guild_only()
    async def thinspace_quiz(self, ctx: commands.Context):
        """Asks users to find a path between two random cells. Anyone can guess."""
        all_guild_spaces = await self.config.guild(ctx.guild).thinspaces()
        if not all_guild_spaces:
            await ctx.send("No thinspaces defined yet to create a quiz!")
            return

        unique_cells = set()
        for thinspace_name in all_guild_spaces.keys():
            parts = thinspace_name.split('-')
            if len(parts) == 2:
                unique_cells.add(parts[0])
                unique_cells.add(parts[1])
        
        unique_cells_list = list(unique_cells)

        if len(unique_cells_list) < 2:
            await ctx.send("Not enough unique cells defined (need at least 2) to create a quiz.")
            return

        start_cell, end_cell = random.sample(unique_cells_list, 2)

        prompt_message_text = (
            f"**Routing Quiz Time! (No using the map or Directory!)**\n"
            f"Find a valid path from **{start_cell}** to **{end_cell}**.\n"
            f"Type your path using '>' as a separator (e.g., `{start_cell}>MID_CELL>{end_cell}`). You have 60 seconds to guess!"
        )
        await ctx.send(prompt_message_text)

        quiz_duration = 60.0
        quiz_start_time = self.bot.loop.time()
        winner = None

        while True:
            time_elapsed = self.bot.loop.time() - quiz_start_time
            remaining_time = quiz_duration - time_elapsed

            if remaining_time <= 0:
                if not winner:
                    await ctx.send(f"Time's up! No correct path provided for {start_cell} to {end_cell}. Time to study!")
                break

            def check(message: discord.Message) -> bool:
                # Check if it's the same channel and not a bot
                is_correct_channel = message.channel == ctx.channel
                is_not_bot = not message.author.bot
                return is_correct_channel and is_not_bot

            user_message = None # Initialize before try block
            try:
                user_message = await self.bot.wait_for("message", check=check, timeout=remaining_time)
            except asyncio.TimeoutError:
                if not winner:
                    await ctx.send(f"Time's up! No correct path provided for {start_cell} to {end_cell}.")
                break 
            except Exception as e:
                break


            if user_message is None: # Should ideally not happen if no timeout
                break

            user_path_str = user_message.content
            user_path_cells = [cell.strip().upper() for cell in re.split(r'>', user_path_str) if cell.strip()]

            path_is_valid = True # Assume valid until a check fails
            validation_message = ""

            # --- Path Validation Logic ---
            if not user_path_cells or len(user_path_cells) < 2:
                path_is_valid = False
                validation_message = "Your path is too short or empty."
            elif user_path_cells[0] != start_cell:
                path_is_valid = False
                validation_message = f"That path doesn't start with **{start_cell}**."
            elif user_path_cells[-1] != end_cell:
                path_is_valid = False
                validation_message = f"That path doesn't end with **{end_cell}**."
            else:
                for i in range(len(user_path_cells) - 1):
                    step_start_cell = user_path_cells[i]
                    step_end_cell = user_path_cells[i+1]
                    
                    if step_start_cell == step_end_cell:
                        path_is_valid = False
                        validation_message = f"Path cannot directly loop back on itself ({step_start_cell}>{step_end_cell})."
                        break
                    
                    try:
                        normalized_step = self._normalize_thinspace(f"{step_start_cell}-{step_end_cell}")
                    except ValueError:
                        path_is_valid = False
                        validation_message = f"The step '{step_start_cell}-{step_end_cell}' is not a valid thinspace format."
                        break
                    
                    if normalized_step not in all_guild_spaces:
                        path_is_valid = False
                        validation_message = f"The connection '{normalized_step}' in your path does not exist."
                        break
            # --- End Path Validation ---
            
            if path_is_valid:
                winner = user_message.author
                # --- ADD TIME CALCULATION AND MODIFY MESSAGE ---
                time_taken = self.bot.loop.time() - quiz_start_time
                await ctx.send(
                    f"Correct, {winner.mention}! `{user_path_str}` is a valid path from "
                    f"**{start_cell}** to **{end_cell}**. You guessed it in {time_taken:.2f} seconds!"
                )
                # --- END MODIFICATION ---
                break 
            else:
                await ctx.send(f"Sorry {user_message.author.mention}, that's not quite right. {validation_message} Try again!")
                
                current_time_left_for_prompt = quiz_duration - (self.bot.loop.time() - quiz_start_time)
                if current_time_left_for_prompt > 1:
                    await ctx.send(f"Path from **{start_cell}** to **{end_cell}**? {int(current_time_left_for_prompt)} seconds remaining.")
                # If no time left, the main loop condition will catch it next iteration.

    @commands.group()
    @commands.guild_only()
    @checks.admin_or_permissions(manage_guild=True)
    async def custodianset(self, ctx: commands.Context):
        """Configure Custodian settings."""
        pass

    @custodianset.command(name="resettime")
    async def set_reset_time(self, ctx: commands.Context, day: int, hour_utc: int, minute_utc: int = 0):
        """Sets the weekly reset time (Day 0-6, Hour 0-23 UTC, Minute 0-59)."""
        if not (0 <= day <= 6):
             await ctx.send("Day must be between 0 (Monday) and 6 (Sunday).")
             return
        if not (0 <= hour_utc <= 23):
             await ctx.send("Hour must be between 0 and 23 (UTC).")
             return
        if not (0 <= minute_utc <= 59):
             await ctx.send("Minute must be between 0 and 59.")
             return

        await self.config.guild(ctx.guild).reset_day.set(day)
        await self.config.guild(ctx.guild).reset_hour_utc.set(hour_utc)
        await self.config.guild(ctx.guild).reset_minute_utc.set(minute_utc)
        await ctx.send(f"Weekly reset time set to Day {day} at {hour_utc:02d}:{minute_utc:02d} UTC.")
        
        await self.config.guild(ctx.guild).is_reset_paused.set(False)
        
        await ctx.send(
            f"Weekly reset time set to Day {day} at {hour_utc:02d}:{minute_utc:02d} UTC.\n"
            "*(The reset loop has been automatically un-paused.)*"
        )

    @custodianset.command(name="channel")
    async def set_tracking_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Sets the channel for reset logs and updates (omit to clear)."""
        channel_id = channel.id if channel else None
        # Add permission check from user's code
        if channel:
             perms = channel.permissions_for(ctx.guild.me)
             if not (perms.send_messages and perms.read_messages):
                 await ctx.send(f"Warning: I may not have permission to read or send messages in {channel.mention}. Please check my permissions.")
                 # return # Decide if you want to stop or just warn

        await self.config.guild(ctx.guild).tracking_channel.set(channel_id)
        if channel:
             await ctx.send(f"Tracking channel set to {channel.mention}.")
        else:
             await ctx.send("Tracking channel cleared.")

    @custodianset.command(name="defaultlimit")
    async def set_default_limit(self, ctx: commands.Context, limit: int):
        """Sets the default breach limit for newly added thinspaces."""
        if limit <=0:
             await ctx.send("Limit must be positive.")
             return
        await self.config.guild(ctx.guild).default_limit.set(limit)
        await ctx.send(f"Default thinspace limit set to {limit}.")

    @custodianset.command(name="alllimits") # Keep the setalllimits command
    @checks.admin_or_permissions(manage_guild=True)
    async def set_all_limits(self, ctx: commands.Context, new_limit: int):
        """Sets the breach limit for ALL existing thinspaces."""
        if new_limit <= 0:
            await ctx.send("The limit must be a positive number.")
            return

        async with self.config.guild(ctx.guild).thinspaces() as spaces:
            if not spaces:
                await ctx.send("There are no thinspaces configured yet.")
                return

            updated_count = 0
            for space_name in spaces:
                if isinstance(spaces[space_name], dict): # Check type
                    spaces[space_name]["limit"] = new_limit
                    updated_count += 1
                else: # Log if not dict
                    print(f"Warning: Skipping invalid entry in thinspaces config for {space_name} in guild {ctx.guild.id}")

        await ctx.send(f"Updated the limit to {new_limit} for {updated_count} thinspace(s).")
        
    @custodianset.command(name="showsettings", aliases=["view", "show"])
    async def show_settings(self, ctx: commands.Context):
        """Displays the current Custodian cog settings for this server."""

        # Fetch all settings at once
        settings = await self.config.guild(ctx.guild).all()

        # Extract settings, using defaults if necessary (though they should exist)
        reset_day = settings.get("reset_day", 5)
        reset_hour = settings.get("reset_hour_utc", 5)
        reset_minute = settings.get("reset_minute_utc", 0)
        tracking_channel_id = settings.get("tracking_channel")
        default_limit = settings.get("default_limit", 14)
        breach_types = settings.get("breach_types", DEFAULT_BREACH_TYPES) # Use class default if needed

        # --- Format the settings for display ---

        # Convert reset day number to name
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        reset_day_name = days[reset_day] if 0 <= reset_day <= 6 else "Invalid Day"
        reset_time_str = f"{reset_day_name} at {reset_hour:02d}:{reset_minute:02d} UTC"

        # Format tracking channel
        tracking_channel_str = "Not Set"
        if tracking_channel_id:
            channel = ctx.guild.get_channel(tracking_channel_id)
            if channel:
                tracking_channel_str = channel.mention
            else:
                tracking_channel_str = f"Not Found (ID: {tracking_channel_id})"

        # Format breach types
        breach_type_lines = []
        if breach_types:
            for name, cost in sorted(breach_types.items()):
                breach_type_lines.append(f"- {name.capitalize()}: Cost {cost}")
        else:
            breach_type_lines.append("No breach types defined.")
        breach_types_str = "\n".join(breach_type_lines)

        # --- Create Embed ---
        embed = discord.Embed(
            title=f"Custodian Settings for {ctx.guild.name}",
            color=await ctx.embed_colour() # Use the bot's embed color for the server
        )

        embed.add_field(name="Weekly Reset Time", value=reset_time_str, inline=False)
        embed.add_field(name="Tracking Channel", value=tracking_channel_str, inline=False)
        embed.add_field(name="Default Thinspace Limit", value=str(default_limit), inline=False)
        # Add breach types in a separate field, check length for embed limits
        if len(breach_types_str) <= 1024:
             embed.add_field(name="Breach Types & Costs", value=breach_types_str, inline=False)
        else:
             embed.add_field(name="Breach Types & Costs", value="*Too many types to display here.*", inline=False)


        await ctx.send(embed=embed)    
    
    @custodianset.command(name="setmaxdreams")
    async def set_max_dreams(self, ctx: commands.Context, count: int):
        """Sets the maximum number of dreams available per cycle."""
        if count < 0: # Allow 0 max dreams? Or require >= 1? Let's allow 0 for now.
            await ctx.send("Maximum dreams cannot be negative.")
            return
        # Optional: Add an upper sanity limit if desired
        # if count > 10:
        #     await ctx.send("Setting maximum dreams higher than 10 might be excessive. Please confirm.")
        #     # Add confirmation logic if needed
        await self.config.guild(ctx.guild).max_dreams.set(count)
        await ctx.send(f"Maximum dreams per cycle set to {count}.")

    @custodianset.command(name="setbreaches")
    async def set_breaches(
        self, ctx: commands.Context,
        thinspace: str,
        count: int,
        counter_type: Literal["pre", "post"] = "pre" # Optional: target pre or post counter
    ):
        """
        Manually sets the pre-gate or post-gate breach count for a specific thinspace.

        Defaults to setting the 'pre' counter.
        Example: [p]custodianset setbreaches AA-BB 0 post
        """
        if count < 0:
            await ctx.send("Breach count cannot be negative.")
            return

        try:
            normalized_name = self._normalize_thinspace(thinspace)
        except ValueError:
             await ctx.send(f"Invalid thinspace format: {thinspace}. Use AA-BB.")
             return

        key_to_modify = f"{counter_type}_gate_breaches" # Construct key name

        async with self.config.guild(ctx.guild).thinspaces() as spaces:
            if normalized_name not in spaces:
                await ctx.send(f"Thinspace '{normalized_name}' does not exist.")
                return

            # Check if the entry is actually a dictionary before modifying
            if isinstance(spaces[normalized_name], dict):
                spaces[normalized_name][key_to_modify] = count # Set the correct counter
            else:
                await ctx.send(f"Error: Data for thinspace '{normalized_name}' seems corrupted.")
                return

        await ctx.send(f"'{counter_type}' breach count for thinspace '{normalized_name}' manually set to {count}.")

    @custodianset.command(name="setdreams")
    async def set_dreams_left(self, ctx: commands.Context, count: int):
        """Manually sets the current number of dreams left for this cycle."""
        max_dreams = await self.config.guild(ctx.guild).max_dreams()

        if count < 0:
            await ctx.send("Dream count cannot be negative.")
            return
        if count > max_dreams:
            await ctx.send(f"Dream count cannot be set higher than the maximum ({max_dreams}).")
            return

        await self.config.guild(ctx.guild).dreams_left.set(count)
        await ctx.send(f"Current dreams left manually set to {count}/{max_dreams}.")

    @custodianset.command(name="setavailablegates")
    async def set_available_gates(self, ctx: commands.Context, count: int):
        """Manually sets the current number of available gates in the pool.

        Cannot be set higher than the server's maximum gate capacity.
        """
        max_gates = await self.config.guild(ctx.guild).max_gates()

        if count < 0:
            await ctx.send("Available gate count cannot be negative.")
            return
        if count > max_gates:
            await ctx.send(f"Available gates cannot be set higher than the maximum capacity ({max_gates}). Use `setmaxgates` to change the capacity.")
            return

        await self.config.guild(ctx.guild).breachgates_available.set(count)
        await ctx.send(f"Current available gates manually set to {count}/{max_gates}.")

    @custodianset.group(name="breachtype")
    async def set_breachtype(self, ctx: commands.Context):
        """Manage custom breach types and costs for this server."""
        pass # Base group command does nothing on its own

    @set_breachtype.command(name="add")
    async def breachtype_add(self, ctx: commands.Context, name: str, cost: int):
        """Adds a new custom breach type or updates the cost of an existing one.

        Breach type names are stored in lowercase. 'Hand' is default and cannot be changed.
        Cost must be 1 or greater.
        """
        type_name = name.lower() # Store and compare in lowercase

        # Prevent modifying the implicit 'hand' type if needed, or allow override
        # if type_name == "hand":
        #    await ctx.send("'Hand' is the default type and cannot be modified.")
        #    return

        if cost <= 0:
            await ctx.send("Breach cost must be 1 or greater.")
            return

        async with self.config.guild(ctx.guild).breach_types() as types:
            action = "updated" if type_name in types else "added"
            types[type_name] = cost # Add or update the type

        await ctx.send(f"Breach type '{type_name}' {action} with cost {cost}.")

    @set_breachtype.command(name="remove", aliases=["delete", "del"])
    async def breachtype_remove(self, ctx: commands.Context, name: str):
        """Removes a custom breach type.

        Default types ('hand', 'hound', 'mole' if present in defaults) cannot be removed.
        """
        type_name = name.lower()

        # Prevent removal of original default types
        if type_name in DEFAULT_BREACH_TYPES:
             await ctx.send(f"Cannot remove default breach type '{type_name}'.")
             return

        async with self.config.guild(ctx.guild).breach_types() as types:
            if type_name not in types:
                await ctx.send(f"Custom breach type '{type_name}' not found.")
                return

            del types[type_name] # Remove the type

        await ctx.send(f"Custom breach type '{type_name}' removed.")

    @set_breachtype.command(name="list")
    async def breachtype_list(self, ctx: commands.Context):
        """Lists all currently defined breach types and their costs for this server."""

        types = await self.config.guild(ctx.guild).breach_types()

        if not types:
            await ctx.send("No breach types are defined for this server (should at least have defaults).")
            return

        # Create embed for nice formatting
        embed = discord.Embed(
            title=f"Breach Types for {ctx.guild.name}",
            color=await ctx.embed_colour()
        )

        description_lines = []
        # Sort by name for consistent listing
        for name, cost in sorted(types.items()):
            description_lines.append(f"- **{name.capitalize()}**: Cost {cost}")

        # Join lines and add to embed description (or fields if preferred)
        embed.description = "\n".join(description_lines)

        await ctx.send(embed=embed)
        
    @custodianset.command(name="setcycle")
    async def set_cycle_number(self, ctx: commands.Context, number: int):
        """Manually sets the current cycle number."""
        if number < 1:
            await ctx.send("Cycle number must be 1 or greater.")
            return

        await self.config.guild(ctx.guild).cycle_number.set(number)
        await ctx.send(f"Cycle number manually set to {number}.")
    # Note: This does not trigger a reset, only changes the number for the *next* reset.
    
    @custodianset.command(name="setmaxgates")
    async def set_max_gates(self, ctx: commands.Context, count: int):
        """Sets the maximum number of breachgates the server refills to weekly."""
        if count < 0:
            await ctx.send("Maximum gates cannot be negative.")
            return

        await self.config.guild(ctx.guild).max_gates.set(count)
        # Important decision: Should setting the max also immediately affect the current available count?
        # Option 1: Only affect future refills (simplest)
        # Option 2: Also set current available, capped by new max
        # current_available = await self.config.guild(ctx.guild).breachgates_available()
        # await self.config.guild(ctx.guild).breachgates_available.set(min(current_available, count))
        # Let's go with Option 1 for now - only affects future refills.

        await ctx.send(f"Maximum breachgate capacity set to {count}. Available gates will refill to this amount during the next weekly reset.")
    

    @custodianset.command(name="pausereset")
    async def pause_reset(self, ctx: commands.Context):
        """Pauses the automatic weekly reset loop for this server."""
        await self.config.guild(ctx.guild).is_reset_paused.set(True)
        await ctx.send("✅ The automatic weekly reset has been **paused**.")

    @custodianset.command(name="unpausereset")
    async def unpause_reset(self, ctx: commands.Context):
        """Resumes the automatic weekly reset loop for this server."""
        await self.config.guild(ctx.guild).is_reset_paused.set(False)
        await ctx.send("✅ The automatic weekly reset has been **resumed**. It will perform a reset at the next scheduled time.")

    @commands.group(aliases=["custodianset"]) # Or use custodianset if you prefer
    @checks.admin_or_permissions(manage_guild=True)
    async def triosetup(self, ctx: commands.Context):
        """Manage Trio system settings."""
        pass

    @custodianset.command(name="setlistchannel")
    async def triosetup_listchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Sets or clears the channel for the persistent Trio list.

        If no channel is provided, the feature will be disabled and existing messages cleared.
        The bot needs Send Messages, Embed Links, Manage Messages, and Read Message History permissions in the channel.
        """
        guild_config = self.config.guild(ctx.guild)
        old_channel_id = await guild_config.persistent_trio_list_channel_id()
        old_message_ids = await guild_config.persistent_trio_list_message_ids()

        # Clear old messages if channel is changing or being cleared
        if old_channel_id and old_message_ids:
            old_channel = ctx.guild.get_channel(old_channel_id)
            if old_channel:
                await ctx.send(f"Attempting to clear old list messages from {old_channel.mention}...")
                for msg_id in old_message_ids:
                    try:
                        message = await old_channel.fetch_message(msg_id)
                        await message.delete()
                    except discord.NotFound: pass
                    except discord.Forbidden:
                        await ctx.send(f"Could not delete old message {msg_id} from {old_channel.mention} due to missing permissions.")
                    except Exception as e:
                        await ctx.send(f"Error deleting old message {msg_id}: {e}")
            await guild_config.persistent_trio_list_message_ids.set([]) # Clear stored IDs

        if channel is None:
            await guild_config.persistent_trio_list_channel_id.set(None)
            await ctx.send("Persistent Trio list channel has been cleared and disabled.")
            return
        
        # Check bot permissions in new channel
        perms = channel.permissions_for(ctx.guild.me)
        if not (perms.send_messages and perms.embed_links and perms.manage_messages and perms.read_message_history):
            await ctx.send(
                f"Error: I need 'Send Messages', 'Embed Links', 'Manage Messages', and 'Read Message History' "
                f"permissions in {channel.mention} to manage the persistent Trio list."
            )
            return

        await guild_config.persistent_trio_list_channel_id.set(channel.id)
        await ctx.send(f"Persistent Trio list channel set to {channel.mention}. I will now post the initial list.")
        await self._update_persistent_trio_list(ctx.guild) # Initial post
        
        
    @commands.group(aliases=["trioset"]) # Using your existing group
    @checks.admin_or_permissions(manage_guild=True)
    async def triosetup(self, ctx: commands.Context):
        """Manage Trio system settings."""
        pass

    @custodianset.command(name="postcontrolpanel")
    async def post_trio_control_panel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Posts or replaces the persistent Trio management button panel."""
        target_channel = channel or ctx.channel
        guild_config = self.config.guild(ctx.guild)

        perms = target_channel.permissions_for(ctx.guild.me)
        if not (perms.send_messages and perms.embed_links and perms.manage_messages): # Need manage_messages to delete old
            await ctx.send(f"I need 'Send Messages', 'Embed Links', and 'Manage Messages' permissions in {target_channel.mention}.")
            return

        # Fetch old message and channel IDs
        old_msg_id = await guild_config.trio_control_panel_message_id()
        old_chan_id = await guild_config.trio_control_panel_channel_id()

        # Delete old button message if it exists
        if old_msg_id and old_chan_id:
            old_channel_obj = ctx.guild.get_channel(old_chan_id)
            if old_channel_obj: # Check if old channel still exists
                try:
                    message_to_delete = await old_channel_obj.fetch_message(old_msg_id)
                    await message_to_delete.delete()
                    print(f"[PostControlPanel] Deleted old panel message {old_msg_id} from #{old_channel_obj.name}")
                    await ctx.send("Replaced previous Trio control panel.", ephemeral=True, delete_after=10)
                except discord.NotFound:
                    print(f"[PostControlPanel] Old panel message {old_msg_id} not found in #{old_channel_obj.name}.")
                except discord.Forbidden:
                    print(f"[PostControlPanel] Forbidden to delete old panel message {old_msg_id} in #{old_channel_obj.name}.")
                    await ctx.send("Could not delete old panel message due to permissions.", ephemeral=True, delete_after=10)
                except Exception as e:
                    print(f"Error deleting old control panel message {old_msg_id}: {e}")
            else:
                print(f"[PostControlPanel] Old channel ID {old_chan_id} for panel message not found.")
        
        # Clear the stored IDs from config BEFORE posting the new message
        # This means for a brief moment, on_message will see no protected panel_msg_id
        await guild_config.trio_control_panel_message_id.set(None)
        await guild_config.trio_control_panel_channel_id.set(None) # Also clear channel if storing it

        view = self.PersistentTrioControlView(self)
        embed_text = (
            "**Trio Terminal**\n\n"
            "Use the buttons below to manage your Trio or others'."
        )
        embed = discord.Embed(description=embed_text, color=await ctx.embed_colour())
        
        try:
            sent_message = await target_channel.send(embed=embed, view=view)
            # Now save the new ID and channel
            await guild_config.trio_control_panel_message_id.set(sent_message.id)
            await guild_config.trio_control_panel_channel_id.set(target_channel.id) # Store the channel where it was posted
            print(f"[PostControlPanel] NEW Control Panel Message ID: {sent_message.id} saved for guild {ctx.guild.id} in channel {target_channel.id}")
            await ctx.send(f"Trio control panel posted in {target_channel.mention}. Its buttons will remain active.")
        except Exception as e:
            await ctx.send(f"Failed to post Trio control panel: {e}")
            print(f"Error posting new control panel: {e}")

    @custodianset.command(name="manualreset")
    @commands.is_owner() # Restrict to bot owner(s) for safety
    async def manual_reset_cycle(self, ctx: commands.Context):
        """
        Manually triggers the weekly reset process for this server.

        Warning: This performs the full reset immediately. Use with caution.
        """
        # Manual Confirmation Dialog using wait_for
        prompt_msg = (
            f"**Warning:** Are you sure you want to manually trigger the weekly reset for **{ctx.guild.name}**?\n"
            "This will reset all breach counts, applied gates, dreams, and advance the cycle number.\n"
            "Type `yes` to confirm within 30 seconds."
        )
        confirm_message = await ctx.send(prompt_msg)

        def check(message: discord.Message) -> bool:
            # Check if the message is from the original command author and in the same channel
            # Also check if the content is exactly 'yes' (case-insensitive)
            return message.author == ctx.author and message.channel == ctx.channel and message.content.lower() == "yes"

        try:
            # Wait for a message that passes the check function
            await self.bot.wait_for("message", check=check, timeout=30.0)
            # If wait_for completes without timing out, it means the user typed 'yes'

        except asyncio.TimeoutError:
            # If wait_for times out
            await confirm_message.edit(content="Manual reset cancelled (timeout).")
            # Attempt to delete the user's non-confirming message if possible and desired (optional)
            # try: await ctx.message.delete() except discord.Forbidden: pass
            return
        # No need for an 'else' or checking a result, if it didn't time out, the check passed.

        # Proceed if confirmation was successful
        await confirm_message.edit(content="Confirmation received. Performing manual reset...")

        # --- Call the Helper Function ---
        try:
            log_msg, cycle_msg, next_reset_dt = await self._perform_reset(ctx.guild)
        except Exception as e:
            await ctx.send(f"An error occurred during manual reset: {e}")
            print(f"Error during manual reset for Guild ID: {ctx.guild.id}")
            # import traceback; traceback.print_xc() # For detailed debugging
            return

        # --- Post Messages ---
        tracking_channel_id = await self.config.guild(ctx.guild).tracking_channel()
        channel_to_post = ctx.channel # Default to context channel
        post_failed = False
        if tracking_channel_id:
            found_channel = ctx.guild.get_channel(tracking_channel_id)
            if found_channel and found_channel.permissions_for(ctx.guild.me).send_messages:
                channel_to_post = found_channel
            else:
                await ctx.send(f"Warning: Configured tracking channel ({tracking_channel_id}) not found or I lack permissions. Posting results here instead.")

        try:
            for page in pagify(log_msg): # Post log message
                await channel_to_post.send(page)
            await channel_to_post.send(cycle_msg) # Post cycle message
        except discord.HTTPException as e:
             await ctx.send(f"Error posting results to {channel_to_post.mention}: {e}")
             post_failed = True # Flag if posting fails

        # Send final confirmation to the command channel
        if post_failed:
             await ctx.send("Manual reset logic completed, but failed to post results to the target channel.")
        elif channel_to_post != ctx.channel:
             await ctx.send(f"Manual reset complete. Results posted in {channel_to_post.mention}.")
        
        
    # TRIO COMMANDS

    @commands.group(aliases=["mani"], invoke_without_command=True)
    @commands.guild_only()
    async def trio(self, ctx: commands.Context, *, target_member: discord.Member = None):
        """Manage and interact with Trios (collectible Manifestation discs).

        If no subcommand is given, this command defaults to the 'trio mine' functionality
        for yourself or for the optionally specified [target_member].
        Example:
        [p]trio -> Shows your 'trio mine' menu.
        [p]trio @User -> Shows User's 'trio mine' menu (subject to permissions/locks).
        """
        if ctx.invoked_subcommand is None:
            # Get the 'trio mine' command object
            # The actual method name for 'trio mine' is trio_mine in your class
            mine_command_method = self.trio_mine 
            
            if mine_command_method:
                # We need to call the method directly as if it were invoked by a command.
                # To do this properly and ensure all checks in 'trio_mine' run correctly
                # with the right context, it's best to use ctx.invoke.
                # We need the actual command object for ctx.invoke.
                
                actual_mine_command = self.bot.get_command("trio mine")
                if actual_mine_command:
                    # Pass the target_member to the 'trio mine' command.
                    # The 'trio mine' command's signature is:
                    # async def trio_mine(self, ctx: commands.Context, *, target_member: discord.Member = None)
                    # So we pass 'target_member' to its keyword argument.
                    await ctx.invoke(actual_mine_command, target_member=target_member)
                else:
                    # Fallback if 'trio mine' command somehow can't be found by name
                    await ctx.send_help(ctx.command)
            else:
                # Fallback if the method self.trio_mine doesn't exist (should not happen)
                await ctx.send_help(ctx.command)

    @trio.command(name="add")
    @checks.admin_or_permissions(manage_guild=True)
    async def trio_add(self, ctx: commands.Context, number: int, ability1: str, ability2: str, ability3: str):
        """Defines a new Trio or updates an existing one.

        Example: [p]trio add 1 Cloak Club Candle
        Trios are identified by their number (1-49 recommended).
        """
        if not (1 <= number <= 49): # Or whatever your practical limit is
            await ctx.send("Please provide a Trio number between 1 and 49 (or your desired range).")
            return
        
        trio_id_str = str(number) # Use string for dictionary keys

        new_trio_data = {
            "name": f"Trio {trio_id_str}", # Auto-generated name
            "abilities": [ability1, ability2, ability3],
            "holder_id": None,
            "holder_name": None
        }

        async with self.config.guild(ctx.guild).trios_inventory() as trios_inv:
            action = "updated" if trio_id_str in trios_inv else "added"
            trios_inv[trio_id_str] = new_trio_data
        
        await ctx.send(
            f"Trio #{trio_id_str} ('{new_trio_data['name']}') {action} with Manifestations: "
            f" {ability1}, {ability2}, {ability3}."
        )
        await self._update_persistent_trio_list(ctx.guild)

    @trio.command(name="remove")
    @checks.admin_or_permissions(manage_guild=True)
    async def trio_remove_definition(self, ctx: commands.Context, number: int):
        """Permanently removes a Trio definition from the system.

        <number>: The number of the Trio to remove.
        The Trio must be 'In the Well' (not held or in a Bowl) to be removed.
        """
        trio_id_str = str(number)
        
        trio_name_for_prompt = f"Trio #{trio_id_str}"
        temp_trios_inv = await self.config.guild(ctx.guild).trios_inventory()
        if trio_id_str in temp_trios_inv and isinstance(temp_trios_inv[trio_id_str], dict):
            trio_name_for_prompt = temp_trios_inv[trio_id_str].get("name", f"Trio #{trio_id_str}")

        prompt_text = (
            f"**Warning:** Are you sure you want to permanently delete **{trio_name_for_prompt}**?\n"
            "This action cannot be undone. The Trio must be 'In the Well' (not held by a player or in a Bowl).\n"
            "Type `yes` to confirm within 30 seconds."
        )
        confirm_message = await ctx.send(prompt_text)

        def check(message: discord.Message) -> bool:
            return message.author == ctx.author and message.channel == ctx.channel and message.content.lower() == "yes"

        try:
            await self.bot.wait_for("message", check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await confirm_message.edit(content=f"Removal of {trio_name_for_prompt} cancelled (timeout).")
            return
        
        await confirm_message.delete() # Clean up confirmation prompt

        async with self.config.guild(ctx.guild).trios_inventory() as trios_inv:
            if trio_id_str not in trios_inv:
                await ctx.send(f"Trio #{trio_id_str} not found in the inventory.")
                return

            trio_data = trios_inv[trio_id_str]
            if not isinstance(trio_data, dict): # Should not happen if add command is robust
                await ctx.send(f"Data for Trio #{trio_id_str} is corrupted. Cannot remove.")
                return

            holder_id = trio_data.get("holder_id")
            trio_display_name = trio_data.get("name", f"Trio #{trio_id_str}")

            if holder_id is not None: # It's held by a player OR in a Bowl
                status_msg = ""
                if holder_id == "IN_BOWL":
                    status_msg = "it is currently in a Bowl."
                else:
                    holder_name = trio_data.get("holder_name", "a player")
                    status_msg = f"it is currently held by {holder_name}."
                
                await ctx.send(
                    f"Cannot remove '{trio_display_name}'. It must be returned to 'The Well' first "
                    f"(currently, {status_msg}).\n"
                    f"Use `[p]trio drop @user` (if held by user), `[p]trio empty {trio_id_str}` (if in bowl)."
                )
                return

            # If holder_id is None, it's in the Well and can be deleted
            del trios_inv[trio_id_str]
            await ctx.send(f"Trio '{trio_display_name}' (ID: #{trio_id_str}) has been permanently removed from the system.")
        await self._update_persistent_trio_list(ctx.guild)
    
    @trio.command(name="lock")
    async def trio_lock(self, ctx: commands.Context):
        """Locks your Trio status, preventing others from affecting your held Trio.

        Admins can still override this lock. You can still drop or give your Trio.
        """
        user_id_str = str(ctx.author.id)
        async with self.config.guild(ctx.guild).trio_user_locks() as user_locks:
            user_locks[user_id_str] = True
        
        await ctx.send(
            f"{ctx.author.mention}, your Trio status is now **locked**. "
            "Other players cannot claim a Trio for you or make you drop your currently held Trio. "
            "You can still use `trio drop` or `trio give` yourself."
        )
        await self._update_persistent_trio_list(ctx.guild)

    @trio.command(name="unlock")
    async def trio_unlock(self, ctx: commands.Context):
        """Unlocks your Trio status, allowing others to affect your held Trio again."""
        user_id_str = str(ctx.author.id)
        async with self.config.guild(ctx.guild).trio_user_locks() as user_locks:
            if user_id_str in user_locks:
                user_locks[user_id_str] = False # Explicitly set to False
                # Or, if you only want to store True values: del user_locks[user_id_str]
            # If not in user_locks, it's implicitly unlocked, so no action needed.
        
        await ctx.send(f"{ctx.author.mention}, your Trio status is now **unlocked**.")
        await self._update_persistent_trio_list(ctx.guild)

    @trio.command(name="claim")
    async def trio_claim(self, ctx: commands.Context, identifier: str, *, target_member: discord.Member = None):
        """Claims an available Trio for yourself or a specified member.

        <identifier>: The Trio number or one of its unique ability names.
        [target_member]: (Optional) The member to claim the Trio for.
                       If specified by a non-moderator, the target member must not have their Trio status locked.
        """
        actual_target_user = target_member or ctx.author
        invoker_can_override_lock = ctx.author.guild_permissions.manage_guild

        # 1. Check if target_member has their Trio status locked by an action from another user
        if target_member and target_member != ctx.author: # If acting on someone else
            user_locks = await self.config.guild(ctx.guild).trio_user_locks()
            if user_locks.get(str(actual_target_user.id), False): # And that person's Trio is locked
                if not invoker_can_override_lock: # And the invoker CANNOT override
                    await ctx.send(
                        f"{actual_target_user.display_name} has locked their Trio status. "
                        "Only they can claim a Trio for themself while locked."
                    )
                    return
                else:
                     # Optional: Notify that an override is happening
                    await ctx.send(f"*(Okay Dad, overriding lock for {actual_target_user.display_name}.)*", delete_after=10)


        # 2. Check if the actual_target_user already holds a Trio (rest of the logic remains the same)
        user_trio_info = await self._find_user_trio(ctx.guild, actual_target_user.id)
        if user_trio_info is not None:
            existing_trio_id, existing_trio_data = user_trio_info
            trio_name_display = existing_trio_data.get("name", f"Trio #{existing_trio_id}")
            await ctx.send(f"{actual_target_user.display_name} already holds '{trio_name_display}'. They must drop it first to claim another.")
            return

        # 3. Find the Trio to be claimed
        trio_to_claim_info = await self._find_trio_by_identifier(ctx.guild, identifier)
        if trio_to_claim_info is None:
            await ctx.send(f"Sorry, I couldn't find a Trio matching '{identifier}'.")
            return
        found_trio_id, found_trio_data = trio_to_claim_info
            
        trio_name_to_claim_display = found_trio_data.get("name", f"Trio #{found_trio_id}")

        # 4. Check if the found Trio is available
        if found_trio_data.get("holder_id") is not None:
            current_holder_name = found_trio_data.get("holder_name", "another player")
            await ctx.send(f"'{trio_name_to_claim_display}' is already held by {current_holder_name}.")
            return

        # 5. Claim the Trio
        async with self.config.guild(ctx.guild).trios_inventory() as trios_inv:
            if found_trio_id in trios_inv:
                trios_inv[found_trio_id]["holder_id"] = actual_target_user.id
                trios_inv[found_trio_id]["holder_name"] = actual_target_user.display_name
            else: 
                await ctx.send("An unexpected error occurred retrieving the Trio data. Please try again.")
                print(f"Error in trio_claim: Trio ID '{found_trio_id}' from _find_trio_by_identifier not found in trios_inv during claim.")
                return
        
        abilities_list_str = ", ".join(found_trio_data.get("abilities", ["Unknown abilities"]))
        await ctx.send(
            f"{actual_target_user.display_name} has claimed '{trio_name_to_claim_display}'!\n"
            f"Manifestations: {abilities_list_str}"
        )
        await self._update_persistent_trio_list(ctx.guild)

    @trio.command(name="drop")
    async def trio_drop(self, ctx: commands.Context, *, target_member: discord.Member = None):
        """Makes yourself or a specified member drop their currently held Trio.

        [target_member]: (Optional) The member to make drop their Trio.
                       If specified by a non-moderator, the target member must not have their Trio status locked.
        """
        actual_target_user = target_member or ctx.author
        
        # Check if the invoker has 'Manage Server' permission for overriding locks
        invoker_can_override_lock = ctx.author.guild_permissions.manage_guild

        # (You can remove any previous debug prints for 'is_admin' now)

        # 1. Check if target_member has their Trio status locked when action is by another user
        if target_member and target_member != ctx.author: # If acting on someone else
            user_locks = await self.config.guild(ctx.guild).trio_user_locks()
            if user_locks.get(str(actual_target_user.id), False): # And that person's Trio is locked
                if not invoker_can_override_lock: # And the invoker CANNOT override
                    await ctx.send(
                        f"{actual_target_user.display_name} has locked their Trio status. "
                        "Only they can drop their Trio while locked."
                    )
                    return
                else:
                    # Optional: Notify that an override is happening
                    await ctx.send(f"*(Okay Dad, overriding lock for {actual_target_user.display_name}.)*", delete_after=10)
        
        # 2. Find the Trio held by the actual_target_user (rest of the logic remains the same)
        user_trio_info = await self._find_user_trio(ctx.guild, actual_target_user.id)

        if user_trio_info is None:
            if actual_target_user == ctx.author:
                await ctx.send("You are not currently holding a Trio.")
            else:
                await ctx.send(f"{actual_target_user.display_name} is not currently holding a Trio.")
            return
        
        trio_id_to_drop, trio_data_to_drop = user_trio_info
        trio_name_dropped = trio_data_to_drop.get("name", f"Trio #{trio_id_to_drop}")

        # 3. Drop the Trio (set holder to None)
        async with self.config.guild(ctx.guild).trios_inventory() as trios_inv:
            if trio_id_to_drop in trios_inv:
                trios_inv[trio_id_to_drop]["holder_id"] = None
                trios_inv[trio_id_to_drop]["holder_name"] = None
            else:
                await ctx.send("An unexpected error occurred trying to drop the Trio. Please try again.")
                print(f"Error in trio_drop: Trio ID '{trio_id_to_drop}' not found in trios_inv during drop.")
                return
        
        if actual_target_user == ctx.author:
            await ctx.send(f"You have dropped '{trio_name_dropped}'. It is now in the Well.")
        else:
            await ctx.send(f"{actual_target_user.display_name} has dropped '{trio_name_dropped}'. It is now in the Well.")
        
        await self._update_persistent_trio_list(ctx.guild)
            
    @trio.command(name="list") # Or keep as trio_list_all if you prefer
    async def trio_list_all_command(self, ctx: commands.Context): # Renamed function to avoid clash if keeping old
        """Lists all defined Trios, their Manifestations, and current holders."""
        trios_inv = await self.config.guild(ctx.guild).trios_inventory()

        if not trios_inv:
            await ctx.send("No Trios have been defined for this server yet. Use `[p]trio add`.")
            return
        
        await self._display_trios_list(ctx, trios_inv, "Trio List")
        
    @trio.command(name="available", aliases=["well"])
    async def trio_available(self, ctx: commands.Context):
        """Lists all Trios currently 'In the Well' (unheld)."""
        all_trios_inv = await self.config.guild(ctx.guild).trios_inventory()
        
        available_trios = {
            trio_id: data 
            for trio_id, data in all_trios_inv.items() 
            if isinstance(data, dict) and data.get("holder_id") is None
        }
        
        await self._display_trios_list(ctx, available_trios, "Available Trios (In the Well)")    
    
    @trio.command(name="held")
    async def trio_held(self, ctx: commands.Context):
        """Lists all Trios currently held by players."""
        all_trios_inv = await self.config.guild(ctx.guild).trios_inventory()
        
        held_trios = {
            trio_id: data 
            for trio_id, data in all_trios_inv.items() 
            if isinstance(data, dict) and data.get("holder_id") is not None
        }
        
        await self._display_trios_list(ctx, held_trios, "Held Trios")
    
    @trio.command(name="info")
    async def trio_info(self, ctx: commands.Context, *, identifier: str):
        """Displays detailed information about a specific Trio by its number or one of its Manifestations."""
        trio_info_tuple = await self._find_trio_by_identifier(ctx.guild, identifier)

        if trio_info_tuple is None:
            await ctx.send(f"No Trio found matching the identifier '{identifier}'.")
            return
            
        trio_id_str, trio_data = trio_info_tuple

        if not isinstance(trio_data, dict):
            await ctx.send(f"Data for Trio matching '{identifier}' appears to be corrupted.")
            return

        name = trio_data.get("name", f"Trio #{trio_id_str}")
        abilities = trio_data.get("abilities", [])
        holder_id = trio_data.get("holder_id") # Get holder_id
        holder_name = trio_data.get("holder_name")

        embed = discord.Embed(title=f"Details for {name}", color=await ctx.embed_colour())

        if abilities:
            ability_lines = []
            # Manifestations will be colored by ANSI, so description needs ```ansi
            for i_ab, ability in enumerate(abilities): # Renamed 'i' to 'i_ab' to avoid conflict if pasting into other loops
                ability_lines.append(f"{i_ab+1}. {self.ANSI_CYAN}{ability}{self.ANSI_RESET}")
            manifestations_text_block_content = '\n'.join(ability_lines)
            embed.add_field(name="Manifestations", value=f"```ansi\n{manifestations_text_block_content}\n```", inline=False)
        else:
            embed.add_field(name="Manifestations", value="None defined.", inline=False)

        status_str_for_block = ""
        # --- MODIFIED STATUS LOGIC ---
        if holder_id == "IN_BOWL": # Check for our special Bowl ID
            status_str_for_block = f"Currently {self.ANSI_MAGENTA}In a Bowl{self.ANSI_RESET}"
        elif holder_id is not None and holder_name is not None: # Held by a player
            status_str_for_block = f"Currently held by: {self.ANSI_YELLOW}{holder_name}{self.ANSI_RESET}"
        else: # holder_id is None (In the Well)
            status_str_for_block = f"Currently {self.ANSI_BLUE}In the Well{self.ANSI_RESET}"
        # --- END MODIFIED STATUS LOGIC ---
        
        embed.add_field(name="Status", value=f"```ansi\n{status_str_for_block}\n```", inline=False)
            
        await ctx.send(embed=embed)
        
    @trio.command(name="bowl")
    async def trio_bowl_store(self, ctx: commands.Context, *, identifier: str):
        """Places a Trio into Bowl storage.
        Can take a Trio from the Well or from a player (subject to locks).

        <identifier>: The Trio number or one of its Manifestations.
        """
        trio_to_bowl_info = await self._find_trio_by_identifier(ctx.guild, identifier)

        if trio_to_bowl_info is None:
            await ctx.send(f"No Trio found matching the identifier '{identifier}'.")
            return
        
        trio_id_str, trio_data = trio_to_bowl_info
        trio_name_display = trio_data.get("name", f"Trio #{trio_id_str}")
        current_holder_id = trio_data.get("holder_id")

        if current_holder_id == "IN_BOWL":
            await ctx.send(f"'{trio_name_display}' is already in a Bowl.")
            return

        # Check locks if someone else is holding it and invoker is not a manager
        if current_holder_id is not None and current_holder_id != ctx.author.id: # Held by another player
            invoker_can_override_lock = ctx.author.guild_permissions.manage_guild
            if not invoker_can_override_lock:
                user_locks = await self.config.guild(ctx.guild).trio_user_locks()
                if user_locks.get(str(current_holder_id), False):
                    holder = ctx.guild.get_member(current_holder_id) # Try to get member for name
                    holder_name_for_msg = holder.display_name if holder else "its current holder"
                    await ctx.send(
                        f"Cannot move '{trio_name_display}' to a Bowl. {holder_name_for_msg} has locked their Trio status."
                    )
                    return
            else: # Invoker is overriding lock
                 await ctx.send(f"*(Okay Dad, overriding lock to move '{trio_name_display}' to a Bowl.)*", delete_after=10)


        # Place it in the Bowl
        async with self.config.guild(ctx.guild).trios_inventory() as trios_inv:
            if trio_id_str in trios_inv: 
                original_holder_name = trios_inv[trio_id_str].get("holder_name")
                trios_inv[trio_id_str]["holder_id"] = "IN_BOWL" 
                trios_inv[trio_id_str]["holder_name"] = "In a Bowl" 
            else:
                await ctx.send("An unexpected error occurred. Could not find the Trio to update.")
                return
        
        if current_holder_id is None:
            await ctx.send(f"'{trio_name_display}' has been moved from the Well into a Bowl.")
        elif current_holder_id == ctx.author.id:
            await ctx.send(f"{ctx.author.display_name}, you have placed your '{trio_name_display}' into a Bowl.")
        else: # Moved from another player by an admin/manager
            await ctx.send(f"'{trio_name_display}' (previously held by {original_holder_name}) has been moved into a Bowl.")
        await self._update_persistent_trio_list(ctx.guild)
            
    @trio.command(name="claimbowl")
    async def trio_claim_from_bowl(self, ctx: commands.Context, identifier: str, *, target_member: discord.Member = None):
        """Claims/retrieves a Trio from a Bowl for yourself or a specified member.

        The target member must not already be holding a Trio.
        <identifier>: The Trio number or one of its Manifestations currently in a Bowl.
        [target_member]: (Optional) The member to retrieve the Trio for.
                       If specified by a non-moderator, the target member must not have their Trio status locked.
        """
        actual_target_user = target_member or ctx.author
        invoker_can_override_lock = ctx.author.guild_permissions.manage_guild

        # 1. Lock Check (if acting on another user and invoker does not have override perms)
        if target_member and target_member != ctx.author and not invoker_can_override_lock:
            user_locks = await self.config.guild(ctx.guild).trio_user_locks()
            if user_locks.get(str(actual_target_user.id), False): # Check if lock is True
                await ctx.send(
                    f"{actual_target_user.display_name} has locked their Trio status. "
                    "Only they or someone with 'Manage Server' permission can claim a Trio for them from a Bowl while locked."
                )
                return
            # No specific "admin override" message here as it's a claim *for* them.

        # 2. Check if the actual_target_user already holds a Trio
        user_trio_info = await self._find_user_trio(ctx.guild, actual_target_user.id)
        if user_trio_info is not None:
            existing_trio_id, existing_trio_data = user_trio_info
            trio_name_display = existing_trio_data.get("name", f"Trio #{existing_trio_id}")
            await ctx.send(f"{actual_target_user.display_name} already holds '{trio_name_display}'. They must drop it first to retrieve another from a Bowl.")
            return

        # 3. Find the Trio to be claimed from the Bowl by identifier
        trio_to_claim_info = await self._find_trio_by_identifier(ctx.guild, identifier)
        if trio_to_claim_info is None:
            await ctx.send(f"No Trio found matching the identifier '{identifier}'.")
            return
        found_trio_id, found_trio_data = trio_to_claim_info
        trio_name_to_claim_display = found_trio_data.get("name", f"Trio #{found_trio_id}")

        # 4. Check if the found Trio is actually in a Bowl
        if found_trio_data.get("holder_id") != "IN_BOWL":
            current_holder_id = found_trio_data.get("holder_id")
            current_holder_name = found_trio_data.get("holder_name")
            if current_holder_id is None:
                 await ctx.send(f"'{trio_name_to_claim_display}' is currently in the Well, not in a Bowl. Use `[p]trio claim {identifier}` to claim it.")
            elif current_holder_name: # Held by a player
                 await ctx.send(f"'{trio_name_to_claim_display}' is currently held by {current_holder_name}, not in a Bowl.")
            else: # Some other unknown state (should ideally not happen)
                 await ctx.send(f"'{trio_name_to_claim_display}' is not currently in a Bowl.")
            return

        # 5. Retrieve the Trio from the Bowl and assign to actual_target_user
        async with self.config.guild(ctx.guild).trios_inventory() as trios_inv:
            if found_trio_id in trios_inv: # Should always be true
                trios_inv[found_trio_id]["holder_id"] = actual_target_user.id
                trios_inv[found_trio_id]["holder_name"] = actual_target_user.display_name
            else: # Should not happen
                await ctx.send("An unexpected error occurred. Could not find the Trio to update.")
                print(f"Error in trio_claim_from_bowl: Trio ID '{found_trio_id}' not found in trios_inv during claim from bowl.")
                return
        
        manifestations_list_str = ", ".join(found_trio_data.get("abilities", ["Unknown Manifestations"]))
        await ctx.send(
            f"{actual_target_user.display_name} has claimed '{trio_name_to_claim_display}' from a Bowl!\n"
            f"Manifestations: {manifestations_list_str}"
        )
        await self._update_persistent_trio_list(ctx.guild)

    @trio.command(name="empty")
    async def trio_empty_bowl(self, ctx: commands.Context, *, identifier: str):
        """Moves a Trio currently in a Bowl back to the Well (general availability).

        <identifier>: The Trio number or one of its Manifestations currently in a Bowl.
        Any user can perform this action.
        """
        trio_to_empty_info = await self._find_trio_by_identifier(ctx.guild, identifier)

        if trio_to_empty_info is None:
            await ctx.send(f"No Trio found matching the identifier '{identifier}'.")
            return
        
        trio_id_str, trio_data = trio_to_empty_info
        trio_name_display = trio_data.get("name", f"Trio #{trio_id_str}")

        # Check if the found Trio is actually in a Bowl
        if trio_data.get("holder_id") != "IN_BOWL":
            current_holder_id = trio_data.get("holder_id")
            current_holder_name = trio_data.get("holder_name")
            if current_holder_id is None:
                 await ctx.send(f"'{trio_name_display}' is already in the Well.")
            elif current_holder_name: # Held by a player
                 await ctx.send(f"'{trio_name_display}' is currently held by {current_holder_name}, not in a Bowl. They must place it in a Bowl first or drop it.")
            else: # Some other unknown state
                 await ctx.send(f"'{trio_name_display}' is not currently in a Bowl.")
            return

        # Move to the Well (set holder to None)
        async with self.config.guild(ctx.guild).trios_inventory() as trios_inv:
            if trio_id_str in trios_inv: # Should always be true
                trios_inv[trio_id_str]["holder_id"] = None 
                trios_inv[trio_id_str]["holder_name"] = None
            else: # Should not happen
                await ctx.send("An unexpected error occurred. Could not find the Trio to update.")
                print(f"Error in trio_empty_bowl: Trio ID '{trio_id_str}' not found in trios_inv.")
                return
        
        await ctx.send(f"'{trio_name_display}' has been emptied from a Bowl and is now in the Well (generally available).")
        await self._update_persistent_trio_list(ctx.guild)

    @trio.command(name="listbowl")
    async def trio_list_bowl(self, ctx: commands.Context):
        """Lists all Trios currently stored in a Bowl."""
        all_trios_inv = await self.config.guild(ctx.guild).trios_inventory()
        
        bowled_trios = {
            trio_id: data 
            for trio_id, data in all_trios_inv.items() 
            if isinstance(data, dict) and data.get("holder_id") == "IN_BOWL" # Filter for "IN_BOWL"
        }
        
        # The _display_trios_list helper will handle the "No Trios are currently in a Bowl." message
        # if bowled_trios is empty, due to the title_prefix containing "Bowl".
        await self._display_trios_list(ctx, bowled_trios, "Trios Currently In a Bowl")
    

    @trio.command(name="mine")
    async def trio_mine(self, ctx: commands.Context, *, target_member: discord.Member = None):
        """Shows the Trio held by yourself or a specified member, with management options.
        If not holding a Trio, offers options to claim one.
        """
        actual_target_user = target_member or ctx.author
        invoker_can_manage = ctx.author.guild_permissions.manage_guild

        if actual_target_user != ctx.author and not invoker_can_manage:
            user_locks = await self.config.guild(ctx.guild).trio_user_locks()
            if user_locks.get(str(actual_target_user.id), False):
                await ctx.send(f"{actual_target_user.display_name} has locked their Trio status. You cannot view their 'mine' menu.")
                return
        
        await self._execute_trio_mine(ctx, actual_target_user)
    
    @trio.group(name="title")
    # REMOVED PERMISSION CHECK FROM THE PARENT GROUP
    async def trio_title(self, ctx: commands.Context):
        """Manage alternate names (titles) for users in Trio lists."""
        pass

    @trio_title.command(name="set")
    @checks.admin_or_permissions(manage_guild=True) # APPLIED PERMISSION CHECK HERE
    async def trio_title_set(self, ctx: commands.Context, user: discord.Member, *, title: str):
        """Assigns a title to a user. This title will be used in the 'trio title list' command.
        
        Example: [p]trio title set @User The Wanderer
        """
        async with self.config.guild(ctx.guild).trio_user_titles() as user_titles:
            user_titles[str(user.id)] = title
        
        await ctx.send(f"Set title for {user.display_name} to **{title}**.")

    @trio_title.command(name="remove")
    @checks.admin_or_permissions(manage_guild=True) # APPLIED PERMISSION CHECK HERE
    async def trio_title_remove(self, ctx: commands.Context, user: discord.Member):
        """Removes a previously set title from a user."""
        async with self.config.guild(ctx.guild).trio_user_titles() as user_titles:
            if str(user.id) in user_titles:
                del user_titles[str(user.id)]
                await ctx.send(f"Removed title from {user.display_name}.")
            else:
                await ctx.send(f"{user.display_name} does not have a title set.")
    
    @trio_title.command(name="list")
    async def trio_title_list(self, ctx: commands.Context):
        """Displays the full Trio inventory, using user titles where available."""
        await self._display_trios_list_with_titles(ctx)
    
    @commands.group(aliases=["art"])
    @commands.guild_only()
    async def artifact(self, ctx: commands.Context):
        """
        Manage and use weekly-resettable artifacts.
        """
        pass

    @artifact.group(name="set")
    @checks.admin_or_permissions(manage_guild=True)
    async def artifact_set(self, ctx: commands.Context):
        """
        Admin commands for setting up artifacts.
        """
        pass

    @artifact_set.command(name="add")
    async def artifact_add(self, ctx: commands.Context, item_id: str, *, item_name: str):
        """
        Adds or updates a weekly-resettable artifact.

        The ID should be a short, unique identifier (e.g., DPF).
        Example: [p]artifact set add DPF Dry Palm Frond
        """
        item_id_upper = item_id.upper()
        async with self.config.guild(ctx.guild).weekly_artifacts() as artifacts:
            action = "Updated" if item_id_upper in artifacts else "Added"
            
            # MODIFIED: Use a 'status' string instead of a 'used' boolean.
            artifacts[item_id_upper] = {
                "name": item_name,
                "status": "Unclaimed", # New items start as Unclaimed
                "used_by": None
            }
        
        await ctx.send(f"✅ {action} artifact '{item_name}' with ID `{item_id_upper}`.")
        
    @artifact_set.command(name="status")
    async def artifact_set_status(self, ctx: commands.Context, item_id: str, *, new_status: str):
        """
        Manually sets the status of an artifact.

        Valid statuses are: Unclaimed, Available, Used
        Example: [p]artifact set status DPF Available
        """
        valid_statuses = ["unclaimed", "available", "used"]
        status_input = new_status.lower()

        if status_input not in valid_statuses:
            await ctx.send(f"❌ Invalid status. Please use one of: `Unclaimed`, `Available`, `Used`.")
            return

        item_id_upper = item_id.upper()
        async with self.config.guild(ctx.guild).weekly_artifacts() as artifacts:
            if item_id_upper not in artifacts:
                await ctx.send(f"❌ No artifact found with the ID `{item_id_upper}`.")
                return
            
            # Set the new status
            artifacts[item_id_upper]["status"] = status_input.capitalize()
            
            # Clear used_by if it's no longer used
            if status_input != "used":
                 artifacts[item_id_upper]["used_by"] = None

            await ctx.send(f"✅ Set status of **{artifacts[item_id_upper]['name']}** to `{status_input.capitalize()}`.")

    @artifact_set.command(name="remove", aliases=["delete", "del"])
    async def artifact_remove(self, ctx: commands.Context, item_id: str):
        """
        Removes an artifact from tracking.
        """
        item_id_upper = item_id.upper()
        async with self.config.guild(ctx.guild).weekly_artifacts() as artifacts:
            if item_id_upper in artifacts:
                removed_name = artifacts[item_id_upper].get("name", "Unknown")
                del artifacts[item_id_upper]
                await ctx.send(f"✅ Removed artifact '{removed_name}' (`{item_id_upper}`).")
            else:
                await ctx.send(f"❌ No artifact found with the ID `{item_id_upper}`.")
                
    @artifact.command(name="status", aliases=["list"])
    async def artifact_status(self, ctx: commands.Context):
        """
        Displays the status of all weekly-resettable artifacts.
        """
        artifacts = await self.config.guild(ctx.guild).weekly_artifacts()
        if not artifacts:
            await ctx.send("No weekly artifacts have been configured by an admin yet.")
            return

        embed = discord.Embed(
            title="Weekly Artifact Status",
            color=await ctx.embed_colour()
        )
        
        description_lines = []
        for item_id, data in sorted(artifacts.items()):
            status = data.get("status", "Unknown")
            
            # MODIFIED: Display logic for three states
            if status == "Used":
                status_icon = "🔴"
                status_text = f"Used by **{data.get('used_by', 'Unknown')}**"
            elif status == "Available":
                status_icon = "🟢"
                status_text = "Available"
            else: # Unclaimed or other
                status_icon = "🟡"
                status_text = "Unclaimed"
            
            description_lines.append(f"{status_icon} **{data.get('name')}** (`{item_id}`): {status_text}")
            
        embed.description = "\n".join(description_lines)
        await ctx.send(embed=embed)
    
    @artifact.command(name="claim")
    async def artifact_claim(self, ctx: commands.Context, *, identifier: str):
        """
        Claims an 'Unclaimed' artifact, making it 'Available' to be used.
        """
        async with self.config.guild(ctx.guild).weekly_artifacts() as artifacts:
            found_id = None
            # Find the artifact by ID or name (case-insensitive)
            for item_id, data in artifacts.items():
                if identifier.upper() == item_id or identifier.lower() == data.get("name", "").lower():
                    found_id = item_id
                    break
            
            if not found_id:
                await ctx.send(f"❌ Could not find an artifact matching `{identifier}`.")
                return

            target_artifact = artifacts[found_id]
            current_status = target_artifact.get("status", "Unknown")

            # Check if the artifact is in the correct state to be claimed
            if current_status != "Unclaimed":
                if current_status == "Available":
                    await ctx.send(f"ℹ️ The **{target_artifact['name']}** is already `Available` and can be used.")
                elif current_status == "Used":
                    used_by = target_artifact.get('used_by', 'someone')
                    await ctx.send(f"❌ The **{target_artifact['name']}** has already been used this cycle by {used_by}.")
                else:
                    await ctx.send(f"❌ The **{target_artifact['name']}** cannot be claimed right now (Status: `{current_status}`).")
                return

            # Set the new status to Available
            target_artifact["status"] = "Available"
            
            await ctx.send(f"✅ You have claimed the **{target_artifact['name']}**. It is now `Available` to be used.")

    @artifact.command(name="use")
    async def artifact_use(self, ctx: commands.Context, *, arguments: str):
        """
        Use a weekly artifact, marking it as unavailable for the rest of the cycle.

        You can use the artifact's short ID or its full name.
        To use it for someone else, mention them at the end.
        Example: [p]artifact use DPF @User
        """
        parts = arguments.split()
        target_user = ctx.author
        identifier = arguments

        # Check if the last part is a user mention
        if parts:
            try:
                # Try to convert the last part to a member
                maybe_user = await commands.MemberConverter().convert(ctx, parts[-1])
                target_user = maybe_user
                # If successful, the identifier is the rest of the string
                identifier = " ".join(parts[:-1])
            except commands.MemberNotFound:
                # If it fails, the whole argument string is the identifier
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
            
            # MODIFIED: Check for the 'Available' status
            if target_artifact.get("status") != "Available":
                current_status = target_artifact.get("status", "Unknown")
                await ctx.send(f"❌ The **{target_artifact['name']}** is not available to be used. Its current status is: `{current_status}`.")
                return

            # Mark the artifact as Used
            target_artifact["status"] = "Used"
            target_artifact["used_by"] = target_user.display_name
            
            await ctx.send(f"✅ **{target_user.display_name}** has used the **{target_artifact['name']}** for this cycle.")
        
async def setup(bot: commands.Bot):
    await bot.add_cog(Custodian(bot))
