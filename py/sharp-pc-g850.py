import marimo

__generated_with = "0.10.19"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _():
    import sys
    sys.path.append("d3xx")

    import ftd3xx
    import _ftd3xx_linux as mft
    return ftd3xx, mft, sys


@app.cell
def _(ftd3xx, mft):
    import ctypes

    class Ft600Device():
        def __init__(self):
            self.channel = 0

            self.D3XX = ftd3xx.create(0, mft.FT_OPEN_BY_INDEX)
            if self.D3XX is None:
                raise ValueError("ERROR: Please check if another D3XX application is open! Disconnecting both the FPGA + Ft element and then reconnecting them should help.")

        def __enter__(self):
            return self

        def __exit__(self, type, value, traceback):
            self.D3XX.close()
            self.D3XX = 0

        def write(self, data: bytes):
            buf = ctypes.create_string_buffer(data)
            bytesWritten = self.D3XX.writePipe(self.channel, buf, len(data))
            return bytesWritten

        def read(self, datalen):
            bytesTransferred = mft.ULONG()
            data = ctypes.create_string_buffer(datalen)
            status = ftd3xx.call_ft(mft.FT_ReadPipeEx, self.D3XX.handle, mft.UCHAR(self.channel), data, mft.ULONG(datalen),
                                    ctypes.byref(bytesTransferred), 1)
            if bytesTransferred.value == 0:
                return None
            return data.raw[:bytesTransferred.value]
    return Ft600Device, ctypes


@app.cell
def _(Ft600Device):
    import datetime

    def Send(buffwrite):
        print(datetime.datetime.now())

        with Ft600Device() as d:
            # clear input buffer
            for i in range(100):
                bytes = d.read(1)

            data = []

            while len(data) < 1000:
                bytes = d.read(4)
                if bytes is None:
                    continue
                data.append(bytes)

            return data

            # print(d.write(b'--'))
            # print(d.write(b'++'))

    # DemoLoopback()
    data = Send(b"Helloworld!")
    data
    return Send, data, datetime


@app.cell
def _(data):
    from enum import Enum
    from dataclasses import dataclass
    import struct

    class Type(Enum):
        READ = "R"
        WRITE = "W"
        IO_READ = "r"
        IO_WRITE = "w"

    @dataclass
    class Event:
        type: Type
        val:  int # uint8
        addr: int # uint16
        # raw:  bytes

    def parse_data(data):
        r = []
        for i in data:
            # FIXME: why we're getting 0s if we're not sending them?
            if i[0] == 0:
                continue

            type = Type(chr(i[0]))
            val  = struct.unpack("B", i[1:2])[0]
            addr = struct.unpack("H", i[2:4])[0]
            if type in [Type.IO_READ, Type.IO_WRITE]:
                addr &= 0xFF

            r.append(Event(type, val, addr))
        return r

    parsed = parse_data(data)

    import pandas
    return Enum, Event, Type, dataclass, pandas, parse_data, parsed, struct


@app.cell
def _(pandas, parsed):
    pandas.DataFrame(parsed)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
