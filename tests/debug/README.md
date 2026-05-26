# Debug harnesses

Investigation tools, not part of the automated test suite.

## `replay.py` — offline wire-capture replay for #82

Replays a wire-capture log (as produced by `givenergy-cli capture`) through a
single live `Plant`, watching for cache writes that produce out-of-bounds
values. Each OOB event is emitted as a JSONL record with the originating
frame's raw bytes, the affected field, and the value that landed in the
cache.

Built to discriminate between two hypotheses for the #82 corruption:

- **Wire-delivered** — the dongle is occasionally sending bytes that decode
  into the bad value. The replay reproduces the corruption deterministically
  from the capture; the JSONL record names the exact frame and we can read
  the bad value out of the raw bytes.
- **Library-internal** — the bad value is produced by library state (a
  counter, a stale buffer, etc.) that isn't carried in the wire bytes. The
  replay won't reproduce the corruption, and we move to live-deployment
  instrumentation.

### Usage

```bash
# All known-corruptible fields, full capture, write events to a file
uv run python tests/debug/replay.py \
    --capture ~/git/givenergy-cli/frames-*.log \
    --output replay-events.jsonl

# Only watch specific fields
uv run python tests/debug/replay.py \
    --capture ~/git/givenergy-cli/frames-*.log \
    --fields battery_soc,soc \
    --output replay-events.jsonl

# Write to stdout
uv run python tests/debug/replay.py --capture frames-*.log
```

### Output format

One JSON object per OOB event, one event per line:

```json
{
  "ts": "2026-05-25T03:05:08.123+00:00",
  "device_address": "0x32",
  "field": "soc",
  "registers": ["IR_100"],
  "raw_register_values": [37978],
  "post_conv_value": 37978,
  "min": 0, "max": 100,
  "pdu_type": "ReadInputRegistersResponse",
  "pdu_base_register": 60,
  "pdu_register_count": 60,
  "raw_frame": "5959000100..."
}
```

Stats are emitted to stderr at the end of the run.
