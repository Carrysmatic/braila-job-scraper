
import os
# ... other imports ...

# 1. SETUP & CONFIGURATION
# ---------------------------------------------------------
# SECURITY UPDATE: Read from GitHub Secrets (Environment Variable)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

SITES_FILE = 'sites.json'
HISTORY_FILE = "job_history.json"
# ... rest of the script remains the same ...

def load_json(filename):
    """Loads JSON data safely."""
    if not os.path.exists(filename):
        return {} if filename == HISTORY_FILE else []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        return {} if filename == HISTORY_FILE else []

def save_history(history):
    """Saves the current state."""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

def check_website(site, history):
    site_id = site['id']
    url = site['url']
    selector = site['selector']
    target_attr = site.get('attribute', 'text') # Default to text if not specified

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking {site_id}...")

    # Site-specific SSL verification bypass
    verify_ssl = True
    if site_id == "portal_just_galati":
        verify_ssl = False

    try:
        # Request with SSL verification disabled for specific sites
        response = requests.get(url, headers=HEADERS, timeout=15, verify=verify_ssl)
        response.raise_for_status()

        # --- UPDATED: ROBUST JSON HANDLING ---
        # We check if it is the ANOFM site OR if the headers say JSON
        is_json_site = (site_id == "anofm_braila")
        is_json_header = "application/json" in response.headers.get("Content-Type", "")

        if is_json_site or is_json_header:
            try:
                data = response.json()
                # DEBUG: Uncomment the next line if you want to see how many items downloaded
                print(f"DEBUG: Downloaded {len(data)} items from {site_id}")
                current_items = {}
                if isinstance(data, list):
                    for job in data:
                        # SAFETY FIX: Convert both to string to handle 10 vs "10"
                        # We use '10' for Braila.
                        c_id = str(job.get('county_id', ''))
                        if c_id == '10': 
                            job_id = str(job.get('id'))
                            # Build the title
                            t_occ = job.get('occupation') or "Job"
                            t_emp = job.get('employer_name') or ""
                            job_title = f"{t_occ} - {t_emp}"
                            # Static link since API items don't have pages
                            job_link = "https://mediere.anofm.ro/app/module/mediere/jobs"
                            if job_id:
                                current_items[job_id] = job_title
                    return current_items
            except ValueError:
                # If response.json() fails, it wasn't JSON. Ignore and fall through to HTML.
                pass
        # --- END UPDATED JSON HANDLING ---

        # Normal HTML parsing for all other websites
        soup = BeautifulSoup(response.content, 'html.parser')
        # DEBUG: Print the page title to see if we are blocked
        if "ejobs" in site_id:
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return

    elements = soup.select(selector)
    # 1. Build a dictionary of {ID: Title} for the current page
    current_items = {}
    for el in elements:
        # A. Extract the unique ID (key)
        if target_attr == 'text':
            key = el.get_text().strip()
        else:
            key = el.get(target_attr)
        if not key:
            continue  # Skip if empty
        # Decode URL-encoded characters in key
        key = unquote(key)

        # B. Extract a readable title for the notification (Optional)
        # Only search if title_selector is present and not empty
        readable_title = key
        if 'title_selector' in site and site['title_selector']:
            title_el = el.select_one(site['title_selector'])
            if title_el:
                readable_title = title_el.get_text().strip()
        # Decode URL-encoded characters in title
        readable_title = unquote(readable_title)

        current_items[key] = readable_title


    # 2. Compare with History
    # Support both list and dict formats for backward compatibility
    old_data = history.get(site_id, {})
    if isinstance(old_data, list):
        old_keys = old_data
    else:
        old_keys = list(old_data.keys())

    # Find keys that are in current_items but NOT in old_keys
    new_keys = [k for k in current_items if k not in old_keys]

    if new_keys:
        print(f"   🚨 FOUND {len(new_keys)} NEW UPDATES!")
        for key in new_keys:
            title = current_items[key]
            print(f"      👉 New: {title} (ID: {key})")
            
            # --- SEND NOTIFICATION HERE ---
            # send_email(f"New Job: {title}", url)
            
    else:
        print(f"   ✅ No changes (tracked {len(current_items)} items)")

    # 3. Save the new list of keys to history
    # We only save the keys (IDs), not the titles, to keep the file clean
    history[site_id] = current_items

def main():
    sites = load_json(SITES_FILE)
    history = load_json(HISTORY_FILE)

    if not sites:
        print("⚠️ No sites found in sites.json")
        return


    for site in sites:
        check_website(site, history)

    # Cap history (Keep the FIRST 15 items, which are usually the newest/top of page)
    for site_id in history:
        site_history = history[site_id]
        if isinstance(site_history, dict) and len(site_history) > 15:
            # [:15] keeps the first 15. [-15:] keeps the last 15.
            capped_items = dict(list(site_history.items())[:15]) 
            history[site_id] = capped_items 

    save_history(history)

if __name__ == "__main__":
    main()