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
        archive_name = f"{timestamp}_test_events.log"
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


# @pytest.mark.xfail(reason="Defect: Splitter broadcasts identical data", strict=False)
def test_data_uniqueness_hashing():
    """
    Verify the Splitter actually splits data (Target 1 != Target 2)
    - Purpose: Ensure the Splitter is not sending same data to target_1 and target_2
    - Goal: The SHA256 hash of output target_1 != target_2
    """
    # Cleaning data
    archive_and_clean_state()

    content_t1 = get_container_file_content("target_1", "events.log").encode('utf-8')
    content_t2 = get_container_file_content("target_2", "events.log").encode('utf-8')

    hash_t1 = hashlib.sha256(content_t1).hexdigest()
    hash_t2 = hashlib.sha256(content_t2).hexdigest()

    print(f"Hash Comparison:\ntarget_1: {hash_t1}\ntarget_2: {hash_t2}")

    # If hashes are equal, it means the splitter sent identical data to both (Broadcasting),
    # which contradicts the 'Splitter' requirement.
    assert hash_t1 != hash_t2, "Splitter error: Targets received identical data (Broadcasting detected)"


# @pytest.mark.xfail(reason="Defect: Splitter ignores filter.json config", strict=False)
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


@pytest.mark.parametrize("test_id, input_data", [
    ("special_chars", ["Log #1 with $ymbols!", "User: admin@example.com", "Path: /var/log/sys.log"]),
    ("unicode", ["Emoji log: 🚀 warning", "Japanese: エラー", "Cyrylica: Błąd"]),
    ("whitespace", ["   leading space", "trailing space   ", "\tTabbed\tEntry"]),
    ("json_format", ['{"id": 1, "msg": "json_log"}', '{"status": "error", "code": 500}'])
])
def test_content_handling_variations(test_id, input_data):
    """
    - Purpose: Verify system handles various content types correctly.
    - Goal: Ensures no encoding issues or special character handling bugs.
    """
    # Cleaning data
    archive_and_clean_state()
    
    # Inject data
    inject_test_data(f"test_{test_id}.log", input_data)
    
    # We combine content from both targets (assuming splitter works as expected)
    c1 = get_container_file_content("target_1", TARGET_LOG_FILE)
    c2 = get_container_file_content("target_2", TARGET_LOG_FILE)
    combined_output = c1 + c2
    
    # Assertions. Compare input to output
    for line in input_data:
        err_msg = f"Scenario '{test_id}' failed. Content missing or corrupted: '{line}'"
        assert line in combined_output, err_msg


# @pytest.mark.xfail(reason="Defect: Splitter is breaking lines", strict=False)
def test_large_data_integrity():
    """
    - Purpose: validate data integrity for large data / under high-volume.
    - Goal: Ensures that log lines are not merged, truncated, or split.
    """
    # Cleaning data
    archive_and_clean_state()

    # Inject data
    count = 50000
    lines = [f"record_{i}" for i in range(count)]
    inject_test_data("large_frag_test.log", lines)
    
    # Processing 50k lines
    time.sleep(5)

    # We combine content from both targets (assuming splitter works as expected)
    c1 = get_container_file_content("target_1", TARGET_LOG_FILE)
    c2 = get_container_file_content("target_2", TARGET_LOG_FILE)
    
    # We check if every line in the output follows the strict format "record_NUMBER"
    combined = c1.strip() + "\n" + c2.strip()
    
    error_count = 0
    failures = []

    # Assertions. Compare input to output
    for line in combined.split('\n'):
        if not line: continue
        
        # Valid line: "record_12345"
        # Must start with "record_"
        if not line.startswith("record_"):
            error_count += 1
            failures.append(line)
            continue

        # Must end with a number (and nothing else)
        split_str = line.split('_')
        if len(split_str) != 2 or not split_str[1].isdigit():
            error_count += 1
            failures.append(line)

    # Report findings
    if error_count > 0:
        print(f"\nReport: {error_count} corrupted lines detected.")
        print(f"Failures: {failures}")

    assert error_count == 0, f"Fragmentation detected! {error_count} lines were corrupted/split."
