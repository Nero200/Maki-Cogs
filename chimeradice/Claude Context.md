# ChimeraDice Cog - Claude Context Document

## Overview
ChimeraDice is a comprehensive Discord bot cog for Red-DiscordBot that implements advanced dice rolling with probability-based luck, percentile debt karma, force mechanics, and statistical tracking. Features full d20 library integration with weighted probability manipulation for natural-feeling dice bias. Developed for tabletop RPG gaming with GM control features.

## Core Features

### Dice Types Supported
- **Standard Dice**: `XdY` format using d20 library with full advanced operation support
  - Basic: `1d20`, `3d6+2`, `2d10-1`
  - Keep/Drop: `4d6kh3`, `2d20dl1`, `6d6kl2`, `3d20dh1`
  - Rerolls: `1d20ro<3`, `1d20rr<5`, `2d6ra1`
  - Exploding: `2d6e6`, `1d10e10`
  - Constraints: `8d6mi2`, `3d20ma19`
- **Fudge Dice**: `XdF` format with enhanced visual display and weighted distribution (e.g., `4dF`, `4dF+2`)
- **Fallout Dice**: `XdD` format with faces ["1", "2", "0", "0", "1E", "1E"]

### Advanced Systems
1. **Luck System**: Weighted probability bias (0-100) that naturally influences dice generation
2. **Karma System**: Percentile debt balancing that auto-corrects luck streaks over time
3. **Force System**: GM can force specific results via DM commands
4. **Statistics**: Percentile-based natural luck tracking with advanced operation support
5. **Syntax Translation**: Automatic conversion of user-friendly drop syntax to d20 library format

### Multiple Modifier Support
All dice types support complex expressions:
- `1d20+3-2+1` = d20 + total modifier of +2
- `4dF+5+2-1` = 4 fudge dice + total modifier of +6

## Commands

### Core Rolling Commands
- `>roll` / `>r` - Standard dice rolling (uses luck/karma modes if enabled)
- `>lroll` / `>lr` - Explicit luck rolling (works without luck mode)
- `>kroll` / `>kr` - Explicit karma rolling (works without karma mode)

### Force Command (DM-Only)
- `>force 1d20 15` - Force your own next d20 to show 15
- `>force 123456789012345678 1d20 15` - Force specific user's roll by Discord ID
- **Security**: DM-only, 12-hour expiration, input validation

### User Statistics Commands
- `>stats [user]` - View user's dice statistics and natural luck
- `>globalstats [user]` - View server-wide statistics  
- `>campaignstats` - Show channel activity overview
- `>recent_luck [hours] [user]` - Show luck trend over recent hours (1-24)

### Admin Commands
- `>enable_luck <user>` - Enable luck mode for user in channel
- `>disable_luck <user>` - Disable luck mode
- `>enable_karma <user>` - Enable karma mode for user in channel  
- `>disable_karma <user>` - Disable karma mode
- `>set_luck <user> <value>` - Set user's luck bias (0-100)
- `>reset_karma <user>` - Reset user's karma and percentile debt to 0
- `>set_debt <user> <value>` - Set user's percentile debt (-100 to +100)
- `>admin_stats <user>` - Admin view of complete user statistics
- `>export_user <user>` - Export user's complete roll history
- `>fix_luck_data [user]` - Fix user's luck data structure

## Technical Implementation

### File Structure
```
chimeradice/
├── chimeradice.py              # Main cog implementation
├── info.json                   # Cog metadata
├── __init__.py                 # Package initialization
├── test_karma_probability.py   # Comprehensive probability tests
├── test_karma_simple.py        # Standalone probability tests
└── test_luck_system.py         # Luck system validation tests
```

### Key Classes and Methods

#### ChimeraDice Class
- `__init__()` - Initialize config and forced rolls storage
- `_execute_roll()` - Main roll execution with validation and type routing
- `_handle_fudge_dice()` - Fudge dice specific implementation with weighted probability
- `_handle_fallout_dice()` - Fallout dice implementation

#### Weighted Probability System (New)
- `_roll_weighted_standard_die()` - Weighted probability generation for standard dice
- `_roll_weighted_fudge_dice()` - Weighted sum distribution for fudge dice
- `_generate_realistic_fudge_faces()` - Natural-looking fudge dice face generation
- `_roll_standard_dice_with_karma()` - Karma-biased standard dice rolling
- `_roll_standard_dice_with_luck()` - Luck-biased standard dice rolling

#### Karma & Debt System
- `_apply_karma_modification()` - Manages percentile debt tracking
- `_update_percentile_debt()` - Updates debt based on roll outcomes vs percentiles
- `_update_natural_luck()` - Updates percentile-based statistics
- `_calculate_roll_percentile()` - Calculates percentile for any dice type

#### Advanced Operations Support
- `_translate_dice_syntax()` - Converts user-friendly drop syntax to d20 library format
- `_extract_base_dice()` - Extracts base dice from complex expressions
- `_handle_forced_standard_dice()` - Handles forced results with advanced operations
- `_estimate_keep_percentile()` - Calculates percentiles for keep/drop operations

