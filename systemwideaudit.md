# System-Wide Audit

This document contains the results of a system-wide audit of the AdaptiveHashMapCli project.


## Static Analysis

Running static analysis tools to check for code quality issues.

User requested to ignore the `check` directory. I will exclude it from the linting process.

### Ruff Linting

After excluding the `check` directory, `ruff check . --exclude check` reported 24 errors. The errors are concentrated in the `src/adhash/mission_control` widgets.

<details>
<summary>Full `ruff` output</summary>

```
F821 Undefined name `T`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:271:28
    |
269 |     def _run_background(
270 |         self,
271 |         work: Callable[[], T],
    |                            ^
272 |         on_success: Callable[[T], None],
273 |         on_error: Optional[Callable[[Exception], None]] = None,
    | 

F821 Undefined name `T`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:272:31
    |
270 |         self,
271 |         work: Callable[[], T],
272 |         on_success: Callable[[T], None],
    |                               ^
273 |         on_error: Optional[Callable[[Exception], None]] = None,
274 |     ) -> None:
    | 

F841 [*] Local variable `exc` is assigned to but never used
   --> src/adhash/mission_control/widgets/benchmark_suite.py:278:33
    |
276 |             try:
277 |                 result = work()
278 |             except Exception as exc:
    |                                 ^^^
279 |                 if on_error is None:
280 |                     return self._invoke_main_thread(lambda: None)
    | 
help: Remove assignment to unused variable `exc`

F821 Undefined name `exc`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:281:59
    |
279 |                 if on_error is None:
280 |                     return self._invoke_main_thread(lambda: None)
281 |                 self._invoke_main_thread(lambda: on_error(exc))
    |                                                           ^^^
282 |             else:
283 |                 self._invoke_main_thread(lambda: on_success(result))
    | 

F841 [*] Local variable `exc` is assigned to but never used
   --> src/adhash/mission_control/widgets/benchmark_suite.py:291:33
    |
289 |             try:
290 |                 result = fut.result()
291 |             except Exception as exc:
    |                                 ^^^
292 |                 if on_error is not None:
293 |                     self._invoke_main_thread(lambda: on_error(exc))
    | 
help: Remove assignment to unused variable `exc`

F821 Undefined name `exc`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:293:63
    |
291 |             except Exception as exc:
292 |                 if on_error is not None:
293 |                     self._invoke_main_thread(lambda: on_error(exc))
    |                                                               ^^^
294 |             else:
295 |                 self._invoke_main_thread(lambda: on_success(result))
    | 

F821 Undefined name `BadInputError`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:480:16
    |
478 |         try:
479 |             result = analyze_workload_csv(job.csv, top_keys=8)
480 |         except BadInputError as exc:
    |                ^^^^^^^^^^^^^
481 |             self._show_analysis_message(str(exc), error=True)
482 |             return
    | 

F821 Undefined name `math`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:899:20
    |
897 |             return
898 | 
899 |         side = int(math.ceil(math.sqrt(counts.size)))
    |                    ^^^^ 
900 |         if counts.size < side * side:
901 |             pad = side * side - counts.size
    | 

F821 Undefined name `math`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:899:30
    |
897 |             return
898 | 
899 |         side = int(math.ceil(math.sqrt(counts.size)))
    |                              ^^^^ 
900 |         if counts.size < side * side:
901 |             pad = side * side - counts.size
    | 

F821 Undefined name `QColor`
    --> src/adhash/mission_control/widgets/benchmark_suite.py:1012:17
     |
1010 |         ratio = max(0.0, min(1.0, ratio))
1011 |         hue = int(120 - 120 * ratio)
1012 |         color = QColor.fromHsv(hue, 255, 255)
     |                 ^^^^^^ 
1013 |         return pg.mkBrush(color)
     | 

F401 [*] `typing.Callable` imported but unused
  --> src/adhash/mission_control/widgets/common.py:10:5
   |
 8 |     TYPE_CHECKING,
 9 |     Any,
10 |     Callable,
   |     ^^^^^^^^ 
11 |     Iterable,
12 |     Mapping,
   | 
help: Remove unused import: `typing.Callable`

F401 [*] `typing.List` imported but unused
 --> src/adhash/mission_control/widgets/metrics.py:6:25
  |
5 | import time
6 | from typing import Any, List, Mapping, Optional, Sequence, Tuple
  |                         ^^^^ 
7 | 
8 | from .common import (
  | 
help: Remove unused import

F401 [*] `typing.Sequence` imported but unused
 --> src/adhash/mission_control/widgets/metrics.py:6:50
  |
5 | import time
6 | from typing import Any, List, Mapping, Optional, Sequence, Tuple
  |                                                  ^^^^^^^^ 
7 | 
8 | from .common import (
  | 
help: Remove unused import

F401 [*] `typing.Tuple` imported but unused
 --> src/adhash/mission_control/widgets/metrics.py:6:60
  |
5 | import time
6 | from typing import Any, List, Mapping, Optional, Sequence, Tuple
  |                                                            ^^^^^ 
7 | 
8 | from .common import (
  | 
help: Remove unused import

F401 [*] `.common.QProgressBar` imported but unused
  --> src/adhash/mission_control/widgets/metrics.py:12:5
   |
10 |     QHBoxLayout,
11 |     QPlainTextEdit,
12 |     QProgressBar,
   |     ^^^^^^^^^^^^ 
13 |     QTabWidget,
14 |     Qt,
   | 
help: Remove unused import: `.common.QProgressBar`

F821 Undefined name `MetricsSnapshot`
   --> src/adhash/mission_control/widgets/metrics.py:270:41
    |
268 |         self.summary_label.setText(text)
269 | 
270 |     def update_snapshot(self, snapshot: MetricsSnapshot) -> None:
    |                                         ^^^^^^^^^^^^^^^ 
271 |         self._tick_index += 1
272 |         throughput = self._estimate_throughput(snapshot)
    | 

F821 Undefined name `MetricsSnapshot`
   --> src/adhash/mission_control/widgets/metrics.py:290:45
    |
288 |         self.events_view.setPlainText("\n".join(lines))
289 | 
290 |     def _summarize_snapshot(self, snapshot: MetricsSnapshot, throughput: Optional[float]) -> str:
    |                                             ^^^^^^^^^^^^^^^ 
291 |         tick = snapshot.tick
292 |         backend = tick.get("backend", "unknown")
    | 

F821 Undefined name `MetricsSnapshot`
   --> src/adhash/mission_control/widgets/metrics.py:311:40
    |
309 |         return summary
310 | 
311 |     def _update_charts(self, snapshot: MetricsSnapshot, throughput: Optional[float]) -> None:
    |                                        ^^^^^^^^^^^^^^^ 
312 |         if not self._supports_charts:
313 |             return
    | 

F821 Undefined name `math`
   --> src/adhash/mission_control/widgets/metrics.py:347:16
    |
345 |         ticks = []
346 |         for idx, (upper, _count) in enumerate(series):
347 |             if math.isinf(upper):
    |                ^^^^ 
348 |                 label = "≤inf"
349 |             elif upper >= 1.0:
    | 

F821 Undefined name `MetricsSnapshot`
   --> src/adhash/mission_control/widgets/metrics.py:413:46
    |
411 |             self._heatmap_status.setVisible(not has_data)
412 | 
413 |     def _estimate_throughput(self, snapshot: MetricsSnapshot) -> Optional[float]:
    |                                              ^^^^^^^^^^^^^^^ 
414 |         tick = snapshot.tick
415 |         raw = tick.get("ops_per_second") or tick.get("throughput")
    | 

F401 [*] `typing.Callable` imported but unused
 --> src/adhash/mission_control/widgets/workload_dna.py:7:25
  |
5 | import math
6 | from pathlib import Path
7 | from typing import Any, Callable, List, Optional, Tuple
  |                         ^^^^^^^^ 
8 | 
9 | from adhash.workloads import WorkloadDNAResult, format_workload_dna
  | 
help: Remove unused import: `typing.Callable`

F401 [*] `.common.QTimer` imported but unused
  --> src/adhash/mission_control/widgets/workload_dna.py:23:5
   |
21 |     QToolTip,
22 |     Qt,
23 |     QTimer,
   |     ^^^^^^ 
24 |     QVBoxLayout,
25 |     QWidget,
   | 
help: Remove unused import

F401 [*] `.common.style_plot` imported but unused
  --> src/adhash/mission_control/widgets/workload_dna.py:28:5
   |
26 |     np,
27 |     pg,
28 |     style_plot,
   |     ^^^^^^^^^^ 
29 | )
   | 
help: Remove unused import

F841 Local variable `sentinel` is assigned to but never used
   --> tests/test_mission_control_widgets_qt.py:143:9
    |
141 |         )
142 | 
143 |         sentinel = object()
    |         ^^^^^^^^ 
144 | 
145 |         def slow_discover() -> List[Path]:
    | 
help: Remove assignment to unused variable `sentinel`

Found 24 errors. 
[*] 10 fixable with the `--fix` option (1 hidden fix can be enabled with the `--unsafe-fixes` option).
```

