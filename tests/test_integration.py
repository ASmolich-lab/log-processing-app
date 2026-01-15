import pytest
import docker
import hashlib
import time
import json
import os
import shutil
from datetime import datetime

# Initialize Docker Client (Connects via /var/run/docker.sock)
client = docker.from_env()

# Constants
TIMEOUT = 20
AGENT_INPUT_DIR = "agent/inputs"
AGENT_CONFIG_FILE = "agent/inputs.json"
ARTIFACTS_DIR = "artifacts"
TARGET_LOG_FILE = "events.log" # Root file based on shared volume config

def get_container_file_content(container_name, filepath):
    """
    Retrieves file content from a container
    """
    try:
        container = client.containers.get(container_name)
        # exec_run returns (exit_code, byte_stream)
        exit_code, output = container.exec_run(f"cat {filepath}")
        
        if exit_code != 0:
            return ""
        return output.decode('utf-8')
    except docker.errors.NotFound:
        pytest.fail(f"Container {container_name} not found.")


def archive_and_clean_state():
    """
    - Archives existing events.log to artifacts/ folder.
    - Truncates events.log to 0 bytes to ensure clean slate for next test.
    """
    # Ensure artifacts directory exists
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    # Archive
    if os.path.exists(TARGET_LOG_FILE):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{timestamp}_events.log"
        destination = os.path.join(ARTIFACTS_DIR, archive_name)
        
        try:
            shutil.copy(TARGET_LOG_FILE, destination)
            print(f"Archived logs to: {destination}")
        except IOError as e:
            print(f"Warning: Failed to archive logs: {e}")

    # Clear both targets
    for t in ["target_1", "target_2"]:
        try:
            c = client.containers.get(t)
            c.exec_run(f"truncate -s 0 {TARGET_LOG_FILE}")
        except IOError as e:
            print(f"Warning: Failed to clean logs: {e}")
            pass


def inject_test_data(filename, lines):
    """
    Creates a new input file on the shared volume and points the Agent to it.
    """
    # Create the file in the shared 'agent/inputs' directory
    filepath = os.path.join(AGENT_INPUT_DIR, filename)
    with open(filepath, "w") as f:
        f.write("\n".join(lines) + "\n")
    
    # Update inputs.json to point to this new file
    config = {"monitor": f"inputs/{filename}"}
    with open(AGENT_CONFIG_FILE, "w") as f:
        json.dump(config, f)
        
    # Restart Agent to pick up the new config
    agent = client.containers.get("agent")
    agent.restart()
    time.sleep(5) # Wait for processing


def test_data_uniqueness_hashing():
    """
    Verify the Splitter actually splits data (Target 1 != Target 2)
    - Purpose: Ensure the Splitter is not sending same data to target_1 and target_2
    - Goal: The SHA256 hash of output target_1 != target_2
    """
    content_t1 = get_container_file_content("target_1", "events.log").encode('utf-8')
    content_t2 = get_container_file_content("target_2", "events.log").encode('utf-8')

    hash_t1 = hashlib.sha256(content_t1).hexdigest()
    hash_t2 = hashlib.sha256(content_t2).hexdigest()

    print(f"Hash Comparison:\ntarget_1: {hash_t1}\ntarget_2: {hash_t2}")

    # If hashes are equal, it means the splitter sent identical data to both (Broadcasting),
    # which contradicts the 'Splitter' requirement.
    assert hash_t1 != hash_t2, "Splitter error: Targets received identical data (Broadcasting detected)"


def test_filter_logic():
    """
    - Purpose: Verify that 'info' and 'debug' logs are filtered out.
    - Goal: Only lines containing 'error' should pass (per filter.json).
    """

    # Cleaning data
    archive_and_clean_state()

    # Inject specific test data
    test_lines = [
        "ERROR: Critical failure detected",
        "INFO: System is healthy",
        "DEBUG: Variable x=10",
        "ERROR: Second failure"
    ]
    inject_test_data("filter_test.log", test_lines)
    
    # We combine content from both targets (assuming splitter works as expected)
    c1 = get_container_file_content("target_1", "events.log").lower()
    c2 = get_container_file_content("target_2", "events.log").lower()
    full_content = c1 + c2
    
    # Assertions
    assert "info" not in full_content, "'info' logs found in output"
    assert "debug" not in full_content, "'debug' logs found in output"
    assert "error" in full_content, "'error' logs found in output"
