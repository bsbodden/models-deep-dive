#!/usr/bin/env python3
"""Run the exact article sources sequentially and retain logs, hashes and optional raw casts."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--output", required=True, type=Path, help="New evidence directory")
parser.add_argument("--record", action="store_true", help="Also retain unretimed asciicast v2 recordings")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
order = "chat safetensors embed rerank tools composite decisions speech spring route rag gemma bonsai".split()
versions = {}
for command in [["java", "-version"], ["jbang", "version"], ["modeljars", "version"]]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    versions[" ".join(command)] = {"exitCode": result.returncode, "output": result.stdout}
(output / "environment.json").write_text(json.dumps(versions, indent=2) + "\n")
results = []
for index, name in enumerate(order, 1):
    source = root / "code" / (name + ".java")
    command = ["jbang", source.name]
    log = output / (name + ".log")
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if args.record:
        cast = output / f"{index:02d}-{name}.cast"
        execution = ["asciinema", "record", "--headless", "--return", "-f", "asciicast-v2",
                     "--window-size", "120x36", "--capture-env", "SHELL", "--title", " ".join(command) + " — weights cached",
                     "-c", shlex.join(["python3", str(root / "tools/record_command.py"), source.name]), str(cast)]
        with (output / (name + "-recorder.log")).open("w") as stream:
            result = subprocess.run(execution, cwd=root / "code", stdout=stream, stderr=subprocess.STDOUT)
        if cast.exists():
            events = [json.loads(line) for line in cast.read_text().splitlines()[1:]]
            log.write_text("".join(event[2] for event in events if event[1] == "o"))
    else:
        with log.open("w") as stream:
            result = subprocess.run(command, cwd=root / "code", stdout=stream, stderr=subprocess.STDOUT)
    receipt = {"script": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "command": command, "startedAt": started,
               "finishedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "exitCode": result.returncode, "log": log.name,
               "dependencies": [line.removeprefix("//DEPS ") for line in source.read_text().splitlines()
                                if line.startswith("//DEPS ")]}
    if args.record and cast.exists():
        receipt["cast"] = cast.name
        receipt["castSha256"] = hashlib.sha256(cast.read_bytes()).hexdigest()
    results.append(receipt)
    (output / "runs.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"{name}: exit {result.returncode}", flush=True)
raise SystemExit(any(result["exitCode"] != 0 for result in results))