### MyPy Type Checking

`make type` reported 37 errors. These are mostly `union-attr` errors on optional Qt widgets and undefined names, also concentrated in the Mission Control UI code.

<details>
<summary>Full `make type` output</summary>

```
src/adhash/workloads/dna.py:323: error: Dict entry 0 has incompatible type "str": "str"; expected "str": "float"  [dict-item]
src/adhash/mission_control/widgets/workload_dna.py:172: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:172: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/workload_dna.py:173: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:173: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/workload_dna.py:184: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:184: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/workload_dna.py:185: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:185: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/workload_dna.py:226: error: Item "None" of "Any | None" has no attribute "show"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:490: error: Item "None" of "Any | None" has no attribute "getPlotItem"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:189: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:189: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/run_control.py:190: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:190: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/run_control.py:258: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:258: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/run_control.py:259: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:259: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:92: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:92: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:118: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:118: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:149: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:149: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:177: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:177: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:256: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:256: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:270: error: Name "MetricsSnapshot" is not defined  [name-defined]
src/adhash/mission_control/widgets/metrics.py:290: error: Name "MetricsSnapshot" is not defined  [name-defined]
src/adhash/mission_control/widgets/metrics.py:311: error: Name "MetricsSnapshot" is not defined  [name-defined]
src/adhash/mission_control/widgets/metrics.py:347: error: Name "math" is not defined  [name-defined]
src/adhash/mission_control/widgets/metrics.py:413: error: Name "MetricsSnapshot" is not defined  [name-defined]
src/adhash/mission_control/widgets/connection.py:71: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/connection.py:71: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/connection.py:72: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/connection.py:72: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:194: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:194: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:195: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:195: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:271: error: Name "T" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:272: error: Name "T" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:480: error: Name "BadInputError" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:737: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:737: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:738: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:738: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:749: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:749: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:750: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:750: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:791: error: Item "None" of "Any | None" has no attribute "show"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:899: error: Name "math" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:1012: error: Name "QColor" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:1053: error: Item "None" of "Any | None" has no attribute "getPlotItem"  [union-attr]
tests/test_cli_workload_dna.py:57: error: Dict entry 0 has incompatible type "str": "str"; expected "str": "float"  [dict-item]
Found 37 errors in 7 files (checked 65 source files)
```

