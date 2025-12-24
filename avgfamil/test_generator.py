#!/usr/bin/env python3
"""Simple test script to verify image generation works."""

import sys
import os

# Add parent directory to path so we can import the module
sys.path.insert(0, os.path.dirname(__file__))

from avgfamil import AvgFamil

class MockBot:
    """Mock bot for testing."""
    pass

def test_generation():
    """Test basic image generation."""
    bot = MockBot()
    cog = AvgFamil(bot)

    # Test with sample text
    text1 = "Machine learning"
    text2 = "Neural networks"

    try:
        image_bytes = cog.generate_image(text1, text2)
        print(f"✓ Image generated successfully! Size: {len(image_bytes.getvalue())} bytes")

        # Save to file for inspection
        test_output = os.path.join(os.path.dirname(__file__), "test_output.png")
        with open(test_output, "wb") as f:
            f.write(image_bytes.getvalue())
        print(f"✓ Test image saved to: {test_output}")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_long_text():
    """Test with longer text that requires wrapping."""
    bot = MockBot()
    cog = AvgFamil(bot)

    text1 = "Quantum computing and advanced cryptography systems"
    text2 = "Distributed blockchain consensus mechanisms and proof of work"

    try:
        image_bytes = cog.generate_image(text1, text2)
        print(f"✓ Long text image generated! Size: {len(image_bytes.getvalue())} bytes")

        test_output = os.path.join(os.path.dirname(__file__), "test_long_output.png")
        with open(test_output, "wb") as f:
            f.write(image_bytes.getvalue())
        print(f"✓ Long text image saved to: {test_output}")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Testing AvgFamil image generation...")
    print("-" * 50)

    print("\n1. Testing basic generation:")
    test_generation()

    print("\n2. Testing long text:")
    test_long_text()

    print("\n" + "-" * 50)
    print("Tests complete!")
