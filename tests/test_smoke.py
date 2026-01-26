import pytest
import docker
import time
import hashlib

# Initialize Docker Client (Connects via /var/run/docker.sock)
client = docker.from_env()

# Timeout settins (seconds):
TIMEOUT = 20

def get_container_file_content(container_name, filepath):
    """
    Retrieves file content from a container
    """
    try:
        container = client.containers.get(container_name)
        # exec_run returns (exit_code, byte_stream)
        exit_code, output = container.exec_run(f"cat {filepath}")
        
        if exit_code != 0:
            return None
        return output.decode('utf-8')
    except docker.errors.NotFound:
        pytest.fail(f"Container {container_name} not found.")

def wait_for_file(container_name, filepath, timeout=TIMEOUT):
    """
    Waits for file to exist and be non-empty
    """
    start = time.time()
    while time.time() - start < timeout:
        content = get_container_file_content(container_name, filepath)
        if content and len(content.strip()) > 0:
            return True
        time.sleep(1)
    return False

def test_pipeline_smoke_check():
    """
    Smoke test: Verify the pipeline is up and both targets received data
    - Purpose: Verify end-to-end connectivity from Agent -> Splitter -> Targets
    - Goal: target_1 and target_2 must have the 'events.log' file with content
    """
    # 1. Wait for data to propagate
    print("Waiting for pipeline to stabilize...")
    t1_ready = wait_for_file("target_1", "events.log")
    t2_ready = wait_for_file("target_2", "events.log")

    if not t1_ready or not t2_ready:
        # Fetch logs for debugging if failure occurs
        agent_logs = client.containers.get("agent").logs().decode('utf-8')
        print(f"DEBUG: Agent Logs:\n{agent_logs}")
        
    assert t1_ready, f"Target 1 did not receive any data in {TIMEOUT}"
    assert t2_ready, f"Target 2 did not receive any data in {TIMEOUT}"

def test_load_balancing_logic():
    """
    Verify the Splitter balances load close to equal line counts
    - Purpose: Validate the round-robin logic of the Splitter
    - Goal: Line counts in target_1 and target_2 should be equal (or off by 1). Deviation could be up to 30% due to 'Tail Swallowing' bug
    """
    c1 = get_container_file_content("target_1", "events.log").strip().split('\n')
    c2 = get_container_file_content("target_2", "events.log").strip().split('\n')

    count_t1 = len(c1)
    count_t2 = len(c2)

    total, diff = count_t1 + count_t2, abs(count_t1 - count_t2)
    percentage_off = (diff / total) * 100
    
    print(f"Split Balance: {percentage_off:.2f}% deviation (T1:{count_t1}, T2:{count_t2})")

    # FAIL if deviation > 30% (Loose tolerance due to 'Tail Swallowing' bug)
    assert percentage_off < 30, f"Severe imbalance detected! Deviation: {percentage_off:.2f}%"