#### Security & Validation
- `_validate_dice_expression()` - Enhanced validation with d20 library integration (max 150 chars)
- `_cleanup_expired_forced_rolls()` - 12-hour expiration cleanup
- `_parse_dice_modifiers()` - Multi-modifier parsing

### Data Storage Structure

#### User Data (Red-DiscordBot Config)
```python
DEFAULT_GUILD_USER = {
    "toggles": {
        "luckmode_on": False,
        "karmamode_on": False,
    },
    "set_luck": 50,  # 0-100 bias value
    "current_karma": 0,  # Legacy - kept for backward compatibility
    "percentile_debt": 0.0,  # New karma system - accumulated difference from 50th percentile
    "stats": {
        "server_wide": {
            "standard_rolls": [],
            "luck_rolls": [], 
            "karma_rolls": [],
            "natural_luck": 50.0,  # Percentile average
            "percentile_history": [],  # All roll percentiles
            "total_rolls": 0,
        },
        "campaigns": {},  # Future campaign-specific stats
    },
}
```

#### Forced Rolls Storage (In-Memory)
```python
# Format: {user_id: {dice_expr: {"values": [results], "timestamp": datetime}}}
self.forced_rolls = {
    123456789: {
        "1d20": {
            "values": [15, 18],
            "timestamp": datetime(2025, 1, 13, 10, 30)
        }
    }
}
```

#### Fudge Dice Probability Tables
```python
FUDGE_PROBABILITIES = {
    1: {-1: 1/3, 0: 1/3, 1: 1/3},
    2: {-2: 1/9, -1: 2/9, 0: 3/9, 1: 2/9, 2: 1/9},
    3: {-3: 1/27, -2: 3/27, -1: 6/27, 0: 7/27, 1: 6/27, 2: 3/27, 3: 1/27},
    4: {-4: 1/81, -3: 4/81, -2: 10/81, -1: 16/81, 0: 19/81, 1: 16/81, 2: 10/81, 3: 4/81, 4: 1/81},
    # ... up to 6 dice
}
```

## System Mechanics

### Luck System (Probability-Based)
- **Range**: 0-100 (50 = neutral)
- **Method**: Weighted probability during dice generation
- **Effect**: Natural bias toward higher (>50) or lower (<50) results
- **Implementation**: Converts to debt-equivalent (-50 to +50) for weighted rolling
- **Threshold**: 2.0+ debt required for bias activation
- **Results**: All outcomes remain within natural dice ranges

### Karma System (Percentile Debt)
- **Type**: Percentile debt balancing system
- **Accumulation**: Every roll adds `(50 - percentile)` to debt
- **Application**: Weighted probability when `|debt| > 5.0` (standard) or `> 10.0` (fudge)
- **Scaling**: 10 percentile points = 1 modifier equivalent
- **Decay**: 2% debt reduction per roll prevents infinite accumulation
- **Cap**: ±100 percentile points maximum debt
- **Display**: Shows current debt as `(Debt: +15.3)`

### Force System
- **Access**: DM-only for secrecy
- **Targeting**: Self or others by Discord ID
- **Expiration**: 12 hours automatic cleanup
- **Scope**: Forces base dice result, modifiers added normally
- **Example**: Force 1d20 to 15, roll 1d20+10 = 25 total

### Natural Luck Calculation
- **Method**: Percentile rank system across all roll types
- **Calculation**: Average of all historical roll percentiles
- **Range**: 0-100 (50 = average luck)
- **Updates**: Real-time with each valid roll

## Probability System Details

### Standard Dice Weighting
```python
# Bias strength: 0 to 1 based on debt magnitude
bias_strength = min(abs(debt) / 50.0, 1.0)

# Weight adjustment for each face
if debt > 0:  # Owed good luck
    if face_value > midpoint:
        weight *= (1.0 + bias_strength * 0.4)  # +40% max boost
    else:
        weight *= (1.0 - bias_strength * 0.2)  # -20% max reduction
```

### Fudge Dice Weighting
- **Method**: Weighted sum distribution, then realistic face generation
- **Bias Strength**: Max 80% probability adjustment
- **Face Generation**: Multiple randomization passes for natural appearance
- **Realism**: Pattern frequency analysis ensures no dominant patterns

### Test Results
- **d20 Range**: -1.38 to +1.41 average shift across debt range
- **4dF Range**: -0.35 to +0.35 average shift across debt range
- **Bias Direction**: 100% accuracy in all tests
- **Face Realism**: Max pattern frequency < 4% (natural threshold)

## Security Features

### Input Validation
- Maximum 150 characters per expression (increased for advanced operations)
- Maximum 100 dice per roll
- Maximum die size of 1000
- Maximum modifier values of 1000
- d20 library integration validates complex expressions
- Syntax translation for user-friendly drop operations
- Prevents malicious expressions like `999999d999999`

### Force Command Security
- **DM-only**: Completely hidden from players
- **Guild-restricted**: No cross-server user exposure
- **Expiration**: Automatic cleanup after 12 hours
- **ID-based**: Uses Discord IDs, not searchable usernames

