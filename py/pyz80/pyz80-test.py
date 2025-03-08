import marimo

__generated_with = "0.11.17"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _():
    import pyz80
    return (pyz80,)


@app.cell
def _(pyz80):
    io_ports = [0] * 256  # 256 IO ports
        # unsigned char rom[256] = {
        #     0x01, 0x34, 0x12, // LD BC, $1234
        #     0x3E, 0x01,       // LD A, $01
        #     0xED, 0x79,       // OUT (C), A
        #     0xED, 0x78,       // IN A, (C)
        #     0xc3, 0x09, 0x00, // JMP $0009
        # };
    memory = b'\x01\x34\x12\x3E\x01\xED\x79\xED\x78\xC3\x09\x00'

    def read_byte(addr):
        return memory[addr]

    def write_byte(addr, value):
        memory[addr] = value

    def in_port(port):
        return io_ports[port]

    def out_port(port, value):
        print(f"OUT: port {port} <- {value}")
        io_ports[port] = value

    def debug_message(msg):
        print("DEBUG:", msg)

    def consume_clock(clocks):
        print(f"Consumed {clocks} cycles")

    z80 = pyz80.Z80(read_byte, write_byte, in_port, out_port, returnPortAs16Bits=False)

    z80.set_debug_message(debug_message)
    z80.set_consume_clock_callback(consume_clock)

    cycles_executed = z80.execute(1)
    # print(z80.reg())
    print("Cycles executed:", cycles_executed)

    z80.generate_irq(0xFF)
    z80.generate_nmi(0x1234)
    return (
        consume_clock,
        cycles_executed,
        debug_message,
        in_port,
        io_ports,
        memory,
        out_port,
        read_byte,
        write_byte,
        z80,
    )


@app.cell
def _(z80):
    z80.reg.PC
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
