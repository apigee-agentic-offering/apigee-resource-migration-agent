import os
import shutil
import glob
import tarfile
import zipfile
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import datetime
import json
import config

# --- CONFIGURATION ---
SOURCE_DIR = config.SOURCE_DIR  
OUTPUT_DIR = config.OUTPUT_DIR
EXTRACTION_DIR = config.EXTRACTION_DIR

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
def transform_app(src_file, output_dirs):
    """
    Parses the App JSON, uses 'createdBy' as the developer, extracts credentials 
    and products, and routes the output to success or failed directories.
    """
    filename = os.path.basename(src_file)
    try:
        with open(src_file, 'r', encoding='utf-8') as f:
            app_data = json.load(f)
            
        transformed_data = {}
        transformed_data['name'] = app_data.get('name')

        # 1. Developer Assignment (Strictly using 'createdBy')
        created_by = app_data.get('createdBy')
        
        if not created_by:
            print(f"      * ❌ FAILED: Missing 'createdBy' field for {filename}. Moving to apps_failed.")
            shutil.copy2(src_file, os.path.join(output_dirs['failed'], filename))
            return

        transformed_data['developerEmail'] = created_by

        # 2. Extract Attributes
        transformed_data['attributes'] = app_data.get('attributes', [])

        # 3. Extract Credentials & API Products
        credentials = app_data.get('credentials', [])
        if not credentials:
            print(f"      * ❌ FAILED: No 'credentials' array found for {filename}. Moving to apps_failed.")
            shutil.copy2(src_file, os.path.join(output_dirs['failed'], filename))
            return
            
        first_cred = credentials[0]
        transformed_data['consumerKey'] = first_cred.get('consumerKey')
        transformed_data['consumerSecret'] = first_cred.get('consumerSecret')

        original_products = first_cred.get('apiProducts', [])
        valid_products = []
        
        for p in original_products:
            # Handle standard OPDK object format
            if isinstance(p, dict) and 'apiproduct' in p:
                valid_products.append({
                    "apiproduct": p["apiproduct"],
                    "status": p.get("status", "approved")
                })
            # Handle standard string list format
            elif isinstance(p, str):
                valid_products.append({
                    "apiproduct": p,
                    "status": "approved"
                })

        if not valid_products:
            print(f"      * ❌ FAILED: No valid 'apiProducts' found in credentials for {filename}. Moving to apps_failed.")
            shutil.copy2(src_file, os.path.join(output_dirs['failed'], filename))
            return

        transformed_data['apiProducts'] = valid_products

        # 4. Route and Save File
        dest_file = os.path.join(output_dirs['success'], filename)

        with open(dest_file, 'w', encoding='utf-8') as f:
            json.dump(transformed_data, f, indent=2)
            
        print(f"      * ✅ Transformed: {filename}")

    except json.JSONDecodeError as e:
        print(f"      * ❌ FAILED: Invalid JSON in {filename}: {e}. Moving to apps_failed.")
        shutil.copy2(src_file, os.path.join(output_dirs['failed'], filename))
    except Exception as e:
        print(f"      * ❌ CRITICAL ERROR processing {filename}: {e}. Moving to apps_failed.")
        shutil.copy2(src_file, os.path.join(output_dirs['failed'], filename))

# --- PROCESSING FUNCTIONS ---
def process_apps_dir(source_path, output_dirs):
    print(f"    - Found Apps at: {source_path}")
    
    for filename in os.listdir(source_path):
        if filename.endswith(".json"):
            src_file = os.path.join(source_path, filename)
            transform_app(src_file, output_dirs)

def process_extracted_contents(extract_path, output_dirs):
    for root, dirs, files in os.walk(extract_path):
        for d in dirs:
            if d.lower() == 'apps':
                apps_dir = os.path.join(root, d)
                process_apps_dir(apps_dir, output_dirs)

def main():
    if os.path.exists(EXTRACTION_DIR):
        shutil.rmtree(EXTRACTION_DIR)
        
    # Setup routing directories
    output_dirs = {
        'success': os.path.join(OUTPUT_DIR, "org", "apps_transformed"),
        'failed': os.path.join(OUTPUT_DIR, "org", "apps_failed")
    }

    # Clean existing app directories
    for path in output_dirs.values():
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)

    os.makedirs(EXTRACTION_DIR, exist_ok=True)
    
    source_files = glob.glob(os.path.join(SOURCE_DIR, "*.tgz")) + \
                   glob.glob(os.path.join(SOURCE_DIR, "*.tar.gz")) + \
                   glob.glob(os.path.join(SOURCE_DIR, "*.zip"))
    
    if not source_files:
        print(f"Error: No archives found in '{SOURCE_DIR}'")
        return

    try:
        for archive_file in source_files:
            print(f"\n--- Processing archive: {archive_file} ---")
            
            archive_name = os.path.splitext(os.path.basename(archive_file))[0]
            extract_path = os.path.join(EXTRACTION_DIR, archive_name)
            os.makedirs(extract_path, exist_ok=True)
            
            if archive_file.endswith('.zip'):
                with zipfile.ZipFile(archive_file, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
            else:
                with tarfile.open(archive_file, "r:gz") as tar:
                    tar.extractall(path=extract_path) 
            
            process_extracted_contents(extract_path, output_dirs)
            
            print(f"--- Finished processing {archive_file}. ---")

    finally:
        if os.path.exists(EXTRACTION_DIR):
            shutil.rmtree(EXTRACTION_DIR)

if __name__ == "__main__":
    log_dir = "run_logs/transform_apps"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"apps_run_{timestamp}.log")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_filename, 'w', encoding='utf-8')
    
    try:
        sys.stdout = Tee(original_stdout, log_file)
        sys.stderr = Tee(original_stderr, log_file)
        
        print(f"--- SCRIPT 'app_transformation.py' STARTED ---")
        main()
        print(f"\n--- SCRIPT FINISHED ---")
        print(f"Check '{OUTPUT_DIR}/org/' for the transformed App folders.")

    except Exception as e:
        print(f"\n--- SCRIPT FAILED ---")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()