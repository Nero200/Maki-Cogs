# CPR Mode & Initiative System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Cyberpunk Red game support with exploding/imploding d10s, critical d6 damage, and batch initiative rolling.

**Architecture:** New CPR mode stored per-channel in Red's config. Initiative groups also per-channel. CPR mechanics hook into `_execute_roll` after dice generation. Initiative uses standalone rolling logic.

**Tech Stack:** Red-Bot commands.Cog, Red Config (channel scope), Python re for pattern matching.

---

## Task 1: Add Channel Config Defaults

**Files:**
- Modify: `chimeradice_core.py:35-38`

**Step 1: Add DEFAULT_CHANNEL constant**

Add after `DEFAULT_GUILD` (line 38):

```python
DEFAULT_CHANNEL = {
    "cpr_mode": False,
    "initiative_group": {},  # {name: {"modifier_expr": "14+2", "modifier_total": 16}}
}
```

**Step 2: Run tests to ensure no regressions**

Run: `python run_tests.py`
Expected: All existing tests pass.

**Step 3: Commit**

```bash
git add chimeradice_core.py
git commit -m "feat: add channel config defaults for CPR mode and initiative"
```

---

## Task 2: Register Channel Config in Cog

**Files:**
- Modify: `chimeradice.py:56-62`
- Modify: `chimeradice_core.py:12-13` (export)

**Step 1: Add DEFAULT_CHANNEL to imports**

In `chimeradice.py`, update the import block (around line 14):

```python
from .chimeradice_core import (
    # Constants
    DEFAULT_GUILD_USER,
    DEFAULT_GUILD,
    DEFAULT_CHANNEL,  # Add this line
    FALLOUT_FACES,
    ...
```

**Step 2: Register channel config in __init__**

After line 62 (`self.config.register_user(...)`), add:

```python
        self.config.register_channel(**DEFAULT_CHANNEL)
```

**Step 3: Run tests**

Run: `python run_tests.py`
Expected: All tests pass.

**Step 4: Commit**

```bash
git add chimeradice.py chimeradice_core.py
git commit -m "feat: register channel config for CPR mode and initiative"
```

---

## Task 3: Add CPR Mode Toggle Commands

**Files:**
- Modify: `chimeradice.py` (add after line ~203, after fake commands section)

**Step 1: Add the CPR command group**

Add after the decoy commands section (around line 250):

```python
    # --- CPR MODE COMMANDS ---

    @commands.group(name="cpr", invoke_without_command=True)
    async def cpr(self, ctx: commands.Context):
        """Cyberpunk Red dice mode commands."""
        await ctx.send_help(ctx.command)

    @cpr.command(name="enable", aliases=["on"])
    @commands.admin_or_permissions(manage_guild=True)
    async def cpr_enable(self, ctx: commands.Context):
        """Enable CPR mode for this channel."""
        await self.config.channel(ctx.channel).cpr_mode.set(True)
        await ctx.send("CPR mode enabled for this channel. d10s will explode on 10 and implode on 1. d6 pools will crit on 2+ sixes.")

    @cpr.command(name="disable", aliases=["off"])
    @commands.admin_or_permissions(manage_guild=True)
    async def cpr_disable(self, ctx: commands.Context):
        """Disable CPR mode for this channel."""
        await self.config.channel(ctx.channel).cpr_mode.set(False)
        await ctx.send("CPR mode disabled for this channel.")

    @cpr.command(name="status")
    async def cpr_status(self, ctx: commands.Context):
        """Show CPR mode status for this channel."""
        enabled = await self.config.channel(ctx.channel).cpr_mode()
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"CPR mode is **{status}** for this channel.")
```

**Step 2: Test manually (or write unit test)**

Start bot, run `>cpr enable`, `>cpr status`, `>cpr disable`.
Expected: Commands work, status shows correct state.

**Step 3: Commit**

```bash
git add chimeradice.py
git commit -m "feat: add CPR mode toggle commands (enable/disable/status)"
```

---

## Task 4: Add CPR d10 Roll Logic (Core Function)

