#!/usr/bin/env python3

#imports
import fcntl
import hashlib
import math
import os
from pathlib import Path
import signal
import argparse
import random
import shutil
import sys
import time

#this defines the chars used for the snowflakes
#ANSI escape sequences to tell the terminal where to place 
    #snowflakes without moving the user's typing cursor permanently [line 119]
FLAKES = ["*", ".", "+"]

# Calculate a continuously varying storm intensity from 0.0 to 1.0.
# Smoothstep provides the overall buildup; a small sine wave simulates gusts.
def snowfall_settings(elapsed, duration):
    progress = max(0.0, min(1.0, elapsed / duration))
    baseline = progress * progress * (3.0 - 2.0 * progress)

    # Gusts vary over time, tapering to zero at the start and end.
    gust = (0.10 * math.sin(0.15 * elapsed)
            * math.sin(math.pi * progress))
    intensity = max(0.0, min(1.0, baseline + gust))

    # Intensity controls both snowflake density and time between cycles.
    flakes_per_cycle = max(1, min(8, round(1 + 7 * intensity)))
    interval = max(0.1, 0.5 - 0.4 * intensity)
    return flakes_per_cycle, interval


#preventing multiple instances from running in the same terminal
def acquire_terminal_lock():
    #aonly one LakeEffect instance per terminal

    if not sys.stdout.isatty():
        return None

    #identify the terminal associated with this process
    tty_path = os.ttyname(sys.stdout.fileno())

    #generate a safe, unique lock filename for the terminal
    #this is a hash not encryption. SHA-256 hash of the terminal 
        #path and use the first 16 hexadecimal characters as an identifier
    tty_id = hashlib.sha256(
        tty_path.encode()
    ).hexdigest()[:16]

    lock_dir = os.path.join(
        os.environ.get("XDG_RUNTIME_DIR", f"/tmp/lakeeffect-{os.getuid()}"),
        "lakeeffect"
    )

    os.makedirs(lock_dir, mode=0o700, exist_ok=True)

    lock_path = os.path.join(lock_dir, f"{tty_id}.lock")

    lock_file = open(lock_path, "w")

    try:
        #LOCK_NB means don't wait if another instance owns the lock
        #this way you can have multiple windows into the same box, but not multiple lake effect instances on one ssh session
        fcntl.flock(
            lock_file.fileno(),
            fcntl.LOCK_EX | fcntl.LOCK_NB
        )
    except BlockingIOError:
        lock_file.close()
        return None

    return lock_file

#sigterm for clean up
def handle_sigterm(signum, frame): 
    #if the process receives a SIGTERM during the delay, 
        #the handler raises a KeyboardInterrupt before the cleanup 
        #block is entered
    #the os still releases the file lock when the process exits, 
        #but the cleanup code doesn't run yet
    raise KeyboardInterrupt

signal.signal(signal.SIGTERM, handle_sigterm)

#parse arguments, verify the terminal, and acquire a lock
def main():
    parser = argparse.ArgumentParser(description="LakeEffect Blizzard")
    parser.add_argument("--duration", type=int, default=300)
    parser.add_argument("--delay", type=int, default=5)
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be greater than zero")

    def check_trigger():
        trigger = Path("/etc/bash/LakeEffect/trigger.txt")
        return trigger.is_file()

    if not sys.stdout.isatty():
        print("LakeEffect requires an interactive terminal.")
        return

    lock_file = acquire_terminal_lock()

    if lock_file is None:
        return

#snow go light, heavy, heavier, BLIZZARD
#the try/finally block makes it start after a beginning delay
    try:
        #wait until the trigger file exists
        while not check_trigger():
            time.sleep(0.5)
    
        #trigger detected, begin the startup delay
        time.sleep(max(0, args.delay))
    
        #start the snowfall timer
        started = time.monotonic()

        while time.monotonic() - started < args.duration:
            elapsed = time.monotonic() - started

            #smoothstep progression with simulated wind gusts
            flakes_per_cycle, interval = snowfall_settings(
                elapsed, args.duration
            )

            columns, rows = shutil.get_terminal_size()

            for _ in range(flakes_per_cycle):
                x = random.randint(1, max(1, columns - 1))
                y = random.randint(1, max(1, rows - 2))
                flake = random.choice(FLAKES)

                #save cursor, draw flake, restore cursor
                sys.stdout.write(
                    f"\0337\033[{y};{x}H{flake}\0338"
                )

            sys.stdout.flush()
            time.sleep(interval)

    except KeyboardInterrupt:
        pass
    finally:
        #reset formatting without clearing the terminal
        #release the lock
        sys.stdout.write("\033[0m")
        sys.stdout.flush()
        lock_file.close()


if __name__ == "__main__":
    main()
