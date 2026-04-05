; Safe CE6 ROM supervisor for continuous PC-E500 experiments.
;
; Boot once from BASIC with:
;   CALL &10000
;
; After that the supervisor:
; - leaves IMR untouched
; - emits XR,READY,01,SAFE
; - polls the fixed command block at 0x107E0..0x107FF
; - CALLFs the fixed experiment entry at 0x10100 when the sequence byte changes
; - emits XR,BEGIN,<seq> and XR,END,<seq>,OK around each run
;
; Reserved internal-memory bytes:
; - 0x30: last executed sequence
; - 0x31: current sequence scratch

.ORG 0x10000

start:
    MV (0x30), 0x00

    CALL init_uart
    MV X, ready_line
    CALL emit_string

idle_loop:
    MV A, [0x107FF]
    CMP A, 0x00
    JPZ idle_loop

    MV (0x31), A
    MV A, (0x30)
    XOR A, (0x31)
    JPZ idle_loop

    MV A, [0x107E0]
    CMP A, 0x58
    JPNZ idle_loop
    MV A, [0x107E1]
    CMP A, 0x52
    JPNZ idle_loop
    MV A, [0x107E2]
    CMP A, 0x01
    JPNZ idle_loop

    MV A, (0x31)
    MV (0x30), A

    CALL emit_begin
    MV A, [0x107E4]
    MV [0x1FFF0], A
    CALLF 0x10100
    MV A, [0x107E5]
    MV [0x1FFF2], A
    CALL emit_end
    JP idle_loop

init_uart:
    MV Y, 0x1FFF1
    RET

emit_begin:
    CALL init_uart
    MV X, begin_prefix
    CALL emit_string
    MV A, (0x31)
    CALL emit_hex_byte
    CALL emit_crlf
    RET

emit_end:
    CALL init_uart
    MV X, end_prefix
    CALL emit_string
    MV A, (0x31)
    CALL emit_hex_byte
    MV X, end_suffix
    CALL emit_string
    CALL emit_crlf
    RET

emit_crlf:
    MV A, 0x0D
    CALL emit_char
    MV A, 0x0A
    CALL emit_char
    RET

emit_string:
    MV A, [X++]
    CMP A, 0x00
    JPZ emit_string_done
    CALL emit_char
    JP emit_string

emit_string_done:
    RET

emit_hex_byte:
    MV B, A

    SWAP A
    AND A, 0x0F
    CALL emit_hex_nibble

    MV A, B
    AND A, 0x0F
    CALL emit_hex_nibble
    RET

emit_hex_nibble:
    ADD A, 0x30
    CMP A, 0x3A
    JPC emit_hex_nibble_done
    ADD A, 0x07
emit_hex_nibble_done:
    CALL emit_char
    RET

emit_char:
    MV [Y], A
    ; Keep a minimum gap between echoed bytes so the host UART stays caught up.
    NOP
    NOP
    RET

ready_line:
    defm "XR,READY,01,SAFE"
    defb 0x0D, 0x0A, 0x00

begin_prefix:
    defm "XR,BEGIN,"
    defb 0x00

end_prefix:
    defm "XR,END,"
    defb 0x00

end_suffix:
    defm ",OK"
    defb 0x00

.ORG 0x107E0
    defb 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    defb 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    defb 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    defb 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
