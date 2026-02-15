"""
ChimeraDice Core Module

Pure functions extracted for testability. No Discord or async dependencies.
This module can be imported and tested without the Red-Bot framework.
"""

import re
import random
from typing import List, Dict, Tuple, Optional

# --- CONSTANTS ---

DEFAULT_GUILD_USER = {
    "toggles": {
        "luckmode_on": False,
        "karmamode_on": False,
    },
    "set_luck": 50,
    "current_karma": 0,  # Legacy - kept for backward compatibility
    "percentile_debt": 0.0,  # New karma system - accumulated difference from 50th percentile
    "stats": {
        "server_wide": {
            "standard_rolls": [],
            "luck_rolls": [],
            "karma_rolls": [],
            "natural_luck": 50.0,  # Start at 50th percentile
            "percentile_history": [],
            "total_rolls": 0,
        },
        "campaigns": {},
    },
}

DEFAULT_GUILD = {
    "campaigns": {},
    "users": {},
}

DEFAULT_CHANNEL = {
    "cpr_mode": False,
    "initiative_group": {},  # {name: {"modifier_expr": "14+2", "modifier_total": 16}}
}

# Fallout damage dice faces
FALLOUT_FACES = ["1", "2", "0", "0", "1E", "1E"]

# Fudge dice faces
FUDGE_FACES = [-1, 0, 1]

# Precomputed fudge dice sum probabilities for 1-6 dice
FUDGE_PROBABILITIES = {
    1: {-1: 1/3, 0: 1/3, 1: 1/3},
    2: {-2: 1/9, -1: 2/9, 0: 3/9, 1: 2/9, 2: 1/9},
    3: {-3: 1/27, -2: 3/27, -1: 6/27, 0: 7/27, 1: 6/27, 2: 3/27, 3: 1/27},
    4: {-4: 1/81, -3: 4/81, -2: 10/81, -1: 16/81, 0: 19/81, 1: 16/81, 2: 10/81, 3: 4/81, 4: 1/81},
    5: {-5: 1/243, -4: 5/243, -3: 15/243, -2: 30/243, -1: 45/243, 0: 51/243, 1: 45/243, 2: 30/243, 3: 15/243, 4: 5/243, 5: 1/243},
    6: {-6: 1/729, -5: 6/729, -4: 21/729, -3: 50/729, -2: 90/729, -1: 126/729, 0: 141/729, 1: 126/729, 2: 90/729, 3: 50/729, 4: 21/729, 5: 6/729, 6: 1/729}
}


# --- RESULT CLASSES ---

class DiceRollResult:
    """Mock result object for weighted dice rolls with individual dice display."""
    def __init__(self, total: int, dice_results: List[int], modifier: int):
        self.total = total
        dice_str = ', '.join(map(str, dice_results))
        if len(dice_results) > 1:
            dice_display = f"({dice_str})"
        else:
            dice_display = str(dice_results[0])

        if modifier != 0:
            modifier_str = f" {modifier:+d}" if modifier < 0 else f" +{modifier}"
            self.result = f"{dice_display}{modifier_str} = {total}"
        else:
            self.result = f"{dice_display} = {total}"


class SimpleRollResult:
    """Mock result object for queued rolls with pre-formatted result string."""
    def __init__(self, total: int, result_str: str):
        self.total = total
        self.result = result_str


# --- PERCENTILE FUNCTIONS ---

def single_die_percentile(result: int, die_size: int) -> Optional[float]:
    """Calculate percentile for a single die roll."""
    if result < 1 or result > die_size:
        return None

    # For a single die, percentile is (result - 0.5) / die_size * 100
    # Subtract 0.5 to get midpoint of the result's range
    return ((result - 0.5) / die_size) * 100


