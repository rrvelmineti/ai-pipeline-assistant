import json

with open("pipeline_error.json", encoding="utf-8") as error_file:
    error_details = json.load(error_file)

if error_details.get("status") == "success":
    print("Pipeline succeeded. Total sales:", error_details["total_sales"])
else:
    print(
        f"CSV row {error_details['row']}: {error_details['problem']} Received: {error_details['invalid_value']}")
