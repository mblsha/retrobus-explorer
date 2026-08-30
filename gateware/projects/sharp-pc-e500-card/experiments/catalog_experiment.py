#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from experiment_catalog import EXPERIMENTS


def emit_json(payload: object) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


def usage() -> str:
    return (
        "usage:\n"
        "  catalog_experiment.py list\n"
        "  catalog_experiment.py plan [count] --experiment EXPERIMENT [--no-ft-capture] [--arm-ft-stream]\n"
        "  catalog_experiment.py parse RESULT.json [count] --experiment EXPERIMENT\n"
    )


def parse_cli(args: list[str]) -> tuple[str | None, bool, bool, list[str]]:
    experiment: str | None = None
    no_ft_capture = False
    arm_ft_stream = False
    values: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == '--experiment':
            if index + 1 >= len(args):
                raise SystemExit('--experiment requires a value')
            experiment = args[index + 1]
            index += 2
            continue
        if arg.startswith('--experiment='):
            experiment = arg.split('=', 1)[1]
            index += 1
            continue
        if arg == '--no-ft-capture':
            no_ft_capture = True
            index += 1
            continue
        if arg == '--arm-ft-stream':
            arm_ft_stream = True
            index += 1
            continue
        values.append(arg)
        index += 1
    return experiment, no_ft_capture, arm_ft_stream, values


def require_experiment(experiment: str | None):
    if not experiment:
        raise SystemExit('--experiment is required')
    try:
        return EXPERIMENTS[experiment]
    except KeyError as exc:
        available = ', '.join(sorted(EXPERIMENTS))
        raise SystemExit(f'unknown experiment {experiment!r}; available: {available}') from exc


def parse_count(text: str, *, default: int) -> int:
    value = default if text == '' else int(text, 0)
    if not 1 <= value <= 256:
        raise SystemExit('count must be between 1 and 256')
    return value


def build_plan(spec, count: int, *, no_ft_capture: bool, arm_ft_stream: bool) -> dict[str, object]:
    if no_ft_capture and not spec.supports_ft_capture_flag:
        raise SystemExit(f'{spec.name} does not support --no-ft-capture')
    if arm_ft_stream and not spec.supports_arm_ft_stream:
        raise SystemExit(f'{spec.name} does not support --arm-ft-stream')

    kwargs = {}
    if spec.supports_arm_ft_stream:
        kwargs['arm_ft_stream'] = arm_ft_stream
    asm_text = spec.build_asm(count, **kwargs)

    plan = {
        'name': spec.name,
        'asm_text': asm_text,
        'fill_experiment_region': spec.fill_experiment_region,
        'timing': spec.timing,
        'control_timing': spec.control_timing,
        'timeout_s': spec.timeout_s,
        'start_tag': spec.start_tag,
        'stop_tag': spec.stop_tag,
        'flags': spec.flags,
        'args': list(spec.args),
    }
    if spec.supports_ft_capture_flag:
        plan['ft_capture'] = not no_ft_capture
    if spec.ft_max_retained_words is not None:
        plan['ft_max_retained_words'] = spec.ft_max_retained_words
    if spec.supports_arm_ft_stream:
        plan['arm_ft_stream'] = arm_ft_stream
    return plan


def parse_result(spec, raw_result_path: Path, count: int) -> dict[str, object]:
    raw = json.loads(raw_result_path.read_text())
    measurements = raw.get('measurement', [])
    first = measurements[0] if measurements else None
    ticks_per_step = None
    if first is not None and count:
        ticks_per_step = first['ticks'] / count
    payload = {
        'count': count,
        'measurement_count': len(measurements),
        'first_measurement': first,
        'ticks_per_step': ticks_per_step,
        'uart_lines': raw.get('uart_lines', []),
    }
    if spec.include_ft_capture_in_parse:
        payload['ft_capture'] = raw.get('ft_capture')
    return payload


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit(usage())
    command = argv[1]
    if command == 'list':
        print("\n".join(sorted(EXPERIMENTS)))
        return 0

    experiment, no_ft_capture, arm_ft_stream, values = parse_cli(argv[2:])
    spec = require_experiment(experiment)

    if command == 'plan':
        if len(values) > 1:
            raise SystemExit(usage())
        count = parse_count(values[0] if values else '', default=spec.default_count)
        return emit_json(build_plan(spec, count, no_ft_capture=no_ft_capture, arm_ft_stream=arm_ft_stream))

    if command == 'parse':
        if not values:
            raise SystemExit(usage())
        raw_result_path = Path(values[0])
        count = parse_count(values[1] if len(values) > 1 else '', default=spec.default_count)
        return emit_json(parse_result(spec, raw_result_path, count))

    raise SystemExit(usage())


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