def multiple_dice_percentile(result: int, num_dice: int, die_size: int) -> Optional[float]:
    """Calculate percentile for multiple dice of same type."""
    min_result = num_dice
    max_result = num_dice * die_size

    if result < min_result or result > max_result:
        return None

    # For multiple dice, approximate using normal distribution
    # This is an approximation - true calculation would require probability tables
    mean = num_dice * (die_size + 1) / 2

    # Rough approximation of percentile
    if result <= mean:
        # Below average
        percentile = ((result - min_result) / (mean - min_result)) * 50
    else:
        # Above average
        percentile = 50 + ((result - mean) / (max_result - mean)) * 50

    return max(0, min(100, percentile))


def calculate_fudge_percentile(roll_string: str, result: int) -> Optional[float]:
    """Calculate percentile for fudge dice results."""
    # Extract number of dice from roll string
    match = re.match(r'(\d+)df?', roll_string.lower().split('+')[0].split('-')[0])
    if not match:
        return None

    num_dice = int(match.group(1))
    min_result = -num_dice
    max_result = num_dice

    if result < min_result or result > max_result:
        return None

    # Fudge dice follow a triangular/binomial distribution
    # For 4dF: -4(1.2%), -3(4.9%), -2(12.3%), -1(19.8%), 0(23.5%), +1(19.8%), +2(12.3%), +3(4.9%), +4(1.2%)
    # Approximate percentile calculation
    range_size = max_result - min_result
    position = (result - min_result) / range_size

    # Adjust for bell curve distribution (fudge dice are more likely to be near 0)
    if result == 0:
        percentile = 50  # Exactly at median
    elif result > 0:
        # Positive results
        percentile = 50 + (position - 0.5) * 100 * 0.8  # Slightly compressed
    else:
        # Negative results
        percentile = position * 100 * 0.8  # Slightly compressed

    return max(0, min(100, percentile))


def estimate_keep_percentile(roll_string: str, result: int, num_dice: int, die_size: int) -> Optional[float]:
    """Estimate percentile for keep highest/lowest operations."""
    # Extract keep/drop parameters (numbers are optional, default to 1)
    kh_match = re.search(r'kh(\d*)', roll_string.lower())
    kl_match = re.search(r'kl(\d*)', roll_string.lower())
    dh_match = re.search(r'dh(\d*)', roll_string.lower())
    dl_match = re.search(r'dl(\d*)', roll_string.lower())

    if kh_match:
        # Keep highest X dice (default to 1 if not specified)
        keep_count = int(kh_match.group(1)) if kh_match.group(1) else 1
        # For keep highest, the range is from keep_count to keep_count * die_size
        min_result = keep_count
        max_result = keep_count * die_size

        # Approximate percentile (keep highest skews toward higher values)
        if result < min_result or result > max_result:
            return None

        # Keep highest operations have higher probability for higher results
        range_position = (result - min_result) / (max_result - min_result)
        # Apply a power curve to account for the bias toward higher values
        percentile = (range_position ** 0.7) * 100

    elif kl_match:
        # Keep lowest X dice (default to 1 if not specified)
        keep_count = int(kl_match.group(1)) if kl_match.group(1) else 1
        min_result = keep_count
        max_result = keep_count * die_size

        if result < min_result or result > max_result:
            return None

        # Keep lowest operations have higher probability for lower results
        range_position = (result - min_result) / (max_result - min_result)
        # Apply an inverse power curve to account for the bias toward lower values
        percentile = (range_position ** 1.4) * 100

    elif dh_match:
        # Drop highest X dice (default to 1 if not specified)
        # Equivalent to keep lowest Y where Y = num_dice - X
        drop_count = int(dh_match.group(1)) if dh_match.group(1) else 1
        keep_count = num_dice - drop_count
        min_result = keep_count
        max_result = keep_count * die_size

        if result < min_result or result > max_result:
            return None

        # Drop highest = keep lowest, so bias toward lower results
        range_position = (result - min_result) / (max_result - min_result)
        percentile = (range_position ** 1.4) * 100

    elif dl_match:
        # Drop lowest X dice (default to 1 if not specified)
        # Equivalent to keep highest Y where Y = num_dice - X
        drop_count = int(dl_match.group(1)) if dl_match.group(1) else 1
        keep_count = num_dice - drop_count
        min_result = keep_count
        max_result = keep_count * die_size

        if result < min_result or result > max_result:
            return None

        # Drop lowest = keep highest, so bias toward higher results
        range_position = (result - min_result) / (max_result - min_result)
        percentile = (range_position ** 0.7) * 100

    else:
        # Fallback for other operations
        return multiple_dice_percentile(result, num_dice, die_size)

    return max(0, min(100, percentile))


