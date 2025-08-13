import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from collections import defaultdict

import discord
from aiohttp import web
from redbot.core import commands, Config, checks
from redbot.core.bot import Red

log = logging.getLogger("red.cogs.makialert")

class MakiAlert(commands.Cog):
    """Simple HTTP API for server alerts - sends DMs to Nero"""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        # Simplified configuration
        default_global = {
            "port": 8080,
            "host": "127.0.0.1",
            "enabled": True,  # Auto-enable
            "target_user_id": 178310000484024320,  # Nero's user ID
            "rate_limit": {"requests": 300, "window": 60},  # 300 requests per minute
            "audio_integration": True  # Monitor Audio cog for failures
        }
        
        self.config.register_global(**default_global)
        
        # Runtime state
        self.app = None
        self.runner = None
        self.site = None
        self.rate_limit_tracker = []  # Simple list of timestamps
        
    async def cog_load(self):
        """Called when the cog is loaded - auto-start server"""
        await self.start_server()
        
        # Set up Audio cog integration if enabled
        if await self.config.audio_integration():
            await self.setup_audio_integration()
    
    async def cog_unload(self):
        """Called when the cog is unloaded"""
        await self.stop_server()
        await self.cleanup_audio_integration()
    
    async def start_server(self):
        """Start the HTTP server"""
        try:
            self.app = web.Application()
            self.setup_routes()
            
            host = await self.config.host()
            port = await self.config.port()
            
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, host, port)
            await self.site.start()
            
            log.info(f"MakiAlert HTTP server started on {host}:{port}")
            
        except Exception as e:
            log.error(f"Failed to start MakiAlert HTTP server: {e}")
            await self.stop_server()
    
    async def stop_server(self):
        """Stop the HTTP server"""
        if self.site:
            await self.site.stop()
            self.site = None
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        self.app = None
        log.info("MakiAlert HTTP server stopped")
    
    def setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_post('/alert', self.handle_alert)
    
    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0"
        })
    
    async def validate_request(self, request) -> tuple[bool, Optional[str], Optional[dict]]:
        """Validate incoming request - simplified, no auth needed"""
        try:
            # Only allow localhost
            if request.remote not in ['127.0.0.1', '::1', 'localhost']:
                return False, "Only localhost requests allowed", None
            
            # Check content type for POST requests
            if request.method == 'POST':
                if request.content_type != 'application/json':
                    return False, "Content-Type must be application/json", None
                
                # Parse JSON
                try:
                    data = await request.json()
                except json.JSONDecodeError:
                    return False, "Invalid JSON payload", None
                
                # Check required fields
                if 'service' not in data or 'message' not in data:
                    return False, "Missing required fields: service, message", None
                
                # Simple rate limiting
                if not self.check_rate_limit():
                    return False, "Rate limit exceeded", None
                
                return True, None, data
            
            return True, None, None
            
        except Exception as e:
            log.error(f"Error validating request: {e}")
            return False, "Internal server error", None
    
    def check_rate_limit(self) -> bool:
        """Simple rate limiting"""
        try:
            current_time = time.time()
            
            # Clean old entries
            self.rate_limit_tracker = [
                timestamp for timestamp in self.rate_limit_tracker
                if current_time - timestamp < 60  # 60 second window
            ]
            
            # Check if we're over the limit (300 per minute)
            if len(self.rate_limit_tracker) >= 300:
                return False
            
            # Add this request
            self.rate_limit_tracker.append(current_time)
            return True
            
        except Exception as e:
            log.error(f"Error checking rate limit: {e}")
            return True  # Allow request if rate limit check fails
    
    async def handle_alert(self, request):
        """Handle alert endpoint"""
        valid, error, data = await self.validate_request(request)
        
        if not valid:
            return web.json_response(
                {"error": error}, 
                status=400 if error != "Internal server error" else 500
            )
        
        try:
            # Get alert level (default to info)
            level = data.get('level', 'info').lower()
            if level not in ['info', 'warning', 'error', 'critical', 'status']:
                level = 'info'
            
            # Send the alert
            await self.send_alert_dm(data, level)
            
            return web.json_response({
                "success": True,
                "message": "Alert sent successfully",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
        except Exception as e:
            log.error(f"Error processing alert: {e}")
            return web.json_response({"error": "Internal server error"}, status=500)
    
    async def send_alert_dm(self, data: dict, level: str):
        """Send alert directly to Nero via DM"""
        try:
            user_id = await self.config.target_user_id()
            user = self.bot.get_user(user_id)
            
            if not user:
                log.error(f"Target user {user_id} not found")
                return
            
            embed = self.format_alert_embed(data, level)
            await user.send(embed=embed)
            
        except Exception as e:
            log.error(f"Error sending alert DM: {e}")
    
    def format_alert_embed(self, data: dict, level: str) -> discord.Embed:
        """Format alert data into a Discord embed"""
        # Color and icon mapping
        colors = {
            'info': discord.Color.blue(),
            'status': discord.Color.green(),
            'warning': discord.Color.orange(),
            'error': discord.Color.red(),
            'critical': discord.Color.dark_red()
        }
        
        icons = {
            'info': 'ℹ️',
            'status': '✅',
            'warning': '⚠️',
            'error': '❌',
            'critical': '🚨'
        }
        
        # Create embed
        embed = discord.Embed(
            title=f"{icons.get(level, '📢')} {level.upper()}: {data['service']}",
            description=data['message'],
            color=colors.get(level, discord.Color.default()),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Add details if provided
        if 'details' in data and data['details']:
            embed.add_field(name="Details", value=data['details'], inline=False)
        
        # Add tags if provided
        if 'tags' in data and data['tags']:
            tags_str = ', '.join(f"`{tag}`" for tag in data['tags'])
            embed.add_field(name="Tags", value=tags_str, inline=False)
        
        # Add hostname for context
        import socket
        embed.set_footer(text=f"From: {socket.gethostname()}")
        
        return embed
    
    # Internal bot integration methods
    
    async def send_internal_alert(self, service: str, message: str, level: str = "error", details: str = None, tags: list = None):
        """Method for other cogs to send alerts directly"""
        try:
            data = {
                "service": service,
                "message": message,
                "level": level
            }
            
            if details:
                data["details"] = details
            if tags:
                data["tags"] = tags
                
            await self.send_alert_dm(data, level)
            log.info(f"Internal alert sent: {service} - {message}")
            
        except Exception as e:
            log.error(f"Failed to send internal alert: {e}")
    
    # Audio Cog Integration
    
    async def setup_audio_integration(self):
        """Set up Audio cog event listeners"""
        try:
            # Hook into Red-Bot's event system to listen for Audio cog events
            self.bot.add_listener(self.on_lavalink_track_load_failed, "on_lavalink_track_load_failed")
            self.bot.add_listener(self.on_lavalink_track_exception, "on_lavalink_track_exception")
            self.bot.add_listener(self.on_lavalink_node_disconnect, "on_lavalink_node_disconnect")
            log.info("Audio cog integration enabled")
        except Exception as e:
            log.error(f"Failed to setup audio integration: {e}")
    
    async def cleanup_audio_integration(self):
        """Clean up Audio cog event listeners"""
        try:
            self.bot.remove_listener(self.on_lavalink_track_load_failed, "on_lavalink_track_load_failed")
            self.bot.remove_listener(self.on_lavalink_track_exception, "on_lavalink_track_exception")
            self.bot.remove_listener(self.on_lavalink_node_disconnect, "on_lavalink_node_disconnect")
            log.info("Audio cog integration disabled")
        except Exception as e:
            log.error(f"Failed to cleanup audio integration: {e}")
    
    async def on_lavalink_track_load_failed(self, player, track, reason):
        """Handle Lavalink track load failures"""
        if not await self.config.audio_integration():
            return
            
        try:
            # Extract info about the failed track
            track_title = getattr(track, 'title', 'Unknown')
            track_uri = getattr(track, 'uri', 'Unknown')
            
            await self.send_internal_alert(
                service="audio-system",
                message="Failed to load audio track",
                level="error",
                details=f"Track: {track_title}\nURI: {track_uri}\nReason: {reason}",
                tags=["audio", "lavalink", "track-load"]
            )
        except Exception as e:
            log.error(f"Error handling track load failure: {e}")
    
    async def on_lavalink_track_exception(self, player, track, exception):
        """Handle Lavalink track exceptions during playback"""
        if not await self.config.audio_integration():
            return
            
        try:
            track_title = getattr(track, 'title', 'Unknown')
            track_uri = getattr(track, 'uri', 'Unknown')
            exception_msg = getattr(exception, 'message', str(exception))
            
            # Determine if this is a YouTube-specific error
            is_youtube = 'youtube' in track_uri.lower() or 'youtu.be' in track_uri.lower()
            tags = ["audio", "lavalink", "playback-error"]
            if is_youtube:
                tags.append("youtube")
            
            await self.send_internal_alert(
                service="audio-system",
                message="Audio track exception during playback",
                level="warning",
                details=f"Track: {track_title}\nURI: {track_uri}\nException: {exception_msg}",
                tags=tags
            )
        except Exception as e:
            log.error(f"Error handling track exception: {e}")
    
    async def on_lavalink_node_disconnect(self, node):
        """Handle Lavalink node disconnections"""
        if not await self.config.audio_integration():
            return
            
        try:
            node_name = getattr(node, 'name', 'Unknown')
            node_uri = getattr(node, 'uri', 'Unknown')
            
            await self.send_internal_alert(
                service="lavalink",
                message="Lavalink node disconnected",
                level="critical",
                details=f"Node: {node_name}\nURI: {node_uri}",
                tags=["audio", "lavalink", "connection"]
            )
        except Exception as e:
            log.error(f"Error handling node disconnect: {e}")
    
    # Simple admin commands
    
    @commands.group(name="makialert")
    @checks.is_owner()
    async def makialert(self, ctx):
        """MakiAlert admin commands"""
        pass
    
    @makialert.command(name="status")
    async def server_status(self, ctx):
        """Show server status"""
        enabled = await self.config.enabled()
        host = await self.config.host()
        port = await self.config.port()
        target_user = self.bot.get_user(await self.config.target_user_id())
        audio_integration = await self.config.audio_integration()
        
        embed = discord.Embed(
            title="MakiAlert Status",
            color=discord.Color.green() if enabled else discord.Color.red()
        )
        
        embed.add_field(name="HTTP Server", value="🟢 Running" if self.site else "🔴 Stopped", inline=True)
        embed.add_field(name="Endpoint", value=f"`{host}:{port}/alert`", inline=True)
        embed.add_field(name="Target User", value=target_user.mention if target_user else "Not found", inline=True)
        embed.add_field(name="Recent Requests", value=str(len(self.rate_limit_tracker)), inline=True)
        embed.add_field(name="Audio Integration", value="🟢 Enabled" if audio_integration else "🔴 Disabled", inline=True)
        
        # Check if Audio cog is loaded
        audio_cog = self.bot.get_cog("Audio")
        embed.add_field(name="Audio Cog", value="🟢 Loaded" if audio_cog else "🔴 Not Loaded", inline=True)
        
        await ctx.send(embed=embed)
    
    @makialert.command(name="test")
    async def test_alert(self, ctx):
        """Send a test alert"""
        test_data = {
            "service": "makialert-test",
            "message": "Test alert from Discord command",
            "level": "info",
            "details": "This is a test to verify the alert system is working"
        }
        
        await self.send_alert_dm(test_data, "info")
        await ctx.send("✅ Test alert sent!")
    
    @makialert.command(name="restart")
    async def restart_server(self, ctx):
        """Restart the HTTP server"""
        await self.stop_server()
        await asyncio.sleep(1)
        await self.start_server()
        await ctx.send("✅ MakiAlert server restarted!")
    
    @makialert.command(name="audio")
    async def toggle_audio_integration(self, ctx, enabled: bool = None):
        """Toggle Audio cog integration on/off"""
        if enabled is None:
            current = await self.config.audio_integration()
            await ctx.send(f"Audio integration is currently: {'**Enabled**' if current else '**Disabled**'}")
            return
        
        await self.config.audio_integration.set(enabled)
        
        if enabled:
            await self.setup_audio_integration()
            await ctx.send("✅ Audio integration **enabled** - will monitor for YouTube/Lavalink failures")
        else:
            await self.cleanup_audio_integration()
            await ctx.send("❌ Audio integration **disabled** - will not monitor Audio cog")