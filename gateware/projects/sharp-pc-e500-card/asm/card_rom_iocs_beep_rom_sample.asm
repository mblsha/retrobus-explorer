.ORG 0x10100

; IOCS SYSTM:43h control experiment using an exact tokenized EN-ROM sample:
;   BEEP 2,150,210
;
; This is a control for the hand-built BEEP 1,123,100 token buffer.
; If this sample also returns quickly and silently, the mismatch is not the
; literal packing. It is the SYSTM:43h staging / execution model.

start:
    MV I, 0x0080
    WAIT
    MV I, 0x0080
    WAIT

    ; JP supervisor context keeps the IOCS_WS alias at E6..E8 stale.
    ; Refresh it from the live IOCS workspace pointer at 0x28..0x2A so the
    ; SYSTM:43h bridge reads the same workspace state as working JP IOCS text
    ; helpers do.
    MV A, (0x28)
    MV (IOCS_WS), A
    MV A, (0x29)
    MV (IOCS_WS1), A
    MV A, (0x2A)
    MV (IOCS_WS2), A

    MV X, beep_stmt
    MVW (CL), 0x0008
    MV A, 0x00
    MV IL, 0x43
    CALLF 0x0FFFE8

    ; Give any queued/asynchronous BASIC side work time to run.
    MV I, 0x4000
    WAIT
    MV I, 0x4000
    WAIT
    MV I, 0x4000
    WAIT
    MV I, 0x4000
    WAIT

    RETF

beep_stmt:
    DEFB 0xFE, 0x29
    DEFB 0x1D, 0x00, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00
    DEFB 0x2C
    DEFB 0x1D, 0x00, 0x01, 0x50, 0x00, 0x00, 0x00, 0x00
    DEFB 0x2C
    DEFB 0x1D, 0x00, 0x02, 0x10, 0x00, 0x00, 0x00, 0x00
    DEFB 0x0D
