import re
import os
import sys
import json
from typing import Optional

# Traverse up from manager/tools/ to manager/ where the scripts live
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
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
    
def check_developer_registry(org_name: str, developer_email: str = None) -> dict:
    """Quickly checks the local registry to see if developers exist for an org, or if a specific developer exists."""
    print(f"--- Tool: check_developer_registry called ({org_name}, {developer_email}) ---")
    try:
        # Ensure we can import config
        if PROJECT_ROOT not in sys.path:
            sys.path.append(PROJECT_ROOT)
        import config
        
        reg_dir = getattr(config, 'REGISTRY_LOG_DIR', 'registry-log')
        reg_file_name = getattr(config, 'DEVELOPER_REGISTRY_FILE', 'developer_registry.json')
        registry_file = os.path.join(PROJECT_ROOT, reg_dir, reg_file_name)
        
        # 1. Check if file exists
        if not os.path.exists(registry_file):
            return {"status": "success", "found": False, "message": "Registry file does not exist. No developers have been imported yet."}
            
        with open(registry_file, 'r', encoding='utf-8') as f:
            try:
                registry = json.load(f)
            except json.JSONDecodeError:
                return {"status": "error", "message": "Registry file is corrupt."}
        
        # Handle backward compatibility if someone is still using the old flat-list format
        if isinstance(registry, list):
            current_org = getattr(config, 'APIGEE_HYB_ORG', 'default_org')
            registry = {current_org: registry}

        # 2. Check if the Org exists in the registry
        if org_name not in registry or not registry[org_name]:
            return {"status": "success", "found": False, "message": f"No developers found in the registry for organization '{org_name}'."}
        
        # 3. If a specific developer was requested, check if they exist
        if developer_email and developer_email.lower() != 'all':
            devs = registry[org_name]
            dev_exists = any(d.get("email") == developer_email for d in devs)
            if dev_exists:
                return {"status": "success", "found": True, "message": f"Developer '{developer_email}' found in registry for '{org_name}'."}
            else:
                return {"status": "success", "found": False, "message": f"Developer '{developer_email}' was NOT found in the registry for '{org_name}'."}
        
        # If we are just checking the org, or they requested 'all'
        return {"status": "success", "found": True, "message": f"Found {len(registry[org_name])} registered developers for organization '{org_name}' ready for deletion."}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
def check_kvm_registry(org_name: str, target_scope: str, target_kvm: str) -> dict:
    """
    Quickly checks the local registry to see if KVMs exist for an org, scope, or specific KVM.
    target_scope: 'all', 'org', 'all_envs', or specific env name.
    target_kvm: 'all' or specific kvm name.
    """
    print(f"--- Tool: check_kvm_registry called ({org_name}, {target_scope}, {target_kvm}) ---")
    try:
        # Ensure we can import config
        if PROJECT_ROOT not in sys.path:
            sys.path.append(PROJECT_ROOT)
        import config
        
        reg_dir = getattr(config, 'REGISTRY_LOG_DIR', 'registry-log')
        reg_file_name = getattr(config, 'KVM_REGISTRY_FILE', 'kvm_import_registry.json')
        registry_file = os.path.join(PROJECT_ROOT, reg_dir, reg_file_name)
        
        # 1. Check if file exists
        if not os.path.exists(registry_file):
            return {"status": "success", "found": False, "message": "Registry file does not exist. No KVMs have been imported yet."}
            
        with open(registry_file, 'r', encoding='utf-8') as f:
            try:
                registry = json.load(f)
            except json.JSONDecodeError:
                return {"status": "error", "message": "Registry file is corrupt."}
        
        # Handle backward compatibility if someone is still using the old format
        if isinstance(registry, list):
            return {"status": "error", "message": "Registry is in an outdated list format. Please run an import first to upgrade the registry structure."}

        # 2. Check if the Org exists in the registry
        if org_name not in registry or not registry[org_name]:
            return {"status": "success", "found": False, "message": f"No KVMs found in the registry for organization '{org_name}'."}
        
        org_data = registry[org_name]
        
        # 3. Handle Scope Logic
        scopes_to_check = []
        if target_scope == "all":
            scopes_to_check = list(org_data.keys())
        elif target_scope == "org":
            if "org" in org_data: scopes_to_check = ["org"]
        elif target_scope == "all_envs":
            scopes_to_check = [s for s in org_data.keys() if s != "org"]
        else:
            if target_scope in org_data: scopes_to_check = [target_scope]
            
        if not scopes_to_check:
             return {"status": "success", "found": False, "message": f"Scope '{target_scope}' not found in the registry for '{org_name}'."}

        # 4. Handle Specific KVM Logic
        if target_kvm != "all":
            kvm_found = False
            for scope in scopes_to_check:
                if target_kvm in org_data[scope]:
                    kvm_found = True
                    break
            
            if kvm_found:
                 return {"status": "success", "found": True, "message": f"KVM '{target_kvm}' found in the requested scope(s) for '{org_name}'."}
            else:
                 return {"status": "success", "found": False, "message": f"KVM '{target_kvm}' was NOT found in the requested scope(s) for '{org_name}'."}
            
        # If we made it here, they asked for 'all' KVMs in a valid scope
        return {"status": "success", "found": True, "message": f"Found valid KVM records in the requested scope(s) for '{org_name}'."}

    except Exception as e:
        return {"status": "error", "message": str(e)}