def calculate_roll_percentile(roll_string: str, result: int) -> Optional[float]:
    """Calculate percentile rank for a roll result.

    Returns None for unsupported dice types or invalid inputs.
    """
    try:
        # Handle special dice types
        if 'df' in roll_string.lower():
            return calculate_fudge_percentile(roll_string, result)
        elif 'dd' in roll_string.lower():
            return None  # Skip Fallout dice for now (complex distribution)

        # Check if this uses advanced d20 operations
        has_advanced = bool(re.search(r'(kh|kl|dh|dl|ro|rr|ra|e|mi|ma|p)\d*', roll_string.lower()))

        if has_advanced:
            # For advanced operations, we'll use a simplified approach
            # Extract the base dice and use broad estimates
            base_dice = extract_base_dice(roll_string)
            match = re.match(r'(\d+)d(\d+)', base_dice.lower())
            if match:
                num_dice = int(match.group(1))
                die_size = int(match.group(2))

                # For operations like kh3 on 4d6, estimate based on modified range
                if 'kh' in roll_string.lower() or 'kl' in roll_string.lower():
                    # Keep operations - approximate the new range
                    return estimate_keep_percentile(roll_string, result, num_dice, die_size)
                else:
                    # Other advanced operations - use basic calculation as fallback
                    if num_dice == 1:
                        return single_die_percentile(result, die_size)
                    else:
                        return multiple_dice_percentile(result, num_dice, die_size)

        # Simple regex parsing for standard dice (more reliable than d20 library parsing)
        # Match patterns like: 1d20, 3d6, 5d20+2, 2d10-1
        match = re.match(r'(\d+)d(\d+)(?:[+-]\d+)?', roll_string.lower())

        if match:
            num_dice = int(match.group(1))
            die_size = int(match.group(2))

            # Calculate percentile for single die
            if num_dice == 1:
                return single_die_percentile(result, die_size)
            # Calculate percentile for multiple dice (sum)
            elif num_dice > 1:
                return multiple_dice_percentile(result, num_dice, die_size)

        return None

    except Exception:
        return None


# --- PARSING/VALIDATION FUNCTIONS ---

def parse_dice_modifiers(expression: str) -> Tuple[str, int]:
    """Parse dice expression with multiple modifiers.

    Examples:
    - "4df+5+2-1" -> ("4df", 6)
    - "1d20+3-2+1" -> ("1d20", 2)
    - "4df" -> ("4df", 0)
    """
    # Find the dice part (everything before first + or -)
    dice_match = re.match(r'([^+-]+)', expression)
    if not dice_match:
        return expression, 0

    dice_part = dice_match.group(1)
    modifier_part = expression[len(dice_part):]

    if not modifier_part:
        return dice_part, 0

    # Parse all modifiers using regex
    # This finds patterns like +5, -3, +2, etc.
    modifier_matches = re.findall(r'([+-])(\d+)', modifier_part)

    total_modifier = 0
    for sign, value in modifier_matches:
        if sign == '+':
            total_modifier += int(value)
        else:  # sign == '-'
            total_modifier -= int(value)

    return dice_part, total_modifier


