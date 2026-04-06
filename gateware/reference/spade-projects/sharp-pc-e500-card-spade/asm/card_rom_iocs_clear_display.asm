; PC-E500 CE6 supervisor experiment: invoke IOCS STDO clear display (51h).
;
; This is a minimal native IOCS execution probe. The supervisor brackets the
; run with XR,BEGIN / XR,END and measurement tags externally.

.ORG 0x10100

start:
    MV IL, 0x51
    CALLF 0xFFFE8
    RETF
