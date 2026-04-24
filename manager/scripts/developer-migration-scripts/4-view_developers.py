import os
import subprocess
import sys
import json
import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

APIGEE_HYB_ORG = config.APIGEE_HYB_ORG
SA_ENABLE = getattr(config, 'SA_ENABLE', "false")
SERVICE_ACCOUNT_KEY_FILE = os.path.join(config.SA_KEY_DIR, config.SA_KEY_FILE)

def run_command(command: list) -> tuple:
    if "apigeecli" in command and "--disable-check" not in command:
        command.append("--disable-check")
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()

def authenticate_user() -> str:
    if str(SA_ENABLE).lower() == "true":
        run_command(["gcloud", "auth", "activate-service-account", "--key-file", SERVICE_ACCOUNT_KEY_FILE, "--quiet"])
    else:
        subprocess.run(["gcloud", "auth", "login"], check=True, capture_output=True)
    
    success, token = run_command(["gcloud", "auth", "print-access-token"])
    return token if success else sys.exit(1)

def main():
    auth_token = authenticate_user()
    
    report_data = {
        "organization": APIGEE_HYB_ORG,
        "timestamp": datetime.datetime.now().isoformat(),
        "live_developers": []
    }

    # Fetch live developers from the Org
    success, output = run_command(["apigeecli", "developers", "list", "-o", APIGEE_HYB_ORG, "-t", auth_token])
    
    if success and output:
        try:
            # apigeecli usually returns a list of emails or a JSON array. We parse it here.
            parsed_output = json.loads(output)
            # Depending on the CLI version, it might be a list of strings or dicts.
            if isinstance(parsed_output, list):
                report_data["live_developers"] = parsed_output
            elif isinstance(parsed_output, dict) and "developer" in parsed_output:
                report_data["live_developers"] = parsed_output["developer"]
        except json.JSONDecodeError:
            report_data["error"] = "Could not parse live developer output."

    # Print pure JSON to stdout for the execution tool to capture cleanly
    print(json.dumps(report_data))

if __name__ == "__main__":
    main()