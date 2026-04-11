.ORG 0x10100

; Directly call the JP ROM BEEP helper rather than reimplementing it.
;
; JP ROM entrypoints:
;   0x0F80FF = variable-pitch tone engine
;              In: A=frq, X=time/cycle-count, Y=count
;   0x0F8191 = fixed inter-tone gap helper
;
; Chosen values target about 0.3 s per tone using:
;   cycles ~= duration_s * (256000 / (90 + 4*frq))
; which gives:
;   frq=123 -> X=132
;   frq=100 -> X=157
;   frq=75  -> X=197

start:
    ; Short quiet lead-in.
    MV I, 0x0080
    WAIT
    MV I, 0x0080
    WAIT

    ; Tone 1: ~A4.
    MV A, 123
    MV X, 0x0084
    MV Y, 0x0001
    CALLF 0x0F80FF

    CALLF 0x0F8191

    ; Tone 2: ~C5.
    MV A, 100
    MV X, 0x009D
    MV Y, 0x0001
    CALLF 0x0F80FF

    CALLF 0x0F8191

    ; Tone 3: ~E5.
    MV A, 75
    MV X, 0x00C5
    MV Y, 0x0001
    CALLF 0x0F80FF

    RETF
