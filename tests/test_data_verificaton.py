import subprocess

def test_logs_are_not_empty():
    # Verify target_1 receives data from the Agent/Splitter.
    
    result = subprocess.run(
        ["docker", "exec", "target_1", "cat", "events.log"],
        capture_output=True, 
        text=True, 
        check=True
    )
    
    logs = result.stdout.strip()
    
    # 3. Assertion: If the string length is 0, the test fails
    assert len(logs) > 0, "Target events.log is empty!"
    
    print(f"target_1/events.log contains {len(logs)} chars of data.")