def validate_dice_expression(expression: str) -> Tuple[bool, str]:
    """Validate dice expression for safety and sanity.

    Returns (is_valid, error_message)
    """
    if not expression or len(expression) > 150:  # Increased for advanced operations
        return False, "Dice expression too long (max 150 characters)"

    # Check for basic safety limits
    # Find all numbers in the expression (but exclude those in advanced operators)
    # Remove advanced operation patterns first to avoid false positives
    temp_expr = expression
    for pattern in [r'[<>]\d+', r'(kh|kl|dh|dl|ro|rr|ra|e|mi|ma|p)\d*']:
        temp_expr = re.sub(pattern, '', temp_expr, flags=re.IGNORECASE)

    numbers = re.findall(r'\d+', temp_expr)

    for num_str in numbers:
        num = int(num_str)

        # Reasonable limits to prevent abuse
        if num > 1000:
            return False, f"Number too large: {num} (max 1000)"
        if num < 0:
            return False, f"Negative numbers not allowed: {num}"

    # Check for reasonable dice patterns
    dice_patterns = re.findall(r'(\d+)d(\d+)', expression.lower())
    for num_dice, die_size in dice_patterns:
        num_dice, die_size = int(num_dice), int(die_size)

        if num_dice > 100:
            return False, f"Too many dice: {num_dice} (max 100)"
        if die_size > 1000:
            return False, f"Die size too large: {die_size} (max 1000)"
        if die_size < 1:
            return False, f"Invalid die size: {die_size} (min 1)"

    # Check for fudge dice
    fudge_patterns = re.findall(r'(\d+)df?', expression.lower())
    for num_dice in fudge_patterns:
        if int(num_dice) > 100:
            return False, f"Too many fudge dice: {num_dice} (max 100)"

    # Check for fallout dice
    fallout_patterns = re.findall(r'(\d+)dd?', expression.lower())
    for num_dice in fallout_patterns:
        if int(num_dice) > 100:
            return False, f"Too many fallout dice: {num_dice} (max 100)"

    # Note: d20 library validation is done in the cog, not here
    # This function only does basic safety checks

    return True, ""


def normalize_dice_key(dice_expr: str) -> str:
    """Normalize a dice expression to a consistent lookup key.

    Examples:
    - "1D20" -> "1d20"
    - "d20" -> "1d20" (adds implicit 1)
    - "1d20+5" -> "1d20"
    - "4DF" -> "4df"
    - "dF" -> "1df" (adds implicit 1)
    - "3dD" -> "3dd"
    """
    # Extract just the dice part (no modifiers)
    dice_part, _ = parse_dice_modifiers(dice_expr)
    # Lowercase everything for consistency
    dice_part = dice_part.lower()

    # Add implicit "1" if dice expression starts with "d"
    if dice_part.startswith('d'):
        dice_part = '1' + dice_part

    return dice_part


