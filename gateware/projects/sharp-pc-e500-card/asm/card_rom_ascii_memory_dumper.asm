; Fixed-range ASCII memory dumper for the PC-E500 FPGA card.
; Run CALL &10100 on the calculator after programming this image.
;
; Output format:
;   BEGIN C0000 FFFFF
;   C0000: XX XX XX XX XX XX XX XX XX XX XX XX XX XX XX XX
;   ...
;   END
;
; The range is hardcoded to the main ROM window so the hot path can stay simple:
; - source pointer X streams from 0xC0000
; - output port Y stays pinned at 0x1FFF1
; - I counts 0x4000 lines of 16 bytes each

.ORG 0x10100

start:
    PUSHU F
    PUSHU BA
    PUSHU I
    PUSHU X
    PUSHU Y
    MV A, (0x10)
    PUSHU A
    MV A, (0x11)
    PUSHU A
    MV A, (0x12)
    PUSHU A
    MV A, (0x13)
    PUSHU A

    MV Y, 0x1FFF1
    MV X, header
    CALL emit_string

    MV X, 0xC0000
    MV I, 0x4000

line_loop:
    CALL emit_hex_addr_x

    MV A, 0x3A
    MV [Y], A
    ; Pace the adjacent writes so the FPGA echo UART does not overrun on ": ".
    NOP
    NOP
    MV A, 0x20
    MV [Y], A

    MV (0x13), 0x10

byte_loop:
    MV A, [X++]
    MV B, A

    SWAP A
    AND A, 0x0F
    ADD A, 0x30
    CMP A, 0x3A
    JPC emit_high_nibble
    ADD A, 0x07
emit_high_nibble:
    MV [Y], A

    MV A, B
    AND A, 0x0F
    ADD A, 0x30
    CMP A, 0x3A
    JPC emit_low_nibble
    ADD A, 0x07
emit_low_nibble:
    MV [Y], A

    DEC (0x13)
    JPZ line_done

    MV A, 0x20
    MV [Y], A
    JP byte_loop

line_done:
    CALL emit_crlf

    MV BA, 0x0001
    SUB I, BA
    JPNZ line_loop

    MV X, footer
    CALL emit_string

    POPU A
    MV (0x13), A
    POPU A
    MV (0x12), A
    POPU A
    MV (0x11), A
    POPU A
    MV (0x10), A
    POPU Y
    POPU X
    POPU I
    POPU BA
    POPU F
    RETF

emit_crlf:
    MV A, 0x0D
    MV [Y], A
    ; CR/LF is the tightest write pair in the whole payload; give the echo path time.
    NOP
    NOP
    MV A, 0x0A
    MV [Y], A
    RET

emit_string:
    MV A, [X++]
    CMP A, 0x00
    JPZ emit_string_done
    MV [Y], A
    JP emit_string

emit_string_done:
    RET

emit_hex_addr_x:
    MV (0x10), X

    MV A, (0x12)
    AND A, 0x0F
    CALL emit_hex_nibble

    MV A, (0x11)
    CALL emit_hex_byte

    MV A, (0x10)
    CALL emit_hex_byte
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
    MV [Y], A
    RET

header:
    defm "BEGIN C0000 FFFFF"
    defb 0x0D, 0x0A, 0x00

footer:
    defm "END"
    defb 0x0D, 0x0A, 0x00
