# 🎲 ChimeraDice Commands - User Guide

Welcome to ChimeraDice! Here are all the commands available to players:

## 🎯 Core Rolling Commands

### `>roll` or `>r` - Standard Dice Rolling
Roll any dice expression with full d20 library support!

**Examples:**
```
>r 1d20+5          # Classic d20 with modifier
>r 3d6             # Three six-sided dice  
>r 2d10+3-1        # Multiple modifiers
>r 4d6kh3          # Keep highest 3 (ability scores!)
>r 2d20dl1         # Drop lowest 1 (advantage alternative)
>r 1d20ro<3        # Reroll 1s and 2s once
>r 2d6e6           # Exploding sixes
>r 8d6mi2          # Minimum 2 damage per die
```

### `>lroll` or `>lr` - Luck Rolling
Roll with your luck modifier applied (works even without luck mode enabled).

**Examples:**
```
>lr 1d20+5         # Roll with luck influence
>lr 4d6kh3         # Ability score with luck
```

### `>kroll` or `>kr` - Karma Rolling  
Roll with karma balancing applied (works even without karma mode enabled).

**Examples:**
```
>kr 1d20+3         # Roll with karma adjustment
>kr 2d10+5         # Damage roll with karma
```

## 🎭 Special Dice Types

### Fudge Dice (Fate/FUDGE System)
Use `XdF` for Fudge dice with enhanced display!

**Examples:**
```
>r 4dF             # Classic 4 Fudge dice
>r 4dF+2           # Fudge dice with skill bonus
>r 3dF-1           # Fudge dice with penalty
```

**Display:** (**+**, ☐, **-**, **+**) = **+1**

### Fallout Dice (Fallout RPG)
Use `XdD` for Fallout damage dice!

**Examples:**
```
>r 3dD             # 3 Fallout damage dice
>r 5dD+2           # Fallout dice with bonus
```

**Shows:** Damage total + Effect count

## 📊 Statistics Commands

### `>stats` - Your Dice Statistics
View your rolling statistics and natural luck rating.

**Examples:**
```
>stats             # Your own stats
>stats @username   # Someone else's stats
```

### `>recent_luck` - Recent Performance
Check your luck trend over recent hours.

**Examples:**
```
>recent_luck       # Last 24 hours (default)
>recent_luck 12    # Last 12 hours
>recent_luck 6     # Last 6 hours
```

### `>campaignstats` - Channel Overview
See who's been rolling in this channel.

**Examples:**
```
>campaignstats     # Channel activity summary
```

### `>globalstats` - Server-Wide Stats
View server-wide statistics.

**Examples:**
```
>globalstats       # Your server-wide stats
>globalstats @user # Someone else's server stats
```

## 🎲 Advanced Dice Operations

ChimeraDice supports the full d20 library syntax:

### Keep/Drop Operations
```
4d6kh3             # Keep highest 3 dice
6d6kl2             # Keep lowest 2 dice  
2d20dl1            # Drop lowest 1 die
3d20dh1            # Drop highest 1 die
4d6p1              # Drop lowest 1 (alternative syntax)
```

### Reroll Operations
```
1d20ro<3           # Reroll 1s and 2s once
1d20rr<3           # Reroll 1s and 2s recursively
2d6ra1             # Reroll and add one 1
```

### Exploding Dice
```
2d6e6              # Explode on 6s
1d10e10            # Explode on 10s
3d8e8              # Explode on 8s
```

### Min/Max Constraints
```
8d6mi2             # Minimum 2 on each die
3d20ma19           # Maximum 19 on each die
1d6mi3ma5          # Both min and max
```

## 🍀 Special Features

### Luck System
- When enabled by admins, influences your roll results
- Higher luck (51-100) = better results
- Lower luck (0-49) = worse results
- Track your "natural luck" rating over time!

### Karma System  
- Blue noise balancing system
- Occasionally adjusts streaks to balance outcomes
- Builds up from bad luck, spends on good luck
- Creates more balanced gaming experience

### Natural Luck Tracking
- Automatically calculates your luck percentile
- Tracks all roll types over time
- See if you're truly lucky or unlucky!

## 📝 Usage Tips

1. **Complex Expressions:** Mix and match operations!
   ```
   >r 4d6kh3+2        # Ability score with racial bonus
   >r 2d20dl1+5       # Advantage-style with modifier
   ```

2. **Multiple Modifiers:** Stack them freely!
   ```
   >r 1d8+3+2-1       # Weapon + STR + magic - penalty
   ```

3. **Check Your Luck:** Use `>stats` to see how you're doing!

4. **Recent Performance:** Use `>recent_luck` to spot hot/cold streaks!

---

🎉 **Happy Rolling!** ChimeraDice makes every roll exciting with advanced statistics, luck tracking, and beautiful display formatting.