def parse_roll_and_label(roll_string: str) -> Tuple[str, Optional[str]]:
    """Parse roll string into dice expression and optional label.

    Examples:
    - "1d20+5" -> ("1d20+5", None)
    - "1d20+5 perception" -> ("1d20+5", "perception")
    - "2d6 fireball damage" -> ("2d6", "fireball damage")

    Returns:
        tuple: (dice_expression, label or None)
    """
    parts = roll_string.split(None, 1)  # Split on first whitespace
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def translate_dice_syntax(expression: str) -> str:
    """Translate user-friendly dice syntax to d20 library syntax.

    Supports optional numbers (defaults to 1):
    - "2d20dl" -> "2d20kh1" (drop lowest 1 = keep highest 1)
    - "2d20dl1" -> "2d20kh1" (explicit drop lowest 1 = keep highest 1)
    - "4d6dl" -> "4d6kh3" (drop lowest 1 from 4d6 = keep highest 3)
    - "3d20dh" -> "3d20kl2" (drop highest 1 from 3d20 = keep lowest 2)
    - "2d20kh" -> "2d20kh1" (keep highest 1)
    - "2d20kl" -> "2d20kl1" (keep lowest 1)
    """
    # Handle drop lowest (dl) -> convert to keep highest (kh)
    # Match patterns like: 2d20dl, 2d20dl1, 4d6dl1+5, 3d8dl2-1
    dl_pattern = r'(\d+)d(\d+)dl(\d*)'
    def dl_to_kh(match):
        num_dice = int(match.group(1))
        die_size = match.group(2)
        drop_count = int(match.group(3)) if match.group(3) else 1  # Default to 1
        keep_count = num_dice - drop_count
        if keep_count <= 0:
            # Can't drop more dice than we have, fall back to original
            return match.group(0)
        return f"{num_dice}d{die_size}kh{keep_count}"

    expression = re.sub(dl_pattern, dl_to_kh, expression)

    # Handle drop highest (dh) -> convert to keep lowest (kl)
    # Match patterns like: 3d20dh, 3d20dh1, 5d8dh2+3
    dh_pattern = r'(\d+)d(\d+)dh(\d*)'
    def dh_to_kl(match):
        num_dice = int(match.group(1))
        die_size = match.group(2)
        drop_count = int(match.group(3)) if match.group(3) else 1  # Default to 1
        keep_count = num_dice - drop_count
        if keep_count <= 0:
            # Can't drop more dice than we have, fall back to original
            return match.group(0)
        return f"{num_dice}d{die_size}kl{keep_count}"

    expression = re.sub(dh_pattern, dh_to_kl, expression)

    # Handle keep highest (kh) with optional number
    # Match patterns like: 2d20kh, 2d20kh1, 4d6kh3+5
    kh_pattern = r'(\d+)d(\d+)kh(\d*)'
    def kh_explicit(match):
        num_dice = match.group(1)
        die_size = match.group(2)
        keep_count = match.group(3) if match.group(3) else '1'  # Default to 1
        return f"{num_dice}d{die_size}kh{keep_count}"

    expression = re.sub(kh_pattern, kh_explicit, expression)

    # Handle keep lowest (kl) with optional number
    # Match patterns like: 2d20kl, 2d20kl1, 4d6kl2+3
    kl_pattern = r'(\d+)d(\d+)kl(\d*)'
    def kl_explicit(match):
        num_dice = match.group(1)
        die_size = match.group(2)
        keep_count = match.group(3) if match.group(3) else '1'  # Default to 1
        return f"{num_dice}d{die_size}kl{keep_count}"

    expression = re.sub(kl_pattern, kl_explicit, expression)

    return expression


def extract_base_dice(expression: str) -> str:
    """Extract the base dice notation from a complex expression.

    Examples:
    - "4d6kh3+2" -> "4d6"
    - "1d20ro<3+5" -> "1d20"
    - "2d10e10mi2" -> "2d10"
    """
    # Match basic dice pattern at the start
    match = re.match(r'(\d+d\d+)', expression.lower())
    if match:
        return match.group(1)

    # Fallback to parsing dice modifiers for simple cases
    dice_part, _ = parse_dice_modifiers(expression)
    return dice_part


# --- WEIGHTED ROLLING FUNCTIONS ---

def roll_weighted_standard_die(die_size: int, debt: float) -> int:
    """Roll a single standard die with karma/luck bias using weighted probabilities."""
    if abs(debt) < 5.0:  # Activation threshold - no significant debt, roll normally
        return random.randint(1, die_size)

    # Create weights for each face
    weights = [1.0] * die_size

    # Calculate bias strength (0 to 1)
    bias_strength = min(abs(debt) / 50.0, 1.0)

    # Apply bias to weights
    midpoint = (die_size + 1) / 2
    for i in range(die_size):
        face_value = i + 1

        if debt > 0:  # Owed good luck - bias toward higher values
            if face_value > midpoint:
                weights[i] *= (1.0 + bias_strength * 0.4)  # Boost good faces
            else:
                weights[i] *= (1.0 - bias_strength * 0.2)  # Reduce bad faces
        else:  # Owed bad luck - bias toward lower values
            if face_value < midpoint:
                weights[i] *= (1.0 + bias_strength * 0.4)  # Boost bad faces
            else:
                weights[i] *= (1.0 - bias_strength * 0.2)  # Reduce good faces

    # Roll using weighted probabilities
    return random.choices(range(1, die_size + 1), weights=weights)[0]


