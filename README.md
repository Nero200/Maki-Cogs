# Maki Custom Cogs

A collection of custom cogs for Red-Bot Discord bots, developed for enhanced functionality and gaming features.

## Cogs

### ChimeraDice
An advanced dice rolling cog with luck and karma mechanics for tabletop RPG games.
- **Features**: Statistical tracking, karma system, luck mechanics, comprehensive dice notation support
- **Requirements**: `d20` library
- **Commands**: Use `[p]help dice` for available commands
- **Tags**: dice, fun, games, rpg, ttrpg, roll

### Custodian ⚠️ **DEPRECATED**
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

### PerfectTTT
Interactive tic-tac-toe game implementation for Discord with perfect play.
- **Features**: Player vs player tic-tac-toe matches
- **Commands**: Use `[p]help perfectttt` for available commands
- **Tags**: games, fun, interactive, trickery

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
