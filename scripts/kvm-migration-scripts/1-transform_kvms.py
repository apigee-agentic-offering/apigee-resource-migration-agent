import os
import shutil
import glob
import tarfile
import zipfile
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import datetime
import json
import config  # Ensure config.py is in the same directory

# --- LOGGING HELPER ---
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

# --- CLEANUP LOGIC ---
def sanitize_and_save_kvm(src_file, dest_file):
    """
    Parses the KVM JSON, keeps the monolithic string format intact, 
    but converts inner double quotes to single quotes to safely bypass
    Apigee CLI payload wrapping errors. Also fixes the `#` in the KVM name.
    """
    try:
        with open(src_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if isinstance(data, dict) and 'entry' in data:
            sanitized_entries = []
            
            for entry in data['entry']:
                name = entry.get('name')
                val = entry.get('value')
                
                if not name:
                    continue
                    
                # 1. Ensure the value is a string
                if isinstance(val, (dict, list)):
                    val_str = json.dumps(val, separators=(',', ':'))
                elif val is None:
                    val_str = ""
                else:
                    val_str = str(val)
                    
                # 2. Swap double quotes for single quotes (The CLI Workaround)
                val_str = val_str.replace('"', "'")
                
                # 3. Remove raw newlines and carriage returns
                val_str = val_str.replace('\n', '').replace('\r', '')
                
                sanitized_entries.append({'name': name, 'value': val_str})
            
            data['entry'] = sanitized_entries
            
        # Fix the root KVM name inside the JSON so it matches the new safe filename
        if isinstance(data, dict) and 'name' in data:
            data['name'] = data['name'].replace("#", "-")
            
        # Write the cleaned, single-quote JSON back out
        with open(dest_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
        return True
            
    except Exception as e:
        print(f"    - ❌ ERROR processing {os.path.basename(src_file)}: {e}")
        # If JSON parsing fails, just copy the raw file as a fallback
        shutil.copy2(src_file, dest_file)
        return False

# --- PROCESSING FUNCTIONS ---
def process_org_kvms(org_kvm_path, output_base):
    print(f"    - Found Org KVMs at: {org_kvm_path}")
    output_org_kvm_path = os.path.join(output_base, "org", "kvms")
    os.makedirs(output_org_kvm_path, exist_ok=True)

    for filename in os.listdir(org_kvm_path):
        if filename.endswith(".json"):
            src_file = os.path.join(org_kvm_path, filename)
            
            # Change '#' to '-' in the filename to prevent API Gateway 404 errors
            safe_filename = filename.replace("#", "-")
            dest_file = os.path.join(output_org_kvm_path, safe_filename)
            
            success = sanitize_and_save_kvm(src_file, dest_file)
            if success:
                print(f"    - [SUCCESS] Cleaned & Copied Org KVM: {safe_filename}")

def process_env_kvms(env_config_path, output_base):
    print(f"    - Found Env configs at: {env_config_path}")
    
    for env_name in os.listdir(env_config_path):
        env_path = os.path.join(env_config_path, env_name)
        if os.path.isdir(env_path):
            kvm_path = os.path.join(env_path, "kvms")
            if os.path.exists(kvm_path):
                output_kvm_path = os.path.join(output_base, "env", env_name, "kvms")
                os.makedirs(output_kvm_path, exist_ok=True)
                
                for filename in os.listdir(kvm_path):
                    if filename.endswith(".json"):
                        src_file = os.path.join(kvm_path, filename)
                        
                        safe_filename = filename.replace("#", "-")
                        dest_file = os.path.join(output_kvm_path, safe_filename)
                        
                        success = sanitize_and_save_kvm(src_file, dest_file)
                        if success:
                            print(f"    - [SUCCESS] Cleaned & Copied Env KVM: [{env_name}] {safe_filename}")

def process_extracted_contents(extract_path, output_base):
    for root, dirs, files in os.walk(extract_path):
        if 'orgConfig' in dirs:
            org_kvm_path = os.path.join(root, 'orgConfig', 'kvms')
            if os.path.exists(org_kvm_path):
                process_org_kvms(org_kvm_path, output_base)
                
        if 'envConfig' in dirs:
            env_config_path = os.path.join(root, 'envConfig')
            process_env_kvms(env_config_path, output_base)

def main():
    extraction_dir = getattr(config, 'EXTRACTION_DIR', 'extraction_temp')
    output_dir = getattr(config, 'OUTPUT_DIR', 'transformed_resources')
    source_dir = getattr(config, 'SOURCE_DIR', '.')

    if os.path.exists(extraction_dir):
        shutil.rmtree(extraction_dir)
        
    for path in [os.path.join(output_dir, "org"), os.path.join(output_dir, "env")]:
        if os.path.exists(path):
            shutil.rmtree(path)

    os.makedirs(extraction_dir, exist_ok=True)
    
    # Search for both zip and tar.gz files
    source_files = glob.glob(os.path.join(source_dir, "*.tgz")) + \
                   glob.glob(os.path.join(source_dir, "*.tar.gz")) + \
                   glob.glob(os.path.join(source_dir, "*.zip"))
    
    if not source_files:
        print(f"⚠️ WARNING: No archives found in '{source_dir}'")
        return

    try:
        for archive_file in source_files:
            print(f"\n--- Processing archive: {archive_file} ---")
            
            archive_name = os.path.splitext(os.path.basename(archive_file))[0]
            extract_path = os.path.join(extraction_dir, archive_name)
            os.makedirs(extract_path, exist_ok=True)
            
            if archive_file.endswith('.zip'):
                with zipfile.ZipFile(archive_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
            else:
                with tarfile.open(archive_file, "r:gz") as tar:
                    tar.extractall(path=extract_path) 
            
            process_extracted_contents(extract_path, output_dir)
            
            print(f"--- Finished processing {archive_file}. ---")

    finally:
        if os.path.exists(extraction_dir):
            shutil.rmtree(extraction_dir)

if __name__ == "__main__":
    log_dir = "run_logs/transform_kvms_run"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"transform_kvms_run_{timestamp}.log")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_filename, 'w', encoding='utf-8')
    
    try:
        sys.stdout = Tee(original_stdout, log_file)
        sys.stderr = Tee(original_stderr, log_file)
        
        print(f"--- SCRIPT '1-transform_kvms.py' STARTED ---")
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