### Memory Management
- Automatic cleanup of expired forced rolls
- Legacy format support for migration
- Proper data structure validation

## Special Dice Implementations

### Fudge Dice (XdF) - Enhanced
- **Faces**: [-1, 0, +1]
- **Enhanced Display**: (**+**, ☐, **-**, **+**) with bold +/- and regular ☐ for blanks
- **Special Rule**: All positive = +(num_dice/2 rounded up) bonus
- **Special Rule**: All negative = -(num_dice/2 rounded up) penalty
- **Karma**: Weighted sum distribution with realistic face generation
- **Bias Threshold**: 15.0+ debt for fudge dice activation
- **Example**: `4dF` displaying (**+**, **+**, **+**, **+**) +2 (all +) = **+6**

### Fallout Dice (XdD)
- **Faces**: ["1", "2", "0", "0", "1E", "1E"]
- **Exploding**: "1E" faces can trigger additional mechanics (implementation pending)

## Dependencies
- **Required**: `d20` library for standard dice parsing
- **Framework**: Red-DiscordBot cog system
- **Python**: Standard library (datetime, statistics, random, re)
- **Testing**: Standalone test files with no external dependencies

## Common Patterns

### Adding New Dice Type
1. Add detection in `_execute_roll()`
2. Create `_handle_new_dice()` method
3. Implement weighted probability if needed
4. Add percentile calculation support
5. Add validation rules
6. Update help text

### Modifying Probability System
1. Update weighting functions for new bias behavior
2. Add test cases in probability test files
3. Ensure bias direction correctness
4. Validate natural result ranges
5. Test face/pattern realism

### Modifying Statistics
1. Update `_calculate_roll_percentile()` for new dice type
2. Add support to `_estimate_keep_percentile()` if using keep/drop operations
3. Ensure `_update_natural_luck()` handles new format
4. Add to export functionality if needed

## Known Limitations
- Force command requires Discord IDs in DMs (no username lookup)
- Statistics only track server-wide (campaign-specific planned)
- Complex expressions with mixed dice types not fully supported
- No bulk administrative operations
- Forced rolls with advanced operations fall back to normal rolling
- Percentile calculations for advanced operations use approximations

## Development Notes
- All dice manipulation uses weighted probability during generation, not post-roll modification
- Fudge dice use sum distribution weighting with realistic face back-generation
- Enhanced fudge display uses Discord markdown: `**+**`, `☐`, `**-**`
- Percentile calculations use continuous distribution approximations
- Probability bias prioritizes natural feeling over mathematical precision
- Syntax translation happens before d20.roll() calls for seamless user experience
- Advanced operations pattern: `(kh|kl|dh|dl|ro|rr|ra|e|mi|ma|p)\d*`
- Comprehensive test suite validates probability behavior and realism

## Future Considerations
- Campaign-specific statistics tracking
- More sophisticated karma algorithms
- Bulk administrative commands
- Enhanced complex expression parsing for mixed dice types
- Roll history retention policies
- Improved forced roll support for advanced operations
- Additional dice type implementations (e.g., success counting, dice pools)

## Recent Updates (January 2025)

### Version 3.0 - Probability Revolution
- **✅ Weighted Probability System** - Complete rewrite from modifier-based to probability-based manipulation
- **✅ Unified Luck & Karma** - Both systems now use weighted probability during dice generation
- **✅ Percentile Debt Karma** - Granular karma system based on roll percentiles vs expected
- **✅ Realistic Fudge Faces** - Advanced algorithm ensures natural-looking face patterns
- **✅ Comprehensive Testing** - Extensive probability validation with statistical analysis
- **✅ Code Cleanup** - Removed unused functions, updated documentation, enhanced maintainability

### Version 2.1 - Advanced Operations & Enhanced Display
- **✅ Fixed drop lowest functionality** - Added syntax translation for `dl`/`dh` operations
- **✅ Full d20 library integration** - Support for all advanced operations (keep, drop, reroll, exploding, constraints)
- **✅ Enhanced fudge dice display** - Visual improvement with bold symbols and better balance
- **✅ Advanced percentile calculations** - Support for keep/drop operations in statistics
- **✅ Comprehensive testing** - Unit tests, property tests, and functionality verification
- **✅ User command documentation** - Complete user guide for announcement posts

### Key Improvements in v3.0
- **Natural Results**: All bias applied during generation, results always within normal ranges
- **Granular Control**: Percentile-based system provides smooth, responsive balancing
- **Face Realism**: Fudge dice patterns indistinguishable from natural rolling
- **Performance**: Weighted generation more efficient than post-roll modification
- **Consistency**: Unified approach across all dice types and bias systems

### Translation Examples
- `2d20dl1` → `2d20kh1` (drop lowest = keep highest)
- `4d6dl1` → `4d6kh3` (classic D&D ability scores)
- `3d20dh1` → `3d20kl2` (drop highest = keep lowest)

---
**Last Updated**: January 2025  
**Version**: 3.0 - Probability Revolution  
**Status**: Production ready with comprehensive weighted probability system and extensive testing