</details>


## Testing

Running the test suite to check for regressions and correctness.

`make test` failed because `pytest` was collecting tests from the `check` directory, causing `import file mismatch` errors. I will re-run the tests, ignoring the `check` directory.

<details>
<summary>Full `make test` output</summary>

```
==================================== ERRORS ====================================
__________________ ERROR collecting tests/test_ab_compare.py ___________________
import file mismatch:
imported module 'test_ab_compare' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_ab_compare.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_ab_compare.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_batch_runner.py __________________
import file mismatch:
imported module 'test_batch_runner' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_batch_runner.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_batch_runner.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_cli_contracts.py _________________
import file mismatch:
imported module 'test_cli_contracts' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_cli_contracts.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_cli_contracts.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_______________ ERROR collecting tests/test_cli_workload_dna.py ________________
import file mismatch:
imported module 'test_cli_workload_dna' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_cli_workload_dna.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_cli_workload_dna.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
____________________ ERROR collecting tests/test_config.py _____________________
import file mismatch:
imported module 'test_config' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_config.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_config.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_____________ ERROR collecting tests/test_config_toolkit_schema.py _____________
import file mismatch:
imported module 'test_config_toolkit_schema' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_config_toolkit_schema.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_config_toolkit_schema.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_config_wizard.py _________________
import file mismatch:
imported module 'test_config_wizard' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_config_wizard.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_config_wizard.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_______________ ERROR collecting tests/test_dashboard_assets.py ________________
import file mismatch:
imported module 'test_dashboard_assets' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_dashboard_assets.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_dashboard_assets.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_hybrid_capacity.py ________________
import file mismatch:
imported module 'test_hybrid_capacity' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_hybrid_capacity.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_hybrid_capacity.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_latency_buckets.py ________________
import file mismatch:
imported module 'test_latency_buckets' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_latency_buckets.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_latency_buckets.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_metrics_apply.py _________________
import file mismatch:
imported module 'test_metrics_apply' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_metrics_apply.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_metrics_apply.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_______________ ERROR collecting tests/test_metrics_endpoints.py _______________
import file mismatch:
imported module 'test_metrics_endpoints' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_metrics_endpoints.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_metrics_endpoints.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_metrics_schema.py _________________
import file mismatch:
imported module 'test_metrics_schema' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_metrics_schema.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_metrics_schema.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
____________ ERROR collecting tests/test_mission_control_charts.py _____________
import file mismatch:
imported module 'test_mission_control_charts' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_mission_control_charts.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_mission_control_charts.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_____________ ERROR collecting tests/test_mission_control_stub.py ______________
import file mismatch:
imported module 'test_mission_control_stub' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_mission_control_stub.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_mission_control_stub.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
__________ ERROR collecting tests/test_mission_control_widgets_qt.py ___________
import file mismatch:
imported module 'test_mission_control_widgets_qt' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_mission_control_widgets_qt.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_mission_control_widgets_qt.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
__________________ ERROR collecting tests/test_perf_smoke.py ___________________
import file mismatch:
imported module 'test_perf_smoke' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_perf_smoke.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_perf_smoke.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_process_manager.py ________________
import file mismatch:
imported module 'test_process_manager' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_process_manager.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_process_manager.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_snapshot_header.py ________________
import file mismatch:
imported module 'test_snapshot_header' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_snapshot_header.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_snapshot_header.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
___________________ ERROR collecting tests/test_tui_smoke.py ___________________
import file mismatch:
imported module 'test_tui_smoke' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_tui_smoke.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_tui_smoke.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_workload_dna.py __________________
import file mismatch:
imported module 'test_workload_dna' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_workload_dna.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_workload_dna.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
=========================== short test summary info ============================
ERROR tests/test_ab_compare.py
ERROR tests/test_batch_runner.py
ERROR tests/test_cli_contracts.py
ERROR tests/test_cli_workload_dna.py
ERROR tests/test_config.py
ERROR tests/test_config_toolkit_schema.py
ERROR tests/test_config_wizard.py
ERROR tests/test_dashboard_assets.py
ERROR tests/test_hybrid_capacity.py
ERROR tests/test_latency_buckets.py
ERROR tests/test_metrics_apply.py
ERROR tests/test_metrics_endpoints.py
ERROR tests/test_metrics_schema.py
ERROR tests/test_mission_control_charts.py
ERROR tests/test_mission_control_stub.py
ERROR tests/test_mission_control_widgets_qt.py
ERROR tests/test_perf_smoke.py
ERROR tests/test_process_manager.py
ERROR tests/test_snapshot_header.py
ERROR tests/test_tui_smoke.py
ERROR tests/test_workload_dna.py
!!!!!!!!!!!!!!!!!!! Interrupted: 21 errors during collection !!!!!!!!!!!!!!!!!!!
```

</details>

After ignoring the `check` directory, the tests ran, but with one failure.

<details>
<summary>Full `pytest -q --ignore=check` output</summary>

