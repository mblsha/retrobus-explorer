"""Host tooling for the RG35XX Plus booting from the card emulator.

The target has no serial header populated, so every observation of a boot
arrives through the card: a raw debug partition the boot script and userspace
write milestones into, and the passive SD trace the FPGA keeps. The modules
here build the card image that boot path expects and read back what it wrote.
"""
