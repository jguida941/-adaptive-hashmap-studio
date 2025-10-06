# Gemini Code Audit: AdaptiveHashMapCli

This document outlines the findings of a code audit performed by Gemini on the AdaptiveHashMapCli project. The audit focused on identifying potential logic bugs, UI issues, and security flaws.

## Security Vulnerabilities

### High Severity

#### SEC-H-001: Potential for Arbitrary Code Execution via Pickle Deserialization

**Location:** `src/adhash/io/safe_pickle.py`, `src/adhash/core/maps.py`

**Description:**
The project uses a custom "safe" pickle unpickler (`_RestrictedUnpickler`) to prevent arbitrary code execution during deserialization of snapshot files. While this is a good security practice, the allowlist of classes includes several custom classes from the project itself, namely from `adhash.core.maps` and `adhash.config`.

A vulnerability in the `__setstate__` or `__init__` methods of these allowed classes could still be exploited by a maliciously crafted snapshot file. For example, the `HybridAdaptiveHashMap.__setstate__` method in `src/adhash/core/maps.py` takes a dictionary and reconstructs the object. If the dictionary is crafted maliciously, it could lead to unexpected behavior or potentially be used to construct a chain of objects that leads to code execution.

**Recommendation:**
- Avoid using pickle for serialization if possible. Consider using a safer format like JSON or a structured format with a schema (e.g., Protocol Buffers).
- If pickle must be used, the `__setstate__` and `__init__` methods of all allowed classes should be carefully reviewed to ensure they don't have any exploitable vulnerabilities. The `HybridAdaptiveHashMap.__setstate__` method is a good place to start.

### Medium Severity

#### SEC-M-001: Denial of Service via Malicious Environment Variables

**Location:** `src/adhash/config.py`

**Description:**
The `AppConfig.apply_env_overrides` method allows overriding configuration values using environment variables. The method uses `int()` and `float()` to cast the string values from the environment variables. If a malicious user provides an environment variable with a value that cannot be cast to the expected type (e.g., `ADAPTIVE_INITIAL_BUCKETS="not-a-number"`), it will raise a `ValueError` and crash the application.

**Recommendation:**
- The `apply_env_overrides` method should include error handling to catch `ValueError` and log a warning message instead of crashing the application.

### Low Severity

#### SEC-L-001: Server-Side Request Forgery (SSRF) in TUI

**Location:** `src/adhash/tui/app.py`

**Description:**
The `fetch_metrics` and `fetch_history` functions in the TUI application use `urllib.request.urlopen` to fetch data from a user-provided URL. Although the code has a `nosec` comment to suppress a Bandit warning, there is no validation to ensure that the URL is a local address. A malicious user could potentially provide a URL to an internal service on the local network, leading to a Server-Side Request Forgery (SSRF) vulnerability.

**Recommendation:**
- Implement a whitelist of allowed domains or IP addresses for the metrics endpoint.
- If the endpoint is always on the local machine, ensure that the URL is a localhost address.

#### SEC-L-002: Lack of Authentication in Mission Control

**Location:** `src/adhash/mission_control/app.py`

**Description:**
The Mission Control GUI application does not have any authentication. Anyone with local access to the machine can launch the application and execute commands, including running benchmark suites and modifying configuration files. While this requires local access, it could still be a security risk in a multi-user environment.

**Recommendation:**
- Consider adding an authentication mechanism to the Mission Control application, such as a password prompt or integration with the operating system's user accounts.

## Logic Bugs

### LGC-M-001: Unordered Deletion in TwoLevelChainingMap

**Location:** `src/adhash/core/maps.py`

**Description:**
The `TwoLevelChainingMap.delete` method swaps the element to be deleted with the last element in the group and then pops the last element. This is an efficient way to delete from a list, but it changes the order of elements in the group. While this may not affect the correctness of the hash map, it's an unexpected side effect that could cause subtle bugs if other parts of the code rely on the insertion order.

**Recommendation:**
- The documentation for `TwoLevelChainingMap.delete` should mention that the order of elements is not preserved.
- If order preservation is important, the deletion logic should be changed to remove the element directly, which would be less efficient but would preserve the order.

### LGC-L-001: Potential for MemoryError during RobinHoodMap Resize

**Location:** `src/adhash/core/maps.py`

**Description:**
The `RobinHoodMap.put` method resizes the map by doubling its capacity when the load factor exceeds 0.85. If the map grows very large, doubling the capacity could lead to a `MemoryError` if the system runs out of memory.

