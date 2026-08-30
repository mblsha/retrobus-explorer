.ORG 0x10100

; Invoke the far-callable JP BASIC BEEP statement handler directly.
;
; JP ROM entrypoint:
;   0x0F8068 = top-level BASIC BEEP parser
;              In: X -> ASCII argument text
;              Out: RETF on success
;
; We pass three standalone argument strings, each NUL-terminated:
;   "1,123,132"
;   "1,100,157"
;   "1,75,197"
;
; These target about 0.3 s per tone from the published E500 frequency formula.

start:
    MV I, 0x0080
    WAIT
    MV I, 0x0080
    WAIT

    MV X, tone1_args
    CALLF 0x0F8068

    MV X, tone2_args
    CALLF 0x0F8068

    MV X, tone3_args
    CALLF 0x0F8068

    RETF

tone1_args:
    DEFM "1,123,132"
    DEFB 0x00

tone2_args:
    DEFM "1,100,157"
    DEFB 0x00

tone3_args:
    DEFM "1,75,197"
    DEFB 0x00
