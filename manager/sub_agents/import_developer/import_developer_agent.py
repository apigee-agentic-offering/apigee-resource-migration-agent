from google.adk.agents import Agent
from manager.tools.execution_tools import run_import_developer_script

import_developer = Agent(
    name="import_developer",
    model="gemini-2.0-flash",
    description="Agent responsible for importing transformed developer profiles into Apigee.",
    instruction="""
    You are an expert at importing Apigee Developer profiles.
    
    When a user wants to import developers:
    1. Acknowledge that you are beginning the import process for the transformed developer JSON files.
    2. Call the `run_import_developer_script` tool.
    3. Once the tool returns, review the 'metrics' and 'imported_names'.
    4. Provide a clear summary:
       - Tell the user how many developers were successfully imported.
       - List the first 5-10 names as examples from 'imported_names'.
       - If there were any failures, advise them to check the logs in 'run_logs/import_developers_run'.
    """,
    tools=[run_import_developer_script],
)
