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
        
    assert t1_ready, f"Target 1 did not receive any data in {timeout}"
    assert t2_ready, f"Target 2 did not receive any data in {timeout}"

def test_load_balancing_logic():
    """
    Verify the Splitter balances load close to equal line counts
    - Purpose: Validate the round-robin logic of the Splitter
    - Goal: Line counts in target_1 and target_2 should be equal (or off by 1)
    """
    c1 = get_container_file_content("target_1", "events.log").strip().split('\n')
    c2 = get_container_file_content("target_2", "events.log").strip().split('\n')

    count1 = len(c1)
    count2 = len(c2)
    
    print(f"Load Balance Check: T1={count1}, T2={count2}")
    
    # Small delta is OK
    assert abs(count1 - count2) <= 1, f"Imbalanced splitting! T1:{count1} vs T2:{count2}"

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

    print(f"Hash Comparison:\ntarget_1: {hash_t1}\ntarget_1: {hash_t2}")

    # If hashes are equal, it means the splitter sent identical data to both (Broadcasting),
    # which contradicts the 'Splitter' requirement.
    assert hash_t1 != hash_t2, "Splitter failure: Targets received identical data (Broadcasting detected)"
