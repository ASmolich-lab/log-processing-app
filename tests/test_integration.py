import pytest
import hashlib
import time
import json

# @pytest.mark.xfail(reason="Defect: Splitter broadcasts identical data", strict=False)
def test_data_uniqueness_hashing(injector, read_container_file, docker_client):
    """
    Verify the Splitter actually splits data (Target 1 != Target 2)
    """
    # 1. INJECT
    # We manually update config here because 'injector' helper does generic files,
    # but for this specific test we want the pre-existing 1M file.
    config = {"monitor": "inputs/large_1M_events.log"}
    with open("agent/inputs.json", "w") as f:
        json.dump(config, f)
    
    docker_client.containers.get("agent").restart()
    print("Processing large dataset for hash check...")
    time.sleep(3) 

    # 2. VERIFY
    content_t1 = read_container_file("target_1", "events.log").encode('utf-8')
    content_t2 = read_container_file("target_2", "events.log").encode('utf-8')

    assert len(content_t1) > 0, "Target 1 is empty"

    hash_t1 = hashlib.sha256(content_t1).hexdigest()
    hash_t2 = hashlib.sha256(content_t2).hexdigest()

    print(f"Hash Comparison:\ntarget_1: {hash_t1}\ntarget_2: {hash_t2}")

    assert hash_t1 != hash_t2, "Splitter error: Targets received identical data (Broadcasting detected)"


# @pytest.mark.xfail(reason="Defect: Splitter ignores filter.json config", strict=False)
def test_filter_logic(injector, read_container_file):
    """
    Verify that 'info' and 'debug' logs are filtered out.
    """
    # 1. INJECT
    test_lines = [
        "ERROR: Critical failure detected",
        "INFO: System is healthy",
        "DEBUG: Variable x=10",
        "ERROR: Second failure"
    ]
    injector("filter_test.log", test_lines)
    
    # 2. VERIFY
    c1 = read_container_file("target_1", "events.log").lower()
    c2 = read_container_file("target_2", "events.log").lower()
    full_content = c1 + c2

    assert "info" not in full_content, "'info' logs leaked through filter"
    assert "debug" not in full_content, "'debug' logs leaked through filter"
    assert "error" in full_content, "'error' logs missing from output"


@pytest.mark.parametrize("test_id, input_data", [
    ("special_chars", ["Log #1 with $ymbols!", "User: admin@example.com", "Path: /var/log/sys.log"]),
    ("unicode", ["Emoji log: 🚀 warning", "Japanese: エラー", "Cyrylica: Błąd"]),
    ("whitespace", ["   leading space", "trailing space   ", "\tTabbed\tEntry"]),
    ("json_format", ['{"id": 1, "msg": "json_log"}', '{"status": "error", "code": 500}'])
])
def test_content_handling_variations(test_id, input_data, injector, read_container_file):
    """
    Verify system handles various content types correctly.
    """
    # 1. INJECT
    injector(f"test_{test_id}.log", input_data)
    
    # 2. VERIFY
    c1 = read_container_file("target_1", "events.log")
    c2 = read_container_file("target_2", "events.log")
    combined_output = c1 + c2
    
    for line in input_data:
        err_msg = f"Scenario '{test_id}' failed. Content missing or corrupted: '{line}'"
        assert line in combined_output, err_msg


# @pytest.mark.xfail(reason="Defect: Splitter is breaking lines", strict=False)
def test_large_data_integrity(injector, read_container_file):
    """
    Validate data integrity for large data / under high-volume.
    """
    # 1. INJECT
    count = 50000
    lines = [f"record_{i}" for i in range(count)]
    injector("large_frag_test.log", lines)
    
    time.sleep(15)

    # 2. VERIFY
    c1 = read_container_file("target_1", "events.log")
    c2 = read_container_file("target_2", "events.log")
    
    combined = c1.strip() + "\n" + c2.strip()
    
    error_count = 0
    failures = []

    for line in combined.split('\n'):
        if not line: continue
        
        if not line.startswith("record_"):
            error_count += 1
            failures.append(line)
            continue

        split_str = line.split('_')
        if len(split_str) != 2 or not split_str[1].isdigit():
            error_count += 1
            failures.append(line)

    if error_count > 0:
        print(f"\nReport: {error_count} corrupted lines detected.")
        print(f"Sample Failures: {failures[:5]}")

    assert error_count == 0, f"Fragmentation detected! {error_count} lines were corrupted/split."