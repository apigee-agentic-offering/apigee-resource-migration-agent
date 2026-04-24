import os
import subprocess
import sys
import json
import datetime
from typing import List, Tuple
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config 

# ==========================================
# --- CONFIGURATION ---
# ==========================================
APIGEE_HYB_ORG = getattr(config, 'APIGEE_HYB_ORG', 'default_org')
SA_ENABLE = getattr(config, 'SA_ENABLE', 'false')
SERVICE_ACCOUNT_KEY_FILE = os.path.join(getattr(config, 'SA_KEY_DIR', ''), getattr(config, 'SA_KEY_FILE', ''))
REGISTRY_LOG_DIR = getattr(config, 'REGISTRY_LOG_DIR', 'registry-log')
APP_REGISTRY_FILE = "app_import_registry.json"
# ==========================================

STATS = {
    "apps_deleted": 0,
    "failures": 0,
    "already_missing": 0
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
    if SA_ENABLE.lower() == "true":
        if not os.path.exists(SERVICE_ACCOUNT_KEY_FILE):
            log(f"FATAL: SA Key not found: {SERVICE_ACCOUNT_KEY_FILE}", "ERROR")
            sys.exit(1)
        run_command(["gcloud", "auth", "activate-service-account", "--key-file", SERVICE_ACCOUNT_KEY_FILE, "--quiet"], "SA Auth failed")
    else:
        log("Forcing browser login via gcloud...", "INFO")
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

def delete_app(app_name: str, developer_email: str, token: str) -> Tuple[bool, str]:
    """Uses apigeecli to delete a Developer App."""
    cmd = [
        "apigeecli", "apps", "delete",
        "-n", app_name,
        "-i", developer_email,  # <--- FIXED: Changed from -d to -i
        "-o", APIGEE_HYB_ORG,
        "-t", token
    ]
    return run_command(cmd, f"Failed to delete {app_name}", suppress_log=True)

def main():
    registry_path = os.path.join(REGISTRY_LOG_DIR, APP_REGISTRY_FILE)
    
    if not os.path.exists(registry_path):
        log(f"Registry file not found at {registry_path}. Nothing to delete.", "WARN")
        return

    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            registry_data = json.load(f)
    except json.JSONDecodeError:
        log("Registry file is corrupt or empty.", "ERROR")
        return

    apps_to_delete = registry_data.get(APIGEE_HYB_ORG, [])
    
    if not apps_to_delete:
        log(f"No Apps to delete for organization '{APIGEE_HYB_ORG}' in registry.", "INFO")
        return

    print(f"\n{'!'*60}")
    print(f"🧨 WARNING: DESTRUCTIVE ACTION DETECTED 🧨")
    print(f"{'!'*60}")
    print(f"You are about to delete {len(apps_to_delete)} Developer Apps for org '{APIGEE_HYB_ORG}' based on '{APP_REGISTRY_FILE}'.")
    print(f"{'!'*60}")
    
    confirmation = input("\nType 'YES' to confirm and proceed with deletion: ").strip().upper()
    if confirmation != "YES":
        log("Deletion cancelled by user. Exiting safely.", "SUCCESS")
        sys.exit(0)

    log("Checking prerequisites and authenticating...", "HEADER")
    auth_token = authenticate_user()

    log(f"Starting deletion process for {len(apps_to_delete)} Apps.", "HEADER")
    
    remaining_registry = []
    processed_apps = set()

    # Process in reverse order so the most recently added apps are deleted first
    for entry in reversed(apps_to_delete):
        app_name = entry.get("name")
        developer_email = entry.get("developerEmail")
        
        # Prevent double-deletion attempts if registry accidentally has duplicates
        app_identifier = f"{app_name}::{developer_email}"
        if app_identifier in processed_apps:
            continue
            
        log(f"App: {app_name} (Dev: {developer_email})", "SUBHEADER")
        
        if not app_name or not developer_email:
            log("Invalid registry entry (missing name or email). Skipping.", "WARN", indent=1)
            remaining_registry.insert(0, entry) # Put it back in original order
            continue
            
        success, output = delete_app(app_name, developer_email, auth_token)
        processed_apps.add(app_identifier)
        
        if success:
            log(f"Successfully deleted App '{app_name}'.", "SUCCESS", indent=1)
            STATS["apps_deleted"] += 1
        else:
            if "not found" in output.lower() or "404" in output or "does not exist" in output.lower():
                log("App already deleted or does not exist on Apigee.", "WARN", indent=1)
                STATS["already_missing"] += 1
            else:
                log(f"Deletion failed: {output}", "ERROR", indent=1)
                STATS["failures"] += 1
                remaining_registry.insert(0, entry) # Keep it in registry if it failed

    # Re-write the registry file to update items that failed to delete for this org
    try:
        registry_data[APIGEE_HYB_ORG] = remaining_registry
        
        with open(registry_path, 'w', encoding='utf-8') as f:
            json.dump(registry_data, f, indent=2)
            
        if len(remaining_registry) == 0:
            log(f"All registered apps for org '{APIGEE_HYB_ORG}' deleted.", "SUCCESS")
        else:
            log(f"Registry updated for org '{APIGEE_HYB_ORG}' ({len(remaining_registry)} apps remaining).", "INFO")
            
    except Exception as e:
        log(f"Failed to update registry file: {e}", "ERROR")

    print(f"\n{'='*60}")
    print(f"📊 ROLLBACK SUMMARY")
    print(f"{'='*60}")
    for k, v in STATS.items():
        print(f"  {k.replace('_', ' ').title().ljust(25)} : {v}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    log_dir = "run_logs/delete_apps_run"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"delete_apps_run_{timestamp}.log")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_filename, 'w', encoding='utf-8')
    sys.stdout = Tee(original_stdout, log_file)
    sys.stderr = Tee(original_stderr, log_file)
    
    try:
        print(f"--- SCRIPT 'delete_apps.py' STARTED ---")
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