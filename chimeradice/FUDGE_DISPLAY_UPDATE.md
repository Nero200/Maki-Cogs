# Fudge Dice Display Enhancement

## Change Summary
Updated the fudge dice display format to use more visually appealing symbols with bold formatting.

## Before and After

### Previous Format
```
Result: (+1, 0, -1, +1) = +1
```

### New Format
```
Result: (**+**, ☐, **-**, **+**) = **+1**
```

## Changes Made

### Display Symbols
- **Positive (+1)**: `+1` → `**+**` (bold plus sign)
- **Blank (0)**: `0` → `☐` (regular square symbol)  
- **Negative (-1)**: `-1` → `**-**` (bold minus sign)

### Implementation
**File**: `chimeradice.py:891`
**Change**:
```python
# Old
dice_str = ', '.join(['+1' if d == 1 else '0' if d == 0 else '-1' for d in dice_results])

# New  
dice_str = ', '.join(['**+**' if d == 1 else '☐' if d == 0 else '**-**' for d in dice_results])
```

## Benefits

### Visual Clarity
- **Bold formatting** makes meaningful results (+/-) stand out
- **Distinct symbols** are easier to scan quickly
- **Square symbol (☐)** better represents "blank" than "0"
- **Unbolded square** maintains visual balance

### Readability
- Shorter symbols reduce visual clutter
- Bold text draws attention to individual die results
- More intuitive representation of fudge dice faces

### Consistency
- Maintains all existing functionality
- No change to calculation logic
- Same information presented more clearly

## Example Outputs

### Typical Roll
```
🎲 **Player** rolls `4dF+2`...
Result: (**+**, ☐, **-**, **+**) +2 = **+3**
```

### All Positive (with bonus)
```
🎲 **Player** rolls `4dF`...
Result: (**+**, **+**, **+**, **+**) +2 (all +) = **+6**
```

### All Negative (with penalty)
```
🎲 **Player** rolls `4dF-1`...
Result: (**-**, **-**, **-**, **-**) -2 (all -) -1 = **-7**
```

### Mixed Results
```
🎲 **Player** rolls `4dF+1`...
Result: (**+**, ☐, ☐, **-**) +1 = **+1**
```

## Technical Impact
- ✅ **No breaking changes** - pure display enhancement
- ✅ **All calculations identical** - only presentation changed
- ✅ **Backward compatible** - no impact on existing features
- ✅ **Performance neutral** - same string formatting complexity

---

**Status**: ✅ **IMPLEMENTED**
**Fudge dice now display with bold +, -, and ☐ symbols!**