# Security Notes

- Snapshots use Python pickle internally; do **not** load untrusted snapshot files.
- The HTTP dashboard binds to `127.0.0.1` by default. Require an auth token before exposing externally.
- Clamp workload size and reservoir lengths via configuration to avoid unbounded resource usage. Override with caution.
