import os
import subprocess
import sys
import json
import datetime
from typing import List, Tuple, Dict, Any, Optional
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ==========================================
# --- CONFIGURATION ---
# ==========================================
APIGEE_HYB_ORG = getattr(config, 'APIGEE_HYB_ORG', 'default_org')
SA_ENABLE = getattr(config, 'SA_ENABLE', "false")
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)
# ==========================================

STATS = {
    "apps_scanned": 0,
    "apps_needing_cleanup": 0,
    "keys_deleted": 0,
    "failures": 0
}

class Tee(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

def log(message: str, level: str = "INFO", indent: int = 0):
    prefix = ""
    if level == "INFO": prefix = "  ▶"
    elif level == "SUCCESS": prefix = "  ✅"
    elif level == "WARN": prefix = "  ⚠️"
    elif level == "ERROR": prefix = "  ❌"
    elif level == "HEADER": prefix = "\n🔹"
    elif level == "SUBHEADER": prefix = "\n   📌"

    spacer = "   " * indent
    formatted_msg = f"{spacer}{prefix} {message}"
    
    if level == "HEADER":
        print(f"{'='*60}\n{formatted_msg}\n{'='*60}")
    else:
        print(formatted_msg)

def run_command(command: List[str], error_message: str, suppress_log: bool = False) -> Tuple[bool, str]:
    try:
        if "apigeecli" in command and "--disable-check" not in command:
            command.append("--disable-check")

        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, check=True
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not suppress_log:
            log(f"{error_message}: {e.stderr.strip()}", "ERROR", indent=1)
        return False, e.stderr.strip()
    except FileNotFoundError:
        log(f"Required command not found: {command[0]}", "ERROR")
        return False, "Command not found"

def authenticate_user() -> str:
    log("Authenticating User...", "HEADER")
    
    if SA_ENABLE.lower() == "true":
        log(f"Authenticating via Service Account: {os.path.basename(SERVICE_ACCOUNT_KEY_FILE)}", "INFO", indent=1)
        subprocess.run(["gcloud", "auth", "activate-service-account", "--key-file", SERVICE_ACCOUNT_KEY_FILE, "--quiet"], check=True)
    else:
        # Check if a valid token already exists (e.g., from the Agent's validation step)
        success, token = run_command(["gcloud", "auth", "print-access-token"], "Token check", suppress_log=True)
        if success and token:
            log("Active gcloud session found. Proceeding.", "SUCCESS", indent=1)
            return token
            
        # Only trigger the browser if the token is absent
        log("No active session found. Triggering browser login...", "INFO", indent=1)
        subprocess.run(["gcloud", "auth", "login"], check=True)
        
    # Final retrieval for both SA and newly-logged-in Browser users
    success, token = run_command(["gcloud", "auth", "print-access-token"], "Token retrieval failed")
    if success and token:
        return token
    else:
        log("Failed to retrieve access token.", "ERROR", indent=1)
        sys.exit(1)

def parse_json_from_stdout(stdout_str: str) -> Optional[Dict[str, Any]]:
    """Extracts JSON object from CLI output, ignoring surrounding logs."""
    if not stdout_str: return None
    
    start_idx = stdout_str.find('{')
    if start_idx == -1: start_idx = stdout_str.find('[') 
    
    if start_idx != -1:
        json_str = stdout_str[start_idx:]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            end_idx = stdout_str.rfind(']')
            if end_idx == -1: end_idx = stdout_str.rfind('}')
            
            if end_idx != -1 and end_idx >= start_idx:
                try:
                    return json.loads(stdout_str[start_idx : end_idx + 1])
                except:
                    pass
    return None

def cleanup_duplicate_credentials():
    auth_token = authenticate_user()
    
    log("FETCHING ALL APPS WITH CREDENTIALS", "HEADER")
    cmd_list_expand = [
        "apigeecli", "apps", "list", 
        "-o", APIGEE_HYB_ORG, 
        "-t", auth_token, 
        "--expand"
    ]
    
    success, output = run_command(cmd_list_expand, "Failed to list apps with expanded details.", suppress_log=True)
    
    if not success:
        log(f"Fatal: Could not fetch app list. Error: {output}", "ERROR", indent=1)
        sys.exit(1)

    raw_response = parse_json_from_stdout(output)
    
    if not raw_response or 'app' not in raw_response or not isinstance(raw_response['app'], list):
        log("Failed to parse app list. Verify permissions or apigeecli version.", "ERROR", indent=1)
        sys.exit(1)

    all_apps = raw_response['app']
    log(f"Found {len(all_apps)} apps in the organization. Scanning for duplicates...", "SUCCESS", indent=1)

    for app in all_apps:
        STATS["apps_scanned"] += 1
        app_name = app.get("name")
        developer_email = app.get("developerId") 
        credentials = app.get("credentials", [])

        if len(credentials) <= 1:
            continue

        log(f"App: {app_name} (Dev: {developer_email})", "SUBHEADER")
        log(f"Found {len(credentials)} total credentials.", "INFO", indent=1)

        creds_with_products = []
        creds_without_products = []
        
        for cred in credentials:
            products = cred.get("apiProducts", [])
            if products and len(products) > 0:
                creds_with_products.append(cred)
            else:
                creds_without_products.append(cred)

        # Rule 1: All credentials lack products. Do nothing.
        if len(creds_with_products) == 0:
            log("All credentials are empty (no products). Taking no action.", "WARN", indent=2)
            continue
        
        # Rule 2: We have valid credentials AND extra empty credentials. Delete the empty ones.
        if len(creds_without_products) > 0:
            STATS["apps_needing_cleanup"] += 1
            log(f"Found {len(creds_without_products)} empty credential(s) to delete.", "INFO", indent=2)
            
            for cred_to_delete in creds_without_products:
                key_to_delete = cred_to_delete.get("consumerKey")
                log(f"Deleting key: {key_to_delete[:8]}...", "WARN", indent=3)
                
                cmd_del = [
                    "apigeecli", "apps", "keys", "delete",
                    "-n", app_name,
                    "-d", developer_email,  # <--- FIXED: Reverted to -d for apigeecli apps keys delete
                    "-k", key_to_delete,
                    "-o", APIGEE_HYB_ORG,
                    "-t", auth_token
                ]
                
                del_success, del_output = run_command(cmd_del, "Delete failed", suppress_log=True)
                
                if del_success:
                    log("Key deleted successfully.", "SUCCESS", indent=4)
                    STATS["keys_deleted"] += 1
                else:
                    log(f"Failed to delete key: {del_output}", "ERROR", indent=4)
                    STATS["failures"] += 1
        else:
            # Rule 3: Multiple credentials, all have products. Do nothing.
            log("App is clean (multiple valid keys). No action needed.", "INFO", indent=2)

    print(f"\n{'='*60}")
    print(f"📊 CLEANUP SUMMARY")
    print(f"{'='*60}")
    for k, v in STATS.items():
        print(f"  {k.replace('_', ' ').title().ljust(25)} : {v}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    log_dir = "run_logs/cleanup_credentials_run"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"cleanup_credentials_run_{timestamp}.log")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_filename, 'w', encoding='utf-8')
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)
    
    try:
        print(f"--- SCRIPT 'cleanup_duplicate_credentials.py' STARTED ---")
        cleanup_duplicate_credentials()
        print(f"--- SCRIPT FINISHED ---")
    except KeyboardInterrupt:
        print(f"\n--- SCRIPT ABORTED BY USER ---")
    except Exception as e:
        print(f"\n--- SCRIPT FAILED ---")
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()