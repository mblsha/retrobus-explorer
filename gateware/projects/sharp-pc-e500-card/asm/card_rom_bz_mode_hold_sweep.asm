.ORG 0x10100

; Sweep SCR.BZ2:BZ0 hold states from CE6 code.
; Each mode is asserted for a visible window with a quiet gap between modes.
; This is for MSO correlation of CI/CO behavior, not for audible correctness.

start:
    PUSHU IMR
    MV (IMR), 0xA0
    OR (EOL), 0x08
    AND (SCR), 0x8F               ; preserve ISE/VDDC/STS/MTS/DISC, clear BZ2:BZ0

    CALL quiet_gap

    CALL hold_bz_001
    CALL quiet_gap

    CALL hold_bz_010
    CALL quiet_gap

    CALL hold_bz_011
    CALL quiet_gap

    CALL hold_bz_100
    CALL quiet_gap

    CALL hold_bz_101
    CALL quiet_gap

    CALL hold_bz_110
    CALL quiet_gap

    CALL hold_bz_111
    CALL quiet_gap

    AND (SCR), 0x8F
    POPU IMR
    RETF

quiet_gap:
    AND (SCR), 0x8F
    CALL hold_window
    RET

hold_bz_001:
    OR (SCR), 0x10
    CALL hold_window
    AND (SCR), 0x8F
    RET

hold_bz_010:
    OR (SCR), 0x20
    CALL hold_window
    AND (SCR), 0x8F
    RET

hold_bz_011:
    OR (SCR), 0x30
    CALL hold_window
    AND (SCR), 0x8F
    RET

hold_bz_100:
    OR (SCR), 0x40
    CALL hold_window
    AND (SCR), 0x8F
    RET

hold_bz_101:
    OR (SCR), 0x50
    CALL hold_window
    AND (SCR), 0x8F
    RET

hold_bz_110:
    OR (SCR), 0x60
    CALL hold_window
    AND (SCR), 0x8F
    RET

hold_bz_111:
    OR (SCR), 0x70
    CALL hold_window
    AND (SCR), 0x8F
    RET

hold_window:
    ; Roughly tens of ms. Exact duration is not important; we want stable windows.
    MV X, 0xA000
hold_window_loop:
    DEC X
    JPNZ hold_window_loop
    RET
