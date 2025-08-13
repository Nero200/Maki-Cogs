import asyncio
import logging
import io
import wave
import numpy as np
from typing import Optional, Dict, List
from collections import defaultdict

import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

# Speech recognition imports
try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False

# Wake word detection imports  
try:
    import openwakeword
    from openwakeword.model import Model
    WAKE_WORD_AVAILABLE = True
except ImportError:
    WAKE_WORD_AVAILABLE = False

log = logging.getLogger("red.cogs.voicecommands")

class VoiceCommands(commands.Cog):
    """Voice command control for Discord audio playback"""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567891, force_registration=True)
        
        # Configuration defaults
        default_global = {
            "enabled": False,
            "wake_words": ["hey maki", "maki"],
            "confidence_threshold": 0.7,
            "recording_timeout": 3,
            "commands": {
                "pause": ["pause", "stop playing", "halt"],
                "resume": ["resume", "continue", "play"],
                "stop": ["stop", "end", "quit"],
                "disconnect": ["disconnect", "leave", "bye"]
            }
        }
        
        default_guild = {
            "enabled": True,
            "allowed_channels": [],  # Empty means all channels
            "allowed_roles": [],     # Empty means all roles
        }
        
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        
        # Runtime state
        self.listening_sessions: Dict[int, bool] = defaultdict(bool)  # guild_id -> is_listening
        self.wake_word_model: Optional[Model] = None
        self.speech_recognizer: Optional[sr.Recognizer] = None
        
        # Check dependencies
        self.dependencies_ok = SPEECH_RECOGNITION_AVAILABLE and WAKE_WORD_AVAILABLE
        
    async def cog_load(self):
        """Initialize the cog"""
        if not self.dependencies_ok:
            log.error("VoiceCommands: Missing dependencies. Install with: pip install py-cord SpeechRecognition openwakeword numpy librosa")
            return
            
        try:
            # Initialize speech recognition
            self.speech_recognizer = sr.Recognizer()
            
            # Initialize wake word detection
            self.wake_word_model = Model()
            
            log.info("VoiceCommands: Successfully initialized speech recognition and wake word detection")
            
        except Exception as e:
            log.error(f"VoiceCommands: Failed to initialize: {e}")
            self.dependencies_ok = False
    
    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        # Stop any active listening sessions
        for guild_id in list(self.listening_sessions.keys()):
            self.listening_sessions[guild_id] = False
    
    @commands.group(name="voicecommands", aliases=["vc"])
    async def voicecommands(self, ctx: commands.Context):
        """Voice command configuration and control"""
        if not ctx.invoked_subcommand:
            embed = await self._create_status_embed(ctx.guild)
            await ctx.send(embed=embed)
    
    @voicecommands.command(name="enable")
    @checks.admin_or_permissions(manage_guild=True)
    async def enable_voice_commands(self, ctx: commands.Context):
        """Enable voice commands for this server"""
        if not self.dependencies_ok:
            await ctx.send("❌ Voice commands require additional dependencies. Please install: py-cord, SpeechRecognition, openwakeword")
            return
            
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("✅ Voice commands enabled for this server!")
    
    @voicecommands.command(name="disable")
    @checks.admin_or_permissions(manage_guild=True)
    async def disable_voice_commands(self, ctx: commands.Context):
        """Disable voice commands for this server"""
        await self.config.guild(ctx.guild).enabled.set(False)
        # Stop listening if currently active
        self.listening_sessions[ctx.guild.id] = False
        await ctx.send("❌ Voice commands disabled for this server.")
    
    @voicecommands.command(name="start")
    async def start_listening(self, ctx: commands.Context):
        """Start listening for voice commands in your current voice channel"""
        if not self.dependencies_ok:
            await ctx.send("❌ Voice commands require additional dependencies.")
            return
            
        # Check if voice commands are enabled
        if not await self.config.guild(ctx.guild).enabled():
            await ctx.send("❌ Voice commands are disabled for this server. Use `voicecommands enable` to enable them.")
            return
            
        # Check if user is in a voice channel
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("❌ You must be in a voice channel to start voice commands.")
            return
            
        voice_channel = ctx.author.voice.channel
        
        # Check if bot is already in a voice channel
        if ctx.guild.voice_client:
            if ctx.guild.voice_client.channel != voice_channel:
                await ctx.send(f"❌ I'm already connected to {ctx.guild.voice_client.channel.mention}. Move me to your channel first.")
                return
        else:
            # Connect to voice channel
            try:
                await voice_channel.connect()
                await ctx.send(f"🔊 Connected to {voice_channel.mention}")
            except Exception as e:
                await ctx.send(f"❌ Failed to connect to voice channel: {e}")
                return
        
        # Start listening session
        self.listening_sessions[ctx.guild.id] = True
        await ctx.send("🎤 Voice commands are now active! Say 'Hey Maki' followed by a command (pause, resume, stop, disconnect).")
        
        # Start the listening task
        asyncio.create_task(self._voice_listening_task(ctx.guild, voice_channel))
    
    @voicecommands.command(name="stop")
    async def stop_listening(self, ctx: commands.Context):
        """Stop listening for voice commands"""
        self.listening_sessions[ctx.guild.id] = False
        await ctx.send("🔇 Voice command listening stopped.")
    
    async def _voice_listening_task(self, guild: discord.Guild, channel: discord.VoiceChannel):
        """Main voice listening loop for a guild"""
        log.info(f"Started voice listening task for guild {guild.id}")
        
        try:
            voice_client = guild.voice_client
            if not voice_client:
                return
                
            # This is where we would implement the actual voice recording
            # For now, this is a placeholder that shows the structure
            while self.listening_sessions[guild.id]:
                try:
                    # In a real implementation, this would:
                    # 1. Record audio from the voice channel
                    # 2. Check for wake word using self.wake_word_model
                    # 3. If wake word detected, record the command
                    # 4. Process the command using self.speech_recognizer
                    # 5. Execute the appropriate audio command
                    
                    # For now, just sleep to prevent busy loop
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    log.error(f"Error in voice listening loop: {e}")
                    await asyncio.sleep(1)
                    
        except Exception as e:
            log.error(f"Voice listening task failed for guild {guild.id}: {e}")
        finally:
            self.listening_sessions[guild.id] = False
            log.info(f"Voice listening task ended for guild {guild.id}")
    
    async def _process_voice_command(self, guild: discord.Guild, command_text: str):
        """Process a recognized voice command"""
        command_text = command_text.lower().strip()
        
        # Get Audio cog
        audio_cog = self.bot.get_cog("Audio")
        if not audio_cog:
            log.warning("Audio cog not found, cannot execute voice command")
            return
        
        # Get command mappings
        commands_config = await self.config.commands()
        
        try:
            # Check for pause commands
            if any(cmd in command_text for cmd in commands_config["pause"]):
                # Call Audio cog's pause method
                # This would need to be adapted based on the actual Audio cog API
                log.info(f"Voice command: pause requested in guild {guild.id}")
                
            # Check for resume commands  
            elif any(cmd in command_text for cmd in commands_config["resume"]):
                log.info(f"Voice command: resume requested in guild {guild.id}")
                
            # Check for stop commands
            elif any(cmd in command_text for cmd in commands_config["stop"]):
                log.info(f"Voice command: stop requested in guild {guild.id}")
                
            # Check for disconnect commands
            elif any(cmd in command_text for cmd in commands_config["disconnect"]):
                if guild.voice_client:
                    await guild.voice_client.disconnect()
                    self.listening_sessions[guild.id] = False
                    log.info(f"Voice command: disconnected from guild {guild.id}")
            
            else:
                log.info(f"Voice command not recognized: '{command_text}' in guild {guild.id}")
                
        except Exception as e:
            log.error(f"Error processing voice command '{command_text}': {e}")
    
    async def _create_status_embed(self, guild: discord.Guild) -> discord.Embed:
        """Create status embed for voice commands"""
        embed = discord.Embed(
            title="🎤 Voice Commands Status",
            color=discord.Color.blue()
        )
        
        # Dependency status
        deps_status = "🟢 Ready" if self.dependencies_ok else "🔴 Missing Dependencies"
        embed.add_field(name="Dependencies", value=deps_status, inline=True)
        
        # Guild enabled status
        guild_enabled = await self.config.guild(guild).enabled()
        guild_status = "🟢 Enabled" if guild_enabled else "🔴 Disabled"
        embed.add_field(name="Server Status", value=guild_status, inline=True)
        
        # Listening status
        is_listening = self.listening_sessions.get(guild.id, False)
        listening_status = "🟢 Active" if is_listening else "🔴 Inactive"
        embed.add_field(name="Voice Listening", value=listening_status, inline=True)
        
        # Voice connection status
        voice_status = "🟢 Connected" if guild.voice_client else "🔴 Not Connected"
        embed.add_field(name="Voice Connection", value=voice_status, inline=True)
        
        # Audio cog status
        audio_cog = self.bot.get_cog("Audio")
        audio_status = "🟢 Loaded" if audio_cog else "🔴 Not Loaded"
        embed.add_field(name="Audio Cog", value=audio_status, inline=True)
        
        # Wake words
        wake_words = await self.config.wake_words()
        embed.add_field(name="Wake Words", value=", ".join(f"'{w}'" for w in wake_words), inline=False)
        
        # Available commands
        commands_config = await self.config.commands()
        cmd_text = []
        for action, words in commands_config.items():
            cmd_text.append(f"**{action}**: {', '.join(words)}")
        
        embed.add_field(name="Available Commands", value="\n".join(cmd_text), inline=False)
        
        if not self.dependencies_ok:
            embed.add_field(
                name="⚠️ Setup Required",
                value="Install dependencies: `pip install py-cord SpeechRecognition openwakeword numpy librosa`",
                inline=False
            )
        
        embed.set_footer(text="Use 'voicecommands start' to begin listening for voice commands")
        
        return embed
    
    @voicecommands.command(name="test")
    async def test_dependencies(self, ctx: commands.Context):
        """Test voice command dependencies"""
        embed = discord.Embed(title="🧪 Dependency Test", color=discord.Color.orange())
        
        # Test speech recognition
        sr_status = "✅ Available" if SPEECH_RECOGNITION_AVAILABLE else "❌ Not Available"
        embed.add_field(name="SpeechRecognition", value=sr_status, inline=True)
        
        # Test wake word detection
        ww_status = "✅ Available" if WAKE_WORD_AVAILABLE else "❌ Not Available"
        embed.add_field(name="OpenWakeWord", value=ww_status, inline=True)
        
        # Test overall status
        overall_status = "✅ Ready" if self.dependencies_ok else "❌ Dependencies Missing"
        embed.add_field(name="Overall Status", value=overall_status, inline=True)
        
        if not self.dependencies_ok:
            embed.add_field(
                name="Installation Command",
                value="```\npip install py-cord SpeechRecognition openwakeword numpy librosa\n```",
                inline=False
            )
        
        await ctx.send(embed=embed)