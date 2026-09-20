# Experiment 34. How often a deep sleep does not come back: many short ones in
# a row, each covered by the watchdog, counted in a place that survives the
# reset a failure causes.
#
# This exists because a rung was nearly kept and nearly thrown away on three
# sleeps. `sr-phy` had eighteen with no failure and `sr-phy-nodisp` had three
# with one, and those two numbers do not separate a firmware that always works
# from one that fails a third of the time: three sleeps of a rung that fails
# one in ten come out clean more often than not. A rate needs tens of sleeps,
# and tens of forty-second measured sleeps cost an hour each. Ten-second ones
# cost nothing and answer the only question being asked here, which is whether
# it comes back -- with the memory it went to sleep with.
#
# Ten seconds is also the longest sleep the watchdog can cover: its longest
# interval is about sixteen and it is armed from the entry, through the wait,
# to the end of the resume, so a hang anywhere becomes a warm reset within
# sixteen seconds instead of a target that stopped answering. That is what
# makes this unattended. The request is one word in RTC general purpose
# register 11, which the stub consumes as it reads it.
#
# The counting is the hard part, and it is why this job writes to the card.
# When a sleep hangs, the board resets, the runner comes back up and finds the
# same job -- the sequence number is unchanged, so from the runner's side this
# is the same job running again -- and everything in tmpfs, including how many
# sleeps had already passed, is gone. The RTC registers survive the reset but
# not the power-off at the end of the run, and the result region is rewritten
# by the pass that follows. So the tally lives in a sector of the debug
# partition that nothing else uses, tagged with the job's sequence number: a
# tally from another sequence is another batch's and is started over, and a
# tally from this one is this batch's own history. A pass that finds one has,
# by definition, restarted, and a restart is a failure -- nothing else takes
# the board round again in the middle of a job.
#
# So one invocation is one batch of `cycles` sleeps however many resets it
# takes, and its last line is the whole result. The host has to allow the run
# to survive those resets: `--expect-reboots 2`, because the runner polls for a
# job on the way back up and that poll is otherwise read as the job being over.
#
# Not a measurement. Ten-second windows are shorter than the measurement rule,
# the watchdog being armed is itself a difference, and the md5 check between
# sleeps is most of the wall clock. It says how often, not how much.

# The shape of the batch comes out of the job's own name, because one script
# that is the control and all of its variants is one script whose counting has
# been checked once. A name containing `-s40w0c6-` is six sleeps of forty
# seconds with no watchdog request; the default, and what a name that says
# nothing gets, is twelve of ten seconds with it.
#
# The watchdog request is worth varying because it is the one thing this job
# does that no measured sleep has ever done, and therefore the first suspect
# when this job sees failures that the measurements did not. It is not what
# makes a failed rebuild leave evidence: the stub arms its own half-second
# watchdog on the way into stub_reset(), so a rebuild that gives up takes the
# board round again whether or not the request was made. The request only
# covers a hang that never reaches that code.
shape="$($BB printf '%s' "$JOB_NAME" | $BB sed -n 's/.*[-_]s\([0-9][0-9]*\)w\([01]\)c\([0-9][0-9]*\).*/\1 \2 \3/p')"
set -- $shape
seconds="${1:-10}"
watchdog="${2:-1}"
cycles="${3:-12}"

# Sectors 256..279 are the runner's scratch and 128..255 the result; this is
# the next free page above both, two pages clear of the mark so that a read of
# it can never be mistaken for one. See rg35xx/debug_partition.py.
TALLY_SECTOR=288

devmem_hex() {
    $BB devmem "$1" 2>/dev/null || echo UNREADABLE
}

markers() {
    echo "el3 stage=$(devmem_hex 0x07000130) entered=$(devmem_hex 0x07000134) resumed=$(devmem_hex 0x07000138) wake_irq=$(devmem_hex 0x0700013c)"
    echo "stub fail_reg=$(devmem_hex 0x07000120) fail_info=$(devmem_hex 0x07000124) await=$(devmem_hex 0x07000128) debug=$(devmem_hex 0x0700012c)"
    echo "params status=$(devmem_hex 0x2002c) stage=$(devmem_hex 0x20030) fail=$(devmem_hex 0x2003c)@$(devmem_hex 0x20038)"
}

# One line of everything a failure left behind, short enough that several fit
# in the tally sector beside the counts.
failure_evidence() {
    echo "stage=$(devmem_hex 0x07000130),fail_reg=$(devmem_hex 0x07000120),fail_info=$(devmem_hex 0x07000124),await=$(devmem_hex 0x07000128),entered=$(devmem_hex 0x07000134),resumed=$(devmem_hex 0x07000138)"
}

# The stub reads this once and clears it; see STUB_DEBUG_WATCHDOG in stub.h.
# It can only cover a sleep shorter than the watchdog's longest interval of
# about sixteen seconds, so a batch of longer sleeps asks for nothing.
ask_for_the_watchdog() {
    [ "$watchdog" = 1 ] || return 0
    $BB devmem 0x0700012c 32 0x57440001 2>/dev/null
}

