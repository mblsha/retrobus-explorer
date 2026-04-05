; Smallest valid experiment payload for the CE6 supervisor.
; The supervisor CALLFs 0x10100 and expects a RETF back to the idle loop.

.ORG 0x10100

start:
    RETF
