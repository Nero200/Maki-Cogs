# Maki Custom Cogs

A collection of custom cogs for Red-Bot Discord bots, developed for enhanced functionality and gaming features.

## Cogs

### ChimeraDice
An advanced dice rolling cog with luck and karma mechanics for tabletop RPG games.
- **Features**: Statistical tracking, karma system, luck mechanics, comprehensive dice notation support
- **Requirements**: `d20` library
- **Commands**: Use `[p]help dice` for available commands
- **Tags**: dice, fun, games, rpg, ttrpg, roll

### Custodian **DEPRECATED**
Designed for a PbP game to help with resource and traversal mechanic tracking. 
**Note**: This cog is deprecated due to end of game and is no longer maintained.
- **Features**: Resource tracking, weekly resets, breach management, cycle automation
- **Commands**: Use `[p]help Custodian` for available commands
- **Tags**: tracking, utility, game, resource management

### MsgPrune
Advanced message pruning utility for Discord Bot DMs
- **Features**: Bulk message deletion with filtering options
- **Commands**: Use `[p]help msgprune` for available commands
- **Tags**: moderation, utility, cleanup

### DMListen
DM logging and forwarding system with bidirectional reply capability.
- **Features**: Automatic DM logging to text file, forwards all DMs to owner, reply to forwarded messages to respond to sender, detailed logging with timestamps/user info/attachments/embeds
- **Requirements**: No additional dependencies
- **Commands**: Use `[p]help dmlisten` for available commands
- **Tags**: dm, logging, forwarding, modmail, utility
- **Note**: Reply to forwarded DM messages using Discord's reply feature to send responses back to the original sender

### PerfectTTT
Interactive tic-tac-toe game implementation for Discord with perfect play.
- **Features**: Player vs player tic-tac-toe matches
- **Commands**: Use `[p]help perfectttt` for available commands
- **Tags**: games, fun, interactive, trickery

### WordCloudRe
Refactored word cloud generator that creates visual word clouds from Discord channel message history.
- **Features**: Custom masks, color themes, word filtering, time-based analysis, file upload/download validation
- **Requirements**: `wordcloud`, `numpy`, `matplotlib` (system dependencies: `libstdc++.so.6`, `libz.so.1`)
- **Commands**: Use `[p]help wordcloud` for available commands
- **Tags**: word, cloud, wordcloud, refactored, visualization, analytics
- **Note**: Refactored version of original cog by FlapJack and aikaterna with bug fixes and security improvements

### MakiAlert
Simple HTTP-based alert system that sends notifications to Discord DMs.
- **Features**: HTTP endpoint for external services, auto-start server, rate limiting, audio cog integration
- **Requirements**: No additional dependencies
- **Commands**: Use `[p]help makialert` for available commands
- **Tags**: alerts, monitoring, http, notifications, system
- **Endpoint**: `POST http://localhost:8080/alert` (localhost only, no auth required)

### VoiceCommands
Voice control system for Discord audio playback using speech recognition and wake word detection.
- **Features**: Wake word detection ("Hey Maki"), offline processing, audio cog integration
- **Requirements**: `py-cord`, `SpeechRecognition`, `openwakeword`, `numpy`, `librosa`
- **Commands**: Use `[p]help voicecommands` for available commands
- **Tags**: voice, audio, speech recognition, wake word, control
- **Note**: Requires py-cord instead of standard discord.py for voice recording capabilities

## Installation

To install these cogs on your Red-Bot instance:

1. Add this repository to your bot:
   ```
   [p]repo add maki-cogs https://github.com/Nero200/Maki-Cogs  
   ```

2. Install the desired cog:
   ```
   [p]cog install maki-cogs <cog_name>
   ```

3. Load the cog:
   ```
   [p]load <cog_name>
   ```

## Requirements

- Red-Bot v3.5.0 or higher
- Python 3.8+
- Additional requirements per cog (see individual `info.json` files)

## Contributing

Feel free to submit issues and pull requests for improvements or bug fixes.

## License

MIT License - See individual cog files for specific licensing information.

## Author

Developed by Nero for the Maki Discord bot instance.
