import os
import glob
import subprocess
import sys
from typing import List, Tuple, Set
import datetime
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ==========================================
# --- CONFIGURATION ---
# ==========================================
BASE_DIR = config.OUTPUT_DIR
PRODUCT_DIR = os.path.join(BASE_DIR, "org", "apiproducts")
APIGEE_HYB_ORG = config.APIGEE_HYB_ORG
SA_ENABLE = config.SA_ENABLE 
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)
REGISTRY_LOG_DIR = config.REGISTRY_LOG_DIR
PRODUCT_REGISTRY_FILE = "api_product_import_registry.json"
# ==========================================

PRODUCT_REGISTRY = []
STATS = {
    "files_processed": 0, 
    "products_created": 0, 
    "skipped_missing_proxies": 0,
    "files_deleted": 0, 
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

def ensure_prerequisites():
    log("Checking Environment Dependencies...", "HEADER")
    success, _ = run_command(["gcloud", "--version"], "gcloud not installed", suppress_log=True)
    if not success: sys.exit(1)
    
    success, _ = run_command(["apigeecli", "products", "list", "-h"], "apigeecli not found", suppress_log=True)
    if not success:
        log("Installing apigeecli...", "WARN")
        run_command([sys.executable, "-m", "pip", "install", "apigeecli", "--user", "--break-system-packages"], "Failed to install apigeecli")

def authenticate_user() -> str:
    log("Authenticating User...", "HEADER")
    if SA_ENABLE.lower() == "true":
        if not os.path.exists(SERVICE_ACCOUNT_KEY_FILE):
            log(f"FATAL: SA Key not found: {SERVICE_ACCOUNT_KEY_FILE}", "ERROR")
            sys.exit(1)
        run_command(["gcloud", "auth", "activate-service-account", "--key-file", SERVICE_ACCOUNT_KEY_FILE, "--quiet"], "SA Auth failed")
        log("Authenticated via Service Account.", "SUCCESS", indent=1)
    else:
        log("Forcing browser login via gcloud...", "INFO", indent=1)
        try:
            subprocess.run(["gcloud", "auth", "login"], check=True)
            log("Browser login successful.", "SUCCESS", indent=1)
        except subprocess.CalledProcessError:
            log("Browser login failed.", "ERROR", indent=1)
            sys.exit(1)

    success, token = run_command(["gcloud", "auth", "print-access-token"], "Token retrieval failed", suppress_log=True)
    if success and token: 
        log("Access token retrieved.", "SUCCESS", indent=1)
        return token
    sys.exit(1)

def get_hybrid_proxy_list(token: str) -> Set[str]:
    log("Fetching remote proxy list for validation...", "INFO")
    
    cmd = ["apigeecli", "apis", "list", "-o", APIGEE_HYB_ORG, "-t", token]
    success, output = run_command(cmd, "Could not fetch proxy list", suppress_log=True)
    
    if not success:
        log("Failed to fetch proxy list. Aborting import.", "ERROR", indent=1)
        sys.exit(1)
        
    try:
        data = json.loads(output)
        if "proxies" in data and data["proxies"] is None:
             log("Found 0 proxies in the organization.", "WARN", indent=1)
             return set()
             
        proxy_list = [proxy.get("name") for proxy in data.get("proxies", []) if proxy.get("name")]
        proxy_set = set(proxy_list)
        
        log(f"Found {len(proxy_set)} proxies in the organization.", "SUCCESS", indent=1)
        return proxy_set
        
    except json.JSONDecodeError:
        log("Failed to parse proxy list output.", "ERROR", indent=1)
        sys.exit(1)

def import_api_products(token: str, hybrid_proxies: Set[str]):
    product_files = glob.glob(os.path.join(PRODUCT_DIR, "*.json"))
    if not product_files: return

    log("Importing API Products", "HEADER")

    for product_file in product_files:
        STATS["files_processed"] += 1
        product_name = "Unknown"
        
        try:
            with open(product_file, 'r', encoding='utf-8') as f:
                product_data = json.load(f)
            
            product_name = product_data.get("name", "Unknown")
            log(f"Product: {product_name}", "SUBHEADER")
            
            display_name = product_data.get("displayName")
            approval_type = product_data.get("approvalType")
            proxies_required = product_data.get("proxies", [])
            environments = product_data.get("environments", [])
            
            if not all([product_name, display_name, approval_type]):
                 log(f"Skipping {os.path.basename(product_file)}: Missing required fields.", "WARN", indent=1)
                 STATS["failures"] += 1
                 continue

            # Proxy Validation against Live Environment
            missing_proxies = [p for p in proxies_required if p not in hybrid_proxies]
            if missing_proxies:
                log(f"Skipping due to missing proxies on Apigee: {missing_proxies}", "WARN", indent=1)
                STATS["skipped_missing_proxies"] += 1
                continue 
            
            # Construct Command
            cmd = [
                "apigeecli", "products", "create",
                "-n", product_name, "-o", APIGEE_HYB_ORG, "-t", token,
                "-m", display_name, "-f", approval_type
            ]
            
            if product_data.get("description"): cmd.extend(["-d", product_data["description"]])
            for env in environments: cmd.extend(["-e", env])
            for proxy in proxies_required: cmd.extend(["-p", proxy])
            for scope in product_data.get("scopes", []): cmd.extend(["-s", scope])
                
            attr_list = [f"{attr['name']}={attr['value']}" for attr in product_data.get("attributes", []) if 'name' in attr and 'value' in attr]
            if attr_list:
                cmd.extend(["--attrs", ",".join(attr_list)])

            # Execute
            success, output = run_command(cmd, f"Failed to create", suppress_log=True)
            
            if success:
                log(f"Successfully created product.", "SUCCESS", indent=1)
                
                # --- NEW REGISTRY DATA EXTRACTION ---
                dev_email = "unknown"
                for attr in product_data.get("attributes", []):
                    if attr.get("name") == "developer":
                        dev_email = attr.get("value", "unknown")
                        break
                        
                env_str = ",".join(environments) if environments else "all"
                
                PRODUCT_REGISTRY.append({
                    "name": product_name,
                    "env": env_str,
                    "developer": dev_email
                })
                # ------------------------------------
                
                STATS["products_created"] += 1
                
                try:
                    os.remove(product_file)
                    log(f"Source file deleted.", "INFO", indent=2)
                    STATS["files_deleted"] += 1
                except Exception as e:
                     log(f"Created but failed to delete file: {e}", "WARN", indent=2)
            else:
                if "409" in output or "already exists" in output.lower():
                    log("Product already exists. Skipping creation.", "WARN", indent=1)
                else:
                    log("Failed to create:", "ERROR", indent=1)
                    for line in output.splitlines():
                        log(line, "ERROR", indent=2)
                STATS["failures"] += 1

        except Exception as e:
            log(f"Unexpected error: {e}", "ERROR", indent=1)
            STATS["failures"] += 1

def main():
    ensure_prerequisites()
    os.makedirs(REGISTRY_LOG_DIR, exist_ok=True)
    registry_file = os.path.join(REGISTRY_LOG_DIR, PRODUCT_REGISTRY_FILE)

    try:
        auth_token = authenticate_user()
        hybrid_proxies = get_hybrid_proxy_list(auth_token)
        
        import_api_products(auth_token, hybrid_proxies)

        # Update Registry with ORG-SPECIFIC Structure
        if PRODUCT_REGISTRY:
            existing_registry = {}
            if os.path.exists(registry_file):
                try:
                    with open(registry_file, 'r', encoding='utf-8') as f:
                        loaded_reg = json.load(f)
                        if isinstance(loaded_reg, dict):
                            existing_registry = loaded_reg
                        else:
                            log("Old flat registry format detected. Overwriting with Org-Specific structure.", "WARN")
                except json.JSONDecodeError:
                    log("Existing registry corrupt. Creating new.", "WARN")
            
            # Ensure the organization key exists
            if APIGEE_HYB_ORG not in existing_registry:
                existing_registry[APIGEE_HYB_ORG] = []
                
            org_registry = existing_registry[APIGEE_HYB_ORG]
            
            # Ensure unique entries based on product name
            existing_names = {item.get("name") for item in org_registry if item.get("name")}
            added_count = 0
            
            for new_prod in PRODUCT_REGISTRY:
                if new_prod.get("name") not in existing_names:
                    org_registry.append(new_prod)
                    existing_names.add(new_prod.get("name"))
                    added_count += 1
            
            with open(registry_file, 'w', encoding='utf-8') as f:
                json.dump(existing_registry, f, indent=2)
            log(f"Registry updated ({added_count} new products appended to org '{APIGEE_HYB_ORG}').", "INFO")
            
    except Exception as e:
        log(f"Script crash: {e}", "ERROR")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"📊 MIGRATION SUMMARY")
    print(f"{'='*60}")
    for k, v in STATS.items():
        print(f"  {k.replace('_', ' ').title().ljust(25)} : {v}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    log_dir = "run_logs/import_api_products_run"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"import_products_run_{timestamp}.log")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_filename, 'w', encoding='utf-8')
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)
    
    try:
        print(f"--- SCRIPT 'import_api_product.py' STARTED ---")
        main()
        print(f"--- SCRIPT FINISHED ---")
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()