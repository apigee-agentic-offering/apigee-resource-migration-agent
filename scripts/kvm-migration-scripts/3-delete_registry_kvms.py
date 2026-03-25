import os
import subprocess
import sys
import datetime # Added for logging
import json
import argparse

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# --- LOGGING HELPER ---
class Tee(object):
    """Ensures logs go to both console and file."""
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

# --- CONFIGURATION ---
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)
REGISTRY_FILE = os.path.join(config.REGISTRY_LOG_DIR, getattr(config, 'KVM_REGISTRY_FILE', 'kvm_import_registry.json'))

STATS = {
    "deleted": 0,
    "failed": 0, # Fixed typo from user script 'failures' vs 'failed'
    "not_found_in_registry": 0
}

def log(message: str, level: str = "INFO", indent: int = 0):
    prefix = {"INFO": "  ▶", "SUCCESS": "  ✅", "WARN": "  ⚠️", "ERROR": "  ❌"}.get(level, "  ▶")
    print(f"{'    ' * indent}{prefix} {message}")

def run_command(command: list) -> bool:
    """Executes a command and returns success status."""
    if "apigeecli" in command and "--disable-check" not in command:
        command.append("--disable-check")
    try:
        # We don't pipe stdout here so we can see the output in the logs
        subprocess.run(command, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        log(f"Command Error: {e.stderr.strip()}", "ERROR", 1)
        return False

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

def delete_kvm(token: str, org: str, scope: str, kvm_name: str) -> bool:
    cmd = ["apigeecli", "kvms", "delete", "-n", kvm_name, "-o", org, "-t", token]
    if scope != "org":
        cmd.extend(["-e", scope])
    
    if run_command(cmd):
        log(f"[SUCCESS] Deleted: {kvm_name} (Scope: {scope})", "SUCCESS", 1)
        return True
    else:
        log(f"[FAILURE] Failed to delete: {kvm_name} (Scope: {scope})", "ERROR", 1)
        return False

def main():
    parser = argparse.ArgumentParser(description="Surgical KVM Deletion via Registry")
    parser.add_argument("--org", required=True, help="Target Apigee Org")
    parser.add_argument("--scope", required=True, help="'all', 'org', 'all_envs', or specific env name")
    parser.add_argument("--kvm", required=True, help="'all' or specific kvm name")
    args = parser.parse_args()

    if not os.path.exists(REGISTRY_FILE):
        log("Registry file not found. Nothing to delete.", "WARN")
        return

    with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
        registry = json.load(f)

    if args.org not in registry:
        log(f"Org '{args.org}' not found in registry.", "WARN")
        return

    auth_token = authenticate_user()
    
    print(f"\n{'='*60}\n🔹 INITIATING SURGICAL DELETION\n{'='*60}")
    log(f"Target Org: {args.org} | Scope: {args.scope} | KVM: {args.kvm}", "INFO")

    org_data = registry[args.org]
    scopes_to_process = []

    if args.scope == "all":
        scopes_to_process = list(org_data.keys())
    elif args.scope == "org":
        if "org" in org_data: scopes_to_process = ["org"]
    elif args.scope == "all_envs":
        scopes_to_process = [s for s in org_data.keys() if s != "org"]
    else:
        if args.scope in org_data: scopes_to_process = [args.scope]

    # Perform Deletions
    for scope in scopes_to_process:
        kvms_in_scope = list(org_data[scope].keys())
        kvms_to_delete = kvms_in_scope if args.kvm == "all" else [args.kvm] if args.kvm in kvms_in_scope else []

        if not kvms_to_delete and args.kvm != "all":
            log(f"KVM '{args.kvm}' not found in scope '{scope}' in registry.", "WARN", 1)
            STATS["not_found_in_registry"] += 1
            continue

        for kvm_name in kvms_to_delete:
            if delete_kvm(auth_token, args.org, scope, kvm_name):
                STATS["deleted"] += 1
                del registry[args.org][scope][kvm_name]
            else:
                STATS["failed"] += 1

        if not registry[args.org][scope]:
            del registry[args.org][scope]

    if not registry[args.org]:
        del registry[args.org]

    # Save cleaned registry back to file
    with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2)

    print(f"\n{'='*60}\n📊 DELETION SUMMARY\n{'='*60}")
    print(f"  Successfully Deleted : {STATS['deleted']}")
    print(f"  Failed Deletions     : {STATS['failed']}")
    print(f"  Not Found in Registry: {STATS['not_found_in_registry']}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    # Setup Logging Directory
    # Note: We use scripts/run_logs to match your other scripts
    script_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(script_base_dir, "run_logs", "delete_kvms_run")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"delete_kvms_run_{timestamp}.log")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_filename, 'w', encoding='utf-8')
    
    try:
        sys.stdout = Tee(original_stdout, log_file)
        sys.stderr = Tee(original_stderr, log_file)
        
        print(f"--- SCRIPT '3-delete_kvm.py' STARTED ---")
        main()
        print(f"\n--- SCRIPT FINISHED ---")

    except Exception as e:
        print(f"\n--- SCRIPT FAILED ---")
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()
