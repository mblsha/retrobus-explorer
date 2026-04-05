; Minimal CE6 echo smoke test that returns cleanly to BASIC.
;
; Program this image, then run:
;   CALL &10100
;
; Expected USB-UART output:
;   OK\r\n
;
; The three NOPs after each CE6 ECHO write keep a fixed gap between bytes while
; staying simple enough for direct bus inspection.

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
    NOP
    NOP
    NOP
    JP emit_next

emit_done:
    POPU X
    POPU A
    POPU F
    RETF

message:
    defm "OK"
    defb 0x0D, 0x0A, 0x00
