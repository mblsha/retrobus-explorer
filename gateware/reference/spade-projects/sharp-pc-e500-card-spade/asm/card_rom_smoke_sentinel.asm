; Small proof-of-life payload for the FPGA-backed card ROM.
; It writes 0xA5 to the sentinel byte at 0x107F1 and returns.
; Run CALL &10000 on the PC-E500 after programming this image, then read 0x107F1.

.ORG 0x10000

    MV A, 0xA5
    MV [0x107F1], A
    RET

.ORG 0x107F1

    defb 0x00