def roll_weighted_fudge_dice(num_dice: int, debt: float) -> Tuple[List[int], int]:
    """Roll fudge dice with karma/luck bias using weighted sum distribution."""
    if abs(debt) < 5.0 or num_dice not in FUDGE_PROBABILITIES:
        # Activation threshold - no significant debt or unsupported dice count, roll normally
        dice_results = [random.choice(FUDGE_FACES) for _ in range(num_dice)]
        return dice_results, sum(dice_results)

    # Get natural probabilities for this number of dice
    natural_probs = FUDGE_PROBABILITIES[num_dice].copy()

    # Apply bias to probabilities
    bias_strength = min(abs(debt) / 75.0, 0.8)  # Max 80% bias for fudge

    for sum_value in natural_probs:
        if debt > 0:  # Owed good luck - bias toward positive sums
            if sum_value > 0:
                natural_probs[sum_value] *= (1.0 + bias_strength * 0.5)
            elif sum_value < 0:
                natural_probs[sum_value] *= (1.0 - bias_strength * 0.3)
        else:  # Owed bad luck - bias toward negative sums
            if sum_value < 0:
                natural_probs[sum_value] *= (1.0 + bias_strength * 0.5)
            elif sum_value > 0:
                natural_probs[sum_value] *= (1.0 - bias_strength * 0.3)

    # Normalize probabilities
    total_prob = sum(natural_probs.values())
    for sum_value in natural_probs:
        natural_probs[sum_value] /= total_prob

    # Roll weighted sum
    sums = list(natural_probs.keys())
    weights = list(natural_probs.values())
    target_sum = random.choices(sums, weights=weights)[0]

    # Generate realistic-looking dice faces that sum to target
    dice_results = generate_realistic_fudge_faces(num_dice, target_sum)

    return dice_results, target_sum


def generate_fudge_dice_for_sum(num_dice: int, target_sum: int) -> List[int]:
    """Generate fudge dice that sum to approximately the target."""
    # Clamp target to possible range
    target_sum = max(-num_dice, min(num_dice, target_sum))

    # Start with all zeros
    dice = [0] * num_dice
    current_sum = 0

    # Adjust dice to reach target sum
    remaining = target_sum - current_sum
    for i in range(num_dice):
        if remaining > 0:
            dice[i] = 1
            remaining -= 1
        elif remaining < 0:
            dice[i] = -1
            remaining += 1

    # Shuffle for randomness
    random.shuffle(dice)

    return dice


def generate_realistic_fudge_faces(num_dice: int, target_sum: int) -> List[int]:
    """Generate realistic fudge dice faces that sum to target while looking natural."""
    # Clamp target to possible range
    target_sum = max(-num_dice, min(num_dice, target_sum))

    # Start with all zeros
    dice = [0] * num_dice
    remaining = target_sum

    # First pass: distribute the sum efficiently
    for i in range(num_dice):
        if remaining > 0:
            # Add positive faces, but don't exceed what we need
            add_amount = min(1, remaining)
            dice[i] = add_amount
            remaining -= add_amount
        elif remaining < 0:
            # Add negative faces
            subtract_amount = max(-1, remaining)
            dice[i] = subtract_amount
            remaining -= subtract_amount

    # Second pass: randomize the distribution while maintaining sum
    # This makes the faces look more natural by spreading values around
    # Skip if we don't have at least 2 dice to swap between
    if num_dice < 2:
        return dice

    for _ in range(num_dice * 2):  # Multiple randomization passes
        # Pick two random dice
        i, j = random.sample(range(num_dice), 2)

        # Try to transfer value from one to another (keeping sum constant)
        if dice[i] > -1 and dice[j] < 1:  # Can transfer from i to j
            if random.random() < 0.3:  # 30% chance to make this swap
                dice[i] -= 1
                dice[j] += 1
        elif dice[i] < 1 and dice[j] > -1:  # Can transfer from j to i
            if random.random() < 0.3:
                dice[i] += 1
                dice[j] -= 1

    # Final shuffle to randomize position
    random.shuffle(dice)

    return dice


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
        explosion = random.randint(1, 10)
        return (base_roll + explosion, base_roll, explosion)
    elif base_roll == 1:
        implosion = random.randint(1, 10)
        return (base_roll - implosion, base_roll, -implosion)
    else:
        return (base_roll, base_roll, None)


