#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pc_e500_ft600 import (
    annotate_event_stream,
    compact_event_stream,
    decode_word_stream,
    find_measurement_window,
    infer_execution_window,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decode FT600 sampled-bus words from an experiment JSON")
    parser.add_argument("input", type=Path, help="path to experiment JSON produced by expctl/expd")
    parser.add_argument("--compact", action="store_true", help="drop synthetic followups and identical adjacent events")
    parser.add_argument("--limit", type=int, default=0, help="maximum number of events to print (0 = all)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a text table")
    parser.add_argument("--markdown", action="store_true", help="emit a Markdown table")
    parser.add_argument(
        "--window",
        choices=["all", "execution", "measurement"],
        default="all",
        help="select a derived event window before formatting",
    )
    return parser


def load_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def load_words(payload: dict[str, object]) -> list[int]:
    return list(payload.get("ft_capture", {}).get("words", []))


def format_status(event) -> str:
    flags: list[str] = []
    if event.rw:
        flags.append("rw")
    if event.ce1_active:
        flags.append("ce1")
    if event.ce6_active:
        flags.append("ce6")
    if event.synthetic_followup:
        flags.append("syn")
    if event.from_cycle_start:
        flags.append("cycle")
    if event.ctrl_range:
        flags.append("ctrl")
    return "|".join(flags) if flags else "-"


def format_region(annotated) -> str:
    bits = [annotated.region]
    if annotated.addr_label:
        bits.append(annotated.addr_label)
    return " / ".join(bits)


def render_json(annotated_events) -> int:
    payload = [
        {
            "index": annotated.event.index,
            "addr": annotated.event.addr,
            "data": annotated.event.data,
            "status": annotated.event.status,
            "kind": annotated.event.kind,
            "raw_word": annotated.event.raw_word,
            "raw_hex": f"{annotated.event.raw_word:08X}",
            "rw": annotated.event.rw,
            "ce1_active": annotated.event.ce1_active,
            "ce6_active": annotated.event.ce6_active,
            "synthetic_followup": annotated.event.synthetic_followup,
            "from_cycle_start": annotated.event.from_cycle_start,
            "ctrl_range": annotated.event.ctrl_range,
            "region": annotated.region,
            "addr_label": annotated.addr_label,
            "note": annotated.note,
        }
        for annotated in annotated_events
    ]
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def render_markdown(annotated_events) -> int:
    print("| Idx | Addr | Data | Kind | Status | Region | Raw |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for annotated in annotated_events:
        event = annotated.event
        print(
            f"| {event.index} | `0x{event.addr:05X}` | `0x{event.data:02X}` | "
            f"`{event.kind}` | `{format_status(event)}` | `{format_region(annotated)}` | `{event.raw_word:08X}` |"
        )
    return 0


def render_text(annotated_events) -> int:
    print("idx  addr   data  kind                status        region                       raw")
    print("---  -----  ----  ------------------  ------------  ---------------------------  --------")
    for annotated in annotated_events:
        event = annotated.event
        print(
            f"{event.index:>3}  "
            f"{event.addr:05X}  "
            f"{event.data:02X}    "
            f"{event.kind:<18}  "
            f"{format_status(event):<12}  "
            f"{format_region(annotated):<27}  "
            f"{event.raw_word:08X}"
        )
    return 0


def main() -> int:
    args = build_parser().parse_args()
    payload = load_payload(args.input)
    words = load_words(payload)
    events = decode_word_stream(words)
    if args.window == "measurement":
        measurement = payload.get("measurement", [])
        first = measurement[0] if measurement else None
        if first is not None:
            window_events = find_measurement_window(
                events,
                start_tag=int(first["start_tag"]),
                stop_tag=int(first["stop_tag"]),
            )
            if window_events:
                events = window_events
    elif args.window == "execution":
        window_events = infer_execution_window(events)
        if window_events:
            events = window_events
    if args.compact:
        events = compact_event_stream(events)
    if args.limit > 0:
        events = events[: args.limit]
    annotated_events = annotate_event_stream(events)

    if args.json:
        return render_json(annotated_events)
    if args.markdown:
        return render_markdown(annotated_events)
    return render_text(annotated_events)


if __name__ == "__main__":
    raise SystemExit(main())
