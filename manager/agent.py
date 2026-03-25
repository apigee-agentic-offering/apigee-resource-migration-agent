from google.adk.agents import Agent

from .sub_agents.transform_kvm.transform_kvm_agent import transform_kvm
from .sub_agents.import_kvm.import_kvm_agent import import_kvm
from .sub_agents.delete_kvm.delete_kvm_agent import delete_kvm
from .sub_agents.view_kvm.view_kvm_agent import view_kvm
from .sub_agents.transform_developer.transform_developer_agent import transform_developer
from .sub_agents.import_developer.import_developer_agent import import_developer
from .sub_agents.delete_developer.delete_developer_agent import delete_developer

root_agent = Agent(
    name="apigee_resource_migrator",
    model="gemini-2.0-flash",
    description="Apigee Resource agent that orchestrates the Apigee migration process.",
    instruction="""
    You are an Apigee Resource Migration agent responsible for overseeing the Apigee migration toolkit.

    Always delegate tasks to the appropriate sub-agent based on the user's request. 
    
    You are responsible for delegating tasks to the following agents:
    - `transform_kvm`: Use this when the user wants to transform KVM files or process .tgz files.
    - `import_kvm`: Use this when the user wants to import KVMs, sync to Apigee, or upload configurations.
    - `delete_kvm`: Use this when the user wants to safely delete, rollback, or remove previously imported KVMs.
    - `view_kvm`: Use this when the user wants to view, see, or audit KVMs (either uploaded ones or all KVMs in Apigee).
    - `transform_developer`: Use this when the user wants to transform Developer profiles.
    - `import_developer`: Upload transformed developers to Apigee.
    - `delete_developer`: Rollback/delete developers from Apigee using the registry.
    
    When a user greets you, briefly explain your capabilities and ask what they would like to do. 
    Once they decide, IMMEDIATELY delegate the task to the appropriate sub-agent. Do not ask any follow-up questions about configuration, paths, or authentication yourself.
    """,
    sub_agents=[transform_kvm, import_kvm, delete_kvm, view_kvm, transform_developer, import_developer, delete_developer],
)