def check_cpr_d6_critical(dice_results: List[int]) -> bool:
    """Check if d6 pool roll is a critical (2+ sixes).

    Args:
        dice_results: List of individual d6 results

    Returns:
        True if 2 or more dice show 6
    """
    return dice_results.count(6) >= 2


def format_cpr_d10_result(total: int, base_roll: int, explosion_roll: Optional[int], modifier: int) -> str:
    """Format CPR d10 result for display.

    Args:
        total: Final total including modifier
        base_roll: The initial d10 result (1-10)
        explosion_roll: Positive for explosion, negative for implosion, None for normal
        modifier: The modifier applied to the roll

    Returns:
        Formatted string for the dice portion of the result
    """
    if explosion_roll is None:
        return f"({base_roll})"
    elif explosion_roll > 0:
        return f"(10->10!+{explosion_roll})"
    else:
        implosion_value = abs(explosion_roll)
        luck_total = 1 + modifier
        luck_breakdown = f"1+{modifier}" if modifier >= 0 else f"1{modifier}"
        return f"(1->1!-{implosion_value}) [Luck? **{luck_total}** ({luck_breakdown})]"


# --- CPR CRITICAL INJURY TABLES ---

CPR_CRITICAL_BODY = {
    2: {
        "name": "Dismembered Arm",
        "effect": "The Dismembered Arm is gone. You drop any items in that dismembered arm's hand immediately. Base Death Save Penalty is increased by 1.",
        "quick_fix": "N/A",
        "treatment": "Surgery DV17",
    },
    3: {
        "name": "Dismembered Hand",
        "effect": "The Dismembered Hand is gone. You drop any items in the dismembered hand immediately. Base Death Save Penalty is increased by 1.",
        "quick_fix": "N/A",
        "treatment": "Surgery DV17",
    },
    4: {
        "name": "Collapsed Lung",
        "effect": "-2 to MOVE (minimum 1). Base Death Save Penalty is increased by 1.",
        "quick_fix": "Paramedic DV15",
        "treatment": "Surgery DV15",
    },
    5: {
        "name": "Broken Ribs",
        "effect": "At the end of every Turn where you move further than 4m/yds on foot, you re-suffer this Critical Injury's Bonus Damage directly to your Hit Points.",
        "quick_fix": "Paramedic DV13",
        "treatment": "Paramedic DV15 or Surgery DV13",
    },
    6: {
        "name": "Broken Arm",
        "effect": "The Broken Arm cannot be used. You drop any items in that arm's hand immediately.",
        "quick_fix": "Paramedic DV13",
        "treatment": "Paramedic DV15 or Surgery DV13",
    },
    7: {
        "name": "Foreign Object",
        "effect": "At the end of every Turn where you move further than 4m/yds on foot, you re-suffer this Critical Injury's Bonus Damage directly to your Hit Points.",
        "quick_fix": "First Aid or Paramedic DV13",
        "treatment": "Quick Fix removes Injury Effect permanently",
    },
    8: {
        "name": "Broken Leg",
        "effect": "-4 to MOVE (minimum 1).",
        "quick_fix": "Paramedic DV13",
        "treatment": "Paramedic DV15 or Surgery DV13",
    },
    9: {
        "name": "Torn Muscle",
        "effect": "-2 to Melee Attacks.",
        "quick_fix": "First Aid or Paramedic DV13",
        "treatment": "Quick Fix removes Injury Effect permanently",
    },
    10: {
        "name": "Spinal Injury",
        "effect": "Next Turn, you cannot take an Action, but you can still take a Move Action. Base Death Save Penalty is increased by 1.",
        "quick_fix": "Paramedic DV15",
        "treatment": "Surgery DV15",
    },
    11: {
        "name": "Crushed Fingers",
        "effect": "-4 to all Actions involving that hand.",
        "quick_fix": "Paramedic DV13",
        "treatment": "Surgery DV15",
    },
    12: {
        "name": "Dismembered Leg",
        "effect": "The Dismembered Leg is gone. -6 to MOVE (minimum 1). You cannot dodge attacks. Base Death Save Penalty is increased by 1.",
        "quick_fix": "N/A",
        "treatment": "Surgery DV17",
    },
}

