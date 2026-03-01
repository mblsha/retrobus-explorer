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
    output wire z80_wait,
    input wire z80_rd,
    input wire z80_wr,

    input wire [7:0] data,
    input wire [15:0] addr,

    input wire [1:0] addr_bnk,
    input wire addr_ceram2,
    input wire addr_cerom2
);
    wire [15:0] ft_data_in = ft_data;
    wire [1:0] ft_be_in = ft_be;
    wire [15:0] ft_data_drive;
    wire [1:0] ft_be_drive;

`ifdef COCOTB_SIM
    assign ft_data = ft_oe ? ft_data_drive : (ft_host_drive ? ft_data_host : 16'hzzzz);
    assign ft_be = ft_oe ? ft_be_drive : (ft_host_drive ? ft_be_host : 2'bzz);
`else
    assign ft_data = ft_oe ? ft_data_drive : 16'hzzzz;
    assign ft_be = ft_oe ? ft_be_drive : 2'bzz;
`endif

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
        .data(data),
        .addr(addr),
        .addr_bnk(addr_bnk),
        .addr_ceram2(addr_ceram2),
        .addr_cerom2(addr_cerom2)
    );
endmodule
