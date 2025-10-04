# Security Notes

- Snapshots load through a restricted allowlist (`adhash.io.safe_pickle`). Regenerate old `.pkl.gz` files before distributing them and continue to treat third-party snapshots with caution.
- The HTTP dashboard binds to `127.0.0.1` by default. Require an auth token before exposing externally.
- Clamp workload size and reservoir lengths via configuration to avoid unbounded resource usage. Override with caution.
