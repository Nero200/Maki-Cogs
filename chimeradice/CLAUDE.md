# ChimeraDice Cog Documentation

**IMPORTANT NOTE FOR CLAUDE**: When you first read this file in a new session, ask the user about the local test utilities (`chimeradice_test.py` and the `>fr2` command) and what they actually do. This is a reminder for context.

## Overview
ChimeraDice is a sophisticated dice rolling cog for Red-Bot with advanced probability systems, multiple dice types, and comprehensive statistics tracking. It's designed for tabletop RPG gaming.

## Core Architecture

### Dice Systems Supported
- **Standard Dice**: Full d20 library integration (`1d20+5`, `4d6kh3`, `2d20dl1`)
- **Fudge Dice**: Enhanced Fate/FUDGE dice (`4dF`) with special display formatting
- **Fallout Dice**: Custom Fallout RPG dice (`3dD`)
- **Advanced Operations**: Keep/drop, rerolls, exploding, constraints, multiple modifiers

### Probability Systems
1. **Luck System**: Weighted probability bias (0-100 scale, 50=neutral)
2. **Karma System**: Percentile debt balancing that auto-corrects streaks

### Key Technical Features
- **Syntax Translation**: Converts user-friendly `dl`/`dh` to d20 library `kh`/`kl` syntax
- **Weighted Probability**: Bias applied during dice generation, not post-roll modification
- **Percentile Tracking**: All dice results converted to percentiles for statistics
- **Security**: Input validation, 12-hour expiration on preset test rolls

## Commands Reference

### Player Commands
- `>roll`/`>r` - Standard rolling with luck/karma if enabled
- `>lroll`/`>lr` - Activate luck rolling (works without luck mode)
- `>kroll`/`>kr` - Activate karma rolling (works without karma mode)
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

### Preset Test Rolls (In-Memory)
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
*Note: Used by local test utilities for development/testing purposes.*

## Technical Implementation Notes

### Probability Weighting
- **Activation Threshold**: Bias only applies when |debt| ≥ 5.0 (both luck and karma)
- **Bias Strength**: Scales from 0 to 1 based on `min(|debt| / 50.0, 1.0)`
- **Weight Adjustments**: Good faces boosted up to 40%, bad faces reduced up to 20%
- Fudge dice use sum distribution weighting with realistic face back-generation
- All results remain within natural dice ranges

### Karma Debt Mechanics
- **Pure Self-Correction**: No artificial decay factor
- Each roll adds `(50 - percentile)` to debt
- Good rolls (>50th percentile) naturally reduce positive debt
- Bad rolls (<50th percentile) naturally reduce negative debt
- System oscillates toward zero through gameplay, not time

### Security Features
- Input validation: max 150 chars, 100 dice, d1000 max
- Preset test rolls: DM-only, 12-hour expiration, Discord ID required (via test utilities)
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

## Logging
ChimeraDice uses Python's standard logging module integrated with Red-Bot's logging system.

### Log Namespace
- **Logger Name**: `red.chimeradice`
- **Log Location**: `/home/nero/redbot/maki/core/logs/latest.log`
- **Rotation**: Automatic (managed by Red-Bot)

### What Gets Logged
- **ERROR**: Roll execution failures, config save errors (with full tracebacks)
- **WARNING**: Debt capping events, large percentile history warnings, config fallback operations
- **INFO**: Admin commands (enable/disable luck/karma, set luck/debt, reset karma, fix data)
- **DEBUG**: Percentile calculations, preset roll cleanup, Fallout dice skips

### What Is NOT Logged
- **Test utility commands**: By design, test commands leave no audit trail
- **Individual bias applications**: Could reveal roll manipulation patterns

### Viewing Logs
```bash
# Follow live logs
tail -f /home/nero/redbot/maki/core/logs/latest.log

# Search ChimeraDice logs
grep "chimeradice" /home/nero/redbot/maki/core/logs/latest.log

# Filter by level
grep "ERROR.*chimeradice" /home/nero/redbot/maki/core/logs/latest.log
```

## Known Limitations
- Test utility commands require Discord IDs (no username lookup in DMs)
- Statistics currently server-wide only (campaign-specific planned)
- Complex mixed dice type expressions have limited support
- Preset test rolls with advanced operations fall back to normal rolling
- Percentile calculations for advanced operations use approximations

---

**Last Updated**: January 2025  
**Current Version**: 3.0 - Probability Revolution  
**Status**: Production ready with comprehensive testing