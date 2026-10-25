"""Lesson 3: parse sample JSON. This is not a live model response.

Parsing checks syntax only; schema and factual validation come next.
Run: python check_response.py
"""

import json

response_text = '{"stage": "validation", "problem": "Nutrition information is missing."}'
data = json.loads(response_text)

print(data["stage"])
print(data["problem"])
