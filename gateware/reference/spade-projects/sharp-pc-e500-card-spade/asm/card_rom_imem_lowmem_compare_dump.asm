; Compare-dump IMEM and the external low address space over the FPGA echo port.
; Run CALL &10100 on the calculator after programming this image.
;
; Output format:
;   BEGIN IDX IM LO
;   00: Ixx Lyy
;   01: Ixx Lyy
;   ...
;   FF: xx yy
;   END
;
; Each line is:
; - IDX: byte index 0x00..0xFF
; - Ixx: IMEM[IDX]
; - Lyy: [0x00000 + IDX]
;
; The IMEM walk uses indexed internal-RAM addressing with BP=0 and PX as the
; loop index, while X streams the external low-address bytes.

.ORG 0x10100

start:
    PUSHU F
    PUSHU A
    PUSHU BA
    PUSHU X
    PUSHU Y

    MV A, (BP)
    PUSHU A
    MV A, (PX)
    PUSHU A
    PUSHU A

    MV Y, 0x1FFF1
    MV X, header
    CALL emit_string

    MV (BP), 0x00
    MV (PX), 0x00
    MV X, 0x00000

line_loop:
    MV A, (PX)
    CALL emit_hex_byte

    MV A, 0x3A
    CALL emit_char
    MV A, 0x20
    CALL emit_char

    MV A, (BP+PX)
    ; Use the reserved byte at [U] as scratch instead of pushing/popping the
    ; live user stack inside the hot loop.
    MV [U], A
    MV A, 0x49
    CALL emit_char
    MV A, [U]
    CALL emit_hex_byte

    MV A, 0x20
    CALL emit_char

    ; Emit a second marker before the external low-memory read.
    MV A, 0x4C
    CALL emit_char
    MV A, [X++]
    CALL emit_hex_byte
    CALL emit_crlf

    INC (PX)
    JPNZ line_loop

    MV X, footer
    CALL emit_string

    POPU A
    POPU A
    MV (PX), A
    POPU A
    MV (BP), A

    POPU Y
    POPU X
    POPU BA
    POPU A
    POPU F
    RETF

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
    ; Every echoed byte goes through this helper so the FPGA UART sees a
    ; consistent minimum gap between writes, not just the separators.
    NOP
    NOP
    RET

header:
    defm "BEGIN IDX IM LO"
    defb 0x0D, 0x0A, 0x00

footer:
    defm "END"
    defb 0x0D, 0x0A, 0x00
