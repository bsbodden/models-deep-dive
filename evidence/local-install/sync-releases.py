"""Populate Maven Local with the exact verified Central release artifacts."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import urllib.request
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
coordinates = json.loads((root / 'coordinates.json').read_text())
repository = Path.home() / '.m2/repository'

def sync(entry):
    group, artifact, version = entry['coordinate'].split(':')
    relative = Path(group.replace('.', '/')) / artifact / version
    staged = root / 'downloads' / relative
    staged.mkdir(parents=True, exist_ok=True)
    files = []
    for extension in ['jar', 'pom', 'module']:
        name = f'{artifact}-{version}.{extension}'
        url = 'https://repo.maven.apache.org/maven2/' + str(relative / name)
        target = staged / name
        with urllib.request.urlopen(url, timeout=180) as response, target.open('wb') as output:
            shutil.copyfileobj(response, output)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        assert digest == entry['files'][extension], (entry['coordinate'], extension)
        files.append((target, digest))
    destination = repository / relative
    destination.mkdir(parents=True, exist_ok=True)
    changes = []
    for source, digest in files:
        target = destination / source.name
        previous = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        if previous != digest:
            if target.exists():
                backup = root / 'previous' / relative / source.name
                backup.parent.mkdir(parents=True, exist_ok=True)
                assert not backup.exists(), backup
                shutil.copy2(target, backup)
            temporary = destination / (source.name + '.release-sync')
            shutil.copy2(source, temporary)
            temporary.replace(target)
        changes.append({'file': str(target), 'sha256': digest, 'previousSha256': previous})
    print(entry['coordinate'] + ': verified and installed', flush=True)
    return {'coordinate': entry['coordinate'], 'files': changes}

with ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(sync, coordinates))
(root / 'maven-local-receipt.json').write_text(json.dumps({
    'updatedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'repository': str(repository), 'source': 'Maven Central', 'artifacts': results,
}, indent=2) + '\n')
project = ET.Element('project', xmlns='http://maven.apache.org/POM/4.0.0')
for key, value in [('modelVersion', '4.0.0'), ('groupId', 'local.release.verification'),
                   ('artifactId', 'installed-release-train'), ('version', '1')]:
    ET.SubElement(project, key).text = value
dependencies = ET.SubElement(project, 'dependencies')
for entry in coordinates:
    group, artifact, version = entry['coordinate'].split(':')
    dependency = ET.SubElement(dependencies, 'dependency')
    for key, value in [('groupId', group), ('artifactId', artifact), ('version', version)]:
        ET.SubElement(dependency, key).text = value
ET.ElementTree(project).write(root / 'pom.xml', encoding='utf-8', xml_declaration=True)
