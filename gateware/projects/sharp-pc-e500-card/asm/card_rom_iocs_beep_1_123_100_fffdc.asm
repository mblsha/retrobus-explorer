.ORG 0x10100

; IOCS compatibility-wrapper experiment:
; run BEEP 1,123,100 via CALLF 0xFFFDC instead of CALLF 0xFFFE8.
;
; The JP/EN compatibility wrapper stages:
;   IL <- [0xBFE02]
;   CL <- [0xBFE00..0xBFE01]
; immediately before it enters the public IOCS dispatcher.
;
; This tests whether direct CE6 CALLF 0xFFFE8 loses the nonzero device
; selector for SYSTM: while the ROM wrapper preserves it.

start:
    ; Short quiet lead-in.
    MV I, 0x0080
    WAIT
    MV I, 0x0080
    WAIT

    ; Refresh the stale IOCS workspace alias at E6..E8 from the live
    ; workspace pointer triple in IMEM 0x28..0x2A.
    MV A, (0x28)
    MV (IOCS_WS), A
    MV A, (0x29)
    MV (IOCS_WS1), A
    MV A, (0x2A)
    MV (IOCS_WS2), A

    ; Stage the compatibility parameter block that CALLF 0xFFFDC consumes.
    ; [BFE00..BFE01] = 0008h => IOCS device 08h (SYSTM:)
    ; [BFE02]        = 43h   => "execute BASIC intermediate code"
    MV A, 0x08
    MV [0x0BFE00], A
    MV A, 0x00
    MV [0x0BFE01], A
    MV A, 0x43
    MV [0x0BFE02], A

    ; X still carries the intermediate-code statement buffer.
    ; The interpreter bridge behind SYSTM:43h expects mode bits in A.
    ; Use A=0 so 0xF5EC9 stays on the normal statement-execution path.
    MV A, 0x00
    MV X, beep_stmt
    CALLF 0x0FFFDC

    ; Leave time for any deferred interpreter work before returning.
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

    ; 1
    DEFB 0x1D, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00
    DEFB 0x2C

    ; 123
    DEFB 0x1D, 0x00, 0x01, 0x23, 0x00, 0x00, 0x00, 0x00
    DEFB 0x2C

    ; 100
    DEFB 0x1D, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00
    DEFB 0x0D
