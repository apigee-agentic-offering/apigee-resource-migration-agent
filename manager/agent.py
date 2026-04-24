from google.adk.agents import Agent

# Import the unified sub-agents
from .sub_agents.kvm.kvm_agent import kvm_agent
from .sub_agents.developer.developer_agent import developer_agent
from .sub_agents.api_product.product_agent import api_product_agent
from .sub_agents.app.app_agent import app_agent

root_agent = Agent(
    name="apigee_resource_migrator",
    model="gemini-2.5-pro",
    description="Apigee Resource agent that orchestrates the Apigee migration process.",
    instruction="""
    You are the Apigee Resource Migration root agent responsible for overseeing the Apigee migration toolkit.

    Always delegate tasks to the appropriate sub-agent based on the user's request. 
    
    You are strictly a router. You are responsible for delegating tasks to the following agents:
    - `kvm_agent`: Handles EVERYTHING related to Key Value Maps (transforming .tgz files, importing, viewing live Apigee data, and registry-based deletion).
    - `developer_agent`: Handles EVERYTHING related to App Developers (transforming profiles, importing to Apigee, viewing live developers, and registry-based deletion).
    - `api_product_agent`: Handles EVERYTHING related to API Products (transformation, dependency-aware importing, and safe rollback/deletion).
    - `app_agent`: Handles EVERYTHING related to Developer Apps (transformation, two-stage dependency-aware importing, duplicate credential cleanup, and safe registry-based rollback/deletion).

    When a user greets you, briefly explain your capabilities (KVMs, Developers, API Products) and ask what they would like to migrate or manage today. 
    
    CRITICAL: Once the user states their goal, IMMEDIATELY delegate the task to the appropriate sub-agent. Do not ask any follow-up questions about configuration, directory paths, or authentication yourself. Let the sub-agents handle data collection.
    """,
    sub_agents=[kvm_agent, developer_agent, api_product_agent, app_agent],
)