import csv
import json
import os

print("Pipeline working folder:", os.getcwd())
with open("Orders.csv", encoding="utf-8-sig", newline="") as file:
    orders = csv.DictReader(file)
    total_sales = 0

    for row_number, order in enumerate(orders, start=2):
        try:
            quantity = int(order["quantity"])
        except ValueError:
            error_details = {
                "status": "error",
                "stage": "validation",
                "row": row_number,
                "field": "quantity",
                "invalid_value": order["quantity"],
                "problem": "Quantity must be a whole number."
            }
            print(json.dumps(error_details, indent=4))
            with open("pipeline_error.json", "w", encoding="utf-8") as error_file:
                json.dump(error_details, error_file, indent=4)
            raise
        unit_price = int(order["unit_price"])
        order_total = quantity * unit_price
        total_sales = total_sales+order_total
        print(order_total)
    print("Total sales", total_sales)
    run_result = {"status": "success", "total_sales": total_sales}

    with open("pipeline_error.json", "w", encoding="utf-8") as result_file:
        json.dump(run_result, result_file, indent=4)