**Files:**
- Modify: `chimeradice_core.py` (add new function)

**Step 1: Write failing test for CPR d10 rolling**

Create `tests/test_cpr_mode.py`:

```python
"""Tests for CPR mode dice mechanics."""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chimeradice_core import roll_cpr_d10, format_cpr_d10_result


class TestCPRd10Rolling(unittest.TestCase):
    """Test CPR d10 explosion and implosion mechanics."""

    def test_roll_cpr_d10_returns_tuple(self):
        """roll_cpr_d10 returns (total, base_roll, explosion_roll)."""
        result = roll_cpr_d10()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_roll_cpr_d10_base_roll_range(self):
        """Base roll is always 1-10."""
        for _ in range(100):
            total, base, explosion = roll_cpr_d10()
            self.assertGreaterEqual(base, 1)
            self.assertLessEqual(base, 10)

    def test_roll_cpr_d10_explosion_only_on_10(self):
        """Explosion roll only happens when base is 10."""
        for _ in range(100):
            total, base, explosion = roll_cpr_d10()
            if base != 10 and base != 1:
                self.assertIsNone(explosion)

    def test_format_cpr_d10_result_normal(self):
        """Format normal roll (no explosion/implosion)."""
        result = format_cpr_d10_result(5, 5, None, 3)
        self.assertEqual(result, "(5)")

    def test_format_cpr_d10_result_explosion(self):
        """Format exploding roll."""
        result = format_cpr_d10_result(16, 10, 6, 0)
        self.assertEqual(result, "(10->10!+6)")

    def test_format_cpr_d10_result_implosion(self):
        """Format imploding roll with luck display."""
        result = format_cpr_d10_result(-4, 1, 5, 2)
        # Total: 1 - 5 + 2 = -2, Luck: 1 + 2 = 3
        self.assertIn("1->1!-5", result)
        self.assertIn("[Luck?", result)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cpr_mode.py -v`
