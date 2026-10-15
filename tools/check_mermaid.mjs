// Install mermaid@11.12.0 and jsdom@26.1.0 in a temporary prefix; pass its node_modules path.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import crypto from 'node:crypto';
const modules = process.argv[2];
if (!modules) throw new Error('Usage: node check_mermaid.mjs /absolute/path/to/node_modules');
const {JSDOM} = await import(pathToFileURL(path.join(modules, 'jsdom/lib/api.js')));
const dom = new JSDOM('');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const {default: mermaid} = await import(pathToFileURL(path.join(modules, 'mermaid/dist/mermaid.esm.mjs')));
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const files = {};
for (const name of fs.readdirSync(path.join(root, 'diagrams')).filter(name => name.endsWith('.mmd')).sort()) {
  const source = fs.readFileSync(path.join(root, 'diagrams', name), 'utf8');
  await mermaid.parse(source);
  files[name] = crypto.createHash('sha256').update(source).digest('hex');
  console.log(`PASS ${name}`);
}
const version = name => JSON.parse(fs.readFileSync(path.join(modules, name, 'package.json'), 'utf8')).version;
fs.writeFileSync(path.join(root, 'evidence/mermaid-validation.json'), JSON.stringify({
  validatedAt: new Date().toISOString(), parser: `mermaid ${version('mermaid')}`,
  dom: `jsdom ${version('jsdom')}`, result: `all ${Object.keys(files).length} diagrams parsed`, files
}, null, 2) + '\n');
