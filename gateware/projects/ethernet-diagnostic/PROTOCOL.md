# Image protocol over Ethernet and USB UART

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

Legacy requests/replies are 540 bytes. Bulk-read, TRACE, and INFO requests can use the
compact 28-byte header-plus-CRC form; bulk reads also accept the original
540-byte padded form. Successful
two-sector bulk-read replies are 1052 bytes (1024 data bytes at offset 24,
followed by CRC32); one-sector and error replies remain 540 bytes:

| Bytes | Meaning |
| --- | --- |
| 0–3 | `RBS1` request / `RBA1` reply |
| 4 | Opcode |
| 5 | Request zero / reply status |
| 6–7 | Reserved zero |
| 8–11 | Nonzero session ID, little endian; zero for TRACE and INFO |
| 12–15 | Sequence ID, little endian |
| 16–19 | LBA, little endian |
| 20–23 | Count, little endian |
| 24–535 | 512-byte payload, zero-filled when unused |
| 536–539 | IEEE CRC32 of bytes 0–535, little endian |

Opcodes: 1 BEGIN (sequence zero, count is upload sectors), 2 WRITE, 3 READ,
4 ARM, 5 DISARM, 6 STATUS, 7 BULK_READ, 8 TRACE, 9 INFO. Legacy READ/WRITE count must be one. After BEGIN, sequences
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
Journal request recovery completes one ordered operation. A new `--upload`
starts at sector zero; `--resume-upload` requires the identical image digest
and sector count, resolves an identical pending write, reconciles the FPGA's
session and sequence through INFO, and continues from its written prefix.
The full image is read back and compared before the host permits ARM.

## Passive SD trace

Opcode 8 (`TRACE`) reads one 32-bit word of passive SD activity. It uses a
compact request with session and sequence zero; LBA selects word 0 through 63.
The reply uses the ordinary 540-byte size, places the selected little-endian
word at payload bytes 24 through 27, and zero-fills the rest. `images.py
--trace` validates word 0's `SDT1` magic and returns named JSON fields:

| Word | Contents |
| ---: | --- |
| 0 | `SDT1` magic |
| 1 | live ARM, DDR, clock, command, write, and read flags |
| 2–5 | clock edges, command frames, valid commands, invalid frames |
| 6–7 | last command and raw argument |
| 8–10 | backend read count, last physical LBA, committed write count |
| 11–13 | response starts, four recent commands, completed responses |
| 14 | frontend protocol and output-enable snapshot |
| 15 | independently decoded CMD IOBUF response length/header/CRC and mismatch |
| 16 | DAT IOBUF sampled-edge count, completed burst count, lane mask, activity, and mismatch |
| 17 | DAT mismatch count and first mismatching sampled-edge index |
| 18 | older four entries of the eight-command history |
| 19..26 | raw arguments paired with the eight-command history, oldest first |
| 27..30 | four completed CMD18/CMD12 summaries: 20-bit start LBA and 12-bit block count, oldest first |
| 31 | CMD response mismatch directions and first mismatching bit |
| 32 | `STC2` enhanced-trace marker |
| 33..36 | MMC CMD6/CMD13 counts, argument, response status, observed `SWITCH_ERROR`, the latched H700 DAT launch phase, and the compiled CMD launch phase |
| 37..42 | independently sampled 136-bit CMD9 R2 response and capture state |
| 43..47 | independently decoded block state, the sector that armed it, CRC16, clock period, and edge span |
| 48..55 | first 32 payload bytes observed on raw DAT0 |
| 56..63 | fabric timestamps and external-edge indexes for CMD18, R1 end, data start/end, CMD12, and DAT release |

The original pin observers compare IOBUF readback with the final serializer
registers. The enhanced CMD9 and first-block decoders instead find framing and
calculate CRC directly from raw pin samples without using serializer indexes.
Both still observe the FPGA side of the Arty JD series resistors and cannot
establish the waveform or setup/hold margin at the host socket.

