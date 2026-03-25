import os
import subprocess
import sys
import json
import datetime
from typing import List, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config 

APIGEE_HYB_ORG = config.APIGEE_HYB_ORG
SA_ENABLE = getattr(config, 'SA_ENABLE', "false")
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)
REGISTRY_FILE = os.path.join(config.REGISTRY_LOG_DIR, config.DEVELOPER_REGISTRY_FILE)

STATS = {"deleted": 0, "failures": 0}

class Tee(object):
    def __init__(self, *files): self.files = files
    def write(self, obj):
        for f in self.files: f.write(obj); f.flush()
    def flush(self):
        for f in self.files: f.flush()

def log(message: str, level: str = "INFO", indent: int = 0):
    prefix = {"INFO": "  ▶", "SUCCESS": "  ✅", "ERROR": "  ❌", "HEADER": "\n🔹"}.get(level, "  ▶")
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
    if not os.path.exists(REGISTRY_FILE):
        log("No registry found. Nothing to delete.", "INFO"); return
    with open(REGISTRY_FILE, 'r') as f: registry = json.load(f)
    token = authenticate_user()
    remaining = []
    log(f"Starting deletion of {len(registry)} developers", "HEADER")
    for dev in registry:
        email = dev["email"]
        cmd = ["apigeecli", "developers", "delete", "-n", email, "-o", APIGEE_HYB_ORG, "-t", token]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 or "404" in result.stderr:
            log(f"[SUCCESS] Deleted: {email}", "SUCCESS", 1)
            STATS["deleted"] += 1
        else:
            log(f"[FAILURE] Failed: {email}", "ERROR", 1)
            remaining.append(dev)
            STATS["failures"] += 1
    with open(REGISTRY_FILE, 'w') as f: json.dump(remaining, f, indent=2)

if __name__ == "__main__":
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "run_logs", "delete_developers_run")
    os.makedirs(log_dir, exist_ok=True)
    log_file = open(os.path.join(log_dir, f"delete_devs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"), 'w')
    sys.stdout = Tee(sys.stdout, log_file); sys.stderr = Tee(sys.stderr, log_file)
    try: main()
    finally: log_file.close()
