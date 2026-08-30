.ORG 0x10100

; ROM-like direct buzzer experiment:
; three single beeps using the PC-E500 BASIC BEEP(count,frq,time) low-level
; path shape. Each tone uses:
;   A = frq byte
;   X = waveform-cycle count
;   Y = repeat count
;
; The cycle counts below target about 0.3 s per tone using:
;   cycles ~= duration_s * (256000 / (90 + 4*frq))
;
; Selected notes:
;   frq=123 -> ~440 Hz -> X=132  (~0.30 s)
;   frq=100 -> ~522 Hz -> X=157  (~0.30 s)
;   frq=75  -> ~656 Hz -> X=197  (~0.30 s)

start:
    ; Initial quiet baseline.
    MV I, 0x0080
    WAIT
    MV I, 0x0080
    WAIT

    ; Tone 1: ~A4.
    MV A, 123
    MV X, 0x0084
    MV Y, 0x0001
    CALL rom_like_beep_var

    CALL inter_tone_gap

    ; Tone 2: ~C5.
    MV A, 100
    MV X, 0x009D
    MV Y, 0x0001
    CALL rom_like_beep_var

    CALL inter_tone_gap

    ; Tone 3: ~E5.
    MV A, 75
    MV X, 0x00C5
    MV Y, 0x0001
    CALL rom_like_beep_var

    RETF

rom_like_beep_var:
    MV [--S], A
    CALL rom_like_beep_prepare
    MV A, [S++]

rom_like_beep_var_loop:
    MV I, 0x0000
    SUB Y, I
    JPZ rom_like_beep_done

    MV [--S], A
    MV [--S], X
    CALL rom_like_waveform

    DEC Y
    JPZ rom_like_beep_finish_cycle

    CALL inter_tone_gap
    MV X, [S++]
    MV A, [S++]
    JP rom_like_beep_var_loop

rom_like_beep_finish_cycle:
    MV X, [S++]
    MV A, [S++]

rom_like_beep_done:
    CALL rom_like_beep_cleanup
    RET

rom_like_beep_prepare:
    PUSHU IMR
    MV (IMR), 0xA0
    MV A, (EOL)
    OR (EOL), 0x08
    OR A, 0xF7
    PUSHU A
    AND (SCR), 0x8F
    RET

rom_like_beep_cleanup:
    MV [--S], A
    PUSHS F
    POPU A
    AND (EOL), A
    POPU IMR
    POPS F
    MV A, [S++]
    RET

rom_like_waveform:
    MV I, 0x0000
    SUB X, I
    JPZ rom_like_waveform_done
    MV (BL), A

rom_like_waveform_cycle:
    OR (SCR), 0x10

    MV A, (BL)
    CMP A, 0x00
    JPZ rom_like_waveform_high_trim_start
rom_like_waveform_high_delay:
    RC
    DEC A
    JPNZ rom_like_waveform_high_delay

rom_like_waveform_high_trim_start:
    RC
    RC
    MV A, 0x0D
rom_like_waveform_high_trim:
    DEC A
    JPNZ rom_like_waveform_high_trim
    RC

    AND (SCR), 0xEF

    MV A, (BL)
    CMP A, 0x00
    JPZ rom_like_waveform_low_trim_start
rom_like_waveform_low_delay:
    RC
    DEC A
    JPNZ rom_like_waveform_low_delay

rom_like_waveform_low_trim_start:
    RC
    MV A, 0x09
rom_like_waveform_low_trim:
    DEC A
    JPNZ rom_like_waveform_low_trim
    RC

    MV A, 0x01
    SUB X, A
    JPNZ rom_like_waveform_reload

rom_like_waveform_done:
    RET

rom_like_waveform_reload:
    MV A, (BL)
    JP rom_like_waveform_cycle

inter_tone_gap:
    MV X, 0x2257
inter_tone_gap_loop:
    DEC X
    JPNZ inter_tone_gap_loop
    RET
