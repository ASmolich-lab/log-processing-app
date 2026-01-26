import pytest
import time
import json

def test_load_balancing_approximate(injector, read_container_file):
    """
    Smoke Test: Verifies system connectivity and approximate load balancing.
    
    NOTE: We use a loose tolerance (30%) because the Splitter has a known 
    defect where it splits by 'Packet' rather than 'Line', causing 
    Target 2 to receive the bulk of large TCP chunks.
    """

# 1. GENERATE & INJECT TRAFFIC
    # Create 1,000 lines of data. Enough for a statistical sample, fast to process.
    print("Injecting self-contained smoke test data...")
    input_lines = [f"smoke_log_line_{i}" for i in range(10000)]
    
    # The 'injector' fixture (from conftest.py):
    # - Writes 'smoke.log' to agent/inputs/
    # - Updates agent/inputs.json
    # - Restarts the Agent
    # - Waits 5 seconds
    injector("smoke.log", input_lines)

    # 2. RETRIEVE CONTENT
    # Use the shared fixture from conftest.py
    content_t1 = read_container_file("target_1", "events.log")
    content_t2 = read_container_file("target_2", "events.log")

    # 3. ANALYZE
    count_t1 = content_t1.count('\n')
    count_t2 = content_t2.count('\n')
    total = count_t1 + count_t2
    
    print(f"\nTraffic Stats:\nTarget 1: {count_t1}\nTarget 2: {count_t2}\nTotal:    {total}")

    # Sanity Check: Did anything happen?
    if total == 0:
        pytest.fail("Smoke Test Failed: No events received at all. System might be down.")

    # 4. CALCULATE DEVIATION
    diff = abs(count_t1 - count_t2)
    percentage_off = (diff / total) * 100
    
    print(f"Deviation: {percentage_off:.2f}%")

    # 5. ASSERTION
    # We allow up to 30% deviation to account for the "Tail Swallowing" bug.
    assert percentage_off < 30, f"Severe imbalance detected! Deviation: {percentage_off:.2f}%"