```
....................................F............................        [100%]
=================================== FAILURES ===================================
________________ test_dashboard_requires_token_and_embeds_meta _________________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11474eb10>

    def test_dashboard_requires_token_and_embeds_meta(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADHASH_TOKEN", "secret")
        metrics = Metrics()
    
        try:
            server, stop_server = start_metrics_server(metrics, 0)
        except PermissionError:
            pytest.skip("network bindings not permitted in sandbox")
        try:
            port = server.server_address[1]
>           wait_for_server(port)

tests/test_metrics_endpoints.py:163:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

port = 64213, retries = 10, delay = 0.05, headers = None

    def wait_for_server(port: int, retries: int = 10, delay: float = 0.05, headers: Dict[str, str] | None = None) -> None:
        """Helper to wait until the HTTP server starts accepting connections."""
    
        for _ in range(retries):
            try:
                request = Request(
                    f"http://127.0.0.1:{port}/api/metrics",
                    headers=headers or {"Accept": "application/json"},
                )
                with urlopen(request, timeout=0.1):
                    return
            except Exception:
                time.sleep(delay)
>       raise RuntimeError("metrics server did not start in time")
E       RuntimeError: metrics server did not start in time

tests/test_metrics_endpoints.py:37: RuntimeError
----------------------------- Captured stderr call -----------------------------
2025-10-04T18:22:17 [INFO] hashmap_cli: Metrics server: http://localhost:0/  (dashboard) and /metrics
=========================== short test summary info ============================
FAILED tests/test_metrics_endpoints.py::test_dashboard_requires_token_and_embeds_meta
1 failed, 64 passed in 83.66s (0:01:23)
```

</details>


## Dynamic Analysis

I will now perform dynamic analysis by executing the tool\'s commands to test its features.

### CLI Commands

`hashmap_cli.py --help` output:

```
usage: hashmap_cli.py [-h]
                      [--mode {fast-insert,fast-lookup,memory-tight,adaptive}]
                      [--log-json] [--log-file LOG_FILE]
                      [--log-max-bytes LOG_MAX_BYTES]
                      [--log-backup-count LOG_BACKUP_COUNT] [--json]
                      [--config CONFIG]
                      {put,get,del,items,profile,generate-csv,run-csv,workload-dna,config-wizard,config-edit,ab-compare,mission-control,serve,compact-snapshot,verify-snapshot}
                      ...

HashMap CLI with multi-backend, adaptive mode, generator, profiler, metrics,
snapshots, verification (with repair), and CI summaries.

positional arguments:
  {put,get,del,items,profile,generate-csv,run-csv,workload-dna,config-wizard,config-edit,ab-compare,mission-control,serve,compact-snapshot,verify-snapshot}
    put
    get
    del
    items
    profile             Profile a CSV workload and print recommended backend.
    generate-csv        Generate a synthetic workload CSV.
    run-csv             Replay a CSV workload (metrics, snapshots, compaction,
                        JSON summary).
    workload-dna        Analyze a CSV workload for ratios, skew, and collision
                        risk.
    config-wizard       Interactively generate a TOML config file.
    config-edit         Edit a config file with preset support using the
                        wizard schema.
    ab-compare          Run paired run-csv jobs and compute throughput/latency
                        deltas.
    mission-control     Launch the Mission Control desktop UI (PyQt6).
    serve               Serve the dashboard/metrics API without running a
                        workload.
    compact-snapshot    Compact a RobinHoodMap snapshot offline.
    verify-snapshot     Verify invariants of a snapshot; optional safe repair
                        (RobinHoodMap).

options:
  -h, --help            show this help message and exit
  --mode {fast-insert,fast-lookup,memory-tight,adaptive}
                        Select backend when not loading a snapshot.
  --log-json            Emit logs in JSON format
  --log-file LOG_FILE   Optional log file path (rotates at 5MB, keeps 5
                        backups by default)
  --log-max-bytes LOG_MAX_BYTES
                        Max bytes per log file before rotation (default:
                        5000000)
  --log-backup-count LOG_BACKUP_COUNT
                        Number of rotated log files to keep (default: 5)
  --json                Emit machine-readable success output to stdout
  --config CONFIG       Path to TOML config file (overrides defaults and env
                        overrides)
```

### Command Execution

I will now execute a series of commands to test the tool\'s features. I will start with the `make smoke` command, which performs a quick end-to-end test.

**`make smoke`**

`make smoke` completed successfully.

```
mkdir -p runs
python hashmap_cli.py generate-csv --outfile runs/smoke.csv --ops 2000 --read-ratio 0.7 --key-skew 0.2 --key-space 500 --seed 7
2025-10-04T18:28:10 [INFO] hashmap_cli: Wrote workload CSV: runs/smoke.csv
python hashmap_cli.py --mode adaptive run-csv --csv runs/smoke.csv --metrics-out-dir runs
2025-10-04T18:28:10 [INFO] hashmap_cli: Adaptive map started on chaining
2025-10-04T18:28:10 [INFO] hashmap_cli: run-csv finished in 0.075996 s, backend=chaining
python scripts/validate_metrics_ndjson.py runs/metrics.ndjson
Validation finished: all lines valid
```

```

```

potentially_problematic_new_string (this is the text that should replace old_string, but MIGHT have bad escaping, or might be entirely correct):
```
# System-Wide Audit

This document contains the results of a system-wide audit of the AdaptiveHashMapCli project.


## Static Analysis

Running static analysis tools to check for code quality issues.

User requested to ignore the `check` directory. I will exclude it from the linting process.

### Ruff Linting

After excluding the `check` directory, `ruff check . --exclude check` reported 24 errors. The errors are concentrated in the `src/adhash/mission_control` widgets.

<details>
<summary>Full `ruff` output</summary>

```
F821 Undefined name `T`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:271:28
    |
269 |     def _run_background(
270 |         self,
271 |         work: Callable[[], T],
    |                            ^
272 |         on_success: Callable[[T], None],
273 |         on_error: Optional[Callable[[Exception], None]] = None,
    | 

F821 Undefined name `T`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:272:31
    |
270 |         self,
271 |         work: Callable[[], T],
272 |         on_success: Callable[[T], None],
    |                               ^
273 |         on_error: Optional[Callable[[Exception], None]] = None,
274 |     ) -> None:
    | 

