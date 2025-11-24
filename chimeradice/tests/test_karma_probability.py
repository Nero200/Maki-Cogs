#!/usr/bin/env python3
"""
Comprehensive probability tests for the karma system.
Tests both standard dice and fudge dice probability distributions.
"""

import sys
import os
import random
import statistics
from collections import defaultdict, Counter
# Optional imports
try:
    import matplotlib.pyplot as plt
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# Add the parent directory to path to import chimeradice
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the ChimeraDice class
from chimeradice import ChimeraDice, FUDGE_PROBABILITIES

class KarmaProbabilityTester:
    def __init__(self):
        self.cog = ChimeraDice(None)  # No bot needed for testing
        
    def test_standard_die_distribution(self, die_size=20, debt_values=None, num_trials=10000):
        """Test probability distribution for standard dice with various debt levels."""
        if debt_values is None:
            debt_values = [0, 10, 25, 50, -10, -25, -50]
        
        print(f"\n=== Testing {die_size}-sided die distribution ===")
        print(f"Trials per debt level: {num_trials}")
        
        results = {}
        
        for debt in debt_values:
            print(f"\nTesting debt level: {debt:+.1f}")
            
            # Collect results
            rolls = []
            face_counts = Counter()
            
            for _ in range(num_trials):
                result = self.cog._roll_weighted_standard_die(die_size, debt)
                rolls.append(result)
                face_counts[result] += 1
            
            # Calculate statistics
            mean_result = statistics.mean(rolls)
            expected_mean = (die_size + 1) / 2
            median_result = statistics.median(rolls)
            
            # Calculate percentile shift
            percentiles = [sum(1 for r in rolls if r <= i) / len(rolls) * 100 for i in range(1, die_size + 1)]
            
            results[debt] = {
                'rolls': rolls,
                'face_counts': face_counts,
                'mean': mean_result,
                'expected_mean': expected_mean,
                'median': median_result,
                'percentiles': percentiles
            }
            
            print(f"  Mean: {mean_result:.2f} (expected: {expected_mean:.2f}, shift: {mean_result - expected_mean:+.2f})")
            print(f"  Median: {median_result:.2f}")
            
            # Show face distribution for extreme values
            if abs(debt) >= 25:
                top_faces = sorted(face_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                bottom_faces = sorted(face_counts.items(), key=lambda x: x[1])[:3]
                print(f"  Most common: {top_faces}")
                print(f"  Least common: {bottom_faces}")
        
        return results
    
    def test_fudge_die_distribution(self, num_dice=4, debt_values=None, num_trials=10000):
        """Test probability distribution for fudge dice with various debt levels."""
        if debt_values is None:
            debt_values = [0, 15, 30, 50, -15, -30, -50]
        
        print(f"\n=== Testing {num_dice}dF distribution ===")
        print(f"Trials per debt level: {num_trials}")
        
        results = {}
        
        # Get expected distribution
        expected_probs = FUDGE_PROBABILITIES.get(num_dice, {})
        expected_mean = 0  # Fudge dice are centered on 0
        
        for debt in debt_values:
            print(f"\nTesting debt level: {debt:+.1f}")
            
            # Collect results
            sums = []
            face_patterns = []
            sum_counts = Counter()
            
            for _ in range(num_trials):
                dice_results, dice_sum = self.cog._roll_weighted_fudge_dice(num_dice, debt)
                sums.append(dice_sum)
                sum_counts[dice_sum] += 1
                face_patterns.append(tuple(dice_results))
            
            # Calculate statistics
            mean_sum = statistics.mean(sums)
            median_sum = statistics.median(sums)
            
            results[debt] = {
                'sums': sums,
                'face_patterns': face_patterns,
                'sum_counts': sum_counts,
                'mean': mean_sum,
                'expected_mean': expected_mean,
                'median': median_sum
            }
            
            print(f"  Mean: {mean_sum:+.2f} (expected: {expected_mean:.2f}, shift: {mean_sum - expected_mean:+.2f})")
            print(f"  Median: {median_sum:+.2f}")
            
            # Compare with expected probabilities
            if expected_probs:
                print("  Sum distribution comparison:")
                for sum_val in sorted(expected_probs.keys()):
                    expected_pct = expected_probs[sum_val] * 100
                    actual_count = sum_counts.get(sum_val, 0)
                    actual_pct = (actual_count / num_trials) * 100
                    diff = actual_pct - expected_pct
                    print(f"    {sum_val:+2d}: {actual_pct:5.1f}% (exp: {expected_pct:5.1f}%, diff: {diff:+5.1f}%)")
            
            # Test face pattern realism
            self._test_fudge_face_realism(face_patterns, num_dice, debt)
        
        return results
    
    def _test_fudge_face_realism(self, patterns, num_dice, debt):
        """Test if fudge dice face patterns look realistic."""
        print("  Face pattern analysis:")
        
        # Count face types across all patterns
        face_type_counts = {-1: 0, 0: 0, 1: 0}
        for pattern in patterns:
            for face in pattern:
                face_type_counts[face] += 1
        
        total_faces = len(patterns) * num_dice
        for face_val, count in face_type_counts.items():
            percentage = (count / total_faces) * 100
            face_symbol = {-1: "-", 0: "0", 1: "+"}[face_val]
            print(f"    {face_symbol} faces: {percentage:.1f}%")
        
        # Check for unrealistic patterns (all same face)
        all_same_patterns = 0
        for pattern in patterns:
            if len(set(pattern)) == 1:
                all_same_patterns += 1
        
        all_same_pct = (all_same_patterns / len(patterns)) * 100
        print(f"    All-same patterns: {all_same_pct:.1f}%")
        
        # Expected all-same for natural fudge dice
        expected_all_same = ((1/3) ** num_dice) * 3 * 100  # 3 possible all-same patterns
        print(f"    Expected all-same: {expected_all_same:.1f}%")
    
    def test_karma_effectiveness(self, trials_per_debt=1000):
        """Test how effectively karma corrects for bad/good luck."""
        print("\n=== Testing Karma Effectiveness ===")
        
        # Simulate a series of rolls with karma correction
        debt_levels = [0, 20, 40, -20, -40]
        
        for initial_debt in debt_levels:
            print(f"\nStarting debt: {initial_debt:+.1f}")
            
            current_debt = initial_debt
            results = []
            debt_history = [current_debt]
            
            for trial in range(trials_per_debt):
                # Roll d20 with current debt
                result = self.cog._roll_weighted_standard_die(20, current_debt)
                results.append(result)
                
                # Calculate how this roll affects debt (simplified)
                percentile = ((result - 0.5) / 20) * 100  # Rough percentile
                debt_change = 50.0 - percentile
                current_debt = (current_debt + debt_change) * 0.98  # Include decay
                current_debt = max(-100, min(100, current_debt))  # Cap limits
                debt_history.append(current_debt)
            
            final_debt = current_debt
            mean_result = statistics.mean(results)
            debt_reduction = abs(initial_debt) - abs(final_debt)
            
            print(f"  Final debt: {final_debt:+.1f}")
            print(f"  Mean roll: {mean_result:.2f}")
            print(f"  Debt reduction: {debt_reduction:+.1f}")
            print(f"  Convergence: {'✓' if abs(final_debt) < abs(initial_debt) else '✗'}")
    
    def visualize_distributions(self, results, title_prefix=""):
        """Create visualizations of the probability distributions."""
        if not HAS_MATPLOTLIB:
            print("Matplotlib not available - skipping visualization")
            return
            
        try:
            
            fig, axes = plt.subplots(2, 2, figsize=(15, 10))
            fig.suptitle(f"{title_prefix} Karma System Probability Analysis")
            
            # Plot 1: Mean shift by debt level
            debts = sorted(results.keys())
            means = [results[debt]['mean'] - results[debt]['expected_mean'] for debt in debts]
            
            axes[0, 0].plot(debts, means, 'bo-')
            axes[0, 0].axhline(y=0, color='r', linestyle='--', alpha=0.5)
            axes[0, 0].set_xlabel('Debt Level')
            axes[0, 0].set_ylabel('Mean Shift from Expected')
            axes[0, 0].set_title('Mean Result Shift vs Debt')
            axes[0, 0].grid(True, alpha=0.3)
            
            # Plot 2: Distribution for extreme debt values
            for i, debt in enumerate([min(debts), 0, max(debts)]):
                if debt in results:
                    face_counts = results[debt]['face_counts']
                    faces = sorted(face_counts.keys())
                    counts = [face_counts[face] for face in faces]
                    
                    axes[0, 1].bar([f + i*0.25 for f in faces], counts, 
                                 width=0.25, alpha=0.7, label=f'Debt: {debt:+.0f}')
            
            axes[0, 1].set_xlabel('Die Face')
            axes[0, 1].set_ylabel('Frequency')
            axes[0, 1].set_title('Face Distribution Comparison')
            axes[0, 1].legend()
            axes[0, 1].grid(True, alpha=0.3)
            
            # Plot 3: Debt effectiveness
            axes[1, 0].text(0.1, 0.5, "Debt Effectiveness Analysis\n(See console output)", 
                           transform=axes[1, 0].transAxes, fontsize=12)
            axes[1, 0].set_title('Karma Effectiveness')
            
            # Plot 4: Bias strength visualization
            bias_strengths = []
            for debt in debts:
                bias_strength = min(abs(debt) / 50.0, 1.0)
                bias_strengths.append(bias_strength)
            
            axes[1, 1].plot(debts, bias_strengths, 'go-')
            axes[1, 1].set_xlabel('Debt Level')
            axes[1, 1].set_ylabel('Bias Strength')
            axes[1, 1].set_title('Bias Strength vs Debt')
            axes[1, 1].grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.show()
            
        except Exception as e:
            print(f"Visualization error: {e}")
    
    def run_comprehensive_tests(self):
        """Run all probability tests."""
        print("🎲 KARMA PROBABILITY SYSTEM TESTS 🎲")
        print("=" * 50)
        
        # Test standard dice
        d20_results = self.test_standard_die_distribution(20)
        d6_results = self.test_standard_die_distribution(6)
        
        # Test fudge dice
        fudge_results = self.test_fudge_die_distribution(4)
        
        # Test karma effectiveness
        self.test_karma_effectiveness()
        
        # Visualize results if available
        if HAS_MATPLOTLIB:
            self.visualize_distributions(d20_results, "d20")
        else:
            print("\n📊 Visualization skipped (matplotlib not available)")
        
        print("\n" + "=" * 50)
        print("✅ PROBABILITY TESTS COMPLETE")
        print("Check the results above to verify karma system behavior.")
        
        return {
            'd20': d20_results,
            'd6': d6_results,
            'fudge': fudge_results
        }

if __name__ == "__main__":
    tester = KarmaProbabilityTester()
    results = tester.run_comprehensive_tests()