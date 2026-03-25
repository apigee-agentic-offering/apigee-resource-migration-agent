from google.adk.agents import Agent
from manager.tools.config_tools import update_config_source_dir
from manager.tools.execution_tools import run_transform_developer_script

transform_developer = Agent(
    name="transform_developer",
    model="gemini-2.5-flash",
    description="Agent responsible for Developer transformation.",
    instruction="""
    You are a helpful assistant for Apigee Developer transformation.
    
    1. Ask for the directory path (unless known).
    2. Call `update_config_source_dir`.
    3. Call `run_transform_developer_script` EXACTLY ONCE.
    4. Provide the summary metrics.
    5. CRITICAL: From the 'transformed_developers' list, list the first 10 names as examples and then provide the total count. 
    6. Tell the user they can find the full list of transformed JSONs in 'transformed_resources/org/developers'.
    """,
    tools=[update_config_source_dir, run_transform_developer_script],
)
