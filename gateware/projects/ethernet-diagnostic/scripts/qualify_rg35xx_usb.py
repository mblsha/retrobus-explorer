#!/usr/bin/env python3
"""Qualify USB image transfer and RG35XX boot under the exact lab lease.

Requires the linux-consoles checkout for its existing supply and trial tools.
Each phase ends with the FPGA disarmed and exact PSU2 read back OFF.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

def main():
    if not __debug__:
        raise SystemExit("Qualification requires Python without -O so every evidence gate runs")
    parser = argparse.ArgumentParser()
    parser.add_argument('--gateware', type=Path, required=True)
    parser.add_argument('--consoles', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--port', required=True)
    parser.add_argument('--ftdi-serial', required=True)
    parser.add_argument('--uart-backend', choices=['ftdi', 'tty'], default='ftdi')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--phase', choices=['smoke', 'full', 'boot'], required=True)
    parser.add_argument('--resume', action='store_true', help='Resume an interrupted full-image transfer')
    args = parser.parse_args()
    if args.resume and args.phase != 'full':
        parser.error('--resume requires --phase full')
    if os.environ.get('ZAURUS_LAB_DEVICE') != 'anbernic-rg35xx-plus' or not os.environ.get('ZAURUS_LAB_LEASE_TOKEN'):
        raise SystemExit('The exact RG35XX device lease is required')
    if args.uart_backend == 'ftdi':
        os.environ['SD_EMULATOR_FTDI_SERIAL'] = args.ftdi_serial
        os.environ.pop('SD_EMULATOR_SERIAL_PORT', None)
    else:
        os.environ['SD_EMULATOR_SERIAL_PORT'] = args.port
        os.environ.pop('SD_EMULATOR_FTDI_SERIAL', None)
    os.environ['SD_EMULATOR_CLIENT_DIR'] = str(args.gateware / 'projects/ethernet-diagnostic/scripts')
    sys.path.insert(0, str(args.consoles))
    sys.path.insert(0, str(args.consoles / 'devices/rg35xx-plus'))
    from bench import card
    from bench.supply import bench_supply, psu_status, supply_is_online, output_is_off, power_off_confirmed
    from rg35xx.image import verify_boot_image
    from rg35xx.debug_partition import decode_records, DEBUG_SECTORS, JOB_LBA, read_reported_at
    images = card.load_client()
    args.output.mkdir(parents=True, exist_ok=True)
    state = args.output / ('smoke-session.json' if args.phase == 'smoke' else 'image-session.json')
    report = dict(phase=args.phase, uart_backend=args.uart_backend, started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), passed=False)
    client = None
    validated = False
    supply = bench_supply(None, 'psu2', switching=True)

    def save():
        (args.output / (args.phase + '-report.json')).write_text(json.dumps(report, indent=2) + '\n')

    def program(log_name):
        with (args.output / log_name).open('w') as stream:
            subprocess.run(['openFPGALoader', '-b', card.BOARD,
                            '--ftdi-serial', args.ftdi_serial, '-m',
                            str(args.build / 'design.bit')], check=True,
                           stdout=stream, stderr=subprocess.STDOUT)

    def progress(message):
        print(time.strftime('%H:%M:%S', time.gmtime()), message, flush=True)

    def open_client():
        return images.Images(state=state, progress=progress)

    try:
        manifest = json.loads((args.build / 'result.json').read_text())
        digest = hashlib.sha256((args.build / 'design.bit').read_bytes()).hexdigest()
        assert digest == manifest['bitstream_sha256']
        assert manifest['serial_image_service'] and manifest['serial_baud'] == 1_000_000
        assert manifest['profile'] == 'h700-rg35xx' and manifest['h700_mmc']
        assert manifest['sd_io_clock_hz'] == 64_000_000 and manifest['sys_clk_freq'] == 80_000_000
        assert manifest['verified_configuration_bits'] > 0
        assert manifest['clocks_mhz']['fclk'][2] == 64
        assert manifest['clocks_mhz']['dclk'][2] == 80
        assert all(clock[1] == 'PASS' for clock in manifest['clocks_mhz'].values())
        validated = True
        report['image'] = verify_boot_image(args.image)
        assert report['image']['card_max_hz'] == 6000000
        assert report['image']['debug_command'] == 'job-runner'
        debug_start = report['image']['partitions'][1]['start_lba']
        report['bitstream_sha256'] = digest
        report['build'] = manifest
        status = psu_status(supply, 'psu2')
        report['psu_before'] = status
        assert supply_is_online(status) and output_is_off(status), status
        if args.phase == 'smoke':
            # Capture the FPGA BIOS before reconfiguration and keep it as evidence.
            import serial
            uart = serial.Serial(port=None, baudrate=115200, timeout=0.2, exclusive=True)
            uart.dtr = uart.rts = False
            uart.port = args.port
            uart.open()
            stop = threading.Event()
            def capture():
                with (args.output / 'program-bios.bin').open('wb') as output:
                    while not stop.is_set():
                        data = uart.read(max(1, uart.in_waiting))
                        if data:
                            output.write(data)
                            output.flush()
            reader = threading.Thread(target=capture)
            reader.start()
            try:
                program('program.log')
                time.sleep(card.PROGRAM_SETTLE_SECONDS)
            finally:
                stop.set()
                reader.join(timeout=2)
                uart.close()
            card.clear_session(state)
            client = open_client()
            deadline = time.monotonic() + 90
            while True:
                initial = client.info()
                if initial['initialized']:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Candidate DDR did not initialize')
                time.sleep(0.5)
            report['initial_info'] = initial
            assert not initial['armed'] and initial['quiescent']
            payload = bytes((index * 31 + (index >> 8) * 7) & 255 for index in range(256 * 512))
            client.begin(256)
            client.initial_upload['sha256'] = hashlib.sha256(payload).hexdigest()
            client.save()
            for lba in range(8):
                client.command(images.Opcode.WRITE, lba, 1, payload[lba * 512:(lba + 1) * 512])
            receive = client.socket.recv
            def lose_ack(size):
                receive(size)
                raise socket.timeout()
            client.socket.recv = lose_ack
            try:
                client.command(images.Opcode.WRITE, 8, 1, payload[8 * 512:9 * 512])
            except TimeoutError:
                assert client.pending is not None
            else:
                raise AssertionError('Lost acknowledgement was not injected')
            report['pending_request'] = images.pending_summary(client.pending)
            client.close()
            client = open_client()
            report['interrupted_info'] = client.info()
            assert report['interrupted_info']['written_sectors'] == 9
            started = time.monotonic()
            client.upload(payload, window=10, resume=True)
            report['smoke_transfer_seconds'] = time.monotonic() - started
            report['transfer_retries'] = client.retries
            report['smoke_bytes'] = len(payload)
            report['smoke_sha256'] = hashlib.sha256(payload).hexdigest()
            report['smoke_verified'] = client.initial_upload['verified']
            assert client.bulk_download(1, start=524287, window=1) == bytes(512)
            report['last_physical_sector_zero'] = True
            report['final_info'] = client.info()
            assert report['final_info']['written_sectors'] == 256
            assert not report['final_info']['armed']
        elif args.phase == 'full':
            client = open_client()
            payload = args.image.read_bytes()
            started = time.monotonic()
            client.upload(payload, window=10, resume=args.resume)
            report['transfer_seconds'] = time.monotonic() - started
            report['transfer_retries'] = client.retries
            report['verified_sha256'] = client.initial_upload['sha256']
            assert client.initial_upload['verified']
            report['final_info'] = client.info()
        else:
            report['trials'] = []
            for number in range(1, 4):
                client = open_client()
                client.command(images.Opcode.ARM)
                client.close()
                client = None
                trial_path = args.output / f'trial-{number}.json'
                with (args.output / f'trial-{number}.log').open('w') as output:
                    subprocess.run([sys.executable, str(args.consoles / 'devices/rg35xx-plus/rg35xx.py'),
                                    'trial', '--state', str(state), '--image', str(args.image),
                                    '--observe', '45', '--interval', '0.1', '--settle', '8',
                                    '--output', str(trial_path)], cwd=args.consoles,
                                   check=True, stdout=output, stderr=subprocess.STDOUT)
                from rg35xx.report import userspace_time
                trial = json.loads(trial_path.read_text())
                reached = userspace_time(trial)
                print(f'Trial {number}: userspace milestone {reached}', flush=True)
                assert reached is not None, 'No userspace milestone'
                job_polling = any(row['elapsed'] >= reached and
                                  row['read_lba'] in read_reported_at(JOB_LBA)
                                  for row in trial['timeline'])
                assert job_polling, 'No new job-runner command polling observed'
                client = open_client()
                debug = client.bulk_download(DEBUG_SECTORS, start=debug_start, window=1)
                (args.output / f'debug-{number}.bin').write_bytes(debug)
                records = decode_records(debug)
                assert any(record.get('detail') == 'rootfs-init-entered' for record in records)
                assert any(record.get('detail', '').startswith('job-runner-ready') for record in records)
                (args.output / f'debug-{number}.json').write_text(json.dumps(records, indent=2) + '\n')
                report['trials'].append(dict(number=number, userspace_seconds=reached,
                                            job_runner_polling=job_polling,
                                            records=records, final_trace=trial['final_trace']))
                client.close()
                client = None
                save()
        report['passed'] = True
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        try:
            if client is None:
                client = open_client()
            report['cleanup_before'] = client.info()
            client.disarm()
            report['cleanup_after'] = client.info()
            assert not report['cleanup_after']['armed']
        except BaseException as error:
            report['cleanup_error'] = repr(error)
            report['passed'] = False
            # Reconfiguration resets ARM even if the serial path itself failed.
            # Its log and last successfully captured status remain in the report.
            if validated:
                program('cleanup-reconfigure.log')
                report['cleanup_reconfigured'] = True
        finally:
            if client is not None:
                client.close()
            report['psu_off_confirmed'] = power_off_confirmed(supply, 'psu2')
            report['psu_after'] = psu_status(supply, 'psu2')
            report['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            save()
            assert report['psu_off_confirmed'], 'PSU2 output was not proven off'
            if 'cleanup_error' in report:
                raise RuntimeError('Serial cleanup failed; see the saved report')


if __name__ == '__main__':
    main()
