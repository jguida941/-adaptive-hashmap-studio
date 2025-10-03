# Snapshot Format v1

Snapshots consist of a versioned header, checksum, and optional gzip-compressed pickle payload.

- Magic bytes: `ADHSNAP1`
- Header struct: `>8s H B B H Q` (magic, version, flags, reserved, checksum length, payload length)
- Flags: bit 0 indicates gzip compression
- Checksum: BLAKE2b (32-byte digest) over the payload bytes
- Payload: pickle-serialized object; gzip-compressed when bit 0 is set

## Security Notes

Treat snapshots as untrusted input and avoid loading files from unknown sources. Future versions (`v2+`) may adopt a safer format (CBOR/Cap'n Proto) as tracked in the roadmap.
