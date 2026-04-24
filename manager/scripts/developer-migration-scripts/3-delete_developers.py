import os
import subprocess
import sys
import json
import datetime
import argparse
from typing import List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config 

SA_ENABLE = getattr(config, 'SA_ENABLE', "false")
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)
REGISTRY_FILE = os.path.join(config.REGISTRY_LOG_DIR, config.DEVELOPER_REGISTRY_FILE)

class Tee(object):
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(obj); f.flush()
    def flush(self):
        for f in self.files: f.flush()

def log(message: str, level: str = "INFO", indent: int = 0):
    prefix = {"INFO": "  ▶", "SUCCESS": "  ✅", "WARN": "  ⚠️", "ERROR": "  ❌", "HEADER": "\n🔹"}.get(level, "  ▶")
    if level == "HEADER": print(f"{'='*60}\n{prefix} {message}\n{'='*60}")
    else: print(f"{'   ' * indent}{prefix} {message}")

def authenticate_user() -> str:
    if SA_ENABLE.lower() == "true":
        subprocess.run(["gcloud", "auth", "activate-service-account", "--key-file", SERVICE_ACCOUNT_KEY_FILE, "--quiet"], check=True)
    else:
        subprocess.run(["gcloud", "auth", "login"], check=True)
    result = subprocess.run(["gcloud", "auth", "print-access-token"], stdout=subprocess.PIPE, text=True, check=True)
    return result.stdout.strip()

def main():
    parser = argparse.ArgumentParser(description="Delete developers from Apigee.")
    parser.add_argument("--org", required=True, help="Target Apigee Organization")
    parser.add_argument("--developer", required=True, help="Specific email or 'all'")
    args = parser.parse_args()

    target_org = args.org
    target_dev = args.developer
    stats = {"deleted": 0, "failures": 0, "message": ""}

    if not os.path.exists(REGISTRY_FILE):
        stats["message"] = "No registry found. Nothing to delete."
        print("\n---AGENT_STRUCTURED_OUTPUT---")
        print(json.dumps(stats))
        return

    with open(REGISTRY_FILE, 'r', encoding='utf-8') as f: 
        try:
            registry_data = json.load(f)
        except json.JSONDecodeError:
            stats["message"] = "Registry file is corrupt or empty."
            print("\n---AGENT_STRUCTURED_OUTPUT---")
            print(json.dumps(stats))
            return
            
    if isinstance(registry_data, list):
        registry_data = {target_org: registry_data}

    if target_org not in registry_data or not registry_data[target_org]:
        stats["message"] = f"No developers have been registered for deletion for org '{target_org}'."
        print("\n---AGENT_STRUCTURED_OUTPUT---")
        print(json.dumps(stats))
        return

    token = authenticate_user()
    all_devs = registry_data[target_org]
    
    if target_dev.lower() == 'all':
        devs_to_process = all_devs
        devs_to_keep = []
    else:
        devs_to_process = [d for d in all_devs if d["email"] == target_dev]
        devs_to_keep = [d for d in all_devs if d["email"] != target_dev]
        
    if not devs_to_process:
        stats["message"] = f"Developer '{target_dev}' is not in the registry for this org."
        print("\n---AGENT_STRUCTURED_OUTPUT---")
        print(json.dumps(stats))
        return

    log(f"Starting deletion of {len(devs_to_process)} developers for org '{target_org}'", "HEADER")
    
    remaining_from_processed = []
    for dev in devs_to_process:
        email = dev["email"]
        cmd = ["apigeecli", "developers", "delete", "-n", email, "-o", target_org, "-t", token]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 or "404" in result.stderr:
            log(f"[SUCCESS] Deleted: {email}", "SUCCESS", 1)
            stats["deleted"] += 1
        else:
            log(f"[FAILURE] Failed: {email}", "ERROR", 1)
            remaining_from_processed.append(dev)
            stats["failures"] += 1
            
    registry_data[target_org] = devs_to_keep + remaining_from_processed
    stats["message"] = "Deletion process completed successfully."
    
    with open(REGISTRY_FILE, 'w', encoding='utf-8') as f: 
        json.dump(registry_data, f, indent=2)

    print("\n---AGENT_STRUCTURED_OUTPUT---")
    print(json.dumps(stats))

if __name__ == "__main__":
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run_logs", "delete_developers_run")
    os.makedirs(log_dir, exist_ok=True)
    log_file = open(os.path.join(log_dir, f"delete_devs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), 'w')
    sys.stdout = Tee(sys.stdout, log_file); sys.stderr = Tee(sys.stderr, log_file)
    try: main()
    finally: log_file.close()