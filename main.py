import requests
from bs4 import BeautifulSoup
import json
import os
import time
import sys
from datetime import datetime
import urllib3

# 0. CRITICAL FIX FOR WINDOWS CONSOLE
# ---------------------------------------------------------
# Forces Python to use UTF-8 for printing, preventing crashes on 'ț' or 'ș'
sys.stdout.reconfigure(encoding='utf-8')

# 1. SETUP & CONFIGURATION
# ---------------------------------------------------------

# OPTION A: For GitHub Actions (Reads from Secrets)
WEBHOOK_FROM_ENV = os.environ.get("DISCORD_WEBHOOK_URL")

# OPTION B: For Local PC Testing (Keep empty for safety)
WEBHOOK_FOR_TESTING = "" 

# The script automatically chooses the right one
DISCORD_WEBHOOK_URL = WEBHOOK_FROM_ENV or WEBHOOK_FOR_TESTING

HISTORY_FILE = "job_history.json"
SITES_FILE = "sites.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.google.ro/',
    'Upgrade-Insecure-Requests': '1'
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 2. HELPER FUNCTIONS
# ---------------------------------------------------------
def log(message):
    """Prints a message with a timestamp."""
    timestamp = datetime.now().strftime('%H:%M:%S')
    try:
        print(f"[{timestamp}] {message}")
    except UnicodeEncodeError:
        # Fallback if the console is completely broken
        print(f"[{timestamp}] (Message contained special characters)")

def load_json(filename):
    """Safely loads a JSON file with UTF-8 encoding."""
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} if filename == HISTORY_FILE else []
    return {} if filename == HISTORY_FILE else []

def save_history(history):
    """Saves history with UTF-8 encoding (Fixes Romanian characters)."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

def send_discord_summary(job_list):
    """Sends a summary message, capped at 15 items to prevent spam."""
    if not DISCORD_WEBHOOK_URL:
        log("   [!] Alert skipped (No Webhook Configured)")
        return

    total_found = len(job_list)
    
    # --- ANTI-SPAM SETTINGS ---
    MAX_DISPLAY = 15
    
    if total_found > MAX_DISPLAY:
        display_list = job_list[:MAX_DISPLAY]
        hidden_count = total_found - MAX_DISPLAY
        footer_note = f"\n... and **{hidden_count} more** (Check the websites!)"
    else:
        display_list = job_list
        footer_note = ""

    log(f"   >>> Sending Summary to Discord ({total_found} jobs found, showing top {len(display_list)})...")

    # Build the Message
    header = f"**📢 Braila Job Update** - {datetime.now().strftime('%d/%m %H:%M')}\n"
    header += f"Found **{total_found}** new opportunities:\n\n"
    
    current_message = header
    
    for job in display_list:
        line = f"• **{job['site']}**: [{job['title']}]({job['link']})\n"
        
        # Check limit (Discord max 2000 chars)
        if len(current_message) + len(line) > 1900:
            _post_to_discord(current_message)
            current_message = line 
        else:
            current_message += line
            
    # Add the "And X more" footer if needed
    if footer_note:
        if len(current_message) + len(footer_note) > 1900:
             _post_to_discord(current_message)
             current_message = footer_note
        else:
             current_message += footer_note

    if current_message:
        _post_to_discord(current_message)

def _post_to_discord(content):
    data = {"username": "Job Bot Braila", "content": content}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data)
        time.sleep(1)
    except Exception as e:
        log(f"Failed to send Discord chunk: {e}")

# 3. CORE LOGIC
# ---------------------------------------------------------
def check_website(site_config):
    site_id = site_config["id"]
    url = site_config["url"]
    current_items = {} 

    log(f"Checking {site_id}...")
    
    verify_ssl = True
    if site_id in ["portal_just_galati", "evpop_braila", "anofm_braila"]:
        verify_ssl = False

    try:
        response = requests.get(url, headers=HEADERS, timeout=25, verify=verify_ssl)
        
        if response.status_code in [403, 503]:
            log(f"   [!] BLOCKED by {site_id}")
            return {}
            
        response.raise_for_status()

        # --- JSON Handling for ANOFM ---
        is_json_site = (site_id == "anofm_braila")
        is_json_header = "application/json" in response.headers.get("Content-Type", "")

        if is_json_site or is_json_header:
            try:
                data = response.json()
                
                # 1. Handle "Hydra" API wrapper
                if isinstance(data, dict) and 'hydra:member' in data:
                    data = data['hydra:member']
                
                # 2. Handle standard list
                if isinstance(data, list):
                    for job in data:
                        c_id = str(job.get('county_id', ''))
                        if c_id == '10': # Braila
                            job_id = str(job.get('id'))
                            t_occ = job.get('occupation') or "Job"
                            t_emp = job.get('employer_name') or ""
                            title = f"{t_occ} - {t_emp}"
                            # Dynamic link if possible
                            link = f"https://mediere.anofm.ro/app/module/mediere/jobs/{job_id}"
                            if job_id:
                                current_items[job_id] = {"title": title, "link": link}
                return current_items
            except ValueError:
                pass 
        # ---------------------------------------

        # HTML Handling
        soup = BeautifulSoup(response.content, 'html.parser')
        elements = soup.select(site_config["selector"])
        
        for el in elements:
            item_id = None
            item_link = url
            item_title = "New Update"

            attr_type = site_config.get("attribute")

            if attr_type == "href":
                item_id = el.get("href")
                item_link = item_id
                if item_id and not item_id.startswith("http"):
                    base_url = "/".join(url.split("/")[:3]) 
                    item_link = base_url + item_id
                    item_id = item_link
            elif attr_type == "id":
                item_id = el.get("id")
            elif attr_type == "data-id":
                item_id = el.get("data-id")
            elif attr_type == "json":
                continue

            if site_config.get("title_selector"):
                title_el = el.select_one(site_config["title_selector"])
                if title_el:
                    item_title = title_el.get_text(strip=True)
            else:
                item_title = el.get_text(strip=True)[:100]

            if item_id:
                current_items[item_id] = {"title": item_title, "link": item_link}

    except Exception as e:
        log(f"Error checking {site_id}: {e}")
    
    return current_items

# 4. MAIN LOOP
# ---------------------------------------------------------
def main():
    if not os.path.exists(SITES_FILE):
        log("Error: sites.json not found.")
        return

    sites = load_json(SITES_FILE)
    history = load_json(HISTORY_FILE)
    daily_digest = [] 

    log("--- Job Scraper Started ---")
    
    for site in sites:
        site_id = site["id"]
        current_jobs = check_website(site)
        
        old_jobs = history.get(site_id, {})
        
        for job_id, job_data in current_jobs.items():
            if job_id not in old_jobs:
                log(f"!!! NEW: {job_data['title']}")
                daily_digest.append({
                    "site": site_id,
                    "title": job_data['title'],
                    "link": job_data['link']
                })
        
        # Save Max 1000 items per site
        if len(current_jobs) > 1000:
            limited_jobs = dict(list(current_jobs.items())[:1000])
            history[site_id] = limited_jobs
        else:
            history[site_id] = current_jobs

    save_history(history)
    
    if daily_digest:
        send_discord_summary(daily_digest)
    else:
        log("No new jobs found.")

if __name__ == "__main__":
    main()