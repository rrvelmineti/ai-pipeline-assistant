import math
import unittest

from calorie_pipeline import calculate_calories


class PipelineTests(unittest.TestCase):
    def test_known_portion(self):
        record = calculate_calories("Test Food", 250, 200)
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["stage"], "calculation")
        self.assertEqual(record["total_calories"], 500)
        self.assertIsNone(record["error"])

    def test_doubling_portion_doubles_total(self):
        small = calculate_calories("Test Food", 250, 200)
        large = calculate_calories("Test Food", 500, 200)
        self.assertEqual(large["total_calories"], small["total_calories"] * 2)

    def test_missing_nutrition_does_not_become_zero(self):
        record = calculate_calories("Test Food", 250, None)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["stage"], "validation")
        self.assertEqual(record["error"], "Nutrition information is missing.")
        self.assertIsNone(record["total_calories"])
        self.assertIsNone(record["inputs"]["calories_per_100g"])

    def test_real_zero_is_valid(self):
        for grams, nutrition in [(0, 200), (250, 0)]:
            with self.subTest(grams=grams, nutrition=nutrition):
                record = calculate_calories("Test Food", grams, nutrition)
                self.assertEqual(record["status"], "success")
                self.assertEqual(record["total_calories"], 0)

    def test_missing_portion(self):
        record = calculate_calories("Test Food", None, 200)
        self.assertEqual(record["error"], "Portion in grams is missing.")
        self.assertIsNone(record["total_calories"])

    def test_invalid_food_names(self):
        for name in (None, "", "  ", 25):
            with self.subTest(name=name):
                record = calculate_calories(name, 250, 200)
                self.assertEqual(record["status"], "error")
                self.assertEqual(record["stage"], "validation")

    def test_invalid_numeric_inputs(self):
        for value in (-1, True, False, "250", math.nan, math.inf, -math.inf, 10**400):
            for grams, nutrition in [(value, 200), (250, value)]:
                with self.subTest(grams=grams, nutrition=nutrition):
                    record = calculate_calories("Test Food", grams, nutrition)
                    self.assertEqual(record["status"], "error")
                    self.assertEqual(record["stage"], "validation")
                    self.assertIsNone(record["total_calories"])

    def test_overflow_at_calculation(self):
        record = calculate_calories("Test Food", 1e308, 1e308)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["stage"], "calculation")
        self.assertIsNone(record["total_calories"])

    def test_fractional_portion(self):
        record = calculate_calories("Test Food", 12.5, 80)
        self.assertAlmostEqual(record["total_calories"], 10)
