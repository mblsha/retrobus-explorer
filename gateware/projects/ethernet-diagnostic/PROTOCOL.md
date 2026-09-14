# Ethernet image protocol

## Network and packet format

The FPGA is `192.168.10.2`, MAC `02:00:00:00:00:01`, UDP port 4000. On the tested
Mac, the directly connected AX88179B is `en20`, `192.168.10.1`. ARP and ICMP echo
are implemented. IPv4 options, fragmentation, VLAN tagging, DHCP, routing, and
half-duplex collision handling are outside this first implementation.

RX accepts only complete frames with valid Ethernet FCS. The network engine
checks the IPv4 header checksum, destination, lengths, fragmentation flags,
protocol and UDP destination port; a nonzero UDP checksum is verified with its
pseudo-header. Transmitted IPv4 UDP packets use checksum zero, which is allowed
for IPv4. Every block request and reply has a mandatory application CRC32.

Legacy requests/replies are 540 bytes. Bulk-read requests can use the compact
28-byte header-plus-CRC form (or the original 540-byte padded form). Successful
two-sector bulk-read replies are 1052 bytes (1024 data bytes at offset 24,
followed by CRC32); one-sector and error replies remain 540 bytes:

| Bytes | Meaning |
| --- | --- |
| 0–3 | `RBS1` request / `RBA1` reply |
| 4 | Opcode |
| 5 | Request zero / reply status |
| 6–7 | Reserved zero |
| 8–11 | Nonzero session ID, little endian |
| 12–15 | Sequence ID, little endian |
| 16–19 | LBA, little endian |
| 20–23 | Count, little endian |
| 24–535 | 512-byte payload, zero-filled when unused |
| 536–539 | IEEE CRC32 of bytes 0–535, little endian |

Opcodes: 1 BEGIN (sequence zero, count is upload sectors), 2 WRITE, 3 READ,
4 ARM, 5 DISARM, 6 STATUS, 7 BULK_READ. Legacy READ/WRITE count must be one. After BEGIN, sequences
start at one. Legacy operations have one request outstanding at a time. The FPGA caches the last
ordered response, including read data, and replays it only when the session,
sequence, and request CRC match. A repeated key with different contents is
rejected. Old and out-of-order requests do not execute.

Statuses: 0 success, 1 format/CRC, 2 session, 3 sequence, 4 armed/not quiescent,
5 bounds/upload order, 6 DDR not initialized, 7 memory error, 8 incomplete image,
9 conflicting retry. Ordered operation refusals consume their sequence;
format, session, and sequence errors do not. STATUS currently acknowledges
service availability; it does not yet expose detailed BIST counters over UDP.

The host journal is executable recovery state. It is validated before network
I/O, and `images.py --inspect` displays its session, next sequence, pending
operation, and initial-upload verification marker without sending packets.
Journal request recovery completes one ordered operation; it does not resume a
partially uploaded image. A new `--upload` starts at sector zero.


## Windowed bulk reads

The newer gateware adds opcode 7 (`BULK_READ`) for one or two sectors, selected
by count. Compact requests put the CRC at bytes 24–27 and contain no unused sector payload.
It validates the current session, bounds, initialization, CRC and
exclusive DDR ownership, but uses sequence as an independent reply token. It
neither advances the legacy control sequence nor replaces its cached reply.
A retry reads the same address again; no memory write or control transition is
replayed. Bulk reads remain rejected while SD is armed or a prior SD operation
is draining. Use one client and keep the image disarmed and unchanged for the
whole transfer; this is not a snapshot protocol for concurrent writers.

The Python client keeps several tokens outstanding, accepts validated replies
in any order, ignores stale/duplicate/corrupt replies, and retries the exact
request after a timeout. Eight 2048-byte receive slots and two transmit slots permit
receive, processing and transmit work to overlap. Registered Gray pointers and
routed crossing-delay checks protect the asynchronous queues. A full queue drops
a complete incoming frame, which the host recovers through retry.

```sh
uv run python projects/ethernet-diagnostic/scripts/images.py \
  --state /private/tmp/arty-network-session.json \
  --download readback.bin --blocks 8192 --bulk --window 10
```

`--bulk` on upload accelerates its readback verification. Upload writes and
control operations keep their existing ordered, journaled protocol. Bulk reads
perform no per-request session-file writes; an interrupted read can simply be
restarted. Do not run another client or an ARM/BEGIN/WRITE operation concurrently.
The default without `--bulk` remains compatible with the earlier gateware.

For measurement, add `--bulk --window N` to `benchmark_reads.py`; compare several
window sizes with real data checks rather than assuming the largest is fastest.
