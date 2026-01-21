# Log Processing Pipeline - QA Automation

## Overview

This repository contains the Black-Box QA automation suite for the Node.js Log Processing Pipeline.
The pipeline consists of:

- **Agent:** Reads logs from a file source.
- **Splitter:** Distributes logs.
- **Targets (x2):** Receives streams and writes to disk.

## Test Architecture

We utilize a **Separate Test Runner** (Sidecar) approach for cross-platform compatibility:

1.  A `tester` container is deployed alongside the application stack.
2.  It shares volumes with the application to inspect output files (`events.log`).
3.  It mounts the Docker socket to restart the `Agent` and force config reloads.

## How to Run Tests (Locally)

1.  **Start the Environment:**

    ```bash
    docker compose up -d --build
    ```

2.  **Execute Smoke Tests:**

    ```bash
    docker compose exec tester pytest tests/test_smoke.py
    ```

3.  **Execute Integration Tests:**

    ```bash
    docker compose exec tester pytest tests/test_integration.py
    ```

4.  **View Results & Artifacts:**
    - Console output indicates Pass/Fail status.
    - Debug logs and file captures are saved to the `artifacts/` directory on your host.

5.  **Teardown:**
    Use `-v` to remove volumes and ensure a clean state for the next run.
    ```bash
    docker compose down -v
    ```

## Known Defects

The following critical issues are detected by this suite (tests will fail to highlight regressions):

- **Splitter Failure:** The Splitter broadcasts identical data to both targets instead of load balancing.
- **Filtering Ignored:** The Splitter ignores `filter.json` configuration and passes all log levels.
- **TCP Fragmentation:** Large datasets are not buffered, causing lines to be merged or truncated.

## CI/CD

GitHub Actions is configured in `.github/workflows/main.yml`. It automatically:

1.  Builds the stack.
2.  Runs the Smoke Tests (Fails build on failure).
3.  Runs the Integration Tests (Fails build if bugs are found).
4.  Uploads all logs to **GitHub Artifacts**.