def check_app_registry(org_name: str) -> dict:
    """
    Quickly checks the local registry to see if Apps exist for an org.
    """
    print(f"--- Tool: check_app_registry called ({org_name}) ---")
    try:
        # Ensure we can import config
        if PROJECT_ROOT not in sys.path:
            sys.path.append(PROJECT_ROOT)
        import config
        
        reg_dir = getattr(config, 'REGISTRY_LOG_DIR', 'registry-log')
        reg_file_name = getattr(config, 'APP_REGISTRY_FILE', 'app_import_registry.json')
        registry_file = os.path.join(PROJECT_ROOT, reg_dir, reg_file_name)
        
        # 1. Check if file exists
        if not os.path.exists(registry_file):
            return {"status": "success", "found": False, "message": "Registry file does not exist. No Apps have been imported yet."}
            
        with open(registry_file, 'r', encoding='utf-8') as f:
            try:
                registry = json.load(f)
            except json.JSONDecodeError:
                return {"status": "error", "message": "Registry file is corrupt."}
        
        # 2. Check if the Org exists in the registry
        if org_name not in registry or not registry[org_name]:
            return {"status": "success", "found": False, "message": f"No Apps found in the registry for organization '{org_name}'."}
            
        return {"status": "success", "found": True, "message": f"Found valid App records in the registry for '{org_name}'."}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_migration_config(source_dir: str = None, sa_enable: str = None, apigee_org: str = None) -> dict:
    """Updates multiple configuration variables in config.py in a single pass to save time."""
    print(f"--- Tool: update_migration_config called ---")
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as file:
            content = file.read()
        
        if source_dir:
            content = re.sub(r'(SOURCE_DIR\s*=\s*)["\'].*?["\']', rf'\g<1>"{source_dir}"', content)
        if sa_enable is not None:
            content = re.sub(r'(SA_ENABLE\s*=\s*)["\'].*?["\']', rf'\g<1>"{str(sa_enable).lower()}"', content)
        if apigee_org:
            content = re.sub(r'(APIGEE_HYB_ORG\s*=\s*)["\'].*?["\']', rf'\g<1>"{apigee_org}"', content)
            
        with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
            file.write(content)
            
        return {"status": "success", "message": "Configuration updated successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
def search_developer_registry(org_name: str, developer_email: Optional[str] = None) -> dict:
    """Surgically searches the local registry for Developer data."""
    print(f"--- Tool: search_developer_registry called for {org_name} ---")
    try:
        if PROJECT_ROOT not in sys.path:
            sys.path.append(PROJECT_ROOT)
        import config
        
        reg_dir = getattr(config, 'REGISTRY_LOG_DIR', 'registry-log')
        reg_file_name = getattr(config, 'DEVELOPER_REGISTRY_FILE', 'developer_registry.json')
        registry_file = os.path.join(PROJECT_ROOT, reg_dir, reg_file_name)
        
        if not os.path.exists(registry_file):
            return {"status": "not_found", "message": "No registry file exists yet."}
            
        with open(registry_file, 'r', encoding='utf-8') as f:
            registry = json.load(f)
            
        # Handle old flat-list format dynamically
        if isinstance(registry, list):
            current_org = getattr(config, 'APIGEE_HYB_ORG', 'default_org')
            registry = {current_org: registry}

        if org_name not in registry or not registry[org_name]:
            return {"status": "org_not_found", "message": f"No records found for organization '{org_name}'."}

        org_data = registry[org_name]
        
        if developer_email and developer_email.lower() != 'all':
            specific_dev = [d for d in org_data if d.get("email") == developer_email]
            if specific_dev:
                return {"status": "success", "type": "specific_developer", "data": specific_dev[0]}
            return {"status": "developer_not_found", "message": f"Developer '{developer_email}' not found in registry for {org_name}."}

        # Limit return size to prevent context overload if there are thousands of devs
        return {
            "status": "success", 
            "type": "org_full", 
            "total_count": len(org_data),
            "data_sample": org_data[:10], # Only return first 10 to LLM
            "message": "Returned a sample of 10 developers to prevent context overload."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
def check_product_registry() -> dict:
    """Checks if the API Product import registry exists and has records for the current org."""
    print(f"--- Tool: check_product_registry called ---")
    try:
        if PROJECT_ROOT not in sys.path:
            sys.path.append(PROJECT_ROOT)
        import config
        
        reg_dir = getattr(config, 'REGISTRY_LOG_DIR', 'registry-log')
        reg_file_name = getattr(config, 'PRODUCT_REGISTRY_FILE', 'api_product_import_registry.json')
        registry_file = os.path.join(PROJECT_ROOT, reg_dir, reg_file_name)
        current_org = getattr(config, 'APIGEE_HYB_ORG', 'default_org')
        
        if not os.path.exists(registry_file):
            return {"status": "success", "found": False, "message": "Registry file does not exist yet."}
            
        with open(registry_file, 'r', encoding='utf-8') as f:
            registry = json.load(f)
            
        # Check for new Dictionary Format
        if isinstance(registry, dict):
            org_products = registry.get(current_org, [])
            if len(org_products) > 0:
                return {"status": "success", "found": True, "count": len(org_products), "message": f"Found {len(org_products)} API Products for '{current_org}' in the registry."}
            else:
                return {"status": "success", "found": False, "message": f"No API Products found for '{current_org}'."}
                
        # Fallback if an old list format is still sitting there
        elif isinstance(registry, list) and len(registry) > 0:
            return {"status": "success", "found": True, "count": len(registry), "message": "Found products in legacy flat registry format."}
            
        return {"status": "success", "found": False, "message": "Registry is empty."}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}