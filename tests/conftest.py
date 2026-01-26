import pytest
import docker
import os
import json
import time
from datetime import datetime

# --- Constants ---
ARTIFACTS_DIR = "artifacts"
TARGET_LOG_FILE = "events.log"
AGENT_INPUT_DIR = "agent/inputs"
AGENT_CONFIG_FILE = "agent/inputs.json"

# --- Infrastructure Fixtures ---

@pytest.fixture(scope="session")
def docker_client():
    """Shared Docker client for the entire test session."""
    return docker.from_env()

@pytest.fixture
def read_container_file(docker_client):
    """
    Fixture that returns a function to safely read files from containers.
    Usage: content = read_container_file("target_1", "events.log")
    """
    def _read(container_name, filepath):
        try:
            container = docker_client.containers.get(container_name)
            exit_code, output = container.exec_run(f"cat {filepath}")
            if exit_code != 0:
                return ""
            return output.decode('utf-8')
        except docker.errors.NotFound:
            pytest.fail(f"Container {container_name} not found.")
            return ""
    return _read

@pytest.fixture
def injector(docker_client):
    """
    Fixture that returns a function to inject data.
    Usage: injector("test_file.log", ["line1", "line2"])
    """
    def _inject(filename, lines):
        # 1. Write file to host volume
        filepath = os.path.join(AGENT_INPUT_DIR, filename)
        with open(filepath, "w") as f:
            f.write("\n".join(lines) + "\n")
        
        # 2. Update config
        config = {"monitor": f"inputs/{filename}"}
        with open(AGENT_CONFIG_FILE, "w") as f:
            json.dump(config, f)
            
        # 3. Restart Agent
        docker_client.containers.get("agent").restart()
        time.sleep(3) # Wait for agent to boot and process
    return _inject

@pytest.fixture(autouse=True)
def managed_environment(request, docker_client, read_container_file):
    """
    Auto-running fixture for Setup/Teardown.
    """
    # --- 1. SETUP (Clean Slate) ---
    for t in ["target_1", "target_2"]:
        try:
            c = docker_client.containers.get(t)
            c.exec_run(f"truncate -s 0 {TARGET_LOG_FILE}")
        except Exception:
            pass 

    # --- 2. RUN TEST ---
    yield 

    # --- 3. TEARDOWN (Archive Evidence) ---
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_name = request.node.name.replace(" ", "_")

    for t in ["target_1", "target_2"]:
        try:
            # Re-use our read fixture inside the teardown!
            content = read_container_file(t, TARGET_LOG_FILE)
            if content:
                filename = f"{test_name}_{timestamp}_{t}.log"
                path = os.path.join(ARTIFACTS_DIR, filename)
                with open(path, "w") as f:
                    f.write(content)
        except Exception as e:
            print(f"Warning: Failed to archive {t}: {e}")