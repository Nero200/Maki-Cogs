"""
Audio Cog Integration for MakiAlert

This file provides hooks to integrate MakiAlert with the Audio cog
to send alerts when YouTube videos fail to load.

Usage:
1. Add this import to your Audio cog: from cuscogs.makialert.audio_integration import send_audio_alert
2. Call send_audio_alert(bot, error_type, details) when errors occur
"""

import logging

log = logging.getLogger("red.cogs.audio_integration")

async def send_audio_alert(bot, error_type: str, details: str, track_info: dict = None):
    """
    Send an audio-related alert via MakiAlert cog
    
    Args:
        bot: The Red bot instance
        error_type: Type of error (e.g., "youtube_load_failed", "track_not_found", "playlist_error")
        details: Detailed error message
        track_info: Optional track information dict with keys like 'title', 'url', 'requester'
    """
    try:
        # Get MakiAlert cog
        makialert_cog = bot.get_cog("MakiAlert")
        if not makialert_cog:
            log.warning("MakiAlert cog not loaded, cannot send audio alert")
            return
        
        # Format message based on error type
        service = "audio-system"
        level = "error"
        tags = ["audio", "media"]
        
        if error_type == "youtube_load_failed":
            message = "Failed to load YouTube video"
            tags.append("youtube")
        elif error_type == "track_not_found":
            message = "Track not found or unavailable"
            level = "warning"
        elif error_type == "playlist_error":
            message = "Playlist processing error"
            tags.append("playlist")
        elif error_type == "lavalink_error":
            message = "Lavalink connection error"
            level = "critical"
            tags.append("lavalink")
        else:
            message = f"Audio system error: {error_type}"
        
        # Add track info to details if provided
        full_details = details
        if track_info:
            track_details = []
            if 'title' in track_info:
                track_details.append(f"Title: {track_info['title']}")
            if 'url' in track_info:
                track_details.append(f"URL: {track_info['url']}")
            if 'requester' in track_info:
                track_details.append(f"Requested by: {track_info['requester']}")
            
            if track_details:
                full_details = f"{details}\n\n" + "\n".join(track_details)
        
        # Send the alert
        await makialert_cog.send_internal_alert(
            service=service,
            message=message,
            level=level,
            details=full_details,
            tags=tags
        )
        
    except Exception as e:
        log.error(f"Failed to send audio alert: {e}")

# Convenience functions for common audio errors

async def youtube_load_failed(bot, url: str, error_msg: str, requester: str = None):
    """Quick function for YouTube load failures"""
    track_info = {"url": url}
    if requester:
        track_info["requester"] = requester
    
    await send_audio_alert(
        bot, 
        "youtube_load_failed", 
        f"YouTube video failed to load: {error_msg}",
        track_info
    )

async def lavalink_connection_error(bot, error_msg: str):
    """Quick function for Lavalink connection errors"""
    await send_audio_alert(
        bot,
        "lavalink_error",
        f"Lavalink connection issue: {error_msg}"
    )

async def playlist_processing_error(bot, playlist_url: str, error_msg: str):
    """Quick function for playlist errors"""
    await send_audio_alert(
        bot,
        "playlist_error", 
        f"Failed to process playlist: {error_msg}",
        {"url": playlist_url}
    )

# Example integration code for Audio cog developers:
"""
# Add this to your Audio cog imports:
try:
    from cuscogs.makialert.audio_integration import youtube_load_failed
    MAKIALERT_AVAILABLE = True
except ImportError:
    MAKIALERT_AVAILABLE = False

# Then in your error handling code:
if MAKIALERT_AVAILABLE:
    await youtube_load_failed(self.bot, track_url, str(error), requester_name)

# Or for more complex alerts:
if MAKIALERT_AVAILABLE:
    from cuscogs.makialert.audio_integration import send_audio_alert
    await send_audio_alert(
        self.bot,
        "custom_error_type",
        "Detailed error message",
        {"title": track_title, "url": track_url, "requester": user.name}
    )
"""