write_tally() {
    {
        $BB printf '%s\n' "$MAGIC"
        $BB printf 'direction=target-to-host\n'
        $BB printf 'kind=reliability\n'
        $BB printf 'seq=%s\n' "$JOB_SEQUENCE"
        $BB printf 'attempted=%s\n' "$attempted"
        $BB printf 'completed=%s\n' "$completed"
        $BB printf 'fails=%s\n' "$fails"
        $BB printf 'passes=%s\n' "$passes"
        $BB printf 'evidence=%s\n' "$evidence"
    } > /tmp/tally
    write_sectors /tmp/tally "$TALLY_SECTOR"
}

read_tally() {
    read_sectors "$DEBUG_DEVICE" "$TALLY_SECTOR" 1 /tmp/tally-back
    if [ "$(field kind /tmp/tally-back)" = reliability ] &&
       [ "$(field seq /tmp/tally-back)" = "$JOB_SEQUENCE" ]; then
        attempted="$(field attempted /tmp/tally-back)"
        completed="$(field completed /tmp/tally-back)"
        fails="$(field fails /tmp/tally-back)"
        passes="$(field passes /tmp/tally-back)"
        evidence="$(field evidence /tmp/tally-back)"
        return 0
    fi
    return 1
}

dram_probe_mb=256

for p in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -e "$p/scaling_governor" ] && echo powersave > "$p/scaling_governor" 2>/dev/null
done

attempted=0
completed=0
fails=0
passes=1
evidence=

echo "=== batch sequence=$JOB_SEQUENCE name=$JOB_NAME target=$cycles cycles of ${seconds}s, watchdog=$watchdog"
echo "uptime at start=$($BB cut -d' ' -f1 /proc/uptime) rtc=$(rtc_now)"
echo "whatever the last boot left behind:"
markers

if read_tally; then
    # The only thing that restarts a job under one sequence number is the board
    # going round again, and the only thing that takes it round is a sleep that
    # did not come back.
    passes=$((passes + 1))
    fails=$((fails + 1))
    evidence="$evidence [$attempted:$(failure_evidence)]"
    echo "RESTARTED: this is pass $passes of sequence $JOB_SEQUENCE"
    echo "FAILURE $fails at sleep $attempted: $(failure_evidence)"
    echo "tally so far attempted=$attempted completed=$completed fails=$fails"
    write_tally
else
    echo "first pass of this batch; the tally sector is being started over"
    write_tally
fi

echo "governor=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor) freq=$($BB cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq)"
echo "mem_sleep=[$($BB cat /sys/power/mem_sleep)] success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail)"
card_check

$BB dd if=/dev/urandom of=/tmp/dram-probe bs=1M count="$dram_probe_mb" 2>/dev/null
before="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
echo "dram-probe ${dram_probe_mb}MiB md5=$before free=$($BB grep MemFree /proc/meminfo)"

while [ "$attempted" -lt "$cycles" ]; do
    attempted=$((attempted + 1))
    echo "=== sleep $attempted of $cycles (pass $passes)"
    # The tally goes down before the sleep, so that a sleep which never
    # returns is still counted as attempted by the pass that follows it.
    write_tally
    ask_for_the_watchdog
    rtc_sleep "$seconds" mem deep
    completed=$((completed + 1))
    write_tally
    markers
    now="$($BB md5sum /tmp/dram-probe | $BB cut -d' ' -f1)"
    if [ "$now" = "$before" ]; then
        echo "dram-check ok $now"
    else
        echo "dram-check FAILED wanted $before got $now"
        fails=$((fails + 1))
        evidence="$evidence [$attempted:md5-mismatch]"
        write_tally
    fi
    echo "uptime=$($BB cut -d' ' -f1 /proc/uptime) rtc=$(rtc_now)"
    [ "$attempted" -lt "$cycles" ] && $BB sleep 2
done

echo "=== batch done"
echo "RELIABILITY seq=$JOB_SEQUENCE name=$JOB_NAME seconds=$seconds watchdog=$watchdog attempted=$attempted completed=$completed fails=$fails passes=$passes"
echo "RELIABILITY evidence=$evidence"
echo "success=$($BB cat /sys/power/suspend_stats/success) fail=$($BB cat /sys/power/suspend_stats/fail) last_failed_dev=[$($BB cat /sys/power/suspend_stats/last_failed_dev)]"
markers
echo "debug register left as $(devmem_hex 0x0700012c), which should be zero"
echo "mctl STAT=$(devmem_hex 0x047fb004) PWRCTL=$(devmem_hex 0x047fb030) MAER0=$(devmem_hex 0x047fa020)"
echo "ccu PLL_VIDEO0=$(devmem_hex 0x03001040) PLL_DE=$(devmem_hex 0x03001060) DE_BGR=$(devmem_hex 0x0300160c)"
card_check
