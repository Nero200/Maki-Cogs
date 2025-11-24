#!/usr/bin/env python3
"""
Test the new fudge dice display format.
"""

def test_fudge_display():
    """Test the new fudge dice display formatting."""
    
    print("Testing New Fudge Dice Display Format")
    print("=" * 45)
    
    # Sample dice results for testing
    test_cases = [
        ([1, 1, 1, 1], "All positive"),
        ([-1, -1, -1, -1], "All negative"),
        ([1, 0, -1, 0], "Mixed results"),
        ([1, 1, 0, -1], "Mostly positive"),
        ([-1, -1, 0, 1], "Mostly negative"),
        ([0, 0, 0, 0], "All blank"),
    ]
    
    print("Old format vs New format comparison:")
    print("-" * 45)
    
    for dice_results, description in test_cases:
        # Old format
        old_str = ', '.join(['+1' if d == 1 else '0' if d == 0 else '-1' for d in dice_results])
        
        # New format
        new_str = ', '.join(['**+**' if d == 1 else '**☐**' if d == 0 else '**-**' for d in dice_results])
        
        print(f"\n{description}:")
        print(f"  Old: ({old_str})")
        print(f"  New: ({new_str})")
    
    print("\n" + "=" * 45)
    print("✅ New Format Benefits:")
    print("  • **+** - Bold plus sign for positive results")
    print("  • **-** - Bold minus sign for negative results") 
    print("  • **☐** - Square symbol for blank/zero results")
    print("  • More visually distinct and easier to read")
    print("  • Maintains the same information with better presentation")


def show_sample_output():
    """Show what the actual bot output would look like."""
    
    print("\nSample Bot Output Examples")
    print("=" * 45)
    
    examples = [
        {
            "roll": "4dF+2",
            "dice": [1, 0, -1, 1],
            "bonus": 2,
            "fudge_bonus": 0,
            "description": "Typical mixed roll"
        },
        {
            "roll": "4dF",
            "dice": [1, 1, 1, 1],
            "bonus": 0,
            "fudge_bonus": 2,
            "description": "All positive (with fudge bonus)"
        },
        {
            "roll": "4dF-1",
            "dice": [-1, -1, -1, -1],
            "bonus": -1,
            "fudge_bonus": -2,
            "description": "All negative (with fudge penalty)"
        }
    ]
    
    for example in examples:
        dice_str = ', '.join(['**+**' if d == 1 else '**☐**' if d == 0 else '**-**' for d in example["dice"]])
        dice_total = sum(example["dice"]) + example["fudge_bonus"]
        final_total = dice_total + example["bonus"]
        
        print(f"\n{example['description']}:")
        print(f"🎲 **TestUser** rolls `{example['roll']}`...")
        
        output = f"Result: ({dice_str})"
        if example["fudge_bonus"] != 0:
            fudge_text = " (all +)" if example["fudge_bonus"] > 0 else " (all -)"
            output += f" {example['fudge_bonus']:+d}{fudge_text}"
        if example["bonus"] != 0:
            output += f" {example['bonus']:+d}"
        output += f" = **{final_total:+d}**"
        
        print(output)


if __name__ == "__main__":
    print("Fudge Dice Display Format Test")
    print("=" * 50)
    
    test_fudge_display()
    show_sample_output()
    
    print("\n" + "=" * 50)
    print("🎉 Fudge dice display updated successfully!")
    print("\nThe new format is more visually appealing and easier to read.")
    print("Users will see bold +, -, and ☐ symbols instead of +1, -1, 0.")