module main (
    input wire clk,
    input wire rst_n,
    output wire [7:0] led,
    input wire usb_rx,
    output wire usb_tx,
    inout wire [47:0] ffc_data,
    output wire [7:0] saleae
`ifdef COCOTB_SIM
    ,
    input wire [47:0] ffc_data_host,
    input wire ffc_host_drive,
    output wire [47:0] ffc_drive_debug,
    output wire [47:0] ffc_oe_debug,
    output wire send_mode_debug,
    output wire [2:0] bank_debug,
    output wire [127:0] counter_debug
`endif
);
    wire [47:0] ffc_data_in;
    wire [47:0] ffc_data_drive;
    wire [47:0] ffc_data_oe;
    wire send_mode;
    wire [2:0] bank;
    wire [127:0] counter;

`ifdef COCOTB_SIM
    wire [47:0] ffc_external_drive = ffc_host_drive ? ffc_data_host : {48{1'bz}};
    assign ffc_data_in = ffc_host_drive ? ffc_data_host : 48'b0;
    assign ffc_drive_debug = ffc_data_drive;
    assign ffc_oe_debug = ffc_data_oe;
    assign send_mode_debug = send_mode;
    assign bank_debug = bank;
    assign counter_debug = counter;
`else
    wire [47:0] ffc_external_drive = {48{1'bz}};
    assign ffc_data_in = ffc_data;
`endif

    genvar pin_index;
    generate
        for (pin_index = 0; pin_index < 48; pin_index = pin_index + 1) begin : ffc_tristate
            assign ffc_data[pin_index] = ffc_data_oe[pin_index]
                ? ffc_data_drive[pin_index]
                : ffc_external_drive[pin_index];
        end
    endgenerate

    main_core core (
        .clk(clk),
        .rst_n(rst_n),
        .led(led),
        .usb_rx(usb_rx),
        .usb_tx(usb_tx),
        .ffc_data_in(ffc_data_in),
        .ffc_data_drive(ffc_data_drive),
        .ffc_data_oe(ffc_data_oe),
        .saleae(saleae),
        .send_mode_debug(send_mode),
        .bank_debug(bank),
        .counter_debug(counter)
    );
endmodule
