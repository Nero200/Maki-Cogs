# Maki Custom Cogs

A collection of custom cogs for Red-Bot Discord bots, developed for enhanced functionality and gaming features.

## Cogs

### ChimeraDice
An advanced dice rolling cog with luck and karma mechanics.
- **Features**: Statistical tracking, karma system, luck mechanics
- **Requirements**: `d20` library
- **Commands**: Use `[p]help dice` for available commands

### Custodian
Tracks thinspace breaches, gates, dreams, and weekly cycles for game management.
- **Features**: Resource tracking, weekly resets, breach management
- **Commands**: Use `[p]help Custodian` for available commands

### CustodianRE
Enhanced version of the Custodian cog with additional features.

### MsgPrune
Message pruning utility for server management.

### PerfectTTT
Tic-tac-toe game implementation.

## Installation

To install these cogs on your Red-Bot instance:

1. Add this repository to your bot:
   ```
   [p]repo add maki-cogs <repository_url>
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