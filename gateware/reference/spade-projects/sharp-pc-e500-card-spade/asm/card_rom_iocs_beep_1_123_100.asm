.ORG 0x10100

; IOCS SYSTM:43h experiment:
; execute a tokenized BASIC statement via the built-in interpreter path
; instead of calling the internal BEEP helper directly.
;
; Statement target:
;   BEEP 1,123,100
;
; Token shape:
;   FE 29            ; BEEP token
;   1D ........      ; numeric literal
;   2C               ; ','
;   1D ........      ; numeric literal
;   2C               ; ','
;   1D ........      ; numeric literal
;   0D               ; end-of-statement
;
; The numeric packing below is inferred from real EN-ROM tokenized BEEP
; statements embedded in the ROM data area.

start:
    ; Short quiet lead-in so the audio boundary is easier to hear.
    MV I, 0x0080
    WAIT
    MV I, 0x0080
    WAIT

    ; JP supervisor context leaves the IOCS_WS IMEM alias stale at E6..E8.
    ; Refresh it from the live IOCS workspace pointer at 0x28..0x2A before
    ; entering SYSTM:43h, because the system-control/interpreter bridge reads
    ; workspace state via [(E6)+offset].
    MV A, (0x28)
    MV (IOCS_WS), A
    MV A, (0x29)
    MV (IOCS_WS1), A
    MV A, (0x2A)
    MV (IOCS_WS2), A

    ; SYSTM:43h "execute BASIC intermediate code"
    ; Current best match to internal wrappers:
    ;   X  = intermediate-code buffer
    ;   A  = 0x00 for a normal public IOCS device call
    ;   IL = 0x43
    ;   CL = 0x0008 (SYSTM: device)
    MV X, beep_stmt
    MVW (CL), 0x0008
    MV A, 0x00
    MV IL, 0x43
    CALLF 0x0FFFE8

    ; Let the trace settle after the IOCS return path.
    MV I, 0x0100
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
