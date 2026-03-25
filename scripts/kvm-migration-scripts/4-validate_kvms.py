import os
import subprocess
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import datetime
import config  # Imports your centralized config
from typing import List, Tuple, Optional, Dict

# ==========================================
# --- CONFIGURATION ---
# ==========================================
APIGEE_HYB_ORG = config.APIGEE_HYB_ORG
SA_ENABLE = getattr(config, 'SA_ENABLE', "false")
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)
# ==========================================

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
    prefix = {"INFO": "  ▶", "SUCCESS": "  ✅", "WARN": "  ⚠️", "ERROR": "  ❌", "HEADER": "\n🔹", "SUBHEADER": "\n   📌"}.get(level, "  ▶")
    spacer = "   " * indent
    if level == "HEADER":
        print(f"{'='*60}\n{spacer}{prefix} {message}\n{'='*60}")
    else:
        print(f"{spacer}{prefix} {message}")

def run_command(command: List[str], error_message: str, suppress_log: bool = False) -> Tuple[bool, str]:
    try:
        if "apigeecli" in command and "--disable-check" not in command:
            command.append("--disable-check")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not suppress_log:
            log(f"{error_message}: {e.stderr.strip()}", "ERROR", indent=1)
        return False, e.stderr.strip()

def authenticate_user() -> str:
    if str(SA_ENABLE).lower() == "true":
        run_command(["gcloud", "auth", "activate-service-account", "--key-file", SERVICE_ACCOUNT_KEY_FILE, "--quiet"], "SA Auth failed")
    else:
        log("Initiating browser login...", "INFO")
        subprocess.run(["gcloud", "auth", "login"], check=True)
    
    success, token = run_command(["gcloud", "auth", "print-access-token"], "Token retrieval failed")
    return token if success else sys.exit(1)

def get_kvm_entries(token: str, kvm_name: str, env: Optional[str] = None) -> Dict[str, str]:
    cmd = ["apigeecli", "kvms", "entries", "list", "-m", kvm_name, "-o", APIGEE_HYB_ORG, "-t", token]
    if env: cmd.extend(["-e", env])
    success, output = run_command(cmd, f"Failed entries for {kvm_name}", suppress_log=True)
    
    entries_dict = {}
    if success and output:
        try:
            data = json.loads(output)
            # Supporting Apigee X (keyValueEntries) and OPDK (entry)
            entries = data.get("keyValueEntries", data.get("entry", [])) if isinstance(data, dict) else data if isinstance(data, list) else []
            for item in entries:
                if isinstance(item, dict) and 'name' in item:
                    entries_dict[item['name']] = str(item.get('value', ''))
        except: entries_dict["ERROR"] = "Parse failure"
    return entries_dict

def main():
    log("Checking Authentication...", "HEADER")
    auth_token = authenticate_user()
    
    report_data = {
        "organization": APIGEE_HYB_ORG,
        "timestamp": datetime.datetime.now().isoformat(),
        "org_kvms": {},
        "env_kvms": {}
    }

    # 1. Org-Level Crawl
    log("Crawling Org-Level KVMs...", "HEADER")
    success, output = run_command(["apigeecli", "kvms", "list", "-o", APIGEE_HYB_ORG, "-t", auth_token], "List Org KVMs failed")
    if success and output:
        for kvm in json.loads(output):
            report_data["org_kvms"][kvm] = get_kvm_entries(auth_token, kvm)

    # 2. Env-Level Crawl
    log("Crawling Environments...", "HEADER")
    success, output = run_command(["apigeecli", "environments", "list", "-o", APIGEE_HYB_ORG, "-t", auth_token], "List Envs failed")
    if success and output:
        for env in json.loads(output):
            report_data["env_kvms"][env] = {}
            s, out = run_command(["apigeecli", "kvms", "list", "-o", APIGEE_HYB_ORG, "-e", env, "-t", auth_token], f"List {env} KVMs failed")
            if s and out:
                for kvm in json.loads(out):
                    report_data["env_kvms"][env][kvm] = get_kvm_entries(auth_token, kvm, env=env)

    # Save the Live Snapshot
    #report_path = os.path.join(config.REGISTRY_LOG_DIR, "migrated_kvms_report.json")
    #with open(report_path, 'w', encoding='utf-8') as f:
        #json.dump(report_data, f, indent=4)
    #log(f"Live report saved: {report_path}", "SUCCESS")
    print(json.dumps(report_data))

if __name__ == "__main__":
    main()
