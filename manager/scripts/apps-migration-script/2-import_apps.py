import os
import glob
import subprocess
import sys
from typing import List, Tuple
import datetime
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ==========================================
# --- CONFIGURATION ---
# ==========================================
BASE_DIR = getattr(config, 'OUTPUT_DIR', 'transformed_resources')
APP_DIR = os.path.join(BASE_DIR, "org", "apps_transformed")
APIGEE_HYB_ORG = getattr(config, 'APIGEE_HYB_ORG', 'default_org')
SA_ENABLE = getattr(config, 'SA_ENABLE', 'false')
SERVICE_ACCOUNT_KEY_FILE = os.path.join(getattr(config, 'SA_KEY_DIR', ''), getattr(config, 'SA_KEY_FILE', ''))
REGISTRY_LOG_DIR = getattr(config, 'REGISTRY_LOG_DIR', 'registry-log')
APP_REGISTRY_FILE = "app_import_registry.json"
# ==========================================

APP_REGISTRY = []
STATS = {
    "files_processed": 0, 
    "apps_created": 0, 
    "files_deleted": 0, 
    "failures": 0,
    "rollbacks_executed": 0
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
    
    spacer = "   " * indent
    print(f"{spacer}{prefix} {message}")

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


def rollback_single_app(token: str, app_name: str, developer_email: str):
    """Deletes a specific app if key import fails to ensure 'all or nothing' migration."""
    log(f"ATOMIC ROLLBACK: Deleting failed app shell...", "WARN", indent=2)
    
    # EXACT COMMAND THAT WORKED IN TERMINAL
    cmd = ["apigeecli", "apps", "delete", "-n", app_name, "-i", developer_email, "-o", APIGEE_HYB_ORG, "-t", token]
    
    success, output = run_command(cmd, f"Failed to rollback app", suppress_log=True)
    if success:
        log("Rollback successful. Shell removed.", "INFO", indent=3)
    else:
        log(f"Rollback failed: {output}", "ERROR", indent=3)
    STATS["rollbacks_executed"] += 1


def import_apps(token: str):
    app_files = glob.glob(os.path.join(APP_DIR, "*.json"))
    if not app_files: 
        log("No apps found to import.", "WARN")
        return

    log("Importing Developer Apps", "HEADER")

    for app_file in app_files:
        STATS["files_processed"] += 1
        
        try:
            with open(app_file, 'r', encoding='utf-8') as f:
                app_data = json.load(f)
            
            app_name = app_data.get("name")
            dev_email = app_data.get("developerEmail", app_data.get("createdBy"))
            consumer_key = app_data.get("consumerKey")
            consumer_secret = app_data.get("consumerSecret")
            
            if not app_name or not dev_email or not consumer_key or not consumer_secret:
                 log(f"❌ Skipping {os.path.basename(app_file)}: Missing required payload fields.", "ERROR", indent=1)
                 STATS["failures"] += 1
                 continue
                 
            log(f"📌 App: {app_name} (Dev: {dev_email})", "INFO", indent=1)

            # Extract Products (Handles both root-level and nested formats)
            products_in_app = []
            for p in app_data.get("apiProducts", []):
                if isinstance(p, dict) and p.get("apiproduct"):
                    products_in_app.append(p.get("apiproduct"))
                elif isinstance(p, str):
                    products_in_app.append(p)
            for cred in app_data.get("credentials", []):
                for p in cred.get("apiProducts", []):
                    if isinstance(p, dict) and p.get("apiproduct"):
                        products_in_app.append(p.get("apiproduct"))
                    elif isinstance(p, str):
                        products_in_app.append(p)
            
            products_in_app = list(set(products_in_app)) # Remove duplicates

            # --- STEP 1: Create App Shell with Attributes ---
            cmd_create = [
                "apigeecli", "apps", "create",
                "-n", app_name, "-e", dev_email,
                "-o", APIGEE_HYB_ORG, "-t", token
            ]
            
            attr_list = [f"{a['name']}={a['value']}" for a in app_data.get("attributes", []) if a.get("name") and a.get("value")]
            if attr_list: 
                cmd_create.extend(["--attrs", ",".join(attr_list)])
            if app_data.get("scope"): 
                cmd_create.extend(["--scopes", app_data["scope"]])
            if app_data.get("redirect_uri"): 
                cmd_create.extend(["--callback", app_data["redirect_uri"]])

            shell_success, shell_output = run_command(cmd_create, "Failed to create app shell", suppress_log=True)
            
            if not shell_success:
                if "already exists" in shell_output.lower() or "409" in shell_output:
                    log("App already exists. Skipping.", "WARN", indent=2)
                else:
                    log(f"❌ Failed to create shell: {shell_output.strip()}", "ERROR", indent=2)
                    STATS["failures"] += 1
                continue

            # --- STEP 2: Import Keys and Bind Products ---
            cmd_keys = [
                "apigeecli", "apps", "keys", "create",
                "-o", APIGEE_HYB_ORG, "-t", token,
                "-d", dev_email, "-n", app_name,
                "-k", consumer_key, "-c", consumer_secret
            ]
            if products_in_app: 
                cmd_keys.extend(["--prods", ",".join(products_in_app)])

            key_success, key_output = run_command(cmd_keys, "Failed to import keys", suppress_log=True)
            
            if not key_success:
                log(f"❌ Key import failed: {key_output.strip()}", "ERROR", indent=2)
                rollback_single_app(token, app_name, dev_email)
                STATS["failures"] += 1
                continue

            # --- SUCCESS CASE ---
            log(f"Successfully imported app and credentials.", "SUCCESS", indent=2)
            
            APP_REGISTRY.append({
                "name": app_name,
                "developerEmail": dev_email
            })
            STATS["apps_created"] += 1
            
            try:
                os.remove(app_file)
                STATS["files_deleted"] += 1
            except: pass

        except Exception as e:
            log(f"❌ Unexpected error processing {app_file}: {e}", "ERROR", indent=1)
            STATS["failures"] += 1

def main():
    os.makedirs(REGISTRY_LOG_DIR, exist_ok=True)
    registry_file = os.path.join(REGISTRY_LOG_DIR, APP_REGISTRY_FILE)

    try:
        # Agent has already validated everything. Go straight to execution.
        auth_token = authenticate_user()
        import_apps(auth_token)

        # Save to Org-Specific Registry
        if APP_REGISTRY:
            existing_registry = {}
            if os.path.exists(registry_file):
                try:
                    with open(registry_file, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict): existing_registry = loaded
                except: pass
            
            if APIGEE_HYB_ORG not in existing_registry:
                existing_registry[APIGEE_HYB_ORG] = []
                
            org_registry = existing_registry[APIGEE_HYB_ORG]
            
            # Ensure unique entries based on App Name + Developer Email
            existing_identifiers = {
                f"{item.get('name')}::{item.get('developerEmail')}" 
                for item in org_registry 
                if item.get('name') and item.get('developerEmail')
            }
            added_count = 0
            
            for new_app in APP_REGISTRY:
                identifier = f"{new_app.get('name')}::{new_app.get('developerEmail')}"
                if identifier not in existing_identifiers:
                    org_registry.append(new_app)
                    existing_identifiers.add(identifier)
                    added_count += 1
            
            with open(registry_file, 'w', encoding='utf-8') as f:
                json.dump(existing_registry, f, indent=2)
            log(f"Registry updated ({added_count} new apps appended to '{APIGEE_HYB_ORG}').", "INFO")
            
    except Exception as e:
        log(f"Script crash: {e}", "ERROR")
        sys.exit(1)
    
    print(f"\n{'='*60}\n📊 MIGRATION SUMMARY\n{'='*60}")
    for k, v in STATS.items(): print(f"  {k.replace('_', ' ').title().ljust(25)} : {v}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    log_dir = "run_logs/import_apps_run"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = open(os.path.join(log_dir, f"import_apps_{timestamp}.log"), 'w', encoding='utf-8')
    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)
    try: main()
    finally: log_file.close()