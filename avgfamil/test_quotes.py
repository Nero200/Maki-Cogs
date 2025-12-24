#!/usr/bin/env python3
"""Test script to verify quote normalization works."""

import sys
import os

# Add parent directory to path so we can import the module
sys.path.insert(0, os.path.dirname(__file__))

from avgfamil import AvgFamil

class MockBot:
    """Mock bot for testing."""
    pass

def test_quotes():
    """Test with various quote types."""
    bot = MockBot()
    cog = AvgFamil(bot)

    # Test with curly quotes (preserving apostrophes in contractions)
    text1 = "Can't use \u201Cmachine learning\u201D"
    text2 = "Don't know \u201Cneural networks\u201D"

    try:
        image_bytes = cog.generate_image(text1, text2)
        print(f"✓ Quote normalization successful! Size: {len(image_bytes.getvalue())} bytes")

        # Save to file for inspection
        test_output = os.path.join(os.path.dirname(__file__), "test_quotes_output.png")
        with open(test_output, "wb") as f:
            f.write(image_bytes.getvalue())
        print(f"✓ Test image saved to: {test_output}")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing quote normalization...")
    print("-" * 50)
    test_quotes()
    print("-" * 50)
    print("Test complete!")
