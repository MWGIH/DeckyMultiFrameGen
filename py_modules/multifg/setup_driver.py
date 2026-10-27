"""Runs HelixSR's setup (helixsr-setup.sh, unchanged) on a pseudo-terminal and answers its questions the way the user
did in the plugin: yes to the downloads it asks for (NVIDIA's DLSS DLL, AMD's driver package for HLX FSR 4), and no
answer (end of input) to everything else. So after the build HelixSR's game installer gets no answer at its first
question and changes no game: games are installed one by one from the plugin.

--yes can't be used for this: from HelixSR 2.0 the setup hands it on to its game installer, which then puts HelixSR into
every game it finds. A terminal is needed because HelixSR 3.0 asks for AMD's download only on one (without one it
takes the question as answered no).

Started detached, so it keeps going when Decky restarts the plugin; the setup's exit code goes to RC_FILE.

    setup_driver.py LOG_FILE RC_FILE SETUP_SCRIPT [ARG]..
"""
import os
import pty
import re
import select
import signal
import subprocess
import sys
import time

# questions answered yes: the downloads the setup asks for ("Download it now? [Y/n]", "Download it from AMD now?
# [Y/n]"); a question waiting at the end of the output is one that ends like these
YES = re.compile(r"download[^\n]*\[Y/n\]\s*$", re.I)
QUESTION = re.compile(r"(\[[^\]\n]*/[^\]\n]*\]\s*|: )$")   # [Y/n], [s/f/n], ...; "(or just Enter to finish): "
QUIET = 1.5          # seconds without output before a question counts as waiting for its answer
MAX_ANSWERS = 40     # a setup that keeps asking is stopped


def main(log_path, rc_path, argv):
    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, close_fds=True)
    os.close(slave)
    pending, answers, last = "", 0, time.monotonic()
    with open(log_path, "ab", buffering=0) as log:
        while True:
            r, _, _ = select.select([master], [], [], 0.5)
            if r:
                try:
                    data = os.read(master, 65536)
                except OSError:   # the setup and everything it started have ended
                    break
                if not data:
                    break
                log.write(data)
                pending = (pending + data.decode(errors="replace")).replace("\r\n", "\n").rsplit("\n", 1)[-1][-400:]
                last = time.monotonic()
                continue
            if proc.poll() is not None:
                break
            if pending.strip() and QUESTION.search(pending) and time.monotonic() - last > QUIET:
                answers += 1
                if answers > MAX_ANSWERS:
                    log.write(b"\n[multifg] the setup keeps asking: stopped\n")
                    proc.send_signal(signal.SIGTERM)
                    break
                yes = bool(YES.search(pending))
                log.write(b"\n[multifg] answered yes\n" if yes else b"\n[multifg] answered nothing (end of input)\n")
                os.write(master, b"y\n" if yes else b"\x04")
                pending, last = "", time.monotonic()
    rc = proc.wait()
    os.close(master)
    with open(rc_path, "w") as f:
        f.write(f"{rc}\n")
    return rc


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
