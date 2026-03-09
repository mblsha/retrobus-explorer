module main (
    input wire clk,
    input wire rst_n,
    output wire [7:0] led,
    input wire usb_rx,
    output wire usb_tx,
    output wire [7:0] saleae,

    input wire rw,
    input wire oe,
    input wire card_ram_ce1,
    input wire card_rom_ce6,
    input wire vcc2,
    input wire nc,
    input wire [17:0] addr,
    inout wire [7:0] data
`ifdef COCOTB_SIM
    ,
    input wire [7:0] data_host,
    input wire data_host_drive
`endif
);
    wire [7:0] data_in = data;
    wire [7:0] data_drive;
    wire data_oe;

`ifdef COCOTB_SIM
    assign data = data_oe ? data_drive : (data_host_drive ? data_host : 8'hzz);
`else
    assign data = data_oe ? data_drive : 8'hzz;
`endif

    main_core core (
        .clk(clk),
        .rst_n(rst_n),
        .led(led),
        .usb_rx(usb_rx),
        .usb_tx(usb_tx),
        .saleae(saleae),
        .rw(rw),
        .oe(oe),
        .card_ram_ce1(card_ram_ce1),
        .card_rom_ce6(card_rom_ce6),
        .vcc2(vcc2),
        .nc(nc),
        .addr(addr),
        .data_in(data_in),
        .data_drive(data_drive),
        .data_oe(data_oe)
    );
endmodule
