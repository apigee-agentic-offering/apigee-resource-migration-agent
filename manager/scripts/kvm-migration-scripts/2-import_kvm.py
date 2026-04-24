# The `3-import_kvm.py` 
# Script automates the migration and synchronization of Key Value Maps (KVMs) 
# from local JSON files into an Apigee Hybrid organization. It is designed to be idempotent and safe for re-runs.

import os
import glob
import subprocess
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from typing import List, Tuple, Optional, Set
import datetime
import json

# --- CONFIGURATION ---
BASE_DIR = config.OUTPUT_DIR
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)
# ---------------------

# Queue to track newly created maps strictly for rollback during a crash
ROLLBACK_QUEUE = []

# Statistics for Final Summary
STATS = {
    "maps_created": 0,
    "maps_synced": 0,
    "entries_created": 0,
    "entries_updated": 0,
    "entries_skipped": 0,
    "files_processed": 0,
    "files_deleted": 0,
    "failures": 0
}

# --- Tee class for logging ---
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
        print(f"{'='*60}")
        print(formatted_msg)
        print(f"{'='*60}")
    else:
        print(formatted_msg)

def run_command(command: List[str], error_message: str, suppress_log: bool = False) -> Tuple[bool, str]:
    try:
        if "apigeecli" in command and "--disable-check" not in command:
            command.append("--disable-check")

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True
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
    
    success, _ = run_command(["apigeecli", "kvms", "list", "-h"], "apigeecli not found", suppress_log=True)
    if not success:
        log("Installing apigeecli...", "WARN")
        install_cmd = [sys.executable, "-m", "pip", "install", "apigeecli", "--user", "--break-system-packages"]
        run_command(install_cmd, "Failed to install apigeecli")

def authenticate_user() -> str:
    sa_enable = getattr(config, 'SA_ENABLE', "false").strip().lower()

    if sa_enable == "true":
        if not os.path.exists(SERVICE_ACCOUNT_KEY_FILE):
            log(f"FATAL: SA Key not found: {SERVICE_ACCOUNT_KEY_FILE}", "ERROR")
            sys.exit(1)

        log(f"Authenticating via Service Account Key...", "INFO")
        run_command(["gcloud", "auth", "activate-service-account", "--key-file", SERVICE_ACCOUNT_KEY_FILE, "--quiet"], "SA Auth failed")
    else:
        log("Forcing browser login via gcloud...", "INFO")
        try:
            subprocess.run(["gcloud", "auth", "login"], check=True)
            log("Browser login successful.", "SUCCESS", indent=1)
        except subprocess.CalledProcessError:
            log("Browser login failed.", "ERROR", indent=1)
            sys.exit(1)

    success, token = run_command(["gcloud", "auth", "print-access-token"], "Token retrieval failed")
    if success and token: 
        log("Access token retrieved successfully.", "SUCCESS", indent=1)
        return token
    else: 
        sys.exit(1)

def cleanup_on_failure(token: str):
    log("TRANSACTION FAILED. ROLLING BACK NEWLY CREATED MAPS...", "ERROR")
    for item in reversed(ROLLBACK_QUEUE):
        cmd = ["apigeecli", "kvms", "delete", "-n", item['name'], "-o", config.APIGEE_HYB_ORG, "-t", token]
        if item['env']: cmd.extend(["-e", item['env']])
        run_command(cmd, f"Failed to delete {item['name']}")

def fetch_existing_keys(token: str, kvm_name: str, env: Optional[str] = None) -> Set[str]:
    """Fetches keys from Apigee, supporting both Apigee X and OPDK response formats."""
    cmd = [
        "apigeecli", "kvms", "entries", "list",
        "-m", kvm_name,
        "-o", config.APIGEE_HYB_ORG,
        "-t", token
    ]
    if env: cmd.extend(["-e", env])

    success, output = run_command(cmd, "List entries failed", suppress_log=True)
    
    existing_keys = set()
    if success and output:
        try:
            data = json.loads(output)
            
            # Use keyValueEntries for Apigee X/Hybrid, fallback to entry for OPDK
            entries = []
            if isinstance(data, dict):
                entries = data.get("keyValueEntries", data.get("entry", []))
            elif isinstance(data, list): 
                entries = data
            
            for entry in entries:
                if isinstance(entry, dict) and 'name' in entry:
                    existing_keys.add(entry['name'])
                elif isinstance(entry, str):
                    existing_keys.add(entry)
        except json.JSONDecodeError:
            pass 
            
    return existing_keys

