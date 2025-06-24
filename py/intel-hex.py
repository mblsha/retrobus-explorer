

import marimo

__generated_with = "0.13.0"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _(mo):
    mo.md(
        r"""
        Python port of https://observablehq.com/@mblsha/intel-hex-parser using Lark. Uses Earley parser, so is very slow compared to the JS version.

        It's quite slow though, so for known contiguous blocks of bytes objcopy is much faster:

        * `objcopy -I ihex rom00.txt -O binary rom00.bin`
        """
    )
    return


@app.cell
def _():
    from enum import Enum
    from typing import NamedTuple, Optional

    import marimo as mo
    from lark import Lark, Token, Transformer, v_args
    return (
        Enum,
        Lark,
        list,
        NamedTuple,
        Optional,
        Token,
        Transformer,
        mo,
        v_args,
    )


@app.cell(hide_code=True)
def _(
    Enum,
    Lark,
    List,
    NamedTuple,
    Optional,
    Token,
    Transformer,
    bytes,
    v_args,
):
    class RecordType(Enum):
        DATA = 1
        EOF = 2
        EXTENDED_LINEAR_ADDRESS = 3
        START_LINEAR_ADDRESS = 4

    class IntelHexRecord(NamedTuple):
        record_type: RecordType
        addr: int
        size: int
        data: Optional[bytes] = None
        checksum: Optional[str] = None

    class Segment(NamedTuple):
        start_address: int
        data: bytes

    grammar = r"""
    start: record*

    record: ":" byte_count address record_data _NL?

    byte_count: hexpair
    address: HEXDIGIT HEXDIGIT HEXDIGIT HEXDIGIT

    record_data: data_record
               | eof_record
               | extended_linear_address_record
               | start_linear_address_record

    data_record: "00" hexpair_seq checksum
    eof_record: "01" /[Ff]{2}/
    extended_linear_address_record: "04" hexpair_seq checksum
    start_linear_address_record: "05" hexpair_seq checksum

    hexpair_seq: hexpair+
    hexpair: HEXDIGIT HEXDIGIT
    checksum: hexpair

    %import common.HEXDIGIT
    %import common.NEWLINE -> _NL

    %import common.WS
    %ignore WS
    """

    class IntermediateRecord(NamedTuple):
        record_type: RecordType
        raw_data: Optional[bytes] = None
        checksum: Optional[str] = None

    @v_args(inline=True)
    class IntelHexTransformer(Transformer):
        def byte_count(self, token: Token) -> int:
            return int(token, 16)

        def address(self, a: Token, b: Token, c: Token, d: Token) -> int:
            return int(a.value + b.value + c.value + d.value, 16)

        def hexpair(self, a: Token, b: Token) -> str:
            return a.value + b.value

        def hexpair_seq(self, *pairs: str) -> bytes:
            return bytes.fromhex(''.join(pairs))

        def checksum(self, pair: str) -> str:
            return pair

        def data_record(self, hex_seq: bytes, checksum: str) -> IntermediateRecord:
            return IntermediateRecord(
                record_type=RecordType.DATA,
                raw_data=hex_seq,
                checksum=checksum
            )

        def eof_record(self, type_token: Token) -> IntermediateRecord:
            return IntermediateRecord(record_type=RecordType.EOF)

        def extended_linear_address_record(self, type_token: Token, hex_seq: bytes, checksum: str) -> IntermediateRecord:
            return IntermediateRecord(
                record_type=RecordType.EXTENDED_LINEAR_ADDRESS,
                raw_data=hex_seq,
                checksum=checksum
            )

        def start_linear_address_record(self, type_token: Token, hex_seq: bytes, checksum: str) -> IntermediateRecord:
            return IntermediateRecord(
                record_type=RecordType.START_LINEAR_ADDRESS,
                raw_data=hex_seq,
                checksum=checksum
            )

        def record_data(self, data: IntermediateRecord) -> IntermediateRecord:
            return data

        def record(self, byte_count: int, address: int, rec_data: IntermediateRecord) -> IntelHexRecord:
            size: int = byte_count
            addr: int = address
            rtype: RecordType = rec_data.record_type
            if rtype in {RecordType.DATA, RecordType.EXTENDED_LINEAR_ADDRESS, RecordType.START_LINEAR_ADDRESS}:
                raw = rec_data.raw_data
                if raw is None or len(raw) != size:
                    raise ValueError(f"Byte count mismatch: expected {size}, got {len(raw) if raw is not None else 0}")
                data_field: bytes = raw
                cs: Optional[str] = rec_data.checksum
            else:  # EOF record
                data_field = None
                cs = None
            return IntelHexRecord(record_type=rtype, addr=addr, size=size, data=data_field, checksum=cs)

        def start(self, *records: IntelHexRecord) -> List[IntelHexRecord]:
            return list(records)


    parser = Lark(grammar, parser="earley")
    return IntelHexRecord, IntelHexTransformer, RecordType, Segment, parser