F841 [*] Local variable `exc` is assigned to but never used
   --> src/adhash/mission_control/widgets/benchmark_suite.py:278:33
    |
276 |             try:
277 |                 result = work()
278 |             except Exception as exc:
    |                                 ^^^
279 |                 if on_error is None:
280 |                     return self._invoke_main_thread(lambda: None)
    | 
help: Remove assignment to unused variable `exc`

F821 Undefined name `exc`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:281:59
    |
279 |                 if on_error is None:
280 |                     return self._invoke_main_thread(lambda: None)
281 |                 self._invoke_main_thread(lambda: on_error(exc))
    |                                                           ^^^
282 |             else:
283 |                 self._invoke_main_thread(lambda: on_success(result))
    | 

F841 [*] Local variable `exc` is assigned to but never used
   --> src/adhash/mission_control/widgets/benchmark_suite.py:291:33
    |
289 |             try:
290 |                 result = fut.result()
291 |             except Exception as exc:
    |                                 ^^^
292 |                 if on_error is not None:
293 |                     self._invoke_main_thread(lambda: on_error(exc))
    | 
help: Remove assignment to unused variable `exc`

F821 Undefined name `exc`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:293:63
    |
291 |             except Exception as exc:
292 |                 if on_error is not None:
293 |                     self._invoke_main_thread(lambda: on_error(exc))
    |                                                               ^^^
294 |             else:
295 |                 self._invoke_main_thread(lambda: on_success(result))
    | 

F821 Undefined name `BadInputError`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:480:16
    |
478 |         try:
479 |             result = analyze_workload_csv(job.csv, top_keys=8)
480 |         except BadInputError as exc:
    |                ^^^^^^^^^^^^^
481 |             self._show_analysis_message(str(exc), error=True)
482 |             return
    | 

F821 Undefined name `math`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:899:20
    |
897 |             return
898 | 
899 |         side = int(math.ceil(math.sqrt(counts.size)))
    |                    ^^^^ 
900 |         if counts.size < side * side:
901 |             pad = side * side - counts.size
    | 

F821 Undefined name `math`
   --> src/adhash/mission_control/widgets/benchmark_suite.py:899:30
    |
897 |             return
898 | 
899 |         side = int(math.ceil(math.sqrt(counts.size)))
    |                              ^^^^ 
900 |         if counts.size < side * side:
901 |             pad = side * side - counts.size
    | 

F821 Undefined name `QColor`
    --> src/adhash/mission_control/widgets/benchmark_suite.py:1012:17
     |
1010 |         ratio = max(0.0, min(1.0, ratio))
1011 |         hue = int(120 - 120 * ratio)
1012 |         color = QColor.fromHsv(hue, 255, 255)
     |                 ^^^^^^ 
1013 |         return pg.mkBrush(color)
     | 

F401 [*] `typing.Callable` imported but unused
  --> src/adhash/mission_control/widgets/common.py:10:5
   |
 8 |     TYPE_CHECKING,
 9 |     Any,
10 |     Callable,
   |     ^^^^^^^^ 
11 |     Iterable,
12 |     Mapping,
   | 
help: Remove unused import: `typing.Callable`

F401 [*] `typing.List` imported but unused
 --> src/adhash/mission_control/widgets/metrics.py:6:25
  |
5 | import time
6 | from typing import Any, List, Mapping, Optional, Sequence, Tuple
  |                         ^^^^ 