def process_kvm_entries(kvm_name: str, json_file: str, token: str, env: Optional[str], registry_data: dict):
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        log(f"Error reading file {json_file}: {e}", "ERROR", indent=2)
        return False

    entries = data.get("entry", [])
    if not entries:
        log(f"No entries found in file. Skipping entry sync.", "WARN", indent=2)
        return True

    # Initialize nested dict structure for this KVM in the registry
    org_name = config.APIGEE_HYB_ORG
    scope = env if env else "org"

    if org_name not in registry_data: registry_data[org_name] = {}
    if scope not in registry_data[org_name]: registry_data[org_name][scope] = {}
    if kvm_name not in registry_data[org_name][scope]: registry_data[org_name][scope][kvm_name] = {}

    # Fetch what is currently on the Apigee Server
    existing_keys = fetch_existing_keys(token, kvm_name, env)
    log(f"Syncing {len(entries)} entries (Current Server Map Size: {len(existing_keys)} keys)", "INFO", indent=2)

    local_created = 0
    local_updated = 0
    local_skipped = 0

    for entry in entries:
        key = entry.get("name")
        value = entry.get("value")

        if not key or value is None: continue

        # --- SMART SKIP LOGIC ---
        # Check if we already imported this exact key/value pair previously
        if key in registry_data[org_name][scope][kvm_name]:
            if registry_data[org_name][scope][kvm_name][key] == value:
                local_skipped += 1
                continue

        # If it's already on the server, we UPDATE. Otherwise, CREATE.
        action = "update" if key in existing_keys else "create"

        cmd = [
            "apigeecli", "kvms", "entries", action, 
            "-m", kvm_name,
            "-o", org_name,
            "--key", key,
            "--value", value,
            "-t", token
        ]
        if env: cmd.extend(["-e", env])

        success, _ = run_command(cmd, f"Failed to {action} entry '{key}'", suppress_log=True)

        if not success:
            log(f"Failed to {action} key: {key}", "ERROR", indent=3)
            return False
        else:
            action_past_tense = "Created" if action == "create" else "Updated"
            # Ensure safe terminal logging by escaping newlines in values
            safe_value = str(value).replace("\n", "\\n").replace("\r", "")
            log(f"{action_past_tense} entry: [{key}:{safe_value}]", "INFO", indent=3)
            
            # Update Local Registry State
            registry_data[org_name][scope][kvm_name][key] = value
            
            if action == "create": local_created += 1
            else: local_updated += 1

    if local_created > 0 or local_updated > 0 or local_skipped > 0:
        log(f"Entries Synced: +{local_created} Created, ~{local_updated} Updated, ⏭ {local_skipped} Skipped", "SUCCESS", indent=2)
    
    STATS["entries_created"] += local_created
    STATS["entries_updated"] += local_updated
    STATS["entries_skipped"] += local_skipped
    
    return True

