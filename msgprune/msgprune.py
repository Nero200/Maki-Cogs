import asyncio
import discord
from redbot.core import commands
from redbot.core.bot import Red


class MsgPrune(commands.Cog):
    """Delete bot messages in DMs by reacting with ❌"""

    def __init__(self, bot: Red):
        self.bot = bot

    @commands.command()
    async def cleardms(self, ctx: commands.Context, limit: int = 1000):
        """Delete bot messages in this DM conversation
        
        Args:
            limit: Maximum number of messages to scan (default: 1000, max: 5000)
        """
        
        # Check if command is used in DMs
        if not isinstance(ctx.channel, discord.DMChannel):
            await ctx.send("This command can only be used in DMs.")
            return
        
        # Check if the user is the DM recipient (not the bot)
        if ctx.author == self.bot.user:
            return
        
        # Validate and cap the limit
        if limit > 5000:
            limit = 5000
        elif limit < 1:
            limit = 1000
        
        try:
            # Send initial status message
            status_msg = await ctx.send(f"Scanning last {limit} messages for bot messages...")
            
            # Process messages in chunks to avoid memory issues
            chunk_size = 100
            bot_messages = []
            scanned_count = 0
            
            async for message in ctx.channel.history(limit=limit):
                scanned_count += 1
                if message.author == self.bot.user and message.id != status_msg.id:
                    bot_messages.append(message)
                
                # Update progress every chunk
                if scanned_count % chunk_size == 0:
                    await status_msg.edit(content=f"Scanning... {scanned_count}/{limit} (found {len(bot_messages)} bot messages)")
                    await asyncio.sleep(0.1)  # Brief pause to avoid rate limits
            
            if not bot_messages:
                await status_msg.edit(content=f"No bot messages found in the last {limit} messages.")
                return
            
            await status_msg.edit(content=f"Found {len(bot_messages)} bot messages. Starting deletion...")
            
            # Delete messages with rate limiting
            deleted_count = 0
            total_messages = len(bot_messages)
            
            for i, message in enumerate(bot_messages):
                try:
                    await message.delete()
                    deleted_count += 1
                    
                    # Update progress every 5 deletions or at the end
                    if deleted_count % 5 == 0 or deleted_count == total_messages:
                        await status_msg.edit(content=f"Deleting... {deleted_count}/{total_messages}")
                    
                    # Rate limiting: 0.5s between deletions
                    if i < total_messages - 1:  # Don't sleep after the last message
                        await asyncio.sleep(0.5)
                        
                except discord.NotFound:
                    # Message was already deleted
                    pass
                except discord.Forbidden:
                    # Bot doesn't have permission to delete the message
                    pass
                except discord.HTTPException:
                    # Other Discord API error, continue with next message
                    pass
            
            # Send final confirmation
            if deleted_count > 0:
                await status_msg.edit(content=f"✅ Deleted {deleted_count} bot messages from this DM.")
            else:
                await status_msg.edit(content="❌ No messages could be deleted.")
                
        except discord.HTTPException:
            await ctx.send("An error occurred while clearing messages.")

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member | discord.User):
        """Listen for ❌ reactions and delete bot messages in DMs"""
        
        # Check if reaction is ❌
        if str(reaction.emoji) != "❌":
            return
        
        # Check if it's in a DM
        if not isinstance(reaction.message.channel, discord.DMChannel):
            return
        
        # Check if the message author is the bot
        if reaction.message.author != self.bot.user:
            return
        
        # Check if the user reacting is the DM recipient (not the bot)
        if user == self.bot.user:
            return
        
        try:
            # Delete the bot's message
            await reaction.message.delete()
        except discord.NotFound:
            # Message was already deleted
            pass
        except discord.Forbidden:
            # Bot doesn't have permission to delete the message
            pass
        except discord.HTTPException:
            # Other Discord API error
            pass


async def setup(bot: Red):
    """Load the MsgPrune cog"""
    await bot.add_cog(MsgPrune(bot))