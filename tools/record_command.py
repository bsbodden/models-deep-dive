#!/usr/bin/env python3
"""Show the command that the recording is about to execute, then replace this process."""
import os
from pathlib import Path
import shlex
import sys

source = Path(sys.argv[1])
if source.name != str(source) or source.suffix != '.java' or not source.is_file():
    raise SystemExit('Expected a Java filename in the current walkthrough directory')
command = ['jbang', source.name]
print('$ ' + shlex.join(command), flush=True)
os.execvp(command[0], command)
