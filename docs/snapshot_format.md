# Snapshot Format v1

Snapshots consist of a versioned header, checksum, and optional gzip-compressed payload encoded with Python's pickle but loaded through a restricted allowlist.

- Magic bytes: `ADHSNAP1`
- Header struct: `>8s H B B H Q` (magic, version, flags, reserved, checksum length, payload length)
- Flags: bit 0 indicates gzip compression
- Checksum: BLAKE2b (32-byte digest) over the payload bytes
- Payload: pickle-serialized object; gzip-compressed when bit 0 is set. Loading always uses the `adhash.io.safe_pickle` unpickler, which rejects globals outside the Adaptive Hash Map allowlist.

## Security Notes

Snapshots no longer execute arbitrary code during load, but legacy pickle files created before this release should be regenerated to benefit from the restricted loader. Future versions (`v2+`) may adopt a fully pickle-free format (CBOR/Cap'n Proto) as tracked in the roadmap.
