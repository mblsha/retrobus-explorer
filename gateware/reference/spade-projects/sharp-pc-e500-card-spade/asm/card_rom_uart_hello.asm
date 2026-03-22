; Minimal CE6 UART smoke test for the PC-E500 card ROM.
; Run CALL &10100 on the calculator after programming this image.
; Expected USB-UART output: HELLO FROM CE6\r\n
; X acts as the moving index into the static NUL-terminated string buffer.

.ORG 0x10100

start:
    PUSHU F
    PUSHU A
    PUSHU X
    MV X, message

emit_next:
    MV A, [X++]
    CMP A, 0x00
    JPZ emit_done
    MV [0x1FFF1], A
    JP emit_next

emit_done:
    POPU X
    POPU A
    POPU F
    RETF

message:
    defm "HELLO FROM CE6"
    defb 0x0D, 0x0A, 0x00
