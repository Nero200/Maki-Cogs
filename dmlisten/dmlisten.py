import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

log = logging.getLogger("red.cogs.dmlisten")


class DMListen(commands.Cog):
    """Logs and forwards DMs with bidirectional reply capability"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567891, force_registration=True)

        # Configuration
        default_global = {
            "owner_id": 178310000484024320,  # Nero's user ID
            "log_file": "dm_logs.txt",
            "enabled": True,
        }

        self.config.register_global(**default_global)

        # Runtime state: Maps forwarded message ID -> original sender ID
        # This allows us to track which forwarded message corresponds to which sender
        self.forward_map: Dict[int, int] = {}

        # Reverse map: original sender ID -> last forwarded message ID
        # This helps us find the conversation thread
        self.sender_map: Dict[int, int] = {}

    async def cog_load(self):
        """Called when the cog is loaded"""
        log.info("DMListen cog loaded - DM monitoring active")

    def _get_log_path(self) -> Path:
        """Get the path to the log file"""
        # Store logs in the cog's data directory
        data_path = Path.cwd() / "maki" / "cogs" / "DMListen"
        data_path.mkdir(parents=True, exist_ok=True)
        return data_path / "dm_logs.txt"

    async def _log_dm(self, message: discord.Message):
        """Log a DM to the text file"""
        try:
            log_path = self._get_log_path()

            # Format the log entry
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            separator = "=" * 80

            log_entry_parts = [
                f"\n{separator}",
                f"Timestamp: {timestamp}",
                f"User: {message.author} ({message.author.id})",
                f"Username: {message.author.name}",
                f"Display Name: {message.author.display_name}",
                f"Message ID: {message.id}",
            ]

            # Add message content
            if message.content:
                log_entry_parts.append(f"\nContent:\n{message.content}")
            else:
                log_entry_parts.append("\nContent: [No text content]")

            # Add attachment information
            if message.attachments:
                log_entry_parts.append(f"\nAttachments ({len(message.attachments)}):")
                for i, attachment in enumerate(message.attachments, 1):
                    log_entry_parts.append(
                        f"  {i}. {attachment.filename} ({attachment.content_type}) - {attachment.url}"
                    )

            # Add embed information
            if message.embeds:
                log_entry_parts.append(f"\nEmbeds ({len(message.embeds)}):")
                for i, embed in enumerate(message.embeds, 1):
                    embed_info = []
                    if embed.title:
                        embed_info.append(f"Title: {embed.title}")
                    if embed.description:
                        embed_info.append(f"Description: {embed.description}")
                    if embed.url:
                        embed_info.append(f"URL: {embed.url}")
                    if embed.fields:
                        embed_info.append(f"Fields: {len(embed.fields)}")
                    log_entry_parts.append(f"  {i}. {' | '.join(embed_info)}")

            log_entry_parts.append(separator)

            # Write to file
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n".join(log_entry_parts) + "\n")

            log.debug(f"Logged DM from {message.author} ({message.author.id})")

        except Exception as e:
            log.error(f"Failed to log DM: {e}", exc_info=True)

    async def _forward_dm(self, message: discord.Message) -> Optional[discord.Message]:
        """Forward a DM to the owner and return the forwarded message"""
        try:
            owner_id = await self.config.owner_id()
            owner = self.bot.get_user(owner_id)

            if not owner:
                log.error(f"Owner user {owner_id} not found")
                return None

            # Create embed with DM details
            embed = discord.Embed(
                title=f"DM from {message.author}",
                description=message.content if message.content else "*[No text content]*",
                color=discord.Color.blue(),
                timestamp=message.created_at
            )

            # Add user information
            embed.set_author(
                name=f"{message.author.name} ({message.author.id})",
                icon_url=message.author.display_avatar.url
            )

            # Add user details field
            user_info = [
                f"**Username:** {message.author.name}",
                f"**Display Name:** {message.author.display_name}",
                f"**User ID:** {message.author.id}",
                f"**Created:** {message.author.created_at.strftime('%Y-%m-%d')}",
            ]
            embed.add_field(name="User Details", value="\n".join(user_info), inline=False)

            # Add attachment information
            if message.attachments:
                attachment_info = []
                for i, attachment in enumerate(message.attachments, 1):
                    attachment_info.append(
                        f"[{i}. {attachment.filename}]({attachment.url})"
                    )
                embed.add_field(
                    name=f"Attachments ({len(message.attachments)})",
                    value="\n".join(attachment_info),
                    inline=False
                )

            # Add embed information
            if message.embeds:
                embed_info = []
                for i, msg_embed in enumerate(message.embeds, 1):
                    embed_parts = []
                    if msg_embed.title:
                        embed_parts.append(f"Title: {msg_embed.title}")
                    if msg_embed.description:
                        desc_preview = msg_embed.description[:100]
                        if len(msg_embed.description) > 100:
                            desc_preview += "..."
                        embed_parts.append(f"Description: {desc_preview}")
                    embed_info.append(f"{i}. {' | '.join(embed_parts)}")
                embed.add_field(
                    name=f"Embeds ({len(message.embeds)})",
                    value="\n".join(embed_info),
                    inline=False
                )

            embed.set_footer(text=f"Message ID: {message.id} | Reply to this message to respond")

            # Send to owner
            forwarded_msg = await owner.send(embed=embed)

            # Store the mapping
            self.forward_map[forwarded_msg.id] = message.author.id
            self.sender_map[message.author.id] = forwarded_msg.id

            log.info(f"Forwarded DM from {message.author} ({message.author.id}) to owner")
            return forwarded_msg

        except Exception as e:
            log.error(f"Failed to forward DM: {e}", exc_info=True)
            return None

    async def _handle_owner_reply(self, message: discord.Message):
        """Handle when the owner replies to a forwarded DM"""
        try:
            # Check if this is a reply
            if not message.reference or not message.reference.message_id:
                return

            # Check if the reply is to a message we forwarded
            replied_to_id = message.reference.message_id
            if replied_to_id not in self.forward_map:
                return

            # Get the original sender
            original_sender_id = self.forward_map[replied_to_id]
            original_sender = self.bot.get_user(original_sender_id)

            if not original_sender:
                log.error(f"Original sender {original_sender_id} not found")
                await message.add_reaction("")
                return

            # Send the reply to the original sender as a plain message
            reply_content = message.content if message.content else ""

            # If there are attachments, include their URLs in the message
            if message.attachments:
                attachment_urls = [attachment.url for attachment in message.attachments]
                if reply_content:
                    reply_content += "\n\n" + "\n".join(attachment_urls)
                else:
                    reply_content = "\n".join(attachment_urls)

            # Send as plain text (or just attachments if no text)
            if reply_content:
                await original_sender.send(reply_content)
            else:
                # No content at all (shouldn't happen, but just in case)
                await original_sender.send("*[Empty reply]*")

            # React to confirm
            await message.add_reaction("✅")

            log.info(f"Sent reply from owner to {original_sender} ({original_sender_id})")

        except Exception as e:
            log.error(f"Failed to handle owner reply: {e}", exc_info=True)
            try:
                await message.add_reaction("❌")
            except:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for DMs and owner replies"""
        # Ignore messages from the bot itself
        if message.author.bot:
            return

        # Check if enabled
        if not await self.config.enabled():
            return

        owner_id = await self.config.owner_id()

        # Handle DMs to the bot (not from the owner)
        if isinstance(message.channel, discord.DMChannel) and message.author.id != owner_id:
            # Log the DM
            await self._log_dm(message)

            # Forward to owner
            await self._forward_dm(message)

        # Handle DMs from the owner (potential replies)
        elif isinstance(message.channel, discord.DMChannel) and message.author.id == owner_id:
            await self._handle_owner_reply(message)

    # Admin commands

    @commands.group(name="dmlisten")
    @checks.is_owner()
    async def dmlisten(self, ctx):
        """DMListen DM logging and forwarding commands"""
        pass

    @dmlisten.command(name="status")
    async def status(self, ctx):
        """Show DMListen status and statistics"""
        enabled = await self.config.enabled()
        owner_id = await self.config.owner_id()
        owner = self.bot.get_user(owner_id)
        log_path = self._get_log_path()

        embed = discord.Embed(
            title="DMListen Status",
            color=discord.Color.green() if enabled else discord.Color.red()
        )

        embed.add_field(
            name="Status",
            value="🟢 Monitoring" if enabled else "🔴 Disabled",
            inline=True
        )
        embed.add_field(
            name="Owner",
            value=owner.mention if owner else f"ID: {owner_id}",
            inline=True
        )
        embed.add_field(
            name="Active Conversations",
            value=str(len(self.sender_map)),
            inline=True
        )
        embed.add_field(
            name="Log File",
            value=f"`{log_path.name}`",
            inline=True
        )

        # Get log file size if it exists
        if log_path.exists():
            size_kb = log_path.stat().st_size / 1024
            embed.add_field(
                name="Log Size",
                value=f"{size_kb:.2f} KB",
                inline=True
            )

        await ctx.send(embed=embed)

    @dmlisten.command(name="toggle")
    async def toggle(self, ctx, enabled: bool = None):
        """Enable or disable DM monitoring"""
        if enabled is None:
            current = await self.config.enabled()
            await ctx.send(f"DM monitoring is currently: {'**Enabled**' if current else '**Disabled**'}")
            return

        await self.config.enabled.set(enabled)

        if enabled:
            await ctx.send("✅ DMListen **enabled** - Now monitoring and forwarding DMs")
        else:
            await ctx.send("❌ DMListen **disabled** - DM monitoring stopped")

    @dmlisten.command(name="clear")
    async def clear_mappings(self, ctx):
        """Clear the message mapping cache"""
        count = len(self.forward_map)
        self.forward_map.clear()
        self.sender_map.clear()
        await ctx.send(f"✅ Cleared {count} message mappings from cache")

    @dmlisten.command(name="viewlog")
    async def view_log(self, ctx, lines: int = 50):
        """View the last N lines of the DM log file"""
        log_path = self._get_log_path()

        if not log_path.exists():
            await ctx.send("No log file found yet.")
            return

        try:
            # Read the last N lines
            with open(log_path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
                last_lines = all_lines[-lines:]
                content = "".join(last_lines)

            # Split into chunks if too long
            if len(content) > 1900:
                # Send as file
                await ctx.send(
                    f"Log is too long to display ({len(content)} chars). Sending as file...",
                    file=discord.File(log_path, filename="dm_logs.txt")
                )
            else:
                await ctx.send(f"```\n{content}\n```")

        except Exception as e:
            await ctx.send(f"❌ Error reading log file: {e}")
