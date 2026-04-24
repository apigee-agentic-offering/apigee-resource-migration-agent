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

# --- TRANSFORMATION LOGIC ---
def transform_developer_json(src_file, dest_file):
    """
    Parses the Developer JSON, lowercases the email, filters allowed attributes.
    """
    try:
        with open(src_file, 'r', encoding='utf-8') as f:
            dev_data = json.load(f)
        
        transformed_data = {}
        
        if 'email' in dev_data: 
            transformed_data['email'] = dev_data['email'].lower()
        
        for field in ['firstName', 'lastName', 'userName', 'status']:
            if field in dev_data: 
                transformed_data[field] = dev_data[field]

        if 'createdBy' in dev_data: 
            transformed_data['createdBy'] = dev_data['createdBy']
                
        if 'attributes' in dev_data and isinstance(dev_data['attributes'], list):
            # Fetch allowed attributes from config, defaulting to an empty list if not found
            allowed_attrs = getattr(config, 'ALLOWED_DEV_ATTRIBUTES', [])
            filtered_attributes = [attr for attr in dev_data['attributes'] if 'name' in attr and attr['name'] in allowed_attrs]
            if filtered_attributes: 
                transformed_data['attributes'] = filtered_attributes
        
        with open(dest_file, 'w', encoding='utf-8') as f:
            json.dump(transformed_data, f, indent=2)
            
        return True
        
    except Exception as e:
        print(f"    - ❌ ERROR processing {os.path.basename(src_file)}: {e}")
        return False

# --- PROCESSING FUNCTIONS ---
def process_org_developers(dev_path, output_base, processed_set):
    print(f"    - Found Developers at: {dev_path}")
    output_dev_path = os.path.join(output_base, "org", "developers")
    os.makedirs(output_dev_path, exist_ok=True)

    for filename in os.listdir(dev_path):
        if filename.endswith(".json"):
            # Check for duplicates across sub-folders in the same zip
            if filename in processed_set:
                continue
                
            src_file = os.path.join(dev_path, filename)
            dest_file = os.path.join(output_dev_path, filename)
            
            success = transform_developer_json(src_file, dest_file)
            if success:
                print(f"    - [SUCCESS] Transformed Developer: {filename}")
                processed_set.add(filename)
            else:
                print(f"    - [FAILURE] Failed to transform Developer: {filename}")

def process_extracted_contents(extract_path, output_base):
    # Track processed developers to avoid duplicates within a single archive
    processed_in_this_archive = set()
    
    for root, dirs, files in os.walk(extract_path):
        if 'orgConfig' in dirs:
            dev_path = os.path.join(root, 'orgConfig', 'developers')
            if os.path.exists(dev_path):
                # We pass the set to avoid double-processing same filenames in UAT/SIT/DEV
                process_org_developers(dev_path, output_base, processed_in_this_archive)

def main():
    extraction_dir = getattr(config, 'EXTRACTION_DIR', 'extraction_temp')
    output_dir = getattr(config, 'OUTPUT_DIR', 'transformed_resources')
    source_dir = getattr(config, 'SOURCE_DIR', '.')

    if os.path.exists(extraction_dir):
        shutil.rmtree(extraction_dir)
        
    dev_output_path = os.path.join(output_dir, "org", "developers")
    if os.path.exists(dev_output_path):
        shutil.rmtree(dev_output_path)

    os.makedirs(extraction_dir, exist_ok=True)
    
    # Search for zip and tar.gz files
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
    log_dir = "run_logs/transform_developers_run"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"transform_developers_run_{timestamp}.log")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_filename, 'w', encoding='utf-8')
    
    try:
        sys.stdout = Tee(original_stdout, log_file)
        sys.stderr = Tee(original_stderr, log_file)
        
        print(f"--- SCRIPT '1-transform_developers.py' STARTED ---")
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