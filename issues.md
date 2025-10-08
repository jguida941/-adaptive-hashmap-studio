Run started:2025-10-08 11:11:28.557423

Test results:
>> Issue: [B404:blacklist] Consider possible security implications associated with the subprocess module.
   Severity: Low   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/blacklists/blacklist_imports.html#b404-import-subprocess
   Location: src/adhash/batch/runner.py:8:0
7	import shlex
8	import subprocess
9	import sys

--------------------------------------------------
>> Issue: [B603:subprocess_without_shell_equals_true] subprocess call - check for execution of untrusted input.
   Severity: Low   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b603_subprocess_without_shell_equals_true.html
   Location: src/adhash/batch/runner.py:158:19
157	        try:
158	            proc = subprocess.run(
159	                command,
160	                stdout=subprocess.PIPE,
161	                stderr=subprocess.PIPE,
162	                cwd=self.spec.working_dir,
163	                text=True,
164	            )
165	            duration = time.perf_counter() - start

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/cli/commands.py:506:8
505	            object_data["size"] = len(payload)  # type: ignore[arg-type]
506	        except Exception:
507	            pass
508	        if hasattr(payload, "backend_name"):

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/cli/commands.py:511:12
510	                object_data["backend"] = payload.backend_name()
511	            except Exception:
512	                pass
513	        for attr, label in (

--------------------------------------------------
>> Issue: [B112:try_except_continue] Try, Except, Continue detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b112_try_except_continue.html
   Location: src/adhash/cli/commands.py:522:16
521	                    value = fn()
522	                except Exception:
523	                    continue
524	                if isinstance(value, (int, float)):

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/cli/commands.py:601:8
600	                return it
601	        except Exception:
602	            pass
603	    if isinstance(payload, dict):

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/cli/commands.py:615:8
614	                return value, True
615	        except Exception:
616	            pass
617	    for candidate, value in _iter_snapshot_items(payload):

--------------------------------------------------
>> Issue: [B311:blacklist] Standard pseudo-random generators are not suitable for security/cryptographic purposes.
   Severity: Low   Confidence: High
   CWE: CWE-330 (https://cwe.mitre.org/data/definitions/330.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/blacklists/blacklist_calls.html#b311-random
   Location: src/adhash/core/latency.py:62:19
61	        self.n = 0
62	        self.rng = random.Random(seed)
63

--------------------------------------------------
>> Issue: [B101:assert_used] Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b101_assert_used.html
   Location: src/adhash/core/maps.py:410:8
409	        migrated = 0
410	        assert self._migrate_iter is not None
411	        target = self._migrate_target

--------------------------------------------------
>> Issue: [B101:assert_used] Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b101_assert_used.html
   Location: src/adhash/hashmap_cli.py:279:8
278	    if apply_preset:
279	        assert preset_dir_path is not None
280	        base_cfg = clone_config(load_preset(apply_preset, preset_dir_path))

--------------------------------------------------
>> Issue: [B101:assert_used] Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b101_assert_used.html
   Location: src/adhash/hashmap_cli.py:368:8
367	    if op == "put":
368	        assert key is not None and value is not None
369	        m.put(key, value)

--------------------------------------------------
>> Issue: [B101:assert_used] Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b101_assert_used.html
   Location: src/adhash/hashmap_cli.py:373:8
372	    elif op == "get":
373	        assert key is not None
374	        v = m.get(key)

--------------------------------------------------
>> Issue: [B101:assert_used] Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b101_assert_used.html
   Location: src/adhash/hashmap_cli.py:379:8
378	    elif op == "del":
379	        assert key is not None
380	        ok = m.delete(key)

--------------------------------------------------
>> Issue: [B311:blacklist] Standard pseudo-random generators are not suitable for security/cryptographic purposes.
   Severity: Low   Confidence: High
   CWE: CWE-330 (https://cwe.mitre.org/data/definitions/330.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/blacklists/blacklist_calls.html#b311-random
   Location: src/adhash/hashmap_cli.py:475:10
474	        raise ValueError("adversarial_ratio in [0,1]")
475	    rng = random.Random(seed)
476	    sample_key_idx = _zipf_sampler(key_space, key_skew, rng)

--------------------------------------------------
>> Issue: [B403:blacklist] Consider possible security implications associated with pickle module.
   Severity: Low   Confidence: High
   CWE: CWE-502 (https://cwe.mitre.org/data/definitions/502.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/blacklists/blacklist_imports.html#b403-import-pickle
   Location: src/adhash/io/safe_pickle.py:7:0
6	import io
7	import pickle
8	from typing import Any, IO, Tuple

--------------------------------------------------
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'ADHASH_TOKEN'
   Severity: Low   Confidence: Medium
   CWE: CWE-259 (https://cwe.mitre.org/data/definitions/259.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b105_hardcoded_password_string.html
   Location: src/adhash/metrics/constants.py:17:16
16
17	TOKEN_ENV_VAR = "ADHASH_TOKEN"
18	AUTH_HEADER = "Authorization"

--------------------------------------------------
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: ''
   Severity: Low   Confidence: Medium
   CWE: CWE-259 (https://cwe.mitre.org/data/definitions/259.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b105_hardcoded_password_string.html
   Location: src/adhash/metrics/server.py:420:25
419	        def _render_dashboard_html(self) -> bytes:
420	            token_meta = ""
421

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/mission_control/app.py:121:4
120	        app.setStyle("Fusion")
121	    except Exception:  # pragma: no cover - style might be missing
122	        pass
123

--------------------------------------------------
>> Issue: [B101:assert_used] Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b101_assert_used.html
   Location: src/adhash/mission_control/builders.py:129:4
128	    window_cls = mission_window_cls or QMAINWINDOW_CLS
129	    assert window_cls is not None  # for mypy
130	    window = window_cls()  # type: ignore[call-arg]

--------------------------------------------------
>> Issue: [B404:blacklist] Consider possible security implications associated with the subprocess module.
   Severity: Low   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/blacklists/blacklist_imports.html#b404-import-subprocess
   Location: src/adhash/mission_control/process_manager.py:7:0
6	import shlex
7	import subprocess
8	import threading

--------------------------------------------------
>> Issue: [B603:subprocess_without_shell_equals_true] subprocess call - check for execution of untrusted input.
   Severity: Low   Confidence: High
   CWE: CWE-78 (https://cwe.mitre.org/data/definitions/78.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b603_subprocess_without_shell_equals_true.html
   Location: src/adhash/mission_control/process_manager.py:31:29
30	            try:
31	                self._proc = subprocess.Popen(
32	                    args,
33	                    stdout=subprocess.PIPE,
34	                    stderr=subprocess.STDOUT,
35	                    text=True,
36	                    bufsize=1,
37	                )
38	            except OSError as exc:

--------------------------------------------------
>> Issue: [B101:assert_used] Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b101_assert_used.html
   Location: src/adhash/mission_control/process_manager.py:65:8
64	    def _pump(self) -> None:
65	        assert self._proc is not None
66	        proc = self._proc

--------------------------------------------------
>> Issue: [B101:assert_used] Use of assert detected. The enclosed code will be removed when compiling to optimised byte code.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b101_assert_used.html
   Location: src/adhash/mission_control/process_manager.py:68:12
67	        try:
68	            assert proc.stdout is not None
69	            stdout = proc.stdout

--------------------------------------------------
>> Issue: [B112:try_except_continue] Try, Except, Continue detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b112_try_except_continue.html
   Location: src/adhash/mission_control/widgets/benchmark_suite.py:307:16
306	                    load_spec(resolved)
307	                except Exception:
308	                    continue
309	                seen.add(resolved)

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/mission_control/widgets/benchmark_suite.py:642:12
641	                self.analysisCompleted.emit(result, job, spec_path)  # type: ignore[attr-defined]
642	            except Exception:  # pragma: no cover
643	                pass
644	        for callback in list(self._analysis_callbacks):

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/mission_control/widgets/config_editor.py:367:12
366	                self.configSaved.emit(path)  # type: ignore[attr-defined]
367	            except Exception:  # pragma: no cover - Qt emits may fail in headless tests
368	                pass
369	        for callback in list(self._config_saved_callbacks):

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/mission_control/widgets/config_editor.py:376:12
375	                self.configLoaded.emit(path)  # type: ignore[attr-defined]
376	            except Exception:  # pragma: no cover
377	                pass
378	        for callback in list(self._config_loaded_callbacks):

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/mission_control/widgets/config_editor.py:385:12
384	                self.presetSaved.emit(path)  # type: ignore[attr-defined]
385	            except Exception:  # pragma: no cover
386	                pass
387	        for callback in list(self._preset_saved_callbacks):

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/mission_control/widgets/metrics.py:300:24
299	                            legend.restoreState(state)  # type: ignore[attr-defined]
300	                        except Exception:
301	                            pass
302	                        legend.setMinimumHeight(22)

--------------------------------------------------
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: '-m'
   Severity: Low   Confidence: Medium
   CWE: CWE-259 (https://cwe.mitre.org/data/definitions/259.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b105_hardcoded_password_string.html
   Location: src/adhash/mission_control/widgets/run_control.py:350:24
349	        for idx, token in enumerate(args):
350	            if token == "-m" and idx + 1 < len(args):
351	                module = args[idx + 1]

--------------------------------------------------
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: '--'
   Severity: Low   Confidence: Medium
   CWE: CWE-259 (https://cwe.mitre.org/data/definitions/259.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b105_hardcoded_password_string.html
   Location: src/adhash/mission_control/widgets/run_control.py:383:24
382	                continue
383	            if token == "--":
384	                return i

--------------------------------------------------
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'run-csv'
   Severity: Low   Confidence: Medium
   CWE: CWE-259 (https://cwe.mitre.org/data/definitions/259.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b105_hardcoded_password_string.html
   Location: src/adhash/mission_control/widgets/run_control.py:412:24
411	            token = args[idx]
412	            if token == "run-csv" or token in option_keys:
413	                break

--------------------------------------------------
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'run-csv'
   Severity: Low   Confidence: Medium
   CWE: CWE-259 (https://cwe.mitre.org/data/definitions/259.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b105_hardcoded_password_string.html
   Location: src/adhash/mission_control/widgets/run_control.py:419:24
418	            token = args[idx]
419	            if token == "run-csv":
420	                seen_run = True

--------------------------------------------------
>> Issue: [B110:try_except_pass] Try, Except, Pass detected.
   Severity: Low   Confidence: High
   CWE: CWE-703 (https://cwe.mitre.org/data/definitions/703.html)
   More Info: https://bandit.readthedocs.io/en/1.8.6/plugins/b110_try_except_pass.html
   Location: src/adhash/mission_control/widgets/snapshot_inspector.py:385:12
384	                    text.append(f"⚠ Load factor {load_factor:.3f} exceeds {warn:.3f}")
385	            except Exception:
386	                pass
387	        self.result_view.setPlainText("\n".join(text))

--------------------------------------------------

Code scanned:
	Total lines of code: 12772
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 3

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 34
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 6
		High: 28
Files skipped (0):
