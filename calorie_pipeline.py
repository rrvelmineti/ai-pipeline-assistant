"""Lesson 1: calculate calories and keep evidence for troubleshooting.

Run in PowerShell: python calorie_pipeline.py
Requires Python 3; no packages, API key, or internet connection needed.
All demo values are made up. This version does not call an AI model.
"""

import json
import math


def calculate_calories(food_name, portion_grams, calories_per_100g):
    """Return the original inputs, a result or error, and the stage reached."""
    # None means unavailable. A real zero stays zero.
    record = {
        "inputs": {
            "food_name": food_name,
            "portion_grams": portion_grams,
            "calories_per_100g": calories_per_100g,
        },
        "status": "error",
        "stage": "validation",
        "total_calories": None,
        "error": None,
    }

    if not isinstance(food_name, str) or not food_name.strip():
        record["error"] = "Food name is missing or invalid."
        return record

    if portion_grams is None:
        record["error"] = "Portion in grams is missing."
        return record

    if calories_per_100g is None:
        record["error"] = "Nutrition information is missing."
        return record

    # Reject text, negative values, and non-finite numbers before calculating.
    for field, value in (
        ("portion_grams", portion_grams),
        ("calories_per_100g", calories_per_100g),
    ):
        try:
            valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value >= 0
            )
        except OverflowError:
            valid = False
        if not valid:
            record["error"] = f"{field} must be a finite number of zero or more."
            return record

    # Nutrition is explicitly PER 100 GRAMS, not per serving.
    record["stage"] = "calculation"
    total = (portion_grams / 100) * calories_per_100g
    if not math.isfinite(total):
        record["error"] = "Calculated calories exceed the supported numeric range."
        return record

    record["status"] = "success"
    record["total_calories"] = total
    return record


def run_demo():
    """Print a readable result and its evidence for each made-up example."""
    examples = [
        ("Normal portion", "Test Food", 250, 200),
        ("Missing nutrition", "Test Food", 250, None),
        ("Double portion", "Test Food", 500, 200),
    ]

    for label, food, grams, nutrition in examples:
        record = calculate_calories(food, grams, nutrition)
        if record["status"] == "success":
            print(f"{label}: {record['total_calories']:g} calories")
        else:
            print(f"{label}: {record['error']}")
        # JSON is a structured text format. Python None appears as JSON null.
        print(json.dumps(record, indent=2))
        print()


if __name__ == "__main__":
    run_demo()
