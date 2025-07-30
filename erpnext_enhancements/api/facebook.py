import requests # --- CONFIG --- ACCESS_TOKEN = "" AD_ACCOUNT_ID = "" ERPNext_URL = "https://yourerpnext.com" ERPNext_API_KEY = "your_api_key" ERPNext_API_SECRET = "your_api_secret" # --- FUNCTIONS --- def get_all_ads(): url = f"https://graph.facebook.com/v23.0/act_{AD_ACCOUNT_ID}/ads" params = { "access_token": ACCESS_TOKEN, "fields": "id,name" } resp = requests.get(url, params=params) resp.raise_for_status() return resp.json().get("data", []) def get_ad_creative(ad_id): url = f"https://graph.facebook.com/v23.0/{ad_id}" params = { "access_token": ACCESS_TOKEN, "fields": "adcreatives{id,name,effective_object_story_id,object_story_spec}" } resp = requests.get(url, params=params) resp.raise_for_status() data = resp.json() # adcreatives is nested, grab first creative if available creatives = data.get("adcreatives", {}).get("data", []) if creatives: return creatives[0] return None def get_lead_form_id(ad_creative): # Try to extract lead_gen_form_id from object_story_spec try: return ad_creative["object_story_spec"]["link_data"]["call_to_action"]["value"]["lead_gen_form_id"] except KeyError: return None def get_leads(lead_form_id): url = f"https://graph.facebook.com/v23.0/{lead_form_id}/leads" params = { "access_token": ACCESS_TOKEN, } resp = requests.get(url, params=params) resp.raise_for_status() return resp.json().get("data", []) def push_lead_to_erpnext(lead): # Customize this based on your ERPNext Lead DocType fields url = f"{ERPNext_URL}/api/resource/Lead" headers = { "Authorization": f"token {ERPNext_API_KEY}:{ERPNext_API_SECRET}", "Content-Type": "application/json" } # Map Facebook lead data to ERPNext fields as needed lead_doc = { "lead_name": lead.get("field_data", [{}])[0].get("values", [""])[0], "email_id": "", "phone": "", "source": "Facebook Lead Ads", "status": "Open" } # Extract actual field values from Facebook lead data for field in lead.get("field_data", []): if field["name"] == "email": lead_doc["email_id"] = field["values"][0] elif field["name"] == "phone_number": lead_doc["phone"] = field["values"][0] elif field["name"] == "full_name": lead_doc["lead_name"] = field["values"][0] response = requests.post(url, json=lead_doc, headers=headers) if response.status_code == 200 or response.status_code == 201: print(f"Lead {lead_doc['lead_name']} pushed successfully.") else: print(f"Failed to push lead: {response.text}") # --- MAIN SCRIPT --- def main(): ads = get_all_ads() print(f"Found {len(ads)} ads.") for ad in ads: print(f"Processing Ad: {ad['name']} ({ad['id']})") creative = get_ad_creative(ad["id"]) if not creative: print(" No creative found, skipping.") continue lead_form_id = get_lead_form_id(creative) if not lead_form_id: print(" No lead form attached to this ad, skipping.") continue print(f" Lead Form ID: {lead_form_id}") leads = get_leads(lead_form_id) print(f" Found {len(leads)} leads.") for lead in leads: push_lead_to_erpnext(lead) if __name__ == "__main__": main()
import requests

# --- CONFIG ---
ACCESS_TOKEN = "EAAIqjN7LARQBPI1gIqgVfcZBoSZAYXEumVuEpiYbwjzMh0epFPcZAb9ldKsvxYYjpqEKg3rmwYKwV3a9Pj9LgjYHz7g4cdhGNTL3c3dR6rIIPrXSjRCfbxVE5wnZCiQDgLD2ooekO1naDbzXVCidbw0QlfMt4yaKC1DQZBmG1GZBOoghjU9LGZCvs2TXOnQZAvdQJlMWBa0AFoAwQscCxEzWsduU0vlAXQpE"
AD_ACCOUNT_ID = "1432230197901889"
ERPNext_URL = "https://jdfarms.storenxt.in"
ERPNext_API_KEY = "your_api_key"
ERPNext_API_SECRET = "your_api_secret"

# --- FUNCTIONS ---

def get_all_ads():
    url = f"https://graph.facebook.com/v23.0/act_{AD_ACCOUNT_ID}/ads"
    params = {
        "access_token": ACCESS_TOKEN,
        "fields": "id,name"
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json().get("data", [])

def get_ad_creative(ad_id):
    url = f"https://graph.facebook.com/v23.0/{ad_id}"
    params = {
        "access_token": ACCESS_TOKEN,
        "fields": "adcreatives{id,name,effective_object_story_id,object_story_spec}"
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()
    
    # adcreatives is nested, grab first creative if available
    creatives = data.get("adcreatives", {}).get("data", [])
    if creatives:
        return creatives[0]
    return None

def get_lead_form_id(ad_creative):
    # Try to extract lead_gen_form_id from object_story_spec
    try:
        return ad_creative["object_story_spec"]["link_data"]["call_to_action"]["value"]["lead_gen_form_id"]
    except KeyError:
        return None

def get_leads(lead_form_id):
    url = f"https://graph.facebook.com/v23.0/{lead_form_id}/leads"
    params = {
        "access_token": ACCESS_TOKEN,
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json().get("data", [])

def push_lead_to_erpnext(lead):
    # Customize this based on your ERPNext Lead DocType fields
    url = f"{ERPNext_URL}/api/resource/Lead"
    headers = {
        "Authorization": f"token {ERPNext_API_KEY}:{ERPNext_API_SECRET}",
        "Content-Type": "application/json"
    }

    # Map Facebook lead data to ERPNext fields as needed
    lead_doc = {
        "lead_name": lead.get("field_data", [{}])[0].get("values", [""])[0],
        "email_id": "",
        "phone": "",
        "source": "Facebook Lead Ads",
        "status": "Open"
    }

    # Extract actual field values from Facebook lead data
    for field in lead.get("field_data", []):
        if field["name"] == "email":
            lead_doc["email_id"] = field["values"][0]
        elif field["name"] == "phone_number":
            lead_doc["phone"] = field["values"][0]
        elif field["name"] == "full_name":
            lead_doc["lead_name"] = field["values"][0]

    response = requests.post(url, json=lead_doc, headers=headers)
    if response.status_code in [200, 201]:
        print(f"Lead {lead_doc['lead_name']} pushed successfully.")
    else:
        print(f"Failed to push lead: {response.text}")

# --- MAIN SCRIPT ---

def main():
    ads = get_all_ads()
    print(f"Found {len(ads)} ads.")

    for ad in ads:
        print(f"Processing Ad: {ad['name']} ({ad['id']})")
        creative = get_ad_creative(ad["id"])
        if not creative:
            print(" No creative found, skipping.")
            continue

        lead_form_id = get_lead_form_id(creative)
        if not lead_form_id:
            print(" No lead form attached to this ad, skipping.")
            continue

        print(f" Lead Form ID: {lead_form_id}")
        leads = get_leads(lead_form_id)
        print(f" Found {len(leads)} leads.")

        for lead in leads:
            push_lead_to_erpnext(lead)

if __name__ == "__main__":
    main()
