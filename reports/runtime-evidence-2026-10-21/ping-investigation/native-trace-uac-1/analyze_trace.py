"""Stream tracerpt XML; retain controller-lifetime scheduler evidence only."""
import collections
import json
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).parent
PID = 56972
NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
EVENT = re.compile(rb'<Event xmlns=.*?</Event>', re.S)
THREAD_GUID = b"{3d6fa8d1-fe05-11d0-9dda-00c04fd7ba7c}"
PROCESS_GUID = b"{3d6fa8d0-fe05-11d0-9dda-00c04fd7ba7c}"
STACK_GUID = b"{def2fe46-7bd6-4b80-bd94-f57fe20d0ce3}"
TIME = re.compile(rb'TimeCreated SystemTime="([^"]+)"')
DATA = re.compile(rb'<Data Name="([^"]+)"[^>]*>(.*?)</Data>', re.S)


def blocks():
    carry = b""
    with (OUT / "decoded.xml").open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            carry += chunk
            end = 0
            for match in EVENT.finditer(carry):
                yield match.group()
                end = match.end()
            carry = carry[end:]


def data(block):
    return {k.decode(): v.decode().strip() for k, v in DATA.findall(block)}


def integer(value):
    return int(value, 16) if value.startswith("0x") else int(value)


def clock(block):
    text = TIME.search(block).group(1).decode()
    # tracerpt renders a suspicious +08:59 offset. Use local time differences
    # only; do not convert this field to UTC or pretend it is broker QPC.
    hours, minutes, seconds = text[11:].split(":", 2)
    whole, fraction = seconds.split(".", 1)
    nanos = int(re.split(r"[+-]", fraction)[0].ljust(9, "0"))
    return (int(hours) * 3600 + int(minutes) * 60 + int(whole)) * 10**9 + nanos


threads = set()
names = {}
process_events = []
thread_events = []
header = None
for block in blocks():
    if header is None and b'Name="EventsLost"' in block:
        header = data(block)
    if (THREAD_GUID in block or PROCESS_GUID in block) and b'Name="ProcessId"' in block:
        values = data(block)
        if integer(values["ProcessId"]) != PID:
            continue
        root = ET.fromstring(block)
        opcode = root.findtext("e:System/e:Opcode", namespaces=NS)
        when = TIME.search(block).group(1).decode()
        if PROCESS_GUID in block:
            process_events.append({"time": when, "opcode": opcode, "data": values})
        else:
            tid = integer(values.get("TThreadId", values.get("ThreadId", "0")))
            threads.add(tid)
            thread_events.append({"time": when, "opcode": opcode, "tid": tid})
            if "ThreadName" in values:
                names[tid] = values["ThreadName"]
print("Mapped controller threads", len(threads), flush=True)

counts = collections.Counter()
off = {}
ready = {}
samples = collections.defaultdict(list)
ready_delays = collections.defaultdict(list)
stack_count = collections.Counter()
unknown_states = collections.Counter()
with (OUT / "controller-scheduler.jsonl").open("w") as retained:
    for block in blocks():
        if THREAD_GUID in block and b"<BinaryEventData>" in block:
            if b"<Opcode>36</Opcode>" not in block or b"<Version>5</Version>" not in block:
                continue
            payload = bytes.fromhex(re.search(rb'<BinaryEventData>(.*?)</BinaryEventData>', block).group(1).decode())
            if len(payload) < 24:
                counts["short_v5_prefix"] += 1
                continue
            new, old = struct.unpack_from("<II", payload)
            counts["all_v5_switches"] += 1
            if new not in threads and old not in threads:
                continue
            now = clock(block)
            state, reason = payload[14], payload[12]
            if state > 9:
                unknown_states[state] += 1
            if old in threads:
                off[old] = (now, state, reason)
            if new in threads:
                if new in off:
                    then, previous_state, previous_reason = off.pop(new)
                    if now >= then:
                        samples[new].append((now - then, previous_state, previous_reason))
                if new in ready:
                    then = ready.pop(new)
                    if now >= then:
                        ready_delays[new].append(now - then)
            retained.write(json.dumps({"kind": "switch", "local_day_ns": now,
                           "new_tid": new, "old_tid": old,
                           "old_state": state, "old_wait_reason": reason}) + "\n")
            counts["controller_switches"] += 1
        elif THREAD_GUID in block and b"<Opcode>ReadyThread</Opcode>" in block:
            values = data(block)
            tid = integer(values["TThreadId"])
            counts["all_ready"] += 1
            if tid in threads:
                now = clock(block)
                ready.setdefault(tid, now)
                retained.write(json.dumps({"kind": "ready", "local_day_ns": now, "tid": tid}) + "\n")
                counts["controller_ready"] += 1
        elif STACK_GUID in block and f'0x{PID:X}'.encode() in block:
            values = data(block)
            if integer(values.get("StackProcess", "0")) == PID:
                tid = integer(values["StackThread"])
                stack_count[tid] += 1
                retained.write(json.dumps({"kind": "stack", "data": values}) + "\n")

summary = {"scope": "Interrupted Setup, old controller only; no MCU timeout observed. Relative scheduler evidence, not failure causality.",
           "decoder": "Microsoft/perfview KernelTraceEventParser.CSwitchTraceData fixed24-byte prefix, version>2 accepts>=24; unknown trailing bytes ignored.",
           "decoder_source": "https://github.com/microsoft/perfview/blob/main/src/TraceEvent/Parsers/KernelTraceEventParser.cs",
           "time_limit": "tracerpt TimeCreated +08:59 is suspicious; only same-rendered-clock relative intervals used, no direct UTC/QPC span attribution.",
           "header": header, "old_controller_pid": PID, "process_events": process_events,
           "thread_events": thread_events, "names": names, "counts": counts,
           "unknown_old_states": unknown_states,
           "threads": {tid: {"name": names.get(tid), "switch_in_intervals": len(samples[tid]),
                       "max_off_cpu_ms": max((v[0] / 1e6 for v in samples[tid]), default=None),
                       "ready_to_switch_samples": len(ready_delays[tid]),
                       "max_ready_to_switch_ms": max((v / 1e6 for v in ready_delays[tid]), default=None),
                       "stack_events": stack_count[tid]} for tid in sorted(threads)},
           "serial_tid_identified": False,
           "limits": ["No serial owner native TID independently established.",
                      "No symbolized wait stacks or GIL/driver/firmware attribution.",
                      "Off-CPU spans include blocked time; ready-to-switch intervals characterize scheduling only.",
                      "Readiness/switch sample matching is illustrative; no latency acceptance conclusion."]}
(OUT / "scheduler-summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps({"threads": len(threads), "counts": counts, "unknown_states": unknown_states}), flush=True)
