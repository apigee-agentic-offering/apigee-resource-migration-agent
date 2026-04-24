# --- SCRIPT CONFIGURATION ---
SOURCE_DIR = "/Users/sharnendradey/Documents/testtgz"

# Create the output in the parent directory (..)
OUTPUT_DIR = "../../transformed_resources"

# --- AUTHENTICATION CONFIGURATION ---
# Directory containing the Service Account key file
SA_KEY_DIR = "../sa-key"

# Filename of the Service Account key
SA_KEY_FILE = "secret-key.json"

# Set to "true" to use Service Account, or "false" to use browser-based (ADC) login
SA_ENABLE = "false"

REGISTRY_LOG_DIR = "../registry-log" 

DEVELOPER_REGISTRY_FILE = "developer_import_registry.json"
KVM_REGISTRY_FILE = "kvm_import_registry.json"
# This can stay the same. It will be created inside the current 
# Phase1_KVM... folder and deleted after, which is clean.
EXTRACTION_DIR = "../extraction_temp"

# This path is *inside* the .tgz file, so it does not change.
EXPORT_BASE_PATH = "target/export"

# Your new Apigee Hybrid Organization name
APIGEE_HYB_ORG = "gemini-ai-apigee-security"

ALLOWED_DEV_ATTRIBUTES = [
    "access_token_lifetime", "active", "allowed_star_domains", "cuid", "default_scope",
    "description", "number_of_devices", "oauth_consent_url", "oauth_image_url",
    "oauth_skip_consent", "pkce_required", "post_logout_redirect_uris", "realm",
    "redirect_uri", "refresh_token_lifetime", "scope", "solution_instance"
]
