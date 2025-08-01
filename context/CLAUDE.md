# ChimeraDice Cog Documentation

## Overview
ChimeraDice is a sophisticated dice rolling cog for Red-Bot with advanced probability systems, multiple dice types, and comprehensive statistics tracking. It's designed for tabletop RPG gaming with both player and GM features.

## Core Architecture

### Dice Systems Supported
- **Standard Dice**: Full d20 library integration (`1d20+5`, `4d6kh3`, `2d20dl1`)
- **Fudge Dice**: Enhanced Fate/FUDGE dice (`4dF`) with special display formatting
- **Fallout Dice**: Custom Fallout RPG dice (`3dD`)
- **Advanced Operations**: Keep/drop, rerolls, exploding, constraints, multiple modifiers

### Probability Systems
1. **Luck System**: Weighted probability bias (0-100 scale, 50=neutral)
2. **Karma System**: Percentile debt balancing that auto-corrects streaks
3. **Force System**: GM-only DM commands to set specific results

### Key Technical Features
- **Syntax Translation**: Converts user-friendly `dl`/`dh` to d20 library `kh`/`kl` syntax
- **Weighted Probability**: Bias applied during dice generation, not post-roll modification
- **Percentile Tracking**: All dice results converted to percentiles for statistics
- **Security**: Input validation, DM-only force commands, 12-hour expiration

## Commands Reference

### Player Commands
- `>roll`/`>r` - Standard rolling with luck/karma if enabled
- `>lroll`/`>lr` - Force luck rolling (works without luck mode)
- `>kroll`/`>kr` - Force karma rolling (works without karma mode)
- `>stats [user]` - View statistics and natural luck rating
- `>recent_luck [hours] [user]` - Luck trend analysis (1-24 hours)
- `>campaignstats` - Channel activity overview
- `>globalstats [user]` - Server-wide statistics

### Admin Commands
- `>enable_luck/disable_luck <user>` - Toggle luck mode per user/channel
- `>enable_karma/disable_karma <user>` - Toggle karma mode per user/channel
- `>set_luck <user> <0-100>` - Set luck bias value
- `>reset_karma <user>` - Reset karma debt to 0
- `>set_debt <user> <value>` - Manually set percentile debt
- `>admin_stats <user>` - Complete admin view of user data
- `>export_user <user>` - Export complete roll history
- `>fix_luck_data [user]` - Repair data structure issues

### GM Commands (DM-Only)
- `>force 1d20 15` - Force your next d20 roll to 15
- `>force <user_id> 1d20 15` - Force another user's roll by Discord ID

## Recent Development History

### Version 3.0 - Probability Revolution (January 2025)
- Complete rewrite from modifier-based to weighted probability system
- Unified luck and karma systems using probability manipulation
- Percentile debt karma system for granular balancing
- Realistic fudge dice face generation algorithm
- Comprehensive probability testing and validation

### Version 2.1 - Advanced Operations Support
- Fixed drop lowest (`dl`) and drop highest (`dh`) functionality
- Added syntax translation layer for user-friendly commands
- Enhanced fudge dice display with bold symbols (`**+**`, `☐`, `**-**`)
- Full d20 library integration with all advanced operations
- Improved percentile calculations for keep/drop operations

## Data Storage Structure

### User Configuration
```python
{
    "toggles": {
        "luckmode_on": False,
        "karmamode_on": False,
    },
    "set_luck": 50,  # 0-100 bias
    "percentile_debt": 0.0,  # Karma debt accumulation
    "stats": {
        "server_wide": {
            "natural_luck": 50.0,  # Overall percentile average
            "percentile_history": [],  # All roll percentiles
            "total_rolls": 0,
        }
    }
}
```

### Forced Rolls (In-Memory)
```python
{
    user_id: {
        "1d20": {
            "values": [15, 18],
            "timestamp": datetime_object
        }
    }
}
```

## Technical Implementation Notes

### Probability Weighting
- Bias strength calculated from debt magnitude (max 40% boost, 20% reduction)
- Fudge dice use sum distribution weighting with realistic face back-generation
- All results remain within natural dice ranges
- Threshold requirements prevent excessive bias activation

### Security Features
- Input validation: max 150 chars, 100 dice, d1000 max
- Force commands: DM-only, 12-hour expiration, Discord ID required
- Memory management: automatic cleanup of expired data
- Cross-server isolation: no user data exposure between guilds

### Advanced Operations Translation
- `2d20dl1` → `2d20kh1` (drop lowest = keep highest)
- `4d6dl1` → `4d6kh3` (classic D&D ability scores)
- `3d20dh1` → `3d20kl2` (drop highest = keep lowest)

## Dependencies and Requirements
- **Required**: `d20` library for dice parsing and rolling
- **Framework**: Red-DiscordBot cog system
- **Python**: 3.8+ with standard library modules
- **Testing**: Standalone test suite with comprehensive probability validation

## Known Limitations
- Force commands require Discord IDs (no username lookup in DMs)
- Statistics currently server-wide only (campaign-specific planned)
- Complex mixed dice type expressions have limited support
- Forced rolls with advanced operations fall back to normal rolling
- Percentile calculations for advanced operations use approximations

---

**Last Updated**: January 2025  
**Current Version**: 3.0 - Probability Revolution  
**Status**: Production ready with comprehensive testing