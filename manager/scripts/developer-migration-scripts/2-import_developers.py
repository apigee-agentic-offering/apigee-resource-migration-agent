import os
import glob
import subprocess
import sys
import json
import datetime
from typing import List, Tuple

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config 

# --- CONFIGURATION FROM GLOBAL CONFIG ---
BASE_DIR = config.OUTPUT_DIR
APIGEE_HYB_ORG = config.APIGEE_HYB_ORG
SA_ENABLE = getattr(config, 'SA_ENABLE', "false")
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)
REGISTRY_LOG_DIR = config.REGISTRY_LOG_DIR
DEVELOPER_REGISTRY_FILE = config.DEVELOPER_REGISTRY_FILE

DEV_REGISTRY = []
STATS = {
    "developers_imported": 0,
    "files_deleted": 0,
    "failures": 0,
    "skipped_invalid_json": 0
}

class Tee(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj); f.flush()
    def flush(self):
        for f in self.files: f.flush()

def log(message: str, level: str = "INFO", indent: int = 0):
    prefix = {"INFO": "  ▶", "SUCCESS": "  ✅", "WARN": "  ⚠️", "ERROR": "  ❌", "HEADER": "\n🔹", "SUBHEADER": "\n   📌"}.get(level, "  ▶")
    spacer = "   " * indent
    if level == "HEADER": print(f"{'='*60}\n{prefix} {message}\n{'='*60}")
    else: print(f"{spacer}{prefix} {message}")

def run_command(command: List[str], error_message: str, suppress_log: bool = False) -> Tuple[bool, str]:
    try:
        if "apigeecli" in command and "--disable-check" not in command: command.append("--disable-check")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not suppress_log: log(f"{error_message}: {e.stderr.strip()}", "ERROR", indent=1)
        return False, e.stderr.strip()

def authenticate_user() -> str:
    if SA_ENABLE.lower() == "true":
        log(f"Authenticating via Service Account: {os.path.basename(SERVICE_ACCOUNT_KEY_FILE)}")
        run_command(["gcloud", "auth", "activate-service-account", "--key-file", SERVICE_ACCOUNT_KEY_FILE, "--quiet"], "SA Auth failed")
    else:
        log("Triggering browser login...", "INFO")
        subprocess.run(["gcloud", "auth", "login"], check=True)
    success, token = run_command(["gcloud", "auth", "print-access-token"], "Token retrieval failed")
    return token if (success and token) else sys.exit(1)

def import_developer_files(token: str):
    dev_dir = os.path.join(BASE_DIR, "org", "developers")
    if not os.path.isdir(dev_dir): return
    json_files = glob.glob(os.path.join(dev_dir, "*.json"))
    log("Processing Org-Level Developers", "HEADER")
    for dev_file in json_files:
        log(f"File: {os.path.basename(dev_file)}", "SUBHEADER")
        try:
            with open(dev_file, 'r', encoding='utf-8') as f: data = json.load(f)
            dev_email = data.get("email")
            if not dev_email: continue
            cmd = ["apigeecli", "developers", "create", "-n", dev_email, "-f", data.get("firstName", ""), "-s", data.get("lastName", ""), "-u", data.get("userName", ""), "-o", APIGEE_HYB_ORG, "-t", token]
            if "attributes" in data:
                for attr in data["attributes"]: cmd.extend(["--attrs", f"{attr.get('name')}={attr.get('value', '')}"])
            success, output = run_command(cmd, f"Failed to import {dev_email}", suppress_log=True)
            if success:
                STATS["developers_imported"] += 1
                log(f"[SUCCESS] Imported: {dev_email}", "SUCCESS", 1)
                DEV_REGISTRY.append({"email": dev_email, "upload_time": datetime.datetime.now().isoformat()})
                os.remove(dev_file)
                STATS["files_deleted"] += 1
            elif "409" in output or "already exists" in output.lower():
                log(f"Developer {dev_email} already exists. Skipping.", "WARN", 1)
                os.remove(dev_file)
                STATS["files_deleted"] += 1
            else:
                STATS["failures"] += 1
        except json.JSONDecodeError:
            log(f"Error: Invalid JSON in {os.path.basename(dev_file)}", "ERROR", 1)
            STATS["skipped_invalid_json"] += 1
        except Exception as e: 
            log(f"Error: {e}", "ERROR", 1)
            STATS["failures"] += 1

def main():
    auth_token = authenticate_user()
    registry_file = os.path.join(REGISTRY_LOG_DIR, DEVELOPER_REGISTRY_FILE)
    import_developer_files(auth_token)
    
    if DEV_REGISTRY:
        registry_data = {}
        
        # 1. Load existing registry state
        if os.path.exists(registry_file):
            try:
                with open(registry_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    
                    if isinstance(loaded_data, dict):
                        # It's already the new format
                        registry_data = loaded_data
                    elif isinstance(loaded_data, list):
                        # Migrate old flat list format to the new Org-based format
                        log("Existing registry uses old list format. Migrating to Org-based structure.", "WARN")
                        registry_data[APIGEE_HYB_ORG] = loaded_data
            except json.JSONDecodeError:
                log("Registry JSON is invalid or corrupt. Starting fresh.", "ERROR")

        # 2. Ensure the current target org exists in the registry dictionary
        if APIGEE_HYB_ORG not in registry_data:
            registry_data[APIGEE_HYB_ORG] = []
            
        # 3. De-duplicate newly imported developers against what's already recorded for this org
        existing_org_devs = registry_data[APIGEE_HYB_ORG]
        unique_devs = {item["email"]: item for item in (existing_org_devs + DEV_REGISTRY)}
        
        # 4. Save the nested data back to the registry
        registry_data[APIGEE_HYB_ORG] = list(unique_devs.values())
        
        with open(registry_file, 'w', encoding='utf-8') as f: 
            json.dump(registry_data, f, indent=2)
            
        log("Registry JSON successfully updated with Org-based structure.", "SUCCESS")
        
    # Output structured data for the agent tool wrapper to parse
    print("\n---AGENT_STRUCTURED_OUTPUT---")
    print(json.dumps(STATS))

if __name__ == "__main__":
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run_logs", "import_developers_run")
    os.makedirs(log_dir, exist_ok=True)
    log_file = open(os.path.join(log_dir, f"import_devs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), 'w')
    sys.stdout = Tee(sys.stdout, log_file); sys.stderr = Tee(sys.stderr, log_file)
    try: main()
    finally: log_file.close()