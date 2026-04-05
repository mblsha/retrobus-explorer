; Pure fetch-loop probe for CALL &10000 tracing.
;
; Purpose:
; - no IMR writes
; - no CE6 control-page writes
; - no stack use
; - no CALL/RET
;
; Expected bus behavior:
; - one short sequential fetch window at 0x10000..
; - then repeated CE6 fetches in the JP loop body

.ORG 0x10000

start:
    MV A, 0x51
    NOP
    NOP

park_forever:
    JP park_forever
