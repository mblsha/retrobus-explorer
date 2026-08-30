; WAIT probe experiment for the CE6 supervisor.
;
; Arguments are read from the fixed command block:
; - 0x107E6: I low byte
; - 0x107E7: I high byte
;
; The supervisor wraps the whole run in outer MARK_START / MARK_STOP tags.

.ORG 0x10100

start:
    MV I, [0x107E6]
    WAIT
    RETF
