# tests/test_data_verificaton.py
import subprocess
import pytest
import time

def run_docker_cmd(container, cmd):
    """Helper to run commands inside sibling containers via the socket."""
    # We execute 'docker exec' from INSIDE the tester container.
    # The command goes through /var/run/docker.sock to the Host Daemon.
    full_cmd = ["docker", "exec", container, "sh", "-c", cmd]
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    return result

def test_log_line_count():
    """
    Verify target_1 receives data from the Agent/Splitter. 
    Checking # of lines directly inside the container.
    """
    time.sleep(5)

    result = run_docker_cmd("target_1", "wc -l < events.log")

    assert result.returncode == 0, f"Command failed: {result.stderr}"
    line_count = int(result.stdout.strip() or 0)
    
    assert line_count > 0, "Target events.log has no data!"
    print(f"target_1/events.log contains {line_count} lines.")

def test_targets_output_comparison():
    """
    Verify target_1 and target_2 have the same amount of lines (Sync Check).
    """
    # Get counts from both containers
    res1 = run_docker_cmd("target_1", "wc -l < events.log")
    res2 = run_docker_cmd("target_2", "wc -l < events.log")

    count1 = int(res1.stdout.strip() or 0)
    count2 = int(res2.stdout.strip() or 0)
    
    print(f"Compare: Target1({count1}) vs Target2({count2})")

    # This asserts strict equality. 
    # NOTE: This will fail if the Splitter uses round-robin and total lines are odd.
    assert count1 == count2, f"Sync Error: Target1({count1}) != Target2({count2})"