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

```text
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

## `soak_skip_if_fresh.py` — live validation of IR(0,60) skip-if-fresh (#196)

Drives the same poll loop a consumer (hass) would run, but with one job: validate
that the fan-out from cloud/app peers is keeping `IR(0,60)` fresh fast enough that
`refresh(ir0_max_age=...)` reliably skips soliciting it.

Run it **alongside** your normal setup (hass / GivTCP) — those peers are what poll
the dongle and produce the fan-out this exploits. The soak is a light extra client;
skip-if-fresh actually reduces the net request count.

### Usage

```bash
uv run python tests/debug/soak_skip_if_fresh.py \
    --host 192.168.1.50 --interval 20 --ir0-max-age 25 --duration 3600
```

Ctrl-C or `--duration` elapsing prints a summary.

### Interpreting the output

```text
tick    4 | ir0_sent=0 (SKIP) | age_before=11.2s age_after=11.2s | dt=1.43s | IR(1)=3284 | ok
tick    5 | ir0_sent=0 (SKIP) | age_before= 9.8s age_after= 9.8s | dt=1.51s | IR(1)=3095 | ok
tick   33 | ir0_sent=1 (SOLICIT) | age_before=25.7s age_after=—  | dt=6.01s | IR(1)=None | FAILED (...)
```

- `ir0_sent=0 (SKIP)` — the fan-out kept `IR(0,60)` fresh; no solicited read went on the wire.
- `ir0_sent=1 (SOLICIT)` — `age_before` exceeded `--ir0-max-age`; the library fell back to
  soliciting. Expected for brief dongle outages or long fan-out gaps.
- `age_before` — how old the cached `IR(0,60)` was at the start of this tick. If this stays
  comfortably under `--ir0-max-age` most ticks, the threshold is well-calibrated.
- `IR(1)` — a raw register from the `IR(0,60)` block read straight from cache. Watch it change
  across `SKIP` ticks to confirm the fan-out is delivering live (not stale) data.

### What the summary line looks like

```text
=== summary: 283 ticks | skipped=281 (99%) solicited=2 | partials=8 failures=2 | worst age_before=29.6s ===
```

A skip rate above ~95% and a `worst age_before` close to `--ir0-max-age` (not far above it)
confirms the fan-out is a reliable source for this device class at this threshold.