def import_kvms_generic(token: str, scope_dir: str, scope_type: str, registry_data: dict):
    is_env_scope = scope_type != "org"
    display_scope = f"Env: {scope_type}" if is_env_scope else "Org-Level"
    
    if not os.path.isdir(scope_dir): return
    files = glob.glob(os.path.join(scope_dir, "*.json"))
    if not files: return

    log(f"Processing {display_scope}", "HEADER")
    log(f"Found {len(files)} KVM files to process.", "INFO")

    for kvm_file in files:
        kvm_name = os.path.basename(kvm_file).replace(".json", "")
        log(f"Map: {kvm_name}", "SUBHEADER")
        STATS["files_processed"] += 1
        
        create_cmd = [
            "apigeecli", "kvms", "create",
            "-n", kvm_name,
            "-o", config.APIGEE_HYB_ORG,
            "-t", token
        ]
        if is_env_scope: create_cmd.extend(["-e", scope_type])

        success, output = run_command(create_cmd, "", suppress_log=True)

        if success:
            log(f"Created new KVM map.", "SUCCESS", indent=1)
            ROLLBACK_QUEUE.append({'name': kvm_name, 'env': scope_type if is_env_scope else None})
            STATS["maps_created"] += 1
        else:
            if "409" in output or "already exists" in output.lower():
                log(f"Map already exists. Checking for updates...", "INFO", indent=1)
                STATS["maps_synced"] += 1
            else:
                log(f"Failed to create map: {output}", "ERROR", indent=1)
                STATS["failures"] += 1
                continue

        # Pass registry_data to process_kvm_entries to be updated
        if process_kvm_entries(kvm_name, kvm_file, token, scope_type if is_env_scope else None, registry_data):
             try:
                 os.remove(kvm_file)
                 log(f"Migration complete. Source file deleted.", "SUCCESS", indent=1)
                 STATS["files_deleted"] += 1
             except Exception as e:
                 log(f"Synced but failed to delete file: {e}", "WARN", indent=1)
        else:
             log(f"Entry sync failed. File retained for retry.", "ERROR", indent=1)
             STATS["failures"] += 1

def main(registry_log_dir):
    ensure_prerequisites()
    auth_token = authenticate_user()
    
    os.makedirs(registry_log_dir, exist_ok=True)
    registry_file = os.path.join(registry_log_dir, config.KVM_REGISTRY_FILE)

    # LOAD EXISTING REGISTRY STATE
    registry_data = {}
    if os.path.exists(registry_file):
        try:
            with open(registry_file, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                # Check if the existing file is an old format (list) and reset if needed
                if isinstance(loaded_data, dict):
                    registry_data = loaded_data
                else:
                    log("Existing registry uses an old list format. Migrating to new structured dictionary.", "WARN")
                    registry_data = {}
        except json.JSONDecodeError:
            log("Existing registry corrupt. Starting fresh.", "WARN")

    try:
        import_kvms_generic(auth_token, os.path.join(BASE_DIR, "org", "kvms"), "org", registry_data)
        
        env_root = os.path.join(BASE_DIR, "env")
        if os.path.isdir(env_root):
            for env_dir in glob.glob(os.path.join(env_root, "*")):
                if os.path.isdir(env_dir):
                    env_name = os.path.basename(env_dir)
                    import_kvms_generic(auth_token, os.path.join(env_dir, "kvms"), env_name, registry_data)

        # SAVE UPDATED REGISTRY STATE
        with open(registry_file, 'w', encoding='utf-8') as f:
            json.dump(registry_data, f, indent=2)
        log(f"Registry JSON successfully updated.", "SUCCESS")
            
    except Exception as e:
        log(f"Script crash: {e}", "ERROR")
        cleanup_on_failure(auth_token)
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"📊 MIGRATION SUMMARY")
    print(f"{'='*60}")
    print(f"  Files Processed : {STATS['files_processed']}")
    print(f"  Maps Created    : {STATS['maps_created']}")
    print(f"  Maps Synced     : {STATS['maps_synced']}")
    print(f"  Entries Created : {STATS['entries_created']}")
    print(f"  Entries Updated : {STATS['entries_updated']}")
    print(f"  Entries Skipped : {STATS['entries_skipped']}")
    print(f"  Files Deleted   : {STATS['files_deleted']}")
    print(f"  Failures        : {STATS['failures']}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    log_dir = "run_logs/import_kvms_run"
    os.makedirs(log_dir, exist_ok=True)
    registry_log_dir = config.REGISTRY_LOG_DIR
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"import_kvms_run_{timestamp}.log")
    
    log_file = open(log_filename, 'w', encoding='utf-8')
    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)
    
    try:
        print(f"--- SCRIPT 'import_kvms.py' STARTED ---")
        main(registry_log_dir)
        print(f"--- SCRIPT FINISHED ---")
    finally:
        log_file.close()