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

    input wire conn_rw,
    input wire conn_oe,
    input wire conn_ci,
    input wire conn_e2,

    input wire conn_mskrom,
    input wire conn_sram1,
    input wire conn_sram2,
    input wire conn_eprom,
    input wire conn_stnby,
    input wire conn_vbatt,
    input wire conn_vpp,

    input wire [19:0] addr,
    input wire [7:0] data
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
        .conn_rw(conn_rw),
        .conn_oe(conn_oe),
        .conn_ci(conn_ci),
        .conn_e2(conn_e2),
        .conn_mskrom(conn_mskrom),
        .conn_sram1(conn_sram1),
        .conn_sram2(conn_sram2),
        .conn_eprom(conn_eprom),
        .conn_stnby(conn_stnby),
        .conn_vbatt(conn_vbatt),
        .conn_vpp(conn_vpp),
        .addr(addr),
        .data(data)
    );
endmodule
