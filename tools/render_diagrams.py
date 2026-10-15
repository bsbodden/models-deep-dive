#!/usr/bin/env python3
"""Render the editable Mermaid sources to SVG and PNG and retain content hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--mmdc', required=True, type=Path)
parser.add_argument('--chrome', required=True, type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
receipts = []
with tempfile.TemporaryDirectory(prefix='models-article-render-') as temporary:
    browser = Path(temporary) / 'puppeteer.json'
    browser.write_text(json.dumps({'executablePath': str(args.chrome.resolve())}))
    for source in sorted((root / 'diagrams').glob('*.mmd')):
        for extension in ['svg', 'png']:
            output = source.with_suffix('.' + extension)
            command = [str(args.mmdc.resolve()), '-i', str(source), '-o', str(output),
                       '-c', str(root / 'diagrams/render-config.json'), '-p', str(browser),
                       '-b', 'white', '-w', '1400', '-s', '2']
            subprocess.run(command, check=True)
            receipts.append({'source': source.name,
                'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'render': output.name, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()})
(root / 'evidence/diagram-renders.json').write_text(json.dumps(receipts, indent=2) + '\n')