7 | 
8 | from .common import (
  | 
help: Remove unused import

F401 [*] `typing.Sequence` imported but unused
 --> src/adhash/mission_control/widgets/metrics.py:6:50
  |
5 | import time
6 | from typing import Any, List, Mapping, Optional, Sequence, Tuple
  |                                                  ^^^^^^^^ 
7 | 
8 | from .common import (
  | 
help: Remove unused import

F401 [*] `typing.Tuple` imported but unused
 --> src/adhash/mission_control/widgets/metrics.py:6:60
  |
5 | import time
6 | from typing import Any, List, Mapping, Optional, Sequence, Tuple
  |                                                            ^^^^^ 
7 | 
8 | from .common import (
  | 
help: Remove unused import

F401 [*] `.common.QProgressBar` imported but unused
  --> src/adhash/mission_control/widgets/metrics.py:12:5
   |
10 |     QHBoxLayout,
11 |     QPlainTextEdit,
12 |     QProgressBar,
   |     ^^^^^^^^^^^^ 
13 |     QTabWidget,
14 |     Qt,
   | 
help: Remove unused import: `.common.QProgressBar`

F821 Undefined name `MetricsSnapshot`
   --> src/adhash/mission_control/widgets/metrics.py:270:41
    |
268 |         self.summary_label.setText(text)
269 | 
270 |     def update_snapshot(self, snapshot: MetricsSnapshot) -> None:
    |                                         ^^^^^^^^^^^^^^^ 
271 |         self._tick_index += 1
272 |         throughput = self._estimate_throughput(snapshot)
    | 

F821 Undefined name `MetricsSnapshot`
   --> src/adhash/mission_control/widgets/metrics.py:290:45
    |
288 |         self.events_view.setPlainText("\n".join(lines))
289 | 
290 |     def _summarize_snapshot(self, snapshot: MetricsSnapshot, throughput: Optional[float]) -> str:
    |                                             ^^^^^^^^^^^^^^^ 
291 |         tick = snapshot.tick
292 |         backend = tick.get("backend", "unknown")
    | 

F821 Undefined name `MetricsSnapshot`
   --> src/adhash/mission_control/widgets/metrics.py:311:40
    |
309 |         return summary
310 | 
311 |     def _update_charts(self, snapshot: MetricsSnapshot, throughput: Optional[float]) -> None:
    |                                        ^^^^^^^^^^^^^^^ 
312 |         if not self._supports_charts:
313 |             return
    | 

F821 Undefined name `math`
   --> src/adhash/mission_control/widgets/metrics.py:347:16
    |
345 |         ticks = []
346 |         for idx, (upper, _count) in enumerate(series):
347 |             if math.isinf(upper):
    |                ^^^^ 
348 |                 label = "≤inf"
349 |             elif upper >= 1.0:
    | 

F821 Undefined name `MetricsSnapshot`
   --> src/adhash/mission_control/widgets/metrics.py:413:46
    |
411 |             self._heatmap_status.setVisible(not has_data)
412 | 
413 |     def _estimate_throughput(self, snapshot: MetricsSnapshot) -> Optional[float]:
    |                                              ^^^^^^^^^^^^^^^ 
414 |         tick = snapshot.tick
415 |         raw = tick.get("ops_per_second") or tick.get("throughput")
    | 

F401 [*] `typing.Callable` imported but unused
 --> src/adhash/mission_control/widgets/workload_dna.py:7:25
  |
5 | import math
6 | from pathlib import Path
7 | from typing import Any, Callable, List, Optional, Tuple
  |                         ^^^^^^^^ 
8 | 
9 | from adhash.workloads import WorkloadDNAResult, format_workload_dna
  | 
help: Remove unused import: `typing.Callable`

F401 [*] `.common.QTimer` imported but unused
  --> src/adhash/mission_control/widgets/workload_dna.py:23:5
   |
21 |     QToolTip,
22 |     Qt,
23 |     QTimer,
   |     ^^^^^^ 
24 |     QVBoxLayout,
25 |     QWidget,
   | 
help: Remove unused import

F401 [*] `.common.style_plot` imported but unused
  --> src/adhash/mission_control/widgets/workload_dna.py:28:5
   |
26 |     np,
27 |     pg,
28 |     style_plot,
   |     ^^^^^^^^^^ 
29 | )
   | 
help: Remove unused import

F841 Local variable `sentinel` is assigned to but never used
   --> tests/test_mission_control_widgets_qt.py:143:9
    |
141 |         )
142 | 
143 |         sentinel = object()
    |         ^^^^^^^^ 
144 | 
145 |         def slow_discover() -> List[Path]:
    | 
help: Remove assignment to unused variable `sentinel`

Found 24 errors. 
[*] 10 fixable with the `--fix` option (1 hidden fix can be enabled with the `--unsafe-fixes` option).
```

### MyPy Type Checking

`make type` reported 37 errors. These are mostly `union-attr` errors on optional Qt widgets and undefined names, also concentrated in the Mission Control UI code.

<details>
<summary>Full `make type` output</summary>

```
src/adhash/workloads/dna.py:323: error: Dict entry 0 has incompatible type "str": "str"; expected "str": "float"  [dict-item]
src/adhash/mission_control/widgets/workload_dna.py:172: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:172: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/workload_dna.py:173: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:173: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/workload_dna.py:184: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:184: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/workload_dna.py:185: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:185: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/workload_dna.py:226: error: Item "None" of "Any | None" has no attribute "show"  [union-attr]
src/adhash/mission_control/widgets/workload_dna.py:490: error: Item "None" of "Any | None" has no attribute "getPlotItem"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:189: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:189: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/run_control.py:190: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:190: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/run_control.py:258: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:258: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/run_control.py:259: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/run_control.py:259: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:92: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:92: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:118: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:118: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:149: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:149: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:177: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:177: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:256: error: Item "None" of "QTabBar | None" has no attribute "setTabToolTip"  [union-attr]
src/adhash/mission_control/widgets/metrics.py:256: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/metrics.py:270: error: Name "MetricsSnapshot" is not defined  [name-defined]
src/adhash/mission_control/widgets/metrics.py:290: error: Name "MetricsSnapshot" is not defined  [name-defined]
src/adhash/mission_control/widgets/metrics.py:311: error: Name "MetricsSnapshot" is not defined  [name-defined]
src/adhash/mission_control/widgets/metrics.py:347: error: Name "math" is not defined  [name-defined]
src/adhash/mission_control/widgets/metrics.py:413: error: Name "MetricsSnapshot" is not defined  [name-defined]
src/adhash/mission_control/widgets/connection.py:71: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/connection.py:71: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/connection.py:72: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/connection.py:72: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:194: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:194: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:195: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:195: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:271: error: Name "T" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:272: error: Name "T" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:480: error: Name "BadInputError" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:737: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:737: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:738: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:738: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:749: error: Item "None" of "QStyle | None" has no attribute "unpolish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:749: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:750: error: Item "None" of "QStyle | None" has no attribute "polish"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:750: note: Error code "union-attr" not covered by "type: ignore" comment
src/adhash/mission_control/widgets/benchmark_suite.py:791: error: Item "None" of "Any | None" has no attribute "show"  [union-attr]
src/adhash/mission_control/widgets/benchmark_suite.py:899: error: Name "math" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:1012: error: Name "QColor" is not defined  [name-defined]
src/adhash/mission_control/widgets/benchmark_suite.py:1053: error: Item "None" of "Any | None" has no attribute "getPlotItem"  [union-attr]
tests/test_cli_workload_dna.py:57: error: Dict entry 0 has incompatible type "str": "str"; expected "str": "float"  [dict-item]
Found 37 errors in 7 files (checked 65 source files)
```

</details>


## Testing

Running the test suite to check for regressions and correctness.

`make test` failed because `pytest` was collecting tests from the `check` directory, causing `import file mismatch` errors. I will re-run the tests, ignoring the `check` directory.

<details>
<summary>Full `make test` output</summary>

```
==================================== ERRORS ====================================
__________________ ERROR collecting tests/test_ab_compare.py ___________________
import file mismatch:
imported module 'test_ab_compare' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_ab_compare.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_ab_compare.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_batch_runner.py __________________
import file mismatch:
imported module 'test_batch_runner' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_batch_runner.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_batch_runner.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_cli_contracts.py _________________
import file mismatch:
imported module 'test_cli_contracts' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_cli_contracts.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_cli_contracts.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_______________ ERROR collecting tests/test_cli_workload_dna.py ________________
import file mismatch:
imported module 'test_cli_workload_dna' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_cli_workload_dna.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_cli_workload_dna.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
____________________ ERROR collecting tests/test_config.py _____________________
import file mismatch:
imported module 'test_config' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_config.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_config.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_____________ ERROR collecting tests/test_config_toolkit_schema.py _____________
import file mismatch:
imported module 'test_config_toolkit_schema' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_config_toolkit_schema.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_config_toolkit_schema.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_config_wizard.py _________________
import file mismatch:
imported module 'test_config_wizard' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_config_wizard.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_config_wizard.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_______________ ERROR collecting tests/test_dashboard_assets.py ________________
import file mismatch:
imported module 'test_dashboard_assets' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_dashboard_assets.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_dashboard_assets.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_hybrid_capacity.py ________________
import file mismatch:
imported module 'test_hybrid_capacity' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_hybrid_capacity.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_hybrid_capacity.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_latency_buckets.py ________________
import file mismatch:
imported module 'test_latency_buckets' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_latency_buckets.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_latency_buckets.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_metrics_apply.py _________________
import file mismatch:
imported module 'test_metrics_apply' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_metrics_apply.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_metrics_apply.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_______________ ERROR collecting tests/test_metrics_endpoints.py _______________
import file mismatch:
imported module 'test_metrics_endpoints' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_metrics_endpoints.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_metrics_endpoints.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_metrics_schema.py _________________
import file mismatch:
imported module 'test_metrics_schema' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_metrics_schema.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_metrics_schema.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
____________ ERROR collecting tests/test_mission_control_charts.py _____________
import file mismatch:
imported module 'test_mission_control_charts' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_mission_control_charts.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_mission_control_charts.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_____________ ERROR collecting tests/test_mission_control_stub.py ______________
import file mismatch:
imported module 'test_mission_control_stub' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_mission_control_stub.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_mission_control_stub.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
__________ ERROR collecting tests/test_mission_control_widgets_qt.py ___________
import file mismatch:
imported module 'test_mission_control_widgets_qt' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_mission_control_widgets_qt.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_mission_control_widgets_qt.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
__________________ ERROR collecting tests/test_perf_smoke.py ___________________
import file mismatch:
imported module 'test_perf_smoke' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_perf_smoke.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_perf_smoke.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_process_manager.py ________________
import file mismatch:
imported module 'test_process_manager' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_process_manager.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_process_manager.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
________________ ERROR collecting tests/test_snapshot_header.py ________________
import file mismatch:
imported module 'test_snapshot_header' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_snapshot_header.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_snapshot_header.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
___________________ ERROR collecting tests/test_tui_smoke.py ___________________
import file mismatch:
imported module 'test_tui_smoke' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_tui_smoke.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_tui_smoke.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
_________________ ERROR collecting tests/test_workload_dna.py __________________
import file mismatch:
imported module 'test_workload_dna' has this __file__ attribute:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/check/adadptivehashmapv4-main/adadptivehashmapv4-main/tests/test_workload_dna.py
which is not the same as the test file we want to collect:
  /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/tests/test_workload_dna.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
=========================== short test summary info ============================
ERROR tests/test_ab_compare.py
ERROR tests/test_batch_runner.py
ERROR tests/test_cli_contracts.py
ERROR tests/test_cli_workload_dna.py
ERROR tests/test_config.py
ERROR tests/test_config_toolkit_schema.py
ERROR tests/test_config_wizard.py
ERROR tests/test_dashboard_assets.py
ERROR tests/test_hybrid_capacity.py
ERROR tests/test_latency_buckets.py
ERROR tests/test_metrics_apply.py
ERROR tests/test_metrics_endpoints.py
ERROR tests/test_metrics_schema.py
ERROR tests/test_mission_control_charts.py
ERROR tests/test_mission_control_stub.py
ERROR tests/test_mission_control_widgets_qt.py
ERROR tests/test_perf_smoke.py
ERROR tests/test_process_manager.py
ERROR tests/test_snapshot_header.py
ERROR tests/test_tui_smoke.py
ERROR tests/test_workload_dna.py
!!!!!!!!!!!!!!!!!!! Interrupted: 21 errors during collection !!!!!!!!!!!!!!!!!!!
```

</details>

After ignoring the `check` directory, the tests ran, but with one failure.

<details>
<summary>Full `pytest -q --ignore=check` output</summary>

```
....................................F............................        [100%]
=================================== FAILURES ===================================
________________ test_dashboard_requires_token_and_embeds_meta _________________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11474eb10>

    def test_dashboard_requires_token_and_embeds_meta(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADHASH_TOKEN", "secret")
        metrics = Metrics()
    
        try:
            server, stop_server = start_metrics_server(metrics, 0)
        except PermissionError:
            pytest.skip("network bindings not permitted in sandbox")
        try:
            port = server.server_address[1]
>           wait_for_server(port)

tests/test_metrics_endpoints.py:163:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

port = 64213, retries = 10, delay = 0.05, headers = None

    def wait_for_server(port: int, retries: int = 10, delay: float = 0.05, headers: Dict[str, str] | None = None) -> None:
        """Helper to wait until the HTTP server starts accepting connections."""
    
        for _ in range(retries):
            try:
                request = Request(
                    f"http://127.0.0.1:{port}/api/metrics",
                    headers=headers or {"Accept": "application/json"},
                )
                with urlopen(request, timeout=0.1):
                    return
            except Exception:
                time.sleep(delay)
>       raise RuntimeError("metrics server did not start in time")
E       RuntimeError: metrics server did not start in time

tests/test_metrics_endpoints.py:37: RuntimeError
----------------------------- Captured stderr call -----------------------------
2025-10-04T18:22:17 [INFO] hashmap_cli: Metrics server: http://localhost:0/  (dashboard) and /metrics
=========================== short test summary info ============================
FAILED tests/test_metrics_endpoints.py::test_dashboard_requires_token_and_embeds_meta
1 failed, 64 passed in 83.66s (0:01:23)
```

</details>


## Dynamic Analysis

I will now perform dynamic analysis by executing the tool\'s commands to test its features.

### CLI Commands

`hashmap_cli.py --help` output:

```
usage: hashmap_cli.py [-h]
                      [--mode {fast-insert,fast-lookup,memory-tight,adaptive}]
                      [--log-json] [--log-file LOG_FILE]
                      [--log-max-bytes LOG_MAX_BYTES]
                      [--log-backup-count LOG_BACKUP_COUNT] [--json]
                      [--config CONFIG]
                      {put,get,del,items,profile,generate-csv,run-csv,workload-dna,config-wizard,config-edit,ab-compare,mission-control,serve,compact-snapshot,verify-snapshot}
                      ...

HashMap CLI with multi-backend, adaptive mode, generator, profiler, metrics,
snapshots, verification (with repair), and CI summaries.

positional arguments:
  {put,get,del,items,profile,generate-csv,run-csv,workload-dna,config-wizard,config-edit,ab-compare,mission-control,serve,compact-snapshot,verify-snapshot}
    put
    get
    del
    items
    profile             Profile a CSV workload and print recommended backend.
    generate-csv        Generate a synthetic workload CSV.
    run-csv             Replay a CSV workload (metrics, snapshots, compaction,
                        JSON summary).
    workload-dna        Analyze a CSV workload for ratios, skew, and collision
                        risk.
    config-wizard       Interactively generate a TOML config file.
    config-edit         Edit a config file with preset support using the
                        wizard schema.
    ab-compare          Run paired run-csv jobs and compute throughput/latency
                        deltas.
    mission-control     Launch the Mission Control desktop UI (PyQt6).
    serve               Serve the dashboard/metrics API without running a
                        workload.
    compact-snapshot    Compact a RobinHoodMap snapshot offline.
    verify-snapshot     Verify invariants of a snapshot; optional safe repair
                        (RobinHoodMap).

options:
  -h, --help            show this help message and exit
  --mode {fast-insert,fast-lookup,memory-tight,adaptive}
                        Select backend when not loading a snapshot.
  --log-json            Emit logs in JSON format
  --log-file LOG_FILE   Optional log file path (rotates at 5MB, keeps 5
                        backups by default)
  --log-max-bytes LOG_MAX_BYTES
                        Max bytes per log file before rotation (default:
                        5000000)
  --log-backup-count LOG_BACKUP_COUNT
                        Number of rotated log files to keep (default: 5)
  --json                Emit machine-readable success output to stdout
  --config CONFIG       Path to TOML config file (overrides defaults and env
                        overrides)
```

### Command Execution

I will now execute a series of commands to test the tool\'s features. I will start with the `make smoke` command, which performs a quick end-to-end test.

**`make smoke`**

`make smoke` completed successfully.

```
mkdir -p runs
python hashmap_cli.py generate-csv --outfile runs/smoke.csv --ops 2000 --read-ratio 0.7 --key-skew 0.2 --key-space 500 --seed 7
2025-10-04T18:28:10 [INFO] hashmap_cli: Wrote workload CSV: runs/smoke.csv
python hashmap_cli.py --mode adaptive run-csv --csv runs/smoke.csv --metrics-out-dir runs
2025-10-04T18:28:10 [INFO] hashmap_cli: Adaptive map started on chaining
2025-10-04T18:28:10 [INFO] hashmap_cli: run-csv finished in 0.075996 s, backend=chaining
python scripts/validate_metrics_ndjson.py runs/metrics.ndjson
Validation finished: all lines valid
```

**`profile` command**

The `profile` command and its `--then` flag both executed successfully, recommending the `fast-lookup` backend for the given workload.

*`python hashmap_cli.py profile --csv data/workloads/w_uniform.csv`*
```
fast-lookup
2025-10-04T18:31:06 [INFO] hashmap_cli: Profile fast-insert: 0.002796 s over 5000 ops
2025-10-04T18:31:06 [INFO] hashmap_cli: Profile fast-lookup: 0.002221 s over 5000 ops
2025-10-04T18:31:06 [INFO] hashmap_cli: Profile pick: fast-lookup
```

*`python hashmap_cli.py profile --csv data/workloads/w_uniform.csv --then get A`*
```
fast-lookup

2025-10-04T18:35:51 [INFO] hashmap_cli: Profile fast-insert: 0.003080 s over 5000 ops
2025-10-04T18:35:51 [INFO] hashmap_cli: Profile fast-lookup: 0.002420 s over 5000 ops
2025-10-04T18:35:51 [INFO] hashmap_cli: Profile pick: fast-lookup
```

```