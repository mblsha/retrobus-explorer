module main (
    input wire clk,
    input wire rst_n,
    input wire usb_rx,
    output wire usb_tx,
    input wire ft_clk,
    input wire ft_rxf,
    input wire ft_txe,
    inout wire [15:0] ft_data,
    inout wire [1:0] ft_be,
    output wire ft_rd,
    output wire ft_wr,
    output wire ft_oe,
    output wire [7:0] led,
    inout wire [19:0] addr,
    inout wire [7:0] data,
    inout wire conn_rw,
    inout wire conn_oe,
    inout wire conn_ci,
    inout wire conn_e2,
    inout wire conn_mskrom,
    inout wire conn_sram1,
    inout wire conn_sram2,
    inout wire conn_eprom,
    input wire conn_stnby,
    input wire conn_vbatt,
    input wire conn_vpp,
    input wire conn_nc02,
    input wire conn_nc42,
    input wire conn_nc43,
    input wire conn_nc44
`ifdef COCOTB_SIM
    ,
    input wire [19:0] addr_host,
    input wire [7:0] data_host,
    input wire [7:0] control_host,
    input wire [6:0] protected_host,
    output wire [19:0] addr_drive_debug,
    output wire [19:0] addr_oe_debug,
    output wire [7:0] data_drive_debug,
    output wire data_oe_debug,
    output wire [7:0] control_drive_debug,
    output wire [7:0] control_oe_debug,
    output wire armed_debug
`endif
);
    wire [19:0] addr_drive;
    wire [19:0] addr_oe;
    wire [7:0] data_drive;
    wire data_oe;
    wire [7:0] control_drive;
    wire [7:0] control_oe;
    wire armed;
    wire [19:0] addr_in;
    wire [7:0] data_in;
    wire [7:0] control_in;
    wire [6:0] protected_in;
    wire [15:0] ft_data_drive;
    wire [1:0] ft_be_drive;
    // OBP5 transmits only full words with fixed metadata. Format those bits
    // at the connector instead of retaining constants in the payload FIFO.
    assign ft_data = ft_oe ? {8'ha5, ft_data_drive[7:0]} : 16'hzzzz;
    assign ft_be = ft_oe ? 2'b11 : 2'bzz;
`ifdef COCOTB_SIM
    assign addr_in = addr_host;
    assign data_in = data_host;
    assign control_in = control_host;
    assign protected_in = protected_host;
    assign addr_drive_debug = addr_drive;
    assign addr_oe_debug = addr_oe;
    assign data_drive_debug = data_drive;
    assign data_oe_debug = data_oe;
    assign control_drive_debug = control_drive;
    assign control_oe_debug = control_oe;
    assign armed_debug = armed;
    localparam [26:0] WATCHDOG_LIMIT = 27'd50000;
`else
    assign addr_in = addr;
    assign data_in = data;
    assign control_in = {conn_eprom, conn_sram2, conn_sram1, conn_mskrom,
                         conn_e2, conn_ci, conn_oe, conn_rw};
    assign protected_in = {conn_nc44, conn_nc43, conn_nc42, conn_nc02,
                           conn_vpp, conn_vbatt, conn_stnby};
    localparam [26:0] WATCHDOG_LIMIT = 27'd100000000;
`endif

    genvar bit_index;
    generate
        for (bit_index = 0; bit_index < 20; bit_index = bit_index + 1) begin : address_buffers
            assign addr[bit_index] = addr_oe[bit_index] ? addr_drive[bit_index] : 1'bz;
        end
        for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1) begin : data_buffers
            assign data[bit_index] = data_oe ? data_drive[bit_index] : 1'bz;
        end
    endgenerate
    assign conn_rw = control_oe[0] ? control_drive[0] : 1'bz;
    assign conn_oe = control_oe[1] ? control_drive[1] : 1'bz;
    assign conn_ci = control_oe[2] ? control_drive[2] : 1'bz;
    assign conn_e2 = control_oe[3] ? control_drive[3] : 1'bz;
    assign conn_mskrom = control_oe[4] ? control_drive[4] : 1'bz;
    assign conn_sram1 = control_oe[5] ? control_drive[5] : 1'bz;
    assign conn_sram2 = control_oe[6] ? control_drive[6] : 1'bz;
    assign conn_eprom = control_oe[7] ? control_drive[7] : 1'bz;

    main_core core (
        .clk(clk), .rst_n(rst_n), .usb_rx(usb_rx), .usb_tx(usb_tx), .led(led),
        .ft_clk(ft_clk), .ft_rxf(ft_rxf), .ft_txe(ft_txe),
        .ft_data(ft_data), .ft_be(ft_be),
        .ft_data_drive(ft_data_drive), .ft_be_drive(ft_be_drive),
        .ft_rd(ft_rd), .ft_wr(ft_wr), .ft_oe(ft_oe),
        .addr(addr_in), .data(data_in),
        .conn_rw(control_in[0]), .conn_oe(control_in[1]),
        .conn_ci(control_in[2]), .conn_e2(control_in[3]),
        .conn_mskrom(control_in[4]), .conn_sram1(control_in[5]),
        .conn_sram2(control_in[6]), .conn_eprom(control_in[7]),
        .conn_stnby(protected_in[0]), .conn_vbatt(protected_in[1]),
        .conn_vpp(protected_in[2]), .conn_nc02(protected_in[3]),
        .conn_nc42(protected_in[4]), .conn_nc43(protected_in[5]),
        .conn_nc44(protected_in[6]), .watchdog_limit(WATCHDOG_LIMIT),
        .addr_drive(addr_drive), .addr_oe(addr_oe),
        .data_drive(data_drive), .data_oe(data_oe),
        .control_drive(control_drive), .control_oe(control_oe),
        .armed_debug(armed)
    );
endmodule
