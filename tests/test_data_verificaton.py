import subprocess

def test_log_line_count():
    # Verify target_1 receives data from the Agent/Splitter. Checking # of lines
    result = subprocess.run(
        ["docker", "exec", "target_1", "sh", "-c", "wc -l < events.log"],
        capture_output=True, text=True, check=True
    )
    
    line_count = int(result.stdout.strip())
    
    assert line_count > 0, "Target events.log has no data!"
    
    print(f"target_1/events.log contains {line_count} lines.")

def test_targets_output_comparison():
    # Verify target_1 and target_1 has same anount of lines in output
    count1 = subprocess.run(["docker", "exec", "target_1", "sh", "-c", "wc -l < events.log"],
                            capture_output=True, text=True).stdout.strip()
    count2 = subprocess.run(["docker", "exec", "target_2", "sh", "-c", "wc -l < events.log"],
                            capture_output=True, text=True).stdout.strip()
    
    assert count1 == count2, f"Sync Error: Target1({count1}) != Target2({count2})"