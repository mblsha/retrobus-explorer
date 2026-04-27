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
    input wire rw,
    input wire oe,
    input wire ce1,
    input wire ce6,
    input wire vcc2,
    input wire nc,
    input wire [17:0] addr,
    inout wire [7:0] data
`ifdef COCOTB_SIM
    ,
    input wire [7:0] data_host,
    input wire data_host_drive,
    output wire data_bus_conflict,
    output wire ft_bus_conflict,
    output wire saleae_3,
    output wire saleae_4,
    output wire saleae_5,
    output wire saleae_6,
    output wire saleae_7
`endif
);
    wire [15:0] ft_data_drive;
    wire [1:0] ft_be_drive;
    wire [7:0] data_drive;
    wire data_oe;
`ifdef COCOTB_SIM
    wire [15:0] ft_data_in = ft_host_drive ? ft_data_host : 16'h0000;
    wire [1:0] ft_be_in = ft_host_drive ? ft_be_host : 2'b00;
    wire [7:0] data_in = data_host_drive ? data_host : 8'h00;
    assign data_bus_conflict = data_host_drive && data_oe;
    assign ft_bus_conflict = ft_host_drive && ft_oe;
    assign saleae_3 = saleae[3];
    assign saleae_4 = saleae[4];
    assign saleae_5 = saleae[5];
    assign saleae_6 = saleae[6];
    assign saleae_7 = saleae[7];
`else
    wire [15:0] ft_data_in = ft_data;
    wire [1:0] ft_be_in = ft_be;
    wire [7:0] data_in = data;
`endif

`ifdef COCOTB_SIM
    assign ft_data = ft_oe ? ft_data_drive : (ft_host_drive ? ft_data_host : 16'hzzzz);
    assign ft_be = ft_oe ? ft_be_drive : (ft_host_drive ? ft_be_host : 2'bzz);
    assign data = data_oe ? data_drive : (data_host_drive ? data_host : 8'hzz);
`else
    assign ft_data = ft_oe ? ft_data_drive : 16'hzzzz;
    assign ft_be = ft_oe ? ft_be_drive : 2'bzz;
    assign data = data_oe ? data_drive : 8'hzz;
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
        .rw(rw),
        .oe(oe),
        .ce1(ce1),
        .ce6(ce6),
        .vcc2(vcc2),
        .nc(nc),
        .addr(addr),
        .data_in(data_in),
        .data_drive(data_drive),
        .data_oe(data_oe)
    );
endmodule
