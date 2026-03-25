from google.adk.agents import Agent
from manager.tools.config_tools import update_config_source_dir
from manager.tools.execution_tools import run_transform_script

transform_kvm = Agent(
    name="transform_kvm",
    model="gemini-2.0-flash",
    description="Agent responsible for configuring the source directory and executing the KVM transformation script.",
    instruction="""
    You are a helpful assistant that transforms Apigee KVM files.
    
    When asked to transform KVMs or process files:
    1. Ask the user for the directory path where the source .tgz files are located.
    2. Once the user provides the path, use the `update_config_source_dir` tool to update the configuration.
    3. Inform the user you are starting the transformation process.
    4. Use the `run_transform_script` tool to execute the script.
    5. The tool will return execution metrics. Format these metrics into a clear summary for the user.
    """,
    tools=[update_config_source_dir, run_transform_script],
)
