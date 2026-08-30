module main (
    input wire clk,
    input wire rst_n,
    output wire [7:0] led,
    input wire usb_rx,
    output wire usb_tx,

    input wire ft_clk,
    input wire ft_rxf,
    input wire ft_txe,
    inout wire [15:0] ft_data,
    inout wire [1:0] ft_be,
`ifdef COCOTB_SIM
    input wire [15:0] ft_data_host,
    input wire [1:0] ft_be_host,
    input wire ft_host_drive,
    output wire [15:0] ft_data_drive,
    output wire [1:0] ft_be_drive,
`endif
    output wire ft_rd,
    output wire ft_wr,
    output wire ft_oe,

    output wire [7:0] saleae,

    input wire z80_mreq,
    input wire z80_m1,
    input wire z80_ioreset,
    input wire z80_iorq,
    input wire z80_int1,
    input wire z80_wait,
    input wire z80_rd,
    input wire z80_wr,

    inout wire [7:0] data,
    input wire [15:0] addr,

    input wire [1:0] addr_bnk,
    input wire addr_ceram2,
    input wire addr_cerom2
`ifdef COCOTB_SIM
    ,
    output wire [7:0] data_drive_debug,
    output wire data_oe_debug,
    output wire [2:0] read_state_debug,
    output wire [2:0] streaming_state_debug,
    output wire [1:0] streaming_bank_debug,
    output wire [15:0] request_count_debug,
    output wire [15:0] streaming_size_debug,
    output wire [15:0] streaming_index_debug,
    output wire ft_bus_conflict
`endif
);
`ifndef COCOTB_SIM
    wire [15:0] ft_data_drive;
    wire [1:0] ft_be_drive;
    wire [2:0] read_state_debug;
    wire [2:0] streaming_state_debug;
    wire [1:0] streaming_bank_debug;
    wire [15:0] request_count_debug;
    wire [15:0] streaming_size_debug;
    wire [15:0] streaming_index_debug;
`endif
    wire [7:0] data_drive;
    wire data_oe;
    wire [15:0] ft_data_in;
    wire [1:0] ft_be_in;

`ifdef COCOTB_SIM
    assign ft_data_in = ft_host_drive ? ft_data_host : 16'h0000;
    assign ft_be_in = ft_host_drive ? ft_be_host : 2'b00;
    assign ft_bus_conflict = ft_host_drive && ft_oe;
    assign data_drive_debug = data_drive;
    assign data_oe_debug = data_oe;
    assign ft_data = ft_oe ? ft_data_drive : (ft_host_drive ? ft_data_host : 16'hzzzz);
    assign ft_be = ft_oe ? ft_be_drive : (ft_host_drive ? ft_be_host : 2'bzz);
`else
    assign ft_data_in = ft_data;
    assign ft_be_in = ft_be;
    assign ft_data = ft_oe ? ft_data_drive : 16'hzzzz;
    assign ft_be = ft_oe ? ft_be_drive : 2'bzz;
`endif
    assign data = data_oe ? data_drive : 8'hzz;

    main_core core (
        .clk(clk),
        .rst_n(rst_n),
        .led(led),
        .usb_rx(usb_rx),
        .usb_tx(usb_tx),
        .ft_clk(ft_clk),
        .ft_rxf(ft_rxf),
        .ft_txe(ft_txe),
        .ft_data(ft_data_in),
        .ft_be(ft_be_in),
        .ft_data_drive(ft_data_drive),
        .ft_be_drive(ft_be_drive),
        .ft_rd(ft_rd),
        .ft_wr(ft_wr),
        .ft_oe(ft_oe),
        .saleae(saleae),
        .z80_mreq(z80_mreq),
        .z80_m1(z80_m1),
        .z80_ioreset(z80_ioreset),
        .z80_iorq(z80_iorq),
        .z80_int1(z80_int1),
        .z80_wait(z80_wait),
        .z80_rd(z80_rd),
        .z80_wr(z80_wr),
        .data_drive(data_drive),
        .data_oe(data_oe),
        .addr(addr),
        .addr_bnk(addr_bnk),
        .addr_ceram2(addr_ceram2),
        .addr_cerom2(addr_cerom2),
        .read_state_debug(read_state_debug),
        .streaming_state_debug(streaming_state_debug),
        .streaming_bank_debug(streaming_bank_debug),
        .request_count_debug(request_count_debug),
        .streaming_size_debug(streaming_size_debug),
        .streaming_index_debug(streaming_index_debug)
    );
endmodule