**Recommendation:**
- Consider adding a check to see if the new capacity would exceed a reasonable limit before attempting to resize.
- The resizing strategy could be made more sophisticated, for example, by increasing the capacity by a smaller factor for very large maps.

### LGC-L-002: Inconsistent State during HybridAdaptiveHashMap Migration

**Location:** `src/adhash/core/maps.py`

**Description:**
The `HybridAdaptiveHashMap` has complex logic for migrating between the `TwoLevelChainingMap` and `RobinHoodMap` backends. The migration is done incrementally in the `_drain_migration` method. If an error occurs during the migration process (e.g., a `MemoryError` when creating the new map), the `HybridAdaptiveHashMap` could be left in an inconsistent state, with some data in the old map and some in the new map.

**Recommendation:**
- The migration process should be made more robust to errors. For example, the new map could be fully populated before the `_backend` is switched.
- Add more logging to the migration process to help debug issues.

### LGC-L-003: Potential for ZeroDivisionError in TUI

**Location:** `src/adhash/tui/app.py`

**Description:**
The `_format_history` function in the TUI calculates throughput by dividing the number of operations by the time elapsed. The code checks for `t1 <= t0` to prevent division by zero, but if `t1 == t0` and `d_ops > 0`, this could still result in a `ZeroDivisionError` if the check was `t1 < t0`.

**Recommendation:**
- The check should be `t1 > t0` to avoid any potential for a `ZeroDivisionError`.

### LGC-L-004: Potential Race Condition in Mission Control Controller

**Location:** `src/adhash/mission_control/controller.py`

**Description:**
In the `MissionControlController`, the `_handle_snapshot` method is called from the `HttpPoller` thread. It uses `self._ui.submit` to schedule a UI update on the main thread. However, the `_poller` object itself is stopped and set to `None` on the main thread in the `_on_connect_clicked` and `_handle_error` methods. There is a potential race condition where the poller is stopped and deallocated in the main thread, but the poller thread is still running and tries to access the poller object.

**Recommendation:**
- Use a lock to protect access to the `_poller` object to prevent it from being deallocated while it's still in use by the poller thread.

## UI Issues

### UI-M-001: Hardcoded Styles in Mission Control

**Location:** `src/adhash/mission_control/app.py`

**Description:**
The `_apply_futuristic_theme` method in the Mission Control application has a large, hardcoded QSS stylesheet string. This makes it difficult to customize the theme and can lead to an inconsistent look and feel if not all widgets are styled correctly. It also makes the code harder to read and maintain.

**Recommendation:**
- Externalize the QSS stylesheet into a separate `.qss` file. This will make it easier to edit and maintain the styles.
- Consider using a more structured approach to theming, such as using a CSS preprocessor like Sass or Less, if the theme becomes more complex.

### UI-L-001: Lack of Robust Error Handling in TUI

**Location:** `src/adhash/tui/app.py`

**Description:**
The TUI's `_poll_and_render` method has some error handling, but it could be improved. For example, if the JSON payload from the metrics endpoint is malformed, the `_format_summary` function might raise an exception, which would crash the TUI. A `KeyError` or `TypeError` could occur if the payload is not what is expected.

**Recommendation:**
- Add more robust error handling to the `_format_summary`, `_format_history`, and `_format_alerts` functions to handle unexpected or malformed JSON payloads gracefully.

### UI-L-002: No Loading Indicator for Refresh in TUI

**Location:** `src/adhash/tui/app.py`

**Description:**
When the user presses 'r' to refresh the data in the TUI, there is no visual feedback to indicate that a refresh is in progress. This can make the UI feel unresponsive, especially if the metrics endpoint is slow to respond.

**Recommendation:**
- Add a loading indicator (e.g., a spinner or a "Loading..." message) that is displayed while the data is being fetched.

### UI-L-003: Lack of Feedback for Long-Running Operations in Mission Control

**Location:** `src/adhash/mission_control/controller.py`

**Description:**
When a user starts a benchmark suite in the Mission Control application, a new process is started to run the suite. This can be a long-running operation, but there is no progress bar or other visual feedback to the user to indicate that the operation is in progress. The UI only shows the log output from the process.

**Recommendation:**
- Add a progress bar or other visual indicator to show the progress of the benchmark suite.
- Consider disabling the "Run" button while a suite is running to prevent the user from starting multiple suites at the same time.
