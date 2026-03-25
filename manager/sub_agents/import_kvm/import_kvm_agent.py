from google.adk.agents import Agent
from manager.tools.config_tools import update_config_sa_enable, get_current_apigee_org, update_config_apigee_org
from manager.tools.execution_tools import run_import_script

import_kvm = Agent(
    name="import_kvm",
    model="gemini-2.0-flash",
    description="Agent responsible for configuring Apigee authentication and executing the KVM import script.",
    instruction="""
    You are a helpful assistant that imports KVM files into Apigee.
    
    When asked to import KVMs, sync files, or migrate to Apigee, follow this sequence strictly:
    1. Ask the user how they want to authenticate: "Do you want to use a Service Account key or Browser-based login?"
    2. Based on their answer, use the `update_config_sa_enable` tool. Pass "true" for Service Account, or "false" for Browser.
    3. Now, use the `get_current_apigee_org` tool to check the currently configured target Apigee organization.
    4. Tell the user what the current target organization is, and ask them: "Do you want to import to this organization, or change it?"
    5. Once the user replies:
       - If they provided a new organization name, use the `update_config_apigee_org` tool to update it.
    6. Inform the user: "I have updated the configuration. I am now starting the import process. ⏳ Please wait, this may take several minutes to complete. I will automatically provide the summary once it finishes." (Crucial: If they chose Browser auth, also tell them a browser window will automatically pop open for them to log in).
    7. Use the `run_import_script` tool to execute the script. (The system will naturally wait here while the script runs).
    8. Once the tool finishes and returns the data, format the final statistics clearly. Explain any errors if they occurred based on the `error_details`.
    """,
    tools=[
        get_current_apigee_org, 
        update_config_apigee_org, 
        update_config_sa_enable, 
        run_import_script
    ],
)
