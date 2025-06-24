import frappe
import requests
import csv
from io import StringIO

def sync_hsn_from_google_sheet():
    # ✅ Final working Google Sheet CSV URL
    csv_url = "https://docs.google.com/spreadsheets/d/1oH5WCQjBm5ViOrokDyHdW5DMIDHLOxLt/export?format=csv&gid=989215930"


    # Fetch the sheet
    response = requests.get(csv_url)
    response.raise_for_status()

    data = StringIO(response.text)
    reader = csv.DictReader(data)
    print("🔍 Reading rows from sheet...")

    for row in reader:
        item_code = row.get("Item Code", "").strip()
        hsn_code = row.get("HSN/SAC", "").strip()
        
        if not item_code or not hsn_code:
            continue

        try:
            item = frappe.get_doc("Item", item_code)
            item.custom_hsnsac = hsn_code  # ✅ updated fieldname
            item.save()
            print(f"✅ Updated: {item_code} -> {hsn_code}")

        except frappe.DoesNotExistError:
            print(f"❌ Item not found: {item_code}")
        except Exception as e:
            print(f"⚠️ Error on {item_code}: {e}")

    frappe.db.commit()
