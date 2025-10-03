# Configuration (TOML)

Adaptive Hash Map CLI can load runtime policy from a TOML file instead of relying on
environment variables. Pass `--config path/to/config.toml` to `hashmap_cli.py` (or set the
`ADHASH_CONFIG` environment variable) and the loader will apply the settings below. Prefer
an interactive workflow? Run `python hashmap_cli.py config-wizard --outfile config.toml` and
follow the prompts to generate a ready-to-use file.

```toml
[adaptive]
start_backend = "chaining"        # "chaining" or "robinhood"
initial_buckets = 64              # power of two
groups_per_bucket = 8             # power of two
initial_capacity_rh = 64          # power of two
incremental_batch = 2048          # items moved per migration tick
max_lf_chaining = 0.82            # migrate to robinhood when exceeded
max_group_len = 8                 # chaining guardrail
max_avg_probe_robinhood = 6.0     # migrate back to chaining when exceeded
max_tombstone_ratio = 0.25        # compact robinhood when exceeded
large_map_warn_threshold = 1000000

[watchdog]
enabled = true                    # disable alerts entirely when false
load_factor_warn = 0.9            # use "none" to disable (0-1)
avg_probe_warn = 8.0              # use "none" to disable (>0)
tombstone_ratio_warn = 0.35       # use "none" to disable (0-1)
```

Values are optional; omitted keys fall back to defaults. Invalid types raise a
`BadInputError` and surface through the error envelope (exit code 2).

To disable a specific watchdog threshold, set the value to the string `"none"`
either in the TOML file or when prompted by the wizard.
