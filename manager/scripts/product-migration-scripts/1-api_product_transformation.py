import os
import shutil
import glob
import tarfile
import zipfile
import sys
import datetime
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
def transform_api_product(src_file, dest_file):
    """
    Parses the API Product JSON, assigns 'createdBy' as a developer attribute,
    validates approval types, and strips legacy metadata.
    """
    try:
        with open(src_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # 1. Treat 'createdBy' as the developer
        # Apigee API Products use 'attributes' for custom metadata, so we append it there.
        developer_email = data.get('createdBy')
        if developer_email:
            if 'attributes' not in data:
                data['attributes'] = []
            
            # Prevent duplicating the attribute if the script is run multiple times
            has_dev_attr = any(
                isinstance(attr, dict) and attr.get('name') == 'developer' 
                for attr in data['attributes']
            )
            
            if not has_dev_attr:
                data['attributes'].append({"name": "developer", "value": developer_email})
                
        # 2. Force 'approvalType' to be valid for Apigee
        approval = data.get('approvalType', '')
        if not isinstance(approval, str) or approval.lower() not in ['manual', 'auto']:
            data['approvalType'] = 'manual'
            
        # 3. Remove legacy metadata keys (which Apigee rejects on import/creation)
        keys_to_remove = ['createdAt', 'createdBy', 'lastModifiedAt', 'lastModifiedBy']
        for key in keys_to_remove:
            data.pop(key, None)
            
        # Write the cleaned JSON back out
        with open(dest_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
    except Exception as e:
        print(f"      * ⚠️ Error processing {os.path.basename(src_file)}: {e}")
        # If transformation fails, copy the original file as a fallback
        shutil.copy2(src_file, dest_file)

# --- PROCESSING FUNCTIONS ---
def process_api_products_dir(source_path, output_base):
    print(f"    - Found API Products at: {source_path}")
    output_product_path = os.path.join(output_base, "org", "apiproducts")
    os.makedirs(output_product_path, exist_ok=True)
    
    for filename in os.listdir(source_path):
        if filename.endswith(".json"):
            src_file = os.path.join(source_path, filename)
            dest_file = os.path.join(output_product_path, filename)
            
            transform_api_product(src_file, dest_file)
            print(f"      * Cleaned & Transformed: {filename}")

def process_extracted_contents(extract_path, output_base):
    for root, dirs, files in os.walk(extract_path):
        # Check for 'apiProducts' directory (case-insensitive to handle different export formats)
        for d in dirs:
            if d.lower() == 'apiproducts':
                products_dir = os.path.join(root, d)
                process_api_products_dir(products_dir, output_base)

def main():
    if os.path.exists(EXTRACTION_DIR):
        shutil.rmtree(EXTRACTION_DIR)
        
    # Clean the output directory specifically for API Products
    product_output_path = os.path.join(OUTPUT_DIR, "org", "apiproducts")
    if os.path.exists(product_output_path):
        shutil.rmtree(product_output_path)

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
            
            process_extracted_contents(extract_path, OUTPUT_DIR)
            
            print(f"--- Finished processing {archive_file}. ---")

    finally:
        if os.path.exists(EXTRACTION_DIR):
            shutil.rmtree(EXTRACTION_DIR)

if __name__ == "__main__":
    log_dir = "run_logs/transform_api_products"
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"api_products_run_{timestamp}.log")
    
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_file = open(log_filename, 'w', encoding='utf-8')
    
    try:
        sys.stdout = Tee(original_stdout, log_file)
        sys.stderr = Tee(original_stderr, log_file)
        
        print(f"--- SCRIPT 'api_product_transformation.py' STARTED ---")
        main()
        print(f"\n--- SCRIPT FINISHED ---")
        print(f"Check '{OUTPUT_DIR}/org/apiproducts' for the transformed files.")

    except Exception as e:
        print(f"\n--- SCRIPT FAILED ---")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        log_file.close()