CPR_CRITICAL_HEAD = {
    2: {
        "name": "Lost Eye",
        "effect": "The Lost Eye is gone. -4 to Ranged Attacks & Perception Checks involving vision. Base Death Save Penalty is increased by 1.",
        "quick_fix": "N/A",
        "treatment": "Surgery DV17",
    },
    3: {
        "name": "Brain Injury",
        "effect": "-2 to all Actions. Base Death Save Penalty is increased by 1.",
        "quick_fix": "N/A",
        "treatment": "Surgery DV17",
    },
    4: {
        "name": "Damaged Eye",
        "effect": "-2 to Ranged Attacks & Perception Checks involving vision.",
        "quick_fix": "Paramedic DV15",
        "treatment": "Surgery DV13",
    },
    5: {
        "name": "Concussion",
        "effect": "-2 to all Actions.",
        "quick_fix": "First Aid or Paramedic DV13",
        "treatment": "Quick Fix removes Injury Effect permanently",
    },
    6: {
        "name": "Broken Jaw",
        "effect": "-4 to all Actions involving speech.",
        "quick_fix": "Paramedic DV13",
        "treatment": "Paramedic or Surgery DV13",
    },
    7: {
        "name": "Foreign Object",
        "effect": "At the end of every Turn where you move further than 4m/yds on foot, you re-suffer this Critical Injury's Bonus Damage directly to your Hit Points.",
        "quick_fix": "First Aid or Paramedic DV13",
        "treatment": "Quick Fix removes Injury Effect permanently",
    },
    8: {
        "name": "Whiplash",
        "effect": "Base Death Save Penalty is increased by 1.",
        "quick_fix": "Paramedic DV13",
        "treatment": "Paramedic or Surgery DV13",
    },
    9: {
        "name": "Cracked Skull",
        "effect": "Aimed Shots to your head multiply the damage that gets through your SP by 3 instead of 2. Base Death Save Penalty is increased by 1.",
        "quick_fix": "Paramedic DV15",
        "treatment": "Paramedic or Surgery DV15",
    },
    10: {
        "name": "Damaged Ear",
        "effect": "Whenever you move further than 4m/yds on foot in a Turn, you cannot take a Move Action on your next Turn. Additionally you take a -2 to Perception Checks involving hearing.",
        "quick_fix": "Paramedic DV13",
        "treatment": "Surgery DV13",
    },
    11: {
        "name": "Crushed Windpipe",
        "effect": "You cannot speak. Base Death Save Penalty is increased by 1.",
        "quick_fix": "N/A",
        "treatment": "Surgery DV15",
    },
    12: {
        "name": "Lost Ear",
        "effect": "The Lost Ear is gone. Whenever you move further than 4m/yds on foot in a Turn, you cannot take a Move Action on your next Turn. Additionally you take a -4 to Perception Checks involving hearing. Base Death Save Penalty is increased by 1.",
        "quick_fix": "N/A",
        "treatment": "Surgery DV17",
    },
}


def lookup_cpr_critical_injury(location: str, roll: int) -> Optional[Dict]:
    """Look up a CPR critical injury by location and 2d6 roll.

    Args:
        location: "body" or "head"
        roll: 2d6 result (2-12)

    Returns:
        Dict with name, effect, quick_fix, treatment or None if invalid
    """
    table = CPR_CRITICAL_BODY if location == "body" else CPR_CRITICAL_HEAD
    return table.get(roll)
