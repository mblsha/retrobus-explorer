; Minimal CE6 startup probe for tracing CALL &10000 on real hardware.
;
; Goals:
; - avoid CALL/RETF entirely
; - avoid stack use entirely
; - prove we can enter CE6 code and hit the CE6 control page
;
; Expected UART output (once):
;   XR,READY,00,BOOT\r\n
;
; After emitting the line, execution parks in a tight loop at park_forever.

.ORG 0x10000

start:
    MV A, 0x51
    MV [0x1FFF0], A

    MV A, 0x58
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x52
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x2C
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x52
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x45
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x41
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x44
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x59
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x2C
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x30
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x30
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x2C
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x42
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x4F
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x4F
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x54
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x0D
    MV [0x1FFF1], A
    NOP
    NOP
    NOP
    NOP

    MV A, 0x0A
    MV [0x1FFF1], A

    MV A, 0x52
    MV [0x1FFF2], A

park_forever:
    JP park_forever
