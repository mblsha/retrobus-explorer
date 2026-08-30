; Minimal internal-memory read/write demo for the PC-E500 card ROM.
; Run CALL &10100 on the calculator after programming this image.
;
; Demonstrates the basic scalar IMEM transfer widths:
; - 1 byte: MV (n), A / MV A, (n)
; - 2 bytes: MV (n), BA / MV BA, (n)
; - 3 bytes: MV (n), X / MV X, (n)
;
; Expected FPGA echo output: ABCDEF\r\n

.ORG 0x10100

start:
    PUSHU F
    PUSHU A
    PUSHU BA
    PUSHU X

    ; 1-byte IMEM write/read via A.
    MV (0x10), 0x41
    MV A, (0x10)
    MV [0x1FFF1], A

    ; 2-byte IMEM write/read via BA. BA=0x4342 stores 42h,43h => 'B','C'.
    MV BA, 0x4342
    MV (0x11), BA
    MV BA, (0x11)
    MV A, (0x11)
    MV [0x1FFF1], A
    MV A, (0x12)
    MV [0x1FFF1], A

    ; 3-byte IMEM write/read via X. X=0x464544 stores 44h,45h,46h => 'D','E','F'.
    MV X, 0x464544
    MV (0x13), X
    MV X, (0x13)
    MV A, (0x13)
    MV [0x1FFF1], A
    MV A, (0x14)
    MV [0x1FFF1], A
    MV A, (0x15)
    MV [0x1FFF1], A

    MV A, 0x0D
    MV [0x1FFF1], A
    MV A, 0x0A
    MV [0x1FFF1], A

    POPU X
    POPU BA
    POPU A
    POPU F
    RETF