@app.cell(hide_code=True)
def _(IntelHexRecord, List, NamedTuple, Optional, RecordType, Segment):
    class ProcessedRecords(NamedTuple):
        segments: List[Segment]
        execution_start_address: Optional[int]

    def process_records(records: List[IntelHexRecord]) -> ProcessedRecords:
        """
        Processes a list of IntelHexRecord parsed from an Intel HEX file.
        It creates data segments using the extended linear address record (if provided)
        and then merges adjacent segments.
        """
        segments: List[Segment] = []
        extended_linear_address: int = 0
        execution_start_address: Optional[int] = None

        # First pass: Build individual segments.
        for record in records:
            if record.record_type == RecordType.EXTENDED_LINEAR_ADDRESS:
                # Convert the two-byte data field to an integer.
                extended_linear_address = int.from_bytes(record.data, byteorder='big')
            elif record.record_type == RecordType.START_LINEAR_ADDRESS:
                execution_start_address = int.from_bytes(record.data, byteorder='big')
            elif record.record_type == RecordType.DATA:
                full_address = (extended_linear_address << 16) + record.addr
                segments.append(Segment(start_address=full_address, data=record.data))
            elif record.record_type == RecordType.EOF:
                # End-of-file record; no action needed.
                pass
            else:
                raise ValueError(f"Unknown record type: {record.record_type}")

        # Second pass: Merge adjacent segments.
        segments.sort(key=lambda seg: seg.start_address)
        merged_segments: List[Segment] = []

        for seg in segments:
            if merged_segments and (merged_segments[-1].start_address + len(merged_segments[-1].data) == seg.start_address):
                # Merge contiguous segments.
                last_seg = merged_segments.pop()
                merged_data = last_seg.data + seg.data
                merged_seg = Segment(start_address=last_seg.start_address, data=merged_data)
                merged_segments.append(merged_seg)
            else:
                merged_segments.append(seg)

        return ProcessedRecords(segments=merged_segments, execution_start_address=execution_start_address)
    return (process_records,)


@app.cell
def _():
    text = """
    :10100000C3AD13000000000000000000000000005D
    :1010100021317FCB8E21187F181221317FCB962171
    """
    return (text,)


@app.cell
def _(IntelHexTransformer, parser, text):
    parsed = IntelHexTransformer().transform(parser.parse(text))
    return (parsed,)


@app.cell
def _(parsed, process_records):
    process_records(parsed)
    return


@app.function
def decode_sequential_bytes(lines):
    """
    Parse lines of "START_ADDR: BYTE1 BYTE2 …", verify sequential addresses
    across all bytes, and write the bytes to a binary file.

    :param lines: iterable of strings, each "ADDRESS: HEXBYTE [HEXBYTE …]"
    :param out_path: path to output binary file
    :raises ValueError: if addresses are not strictly sequential
    """
    prev_addr = None
    data_bytes = bytearray()

    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue

        try:
            addr_str, byte_list_str = line.split(':', 1)
        except ValueError as err:
            raise ValueError(f"Line {lineno}: malformed, expected 'ADDR: BYTE…'") from err

        addr = int(addr_str.strip(), 16)
        byte_strs = byte_list_str.strip().split()

        for offset, b in enumerate(byte_strs):
            this_addr = addr + offset
            byte_val = int(b, 16)
            if not 0 <= byte_val <= 0xFF:
                raise ValueError(f"Line {lineno}, byte #{offset+1}: {b!r} out of range")

            if prev_addr is None:
                # first_addr = this_addr
                pass
            else:
                if this_addr != prev_addr + 1:
                    raise ValueError(
                        f"Non-sequential address at line {lineno}, byte #{offset+1}: "
                        f"expected 0x{prev_addr+1:X}, got 0x{this_addr:X}"
                    )

            data_bytes.append(byte_val)
            prev_addr = this_addr

    if not data_bytes:
        raise ValueError("No data parsed!")

    return data_bytes


@app.cell
def _():
    with open('iq-7000-full-memory2.txt') as f:
        lines = f.readlines()
        bytes = decode_sequential_bytes(lines)
        print(bytes)
        # with open('iq-7000-full-memory2.bin', 'wb') as f:
        #     # pass
        #     f.write(bytes)
    return (bytes,)


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