TRACE is admitted before DDR initialization and outside the ordered session. It
does not advance a sequence, update the retry cache, issue a memory operation,
change ARM state, or recover an outstanding journaled request.


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


## USB UART fallback

The combined gateware always includes a 1,000,000 baud 8N1 UART packet adapter.
Its divisor is derived from the selected fabric clock, including 64 MHz H700.
UDP and UART share one block service, session, retry cache and ARM register.
A complete request gets exclusive service until its reply is buffered; its
reply returns only to the originating transport. The serial reply then drains
independently, so it cannot hold the service while Ethernet is ready.

Serial carries the exact RBS1/RBA1 bytes between `0x7e` delimiters. A data byte
`0x7e` or `0x7d` is encoded as `0x7d` followed by that byte XOR `0x20`. CRC32
remains over the unescaped application bytes. There is one outstanding UART
request. Malformed escapes, oversize frames, and frames arriving while the
UART slot is occupied are discarded; a delimiter restores framing. Retries
send identical application bytes. A retry may use either transport, preserving
the shared application sequence and CRC.

UART TX drives the registered shift bit directly; ready-counter decoding is
kept off the physical line. USB begins with the DDR BIOS console at 115200 baud.
The first reply whose status is not BAD_FORMAT
selects binary UART TX until FPGA reset. A rejected format/CRC request selects
binary TX temporarily through its error frame's final stop bit, then releases
the BIOS console. BIOS output cannot corrupt binary replies. Opening the host port leaves
DTR and RTS inactive. The UART and shared service use the fabric reset and
clock, independently of Ethernet startup and PHY RX/TX clocks.

`images.py --ftdi-serial <arty-ftdi-serial>` selects the exact FT2232H board's
interface B directly through libftdi 1.5 or newer 1.x. Interface A remains
available for JTAG. The adapter holds DTR/RTS inactive, restores the previous
latency setting and requests kernel-driver reattachment on close. It does not
write EEPROM configuration. `--serial-port <arty-uart>` instead uses pySerial
and the host TTY driver. These are two host backends for the same physical
UART and packet protocol; do not open them concurrently.

`SD_EMULATOR_FTDI_SERIAL` and `SD_EMULATOR_SERIAL_PORT` select these backends
for clients that import Images, including linux-consoles. An explicit selector
overrides the environment; two explicit selectors are rejected. If both
environment variables are set, direct FTDI takes precedence. With neither,
UDP remains the default. CLI JSON and journal transport metadata identify the
actual backend and selection source; host/source addresses apply only to UDP.
Keep the same `--state` and logical `--host` identity
when switching transports. Serial bulk reads use one token at a time; UDP
retains its existing window. The padded v1 packet format is intentionally slow:
each ordered write exchanges two 540-byte packets before framing overhead.

## Recovery snapshot

Opcode 9 (`INFO`) accepts a compact 28-byte request, conventionally with
session, sequence, LBA and count zero. The 540-byte reply contains these
little-endian 32-bit words at payload offset 24, followed by zero padding:

| Word | Meaning |
| --- | --- |
| 0 | `RBI1` magic |
| 1 | Physical capacity in sectors |
| 2 | Current session |
| 3 | Next ordered sequence |
| 4 | Successfully written prefix, in sectors |
| 5 | Declared image length, in sectors |
| 6 | Flags: bit 0 armed, 1 initialized, 2 quiescent, 3 retry cache valid |
| 7 | Last cached ordered sequence |
| 8 | Last cached request CRC32 |

The snapshot is captured atomically at dispatch. INFO is available before DDR
initialization and while armed. It never recovers a host's pending request,
updates the cache, issues a DDR transaction, or changes ARM. With no saved
session, host `--disarm` refuses to adopt another client's session. Explicit
`--recover-session --disarm` can recover its session and sequence through INFO
after the caller acquires exclusive device and emulator ownership. Only one
mutating client may operate the bench at a time; packet
arbitration is not a lease between independent host applications.

TRACE and INFO are both unsequenced diagnostics: neither advances the ordered
session sequence or replaces its cached reply.
