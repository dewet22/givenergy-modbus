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

## `unsolicited_responses.py` — fan-out / broadcast detection for #196

Quantifies the responses a dongle volunteers without being asked. It pairs each
received `TransparentResponse` to a preceding `TransparentRequest` using the
library's own `shape_hash` matching (the same logic the network consumer uses to
resolve futures); responses that match no request are unsolicited — the dongle
fanned out someone else's poll (the GE cloud, the app, another client).

Built to inform #196 (Gen3 poll slowness). Finding: across every device class we
have a capture for (AIO, AC, EMS, Gen1 hybrid) the live blocks (`IR(0,60)` etc.)
arrive unsolicited on a ~10–32s cloud-driven cadence — so a slow *solicited*
read is not necessarily a failure if a fan-out frame already refreshed the cache.
The open question it's waiting to answer: does a Gen3 dongle answer solicited
reads at all, or *only* fan out? (No Gen3 capture yet.)

### Usage

```bash
uv run python tests/debug/unsolicited_responses.py CAPTURE.log [CAPTURE2.log ...]
```

### Interpreting the output

```
events=727  requests(tx)=241  responses(rx)=478
solicited (matched a prior request) = 216
unanswered requests                 = 25
UNSOLICITED (no prior request)      = 262

  [   52x] ReadInputRegistersResponse dev=0x31 fc=0x04 base=0 count=60  cadence: min=0.16s avg=11.46s max=22.33s
```

- A **passive** capture (no `tx` lines) trivially reports every response as
  unsolicited — there were no requests to match. It still proves the data flows
  without *us* asking, and the cadence figures are valid.
- A capture containing the client's own `tx` requests is what proves fan-out
  coexists with solicited traffic (here: 216 answered *and* 262 volunteered).
- `cadence` is the inter-arrival time of each unsolicited shape — low jitter and
  a tight `max` mean a consumer could lean on the stream; a large `max` (the AIO
  hits 114s) means passive-only freshness is unreliable.