Expected: FAIL with ImportError (functions don't exist yet)

**Step 3: Implement roll_cpr_d10 and format_cpr_d10_result**

Add to `chimeradice_core.py` (after the weighted rolling functions, around line 350):

```python
# --- CPR MODE FUNCTIONS ---

def roll_cpr_d10() -> Tuple[int, int, Optional[int]]:
    """Roll a d10 with CPR explosion/implosion rules.

    Returns:
        Tuple of (total, base_roll, explosion_roll)
        - explosion_roll is positive for explosions (base=10)
        - explosion_roll is negative for implosions (base=1)
        - explosion_roll is None for normal rolls (2-9)
    """
    base_roll = random.randint(1, 10)

    if base_roll == 10:
        # Exploding 10 - add another d10
        explosion = random.randint(1, 10)
        return (base_roll + explosion, base_roll, explosion)
    elif base_roll == 1:
        # Imploding 1 - subtract another d10
        implosion = random.randint(1, 10)
        return (base_roll - implosion, base_roll, -implosion)
    else:
        # Normal roll
        return (base_roll, base_roll, None)


def format_cpr_d10_result(total: int, base_roll: int, explosion_roll: Optional[int], modifier: int) -> str:
    """Format CPR d10 result for display.

    Args:
        total: Final total including modifier
        base_roll: The initial d10 result (1-10)
        explosion_roll: Positive for explosion, negative for implosion, None for normal
        modifier: The modifier applied to the roll

    Returns:
        Formatted string like "(5)", "(10->10!+6)", or "(1->1!-5)" with luck display
    """
    if explosion_roll is None:
        # Normal roll
        return f"({base_roll})"
    elif explosion_roll > 0:
        # Explosion (base was 10)
        return f"(10->10!+{explosion_roll})"
    else:
        # Implosion (base was 1)
        implosion_value = abs(explosion_roll)
        luck_total = 1 + modifier
        luck_breakdown = f"1+{modifier}" if modifier >= 0 else f"1{modifier}"
        return f"(1->1!-{implosion_value}) [Luck? **{luck_total}** ({luck_breakdown})]"
```

**Step 4: Add to exports in chimeradice_core.py**

The functions are already in the file, no separate export needed for internal tests.

**Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_cpr_mode.py -v`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add chimeradice_core.py tests/test_cpr_mode.py
git commit -m "feat: add CPR d10 rolling and formatting functions"
```

---

## Task 5: Add CPR d6 Critical Logic (Core Function)

**Files:**
- Modify: `chimeradice_core.py`
- Modify: `tests/test_cpr_mode.py`

**Step 1: Write failing test for CPR d6 critical**

Add to `tests/test_cpr_mode.py`:

```python
from chimeradice_core import check_cpr_d6_critical, format_cpr_d6_result


class TestCPRd6Critical(unittest.TestCase):
    """Test CPR d6 critical damage mechanics."""

    def test_check_critical_two_sixes(self):
        """Two sixes triggers critical."""
        self.assertTrue(check_cpr_d6_critical([6, 6]))
        self.assertTrue(check_cpr_d6_critical([6, 4, 6]))
        self.assertTrue(check_cpr_d6_critical([6, 6, 6]))

    def test_check_critical_one_six(self):
        """One six does not trigger critical."""
        self.assertFalse(check_cpr_d6_critical([6, 4, 3]))
        self.assertFalse(check_cpr_d6_critical([6, 5]))

    def test_check_critical_no_sixes(self):
        """No sixes does not trigger critical."""
        self.assertFalse(check_cpr_d6_critical([5, 4, 3]))
        self.assertFalse(check_cpr_d6_critical([1, 2]))

    def test_format_cpr_d6_result_critical(self):
        """Format critical damage result."""
        # 3d6 rolling [6, 4, 6] = 16, +5 crit = 21
        result = format_cpr_d6_result([6, 4, 6], 0, is_critical=True)
        self.assertIn("**+5**", result)
        self.assertIn("Critical Damage", result)

    def test_format_cpr_d6_result_normal(self):
        """Format normal damage result (no critical)."""
        result = format_cpr_d6_result([6, 4, 3], 0, is_critical=False)
        self.assertNotIn("+5", result)
        self.assertNotIn("Critical", result)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cpr_mode.py::TestCPRd6Critical -v`
Expected: FAIL with ImportError

**Step 3: Implement check_cpr_d6_critical and format_cpr_d6_result**

Add to `chimeradice_core.py` after the d10 functions:

```python
def check_cpr_d6_critical(dice_results: List[int]) -> bool:
    """Check if d6 pool roll is a critical (2+ sixes).

    Args:
        dice_results: List of individual d6 results

    Returns:
        True if 2 or more dice show 6
    """
    return dice_results.count(6) >= 2


def format_cpr_d6_result(dice_results: List[int], modifier: int, is_critical: bool) -> str:
    """Format CPR d6 result with optional critical damage.

    Args:
        dice_results: List of individual d6 results
        modifier: The modifier applied to the roll
        is_critical: Whether this is a critical damage roll

    Returns:
        Formatted suffix string like "**+5** = **21** Critical Damage" or ""
    """
    if is_critical:
        base_total = sum(dice_results) + modifier
        crit_total = base_total + 5
        return f" **+5** = **{crit_total}** Critical Damage"
    else:
        return ""
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cpr_mode.py::TestCPRd6Critical -v`
Expected: All tests pass.

**Step 5: Run full test suite**

Run: `python run_tests.py`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add chimeradice_core.py tests/test_cpr_mode.py
git commit -m "feat: add CPR d6 critical damage detection and formatting"
```

---

## Task 6: Integrate CPR Mode into Roll Execution

**Files:**
- Modify: `chimeradice.py:102-202` (_execute_roll method)
- Modify: `chimeradice.py:12-40` (imports)

**Step 1: Add imports for CPR functions**

Update imports in `chimeradice.py`:

```python
from .chimeradice_core import (
    # ... existing imports ...
    # CPR mode functions
    roll_cpr_d10,
    format_cpr_d10_result,
    check_cpr_d6_critical,
    format_cpr_d6_result,
)
```

**Step 2: Add CPR d10 detection helper**

Add new method after `_execute_roll` (around line 203):

```python
    def _is_simple_d10_roll(self, dice_expr: str) -> bool:
        """Check if expression is a simple 1d10+X roll for CPR mode."""
        # Match: d10, 1d10, d10+5, 1d10-3, 1d10+5+2, etc.
        # Must be exactly 1 d10, not 2d10 or 3d10
        pattern = r'^1?d10([+-]\d+)*$'
        return bool(re.match(pattern, dice_expr.lower().replace(' ', '')))

    def _is_simple_d6_pool(self, dice_expr: str) -> Tuple[bool, int]:
        """Check if expression is a simple Nd6+X roll for CPR mode.

        Returns:
            Tuple of (is_d6_pool, num_dice)
        """
        # Match: 2d6, 3d6+2, 4d6-1, etc. Must be 2+ d6.
        pattern = r'^(\d+)d6([+-]\d+)*$'
        match = re.match(pattern, dice_expr.lower().replace(' ', ''))
        if match:
            num_dice = int(match.group(1))
            if num_dice >= 2:
                return (True, num_dice)
        return (False, 0)
```

**Step 3: Add CPR d10 roll handler**

Add new method:

```python
    async def _handle_cpr_d10_roll(self, ctx: commands.Context, dice_expr: str, label: Optional[str]):
        """Handle a d10 roll with CPR explosion/implosion."""
        # Parse modifier from expression
        modifier = 0
        expr_lower = dice_expr.lower().replace(' ', '')

        # Extract modifier (everything after d10)
        d10_idx = expr_lower.find('d10')
        if d10_idx != -1:
            modifier_str = expr_lower[d10_idx + 3:]
            if modifier_str:
                # Evaluate the modifier expression (e.g., "+5+2" -> 7)
                try:
                    modifier = eval(modifier_str)
                except:
                    modifier = 0

        # Roll with CPR rules
        dice_total, base_roll, explosion_roll = roll_cpr_d10()
        final_total = dice_total + modifier

        # Format the result
        dice_display = format_cpr_d10_result(final_total, base_roll, explosion_roll, modifier)

        # Build modifier display string
        modifier_display = ""
        if modifier > 0:
            modifier_display = f" + {modifier}"
        elif modifier < 0:
            modifier_display = f" - {abs(modifier)}"

        # Format output matching existing style
        emoji = self._get_roll_emoji("standard")
        roll_display = f"`{dice_expr}`" if label is None else f"`{dice_expr}` ({label})"

        # Build result string
        if explosion_roll is not None and explosion_roll < 0:
            # Implosion - special format with luck display
            implosion_value = abs(explosion_roll)
            luck_total = 1 + modifier
            luck_breakdown = f"1+{modifier}" if modifier >= 0 else f"1{modifier}"
            result_str = f"1d10 (1->1!-{implosion_value}){modifier_display} = {dice_total + modifier}"
            output = f"{emoji} **{ctx.author.display_name}** rolls {roll_display}...\n"
            output += f"Result: {result_str} = **{final_total}** [Luck? **{luck_total}** ({luck_breakdown})]"
        elif explosion_roll is not None:
            # Explosion
            result_str = f"1d10 (10->10!+{explosion_roll}){modifier_display} = {dice_total + modifier}"
            output = f"{emoji} **{ctx.author.display_name}** rolls {roll_display}...\n"
            output += f"Result: {result_str} = **{final_total}**"
        else:
            # Normal roll
            result_str = f"1d10 ({base_roll}){modifier_display} = {final_total}"
            output = f"{emoji} **{ctx.author.display_name}** rolls {roll_display}...\n"
            output += f"Result: {result_str} = **{final_total}**"

        await ctx.send(output)
        return final_total
```

**Step 4: Add CPR d6 roll handler**

Add new method:

```python
    async def _handle_cpr_d6_roll(self, ctx: commands.Context, dice_expr: str, num_dice: int, label: Optional[str]):
        """Handle a d6 pool roll with CPR critical damage."""
        # Parse modifier
        modifier = 0
        expr_lower = dice_expr.lower().replace(' ', '')

        d6_idx = expr_lower.find('d6')
        if d6_idx != -1:
            modifier_str = expr_lower[d6_idx + 2:]
            if modifier_str:
                try:
                    modifier = eval(modifier_str)
                except:
                    modifier = 0

        # Roll the dice
        dice_results = [random.randint(1, 6) for _ in range(num_dice)]
        dice_total = sum(dice_results)

        # Check for critical
        is_critical = check_cpr_d6_critical(dice_results)
        crit_bonus = 5 if is_critical else 0
        final_total = dice_total + modifier + crit_bonus

        # Format dice display (bold the 6s like d20 library does)
        dice_display_parts = []
        for d in dice_results:
            if d == 6:
                dice_display_parts.append(f"**{d}**")
            else:
                dice_display_parts.append(str(d))
        dice_display = ", ".join(dice_display_parts)

        # Build modifier display
        modifier_display = ""
        if modifier > 0:
            modifier_display = f" + {modifier}"
        elif modifier < 0:
            modifier_display = f" - {abs(modifier)}"

        # Format output
        emoji = self._get_roll_emoji("standard")
        roll_display = f"`{dice_expr}`" if label is None else f"`{dice_expr}` ({label})"

        base_total = dice_total + modifier
        if is_critical:
            result_str = f"{num_dice}d6 ({dice_display}){modifier_display} = {base_total} **+5** = **{final_total}** Critical Damage"
        else:
            result_str = f"{num_dice}d6 ({dice_display}){modifier_display} = {base_total} = **{final_total}**"

        output = f"{emoji} **{ctx.author.display_name}** rolls {roll_display}...\n"
        output += f"Result: {result_str}"

        await ctx.send(output)
        return final_total
```

**Step 5: Integrate CPR check into _execute_roll**

Modify `_execute_roll` to check for CPR mode after the special dice type checks (around line 150).

After line 150 (`return`), add:

```python
            # Check for CPR mode
            cpr_enabled = await self.config.channel(ctx.channel).cpr_mode()
            if cpr_enabled:
                # Check if this is a simple d10 roll
                if self._is_simple_d10_roll(dice_expr):
                    await self._handle_cpr_d10_roll(ctx, dice_expr, label)
                    return

                # Check if this is a d6 pool roll
                is_d6_pool, num_dice = self._is_simple_d6_pool(dice_expr)
                if is_d6_pool:
                    await self._handle_cpr_d6_roll(ctx, dice_expr, num_dice, label)
                    return
```

**Step 6: Test manually**

1. `>cpr enable`
2. `>roll 1d10+5` - should show normal or explosion/implosion
3. `>roll 3d6` - should show critical if 2+ sixes
4. `>cpr disable`
5. `>roll 1d10+5` - should show normal (no explosion)

**Step 7: Commit**

```bash
git add chimeradice.py
git commit -m "feat: integrate CPR mode into roll execution"
```

---

## Task 7: Add Initiative Command Group

**Files:**
- Modify: `chimeradice.py` (add after CPR commands)

**Step 1: Add initiative command group and add command**

```python
    # --- INITIATIVE COMMANDS ---

    @commands.group(name="init", invoke_without_command=True)
    async def init(self, ctx: commands.Context):
        """Initiative tracking commands for Cyberpunk Red."""
        await ctx.send_help(ctx.command)

    @init.command(name="add")
    async def init_add(self, ctx: commands.Context, name: str, *, modifier: str):
        """Add a character to initiative.

        Examples:
            >init add Darius 14+2
            >init add "Goon #1" +8
            >init add Sasha -2
        """
        # Parse and validate the modifier expression
        modifier_expr = modifier.strip()

        # Strip leading + for display (but keep leading -)
        display_expr = modifier_expr.lstrip('+')

        # Evaluate the modifier
        try:
            # Safe evaluation - only allow digits, +, -, and spaces
            clean_expr = modifier_expr.replace(' ', '')
            if not re.match(r'^[+-]?\d+([+-]\d+)*$', clean_expr):
                await ctx.send("Invalid modifier. Use numbers and +/- operators (e.g., `14+2`, `-3`).")
                return
            modifier_total = eval(clean_expr)
        except Exception:
            await ctx.send("Invalid modifier. Use numbers and +/- operators (e.g., `14+2`, `-3`).")
            return

        # Get current initiative group
        init_group = await self.config.channel(ctx.channel).initiative_group()

        # Add/update character (case-insensitive key, preserve display name)
        name_key = name.lower()

        # Check if updating existing
        is_update = name_key in {k.lower() for k in init_group.keys()}

        # Remove old entry if exists (case-insensitive)
        init_group = {k: v for k, v in init_group.items() if k.lower() != name_key}

        # Add new entry
        init_group[name] = {
            "modifier_expr": display_expr,
            "modifier_total": modifier_total
        }

        await self.config.channel(ctx.channel).initiative_group.set(init_group)

        action = "updated" if is_update else "added"
        await ctx.send(f"**{name}** {action} to initiative with modifier {display_expr} (total: {modifier_total:+d}).")

    @init.command(name="remove")
    async def init_remove(self, ctx: commands.Context, *, name: str):
        """Remove a character from initiative."""
        init_group = await self.config.channel(ctx.channel).initiative_group()

        # Find case-insensitive match
        name_key = name.lower()
        matched_name = None
        for existing_name in init_group.keys():
            if existing_name.lower() == name_key:
                matched_name = existing_name
                break

        if matched_name is None:
            await ctx.send(f"Character **{name}** not found in initiative.")
            return

        del init_group[matched_name]
        await self.config.channel(ctx.channel).initiative_group.set(init_group)
        await ctx.send(f"**{matched_name}** removed from initiative.")

    @init.command(name="clear")
    async def init_clear(self, ctx: commands.Context):
        """Clear all characters from initiative."""
        await self.config.channel(ctx.channel).initiative_group.set({})
        await ctx.send("Initiative group cleared.")

    @init.command(name="list")
    async def init_list(self, ctx: commands.Context):
        """Show current initiative group (without rolling)."""
        init_group = await self.config.channel(ctx.channel).initiative_group()

        if not init_group:
            await ctx.send("No characters in initiative. Use `>init add NAME MOD` to add some.")
            return

        lines = ["**Initiative Group:**"]
        for name, data in sorted(init_group.items(), key=lambda x: x[1]["modifier_total"], reverse=True):
            lines.append(f"- {name} ({data['modifier_expr']})")

        await ctx.send("\n".join(lines))
```

**Step 2: Test add/remove/clear/list manually**

1. `>init add Darius 14+2`
2. `>init add James +12-1`
3. `>init list`
4. `>init remove Darius`
5. `>init clear`

**Step 3: Commit**

```bash
git add chimeradice.py
git commit -m "feat: add initiative add/remove/clear/list commands"
```

---

## Task 8: Add Initiative Roll Command

**Files:**
- Modify: `chimeradice.py`

**Step 1: Add the roll command**

Add to the init command group:

```python
    @init.command(name="roll")
    async def init_roll(self, ctx: commands.Context):
        """Roll initiative for all characters."""
        init_group = await self.config.channel(ctx.channel).initiative_group()

        if not init_group:
            await ctx.send("No characters in initiative. Use `>init add NAME MOD` to add some.")
            return

        # Roll for each character
        results = []
        for name, data in init_group.items():
            modifier_total = data["modifier_total"]
            modifier_expr = data["modifier_expr"]

            # Roll d10 with explosion
            base_roll = random.randint(1, 10)
            explosion = None

            if base_roll == 10:
                explosion = random.randint(1, 10)
                dice_total = base_roll + explosion
                dice_display = f"1d10->10!+{explosion}"
            else:
                dice_total = base_roll
                dice_display = f"1d10"

            final_total = dice_total + modifier_total

            # Format the breakdown
            if explosion is not None:
                breakdown = f"({dice_display} +{modifier_expr})"
            else:
                breakdown = f"({dice_display}+{modifier_expr})"

            results.append({
                "name": name,
                "total": final_total,
                "breakdown": breakdown
            })

        # Sort by total, highest first
        results.sort(key=lambda x: x["total"], reverse=True)

        # Format output
        lines = ["**Initiative Round**"]
        for i, result in enumerate(results, 1):
            lines.append(f"{i}. {result['name']} [{result['total']}] {result['breakdown']}")

        await ctx.send("\n".join(lines))
```

**Step 2: Test manually**

1. `>init add Darius 14+2`
2. `>init add James 12-1`
3. `>init add "Goon #1" 4`
4. `>init roll` (run multiple times to see explosions)

**Step 3: Commit**

```bash
git add chimeradice.py
git commit -m "feat: add initiative roll command with exploding d10s"
```

---

## Task 9: Write Integration Tests for CPR Mode

**Files:**
- Modify: `tests/test_cpr_mode.py`

**Step 1: Add more comprehensive tests**

Add to `tests/test_cpr_mode.py`:

```python
class TestCPRPatternMatching(unittest.TestCase):
    """Test pattern matching for CPR mode triggers."""

    def test_simple_d10_patterns(self):
        """Test _is_simple_d10_roll pattern matching."""
        # These should match
        valid_patterns = ['d10', '1d10', 'd10+5', '1d10+5', '1d10-3', '1d10+5+2', 'd10+10-2']

        # These should NOT match
        invalid_patterns = ['2d10', '3d10+5', '1d10kh', '1d10+1d6', '10d10', 'd100']

        # Test patterns using regex directly
        import re
        pattern = r'^1?d10([+-]\d+)*$'

        for expr in valid_patterns:
            self.assertTrue(
                bool(re.match(pattern, expr.lower().replace(' ', ''))),
                f"'{expr}' should match d10 pattern"
            )

        for expr in invalid_patterns:
            self.assertFalse(
                bool(re.match(pattern, expr.lower().replace(' ', ''))),
                f"'{expr}' should NOT match d10 pattern"
            )

    def test_simple_d6_pool_patterns(self):
        """Test _is_simple_d6_pool pattern matching."""
        import re
        pattern = r'^(\d+)d6([+-]\d+)*$'

        # Valid d6 pools (2+ dice)
        valid = [('2d6', 2), ('3d6', 3), ('4d6+2', 4), ('2d6-1', 2), ('10d6', 10)]

        # Invalid (1 die or not d6)
        invalid = ['1d6', 'd6', '1d6+5', '2d8', '3d10', '2d6+1d6']

        for expr, expected_dice in valid:
            match = re.match(pattern, expr.lower().replace(' ', ''))
            self.assertIsNotNone(match, f"'{expr}' should match")
            self.assertEqual(int(match.group(1)), expected_dice)

        for expr in invalid:
            match = re.match(pattern, expr.lower().replace(' ', ''))
            if match:
                num_dice = int(match.group(1))
                self.assertLess(num_dice, 2, f"'{expr}' should not be valid d6 pool")


class TestModifierParsing(unittest.TestCase):
    """Test modifier expression parsing for initiative."""

    def test_valid_modifiers(self):
        """Test valid modifier expressions."""
        test_cases = [
            ('14+2', 16),
            ('+14+2', 16),
            ('12-1', 11),
            ('-2', -2),
            ('8', 8),
            ('+8', 8),
            ('10+5-3', 12),
        ]

        for expr, expected in test_cases:
            clean = expr.replace(' ', '')
            result = eval(clean)
            self.assertEqual(result, expected, f"'{expr}' should evaluate to {expected}")

    def test_display_stripping(self):
        """Test that leading + is stripped for display."""
        test_cases = [
            ('+14+2', '14+2'),
            ('14+2', '14+2'),
            ('-2', '-2'),
            ('+8', '8'),
        ]

        for expr, expected in test_cases:
            display = expr.strip().lstrip('+')
            self.assertEqual(display, expected)
```

**Step 2: Run all CPR tests**

Run: `python -m pytest tests/test_cpr_mode.py -v`
Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/test_cpr_mode.py
git commit -m "test: add integration tests for CPR mode patterns"
```

---

## Task 10: Update CLAUDE.md Documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add CPR mode and initiative documentation**

Add new section after "Commands Reference":

```markdown
## CPR Mode (Cyberpunk Red)

### Toggle Commands
- `>cpr enable` / `>cpr on` - Enable CPR mode for this channel
- `>cpr disable` / `>cpr off` - Disable CPR mode for this channel
- `>cpr status` - Show current CPR mode state

### d10 Behavior (Skill Checks)
When CPR mode is enabled, `1d10+X` rolls use Cyberpunk Red rules:
- **Exploding 10**: Roll 10 → roll another d10 and add it
- **Imploding 1**: Roll 1 → roll another d10 and subtract it, shows Luck escape option
- Display: `1d10 (10→10!+6) + 5 = 21` or `1d10 (1→1!-7) + 5 = -1 [Luck? **6** (1+5)]`

### d6 Behavior (Damage Rolls)
When rolling 2+ d6 in CPR mode:
- **Critical Damage**: 2+ dice showing 6 adds +5 to total
- Display: `3d6 (**6**, 4, **6**) = 16 **+5** = **21** Critical Damage`

## Initiative System

### Commands
- `>init add NAME MOD` - Add character with modifier (e.g., `>init add Darius 14+2`)
- `>init remove NAME` - Remove a character
- `>init roll` - Roll initiative for all, sorted highest to lowest
- `>init clear` - Clear all characters
- `>init list` - Show current group without rolling

### Features
- Per-channel storage (persisted)
- Exploding 10s on initiative rolls
- Case-insensitive name matching
- Supports modifier expressions like `14+2`, `+8`, `-3`
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CPR mode and initiative system to CLAUDE.md"
```

---

## Task 11: Update run_tests.py to Include CPR Tests

**Files:**
- Modify: `run_tests.py`

**Step 1: Add CPR test imports**

Add to the test loading section:

```python
    # Load CPR mode tests
    try:
        from test_cpr_mode import (
            TestCPRd10Rolling,
            TestCPRd6Critical,
            TestCPRPatternMatching,
            TestModifierParsing,
        )

        suite.addTests(loader.loadTestsFromTestCase(TestCPRd10Rolling))
        suite.addTests(loader.loadTestsFromTestCase(TestCPRd6Critical))
        suite.addTests(loader.loadTestsFromTestCase(TestCPRPatternMatching))
        suite.addTests(loader.loadTestsFromTestCase(TestModifierParsing))

        print("✓ Loaded CPR mode tests (4 test classes)")
    except ImportError as e:
        print(f"✗ Failed to load CPR tests: {e}")
```

**Step 2: Run full test suite**

Run: `python run_tests.py`
Expected: All tests pass including new CPR tests.

**Step 3: Commit**

```bash
git add run_tests.py
git commit -m "test: add CPR mode tests to test runner"
```

---

## Task 12: Final Verification

**Step 1: Run complete test suite**

Run: `python run_tests.py`
Expected: All tests pass.

**Step 2: Manual end-to-end testing**

1. Start bot or reload cog
2. `>cpr enable`
3. `>roll 1d10+5` (test multiple times for explosions/implosions)
4. `>roll 3d6` (test multiple times for crits)
5. `>roll 2d20kh` (should work normally, not affected by CPR)
6. `>init add Darius 14+2`
7. `>init add James +12-1`
8. `>init add "Goon #1" 4`
9. `>init roll`
10. `>init remove James`
11. `>init roll`
12. `>init clear`
13. `>cpr disable`
14. `>roll 1d10+5` (should be normal now)

**Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete CPR mode and initiative system implementation"
```

---

## Summary

This plan implements:
1. **CPR Mode** - Channel toggle with exploding d10s and critical d6 damage
2. **Initiative System** - Batch rolling with per-channel persistence
3. **Tests** - Comprehensive unit and integration tests
4. **Documentation** - Updated CLAUDE.md

Total estimated tasks: 12
Total estimated commits: 12
