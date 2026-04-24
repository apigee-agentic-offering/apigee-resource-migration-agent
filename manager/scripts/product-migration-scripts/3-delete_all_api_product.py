import os
import subprocess
import sys
import json
import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from typing import List, Tuple

# ==========================================
# --- CONFIGURATION ---
# ==========================================
APIGEE_HYB_ORG = config.APIGEE_HYB_ORG 
SA_ENABLE = config.SA_ENABLE
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)
REGISTRY_LOG_DIR = config.REGISTRY_LOG_DIR
PRODUCT_REGISTRY_FILE = "api_product_import_registry.json"
# ==========================================

STATS = {
    "products_deleted": 0,
    "skipped_in_use": 0,
    "already_missing": 0,
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
    """Handles Auth and returns token. Prints URL if browser login is needed."""
    sa_enable = getattr(config, 'SA_ENABLE', "false").strip().lower()
    
    if sa_enable == "true":
        if not os.path.exists(SERVICE_ACCOUNT_KEY_FILE):
            log(f"SA Key not found: {SERVICE_ACCOUNT_KEY_FILE}", "ERROR")
            sys.exit(1)
        log(f"Using Service Account: {os.path.basename(SERVICE_ACCOUNT_KEY_FILE)}", "INFO")
        subprocess.run(["gcloud", "auth", "activate-service-account", "--key-file", SERVICE_ACCOUNT_KEY_FILE, "--quiet"], check=True)
    else:
        log("Browser login required. If the URL does not open automatically, please copy it from below:", "WARN")
        try:
            # IMPORTANT: Do NOT capture output here, or the URL will be hidden from the user
            subprocess.run(["gcloud", "auth", "application-default", "login"], check=True)
            result = subprocess.run(["gcloud", "auth", "application-default", "print-access-token"], stdout=subprocess.PIPE, text=True)
        except Exception as e:
            log(f"Browser login triggered: {e}", "INFO")

    result = subprocess.run(["gcloud", "auth", "print-access-token"], stdout=subprocess.PIPE, text=True, check=True)
    return result.stdout.strip()

def delete_api_product(product_name: str, token: str) -> Tuple[bool, str]:
    """Uses apigeecli to delete an API Product."""
    cmd = [
        "apigeecli", "products", "delete",
        "-n", product_name,
        "-o", APIGEE_HYB_ORG,
        "-t", token
    ]
    return run_command(cmd, f"Failed to delete {product_name}", suppress_log=True)

def main():
    registry_path = os.path.join(REGISTRY_LOG_DIR, PRODUCT_REGISTRY_FILE)
    
    if not os.path.exists(registry_path):
        log(f"Registry file not found at {registry_path}. Nothing to delete.", "WARN")
        return

    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            registry_data = json.load(f)
    except json.JSONDecodeError:
        log("Registry file is corrupt or empty.", "ERROR")
        return

    # Check if the org exists in the new dictionary structure
    if not isinstance(registry_data, dict) or APIGEE_HYB_ORG not in registry_data:
        log(f"No API Products found in registry for organization: {APIGEE_HYB_ORG}", "INFO")
        return

    org_products = registry_data[APIGEE_HYB_ORG]
    
    if not org_products:
        log(f"Registry list is empty for {APIGEE_HYB_ORG}. No API Products to delete.", "INFO")
        return

    log("Checking prerequisites and authenticating...", "HEADER")
    auth_token = authenticate_user()

    log(f"Found {len(org_products)} API Product records in the registry for '{APIGEE_HYB_ORG}'.", "HEADER")
    
    remaining_org_products = []
    processed_products = set()

    # Process in reverse order
    for entry in reversed(org_products):
        product_name = entry.get("name")
        
        if product_name in processed_products:
            continue
            
        log(f"API Product: {product_name}", "SUBHEADER")
        
        if not product_name:
            log("Invalid registry entry. Skipping.", "WARN", indent=1)
            remaining_org_products.insert(0, entry) 
            continue
            
        success, output = delete_api_product(product_name, auth_token)
        processed_products.add(product_name)
        
        if success:
            log(f"Successfully deleted API Product '{product_name}'.", "SUCCESS", indent=1)
            STATS["products_deleted"] += 1
        else:
            if "associated with" in output.lower() or "409" in output:
                log(f"Skipped: Product is currently in use by Developer Apps.", "WARN", indent=1)
                STATS["skipped_in_use"] += 1
                remaining_org_products.insert(0, entry) 
            elif "not found" in output.lower() or "404" in output or "does not exist" in output.lower():
                log("API Product already deleted or does not exist on Apigee.", "WARN", indent=1)
                STATS["already_missing"] += 1
            else:
                log(f"Deletion failed: {output}", "ERROR", indent=1)
                STATS["failures"] += 1
                remaining_org_products.insert(0, entry) 

    # Re-write the updated list back into the main registry dictionary
    try:
        registry_data[APIGEE_HYB_ORG] = remaining_org_products
        
        # Clean up the key if the list is empty
        if len(remaining_org_products) == 0:
            del registry_data[APIGEE_HYB_ORG]
            
        with open(registry_path, 'w', encoding='utf-8') as f:
            json.dump(registry_data, f, indent=2)
            
        log(f"Registry updated ({len(remaining_org_products)} products remaining for this org).", "INFO")
            
    except Exception as e:
        log(f"Failed to update registry file: {e}", "ERROR")

    print(f"\n{'='*60}")
    print(f"📊 ROLLBACK SUMMARY")
    print(f"{'='*60}")
    for k, v in STATS.items():
        print(f"  {k.replace('_', ' ').title().ljust(25)} : {v}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    log_dir = "run_logs/delete_api_products_run"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"delete_products_run_{timestamp}.log")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_filename, 'w', encoding='utf-8')
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)
    
    try:
        print(f"--- SCRIPT 'delete_api_products.py' STARTED ---")
        main()
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