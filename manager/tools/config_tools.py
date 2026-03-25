import re
import os
import sys
import json
from typing import Optional

# Traverse up from manager/tools/ to the project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.py")

def update_config_source_dir(new_source_dir: str) -> dict:
    """Updates the SOURCE_DIR variable in config.py."""
    print(f"--- Tool: update_config_source_dir called with path: {new_source_dir} ---")
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Regex to safely replace the string inside the quotes for SOURCE_DIR
        new_content = re.sub(r'(SOURCE_DIR\s*=\s*)["\'].*?["\']', rf'\g<1>"{new_source_dir}"', content)
        
        with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
            file.write(new_content)
            
        return {"status": "success", "message": f"Successfully updated SOURCE_DIR to {new_source_dir}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def update_config_sa_enable(sa_enable: str) -> dict:
    """Updates the SA_ENABLE variable in config.py. Accepts 'true' or 'false'."""
    print(f"--- Tool: update_config_sa_enable called with value: {sa_enable} ---")
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Regex to safely replace the boolean string inside the quotes
        new_content = re.sub(r'(SA_ENABLE\s*=\s*)["\'].*?["\']', rf'\g<1>"{sa_enable.lower()}"', content)
        
        with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
            file.write(new_content)
            
        return {"status": "success", "message": f"Successfully updated SA_ENABLE to {sa_enable}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
def get_current_apigee_org() -> dict:
    """Reads the config.py file to get the current APIGEE_HYB_ORG value."""
    print("--- Tool: get_current_apigee_org called ---")
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
            content = file.read()
            
        # Extract the value of APIGEE_HYB_ORG
        match = re.search(r'(APIGEE_HYB_ORG\s*=\s*)["\'](.*?)["\']', content)
        if match:
            return {"status": "success", "current_org": match.group(2)}
        else:
            return {"status": "error", "message": "APIGEE_HYB_ORG not found in config.py"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def update_config_apigee_org(new_org: str) -> dict:
    """Updates the APIGEE_HYB_ORG variable in config.py."""
    print(f"--- Tool: update_config_apigee_org called with org: {new_org} ---")
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Safely replace the string inside the quotes
        new_content = re.sub(r'(APIGEE_HYB_ORG\s*=\s*)["\'].*?["\']', rf'\g<1>"{new_org}"', content)
        
        with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
            file.write(new_content)
            
        return {"status": "success", "message": f"Successfully updated APIGEE_HYB_ORG to {new_org}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
def check_org_in_registry(org_name: str) -> dict:
    """Checks if a specific organization exists in the KVM import registry."""
    print(f"--- Tool: check_org_in_registry called for {org_name} ---")
    try:
        # Dynamically append SCRIPT_DIR to path just-in-time to safely import config
        if PROJECT_ROOT not in sys.path:
            sys.path.append(PROJECT_ROOT)
        import config
        
        reg_dir = getattr(config, 'REGISTRY_LOG_DIR', 'registry-log')
        reg_file_name = getattr(config, 'KVM_REGISTRY_FILE', 'kvm_import_registry.json')
        registry_file = os.path.join(PROJECT_ROOT, reg_dir, reg_file_name)
        
        if not os.path.exists(registry_file):
            return {"status": "success", "found": False, "message": "Registry file does not exist yet. No KVMs have been imported."}
            
        with open(registry_file, 'r', encoding='utf-8') as f:
            registry = json.load(f)
            
        if org_name in registry:
            return {"status": "success", "found": True, "message": f"KVMs for {org_name} found in registry."}
        else:
            return {"status": "success", "found": False, "message": f"No imported KVMs found for {org_name}."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    
def search_registry(org_name: str, kvm_name: Optional[str] = None) -> dict:
    """
    Surgically searches the local registry for KVM data.[cite: 18]
    If kvm_name is None, returns all KVMs for that org.
    If kvm_name is provided, returns only that KVM's data.
    """
    print(f"--- Tool: search_registry called for {org_name} (KVM: {kvm_name}) ---")
    try:
        if PROJECT_ROOT not in sys.path:
            sys.path.append(PROJECT_ROOT)
        import config
        
        reg_dir = getattr(config, 'REGISTRY_LOG_DIR', 'registry-log')
        reg_file_name = getattr(config, 'KVM_REGISTRY_FILE', 'kvm_import_registry.json')
        registry_file = os.path.join(PROJECT_ROOT, reg_dir, reg_file_name)
        
        if not os.path.exists(registry_file):
            return {"status": "not_found", "message": "No registry file exists yet."}
            
        with open(registry_file, 'r', encoding='utf-8') as f:
            registry = json.load(f)
            
        if org_name not in registry:
            return {"status": "org_not_found", "message": f"No records found for organization '{org_name}'."}

        org_data = registry[org_name]
        
        # Scenario 1: User wants a specific KVM[cite: 18]
        if kvm_name:
            for scope, kvms in org_data.items():
                if kvm_name in kvms:
                    return {
                        "status": "success", 
                        "type": "specific_kvm",
                        "scope": scope,
                        "kvm_name": kvm_name,
                        "data": kvms[kvm_name]
                    }
            return {"status": "kvm_not_found", "message": f"KVM '{kvm_name}' not found in registry for {org_name}."}

        # Scenario 2: User wants everything for the Org[cite: 18]
        return {"status": "success", "type": "org_full", "data": org_data}

    except Exception as e:
        return {"status": "error", "message": str(e)}
