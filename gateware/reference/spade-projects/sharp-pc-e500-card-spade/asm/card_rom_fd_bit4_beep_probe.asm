.ORG 0x10100

start:
    ; Silence baseline.
    MV I, 0x40
    WAIT
    MV I, 0x40
    WAIT

    ; Burst 1: highest pitch of the three.
    MV BA, 0x20
    MV Y, 0x0080
tone1:
    MV I, BA
    OR (SCR), 0x10
    WAIT
    MV I, BA
    AND (SCR), 0xEF
    WAIT
    DEC Y
    JPNZ tone1

    ; Gap.
    MV I, 0x80
    WAIT

    ; Burst 2: medium pitch.
    MV BA, 0x40
    MV Y, 0x0080
tone2:
    MV I, BA
    OR (SCR), 0x10
    WAIT
    MV I, BA
    AND (SCR), 0xEF
    WAIT
    DEC Y
    JPNZ tone2

    ; Gap.
    MV I, 0x80
    WAIT

    ; Burst 3: lowest pitch.
    MV BA, 0x80
    MV Y, 0x0080
tone3:
    MV I, BA
    OR (SCR), 0x10
    WAIT
    MV I, BA
    AND (SCR), 0xEF
    WAIT
    DEC Y
    JPNZ tone3

    RETF
