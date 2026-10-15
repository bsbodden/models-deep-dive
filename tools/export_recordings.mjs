// Export actual casts through the shared Vectors terminal player. Serve the article root locally.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
const [modules, chrome, baseUrl, only] = process.argv.slice(2);
if (!modules || !chrome || !baseUrl) throw new Error('Usage: node export_recordings.mjs NODE_MODULES CHROME LOCAL_BASE_URL');
const {default: puppeteer} = await import(pathToFileURL(path.join(modules, 'puppeteer/lib/esm/puppeteer/puppeteer.js')));
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const receipts = JSON.parse(fs.readFileSync(path.join(root, 'evidence/released-run/runs.json'), 'utf8'));
const sources = fs.readdirSync(path.join(root, 'code')).filter(name => name.endsWith('.java')).sort();
const recorded = receipts.map(run => run.script).sort();
if (JSON.stringify(sources) !== JSON.stringify(recorded) || receipts.some(run => run.exitCode !== 0)) {
  throw new Error('Every article source must have a successful released-run receipt before export');
}
const hash = filename => crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
for (const run of receipts) {
  if (hash(path.join(root, 'code', run.script)) !== run.sha256 ||
      hash(path.join(root, 'evidence/released-run', run.cast)) !== run.castSha256) {
    throw new Error(`${run.script}: source or cast changed since the recorded run`);
  }
}
const browser = await puppeteer.launch({executablePath: chrome, headless: true});
const output = path.join(root, 'recordings');
const receiptPath = path.join(root, 'evidence/video-exports.json');
const exports = only && fs.existsSync(receiptPath) ? JSON.parse(fs.readFileSync(receiptPath, 'utf8')).filter(run => run.script !== only + '.java') : [];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
try {
  for (const run of receipts.filter(run => !only || run.script === only + '.java')) {
    const name = run.script.replace('.java', '');
    const stem = run.cast.replace('.cast', '');
    const page = await browser.newPage();
    await page.setViewport({width: 1920, height: 1080, deviceScaleFactor: 1});
    await page.goto(`${baseUrl}/recordings/index.html?demo=${name}&export=1`, {waitUntil: 'networkidle0'});
    await page.waitForFunction(async () => window.player && (await window.player.getDuration()) > 0, {timeout: 30000});
    const webm = path.join(output, stem + '.webm');
    const mp4 = path.join(output, stem + '.mp4');
    const poster = path.join(output, stem + '.png');
    const capture = name === 'speech' ? path.join(output, stem + '-terminal.webm') : webm;
    const recorder = await page.screencast({path: capture});
    const started = Date.now();
    await page.evaluate(() => window.player.play());
    await page.waitForFunction(() => window.playerEnded || window.playbackError, {timeout: 300000});
    const playbackEndSeconds = (Date.now() - started) / 1000;
    const error = await page.evaluate(() => window.playbackError);
    if (error) throw new Error(`${name}: ${error}`);
    await page.screenshot({path: poster});
    await delay(2500);
    await recorder.stop();
    await page.close();
    let audioStartsAtSeconds = null;
    if (name === 'speech') {
      const probe = spawnSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-show_packets', '-show_entries', 'packet=pts_time,duration_time', '-of', 'json', capture], {encoding: 'utf8'});
      if (probe.status !== 0) throw new Error('Cannot read captured speech duration');
      // Place the generated voice in the final hold using the encoded timeline, not browser wall time.
      const packetEnd = Math.max(...JSON.parse(probe.stdout).packets.map(packet => Number(packet.pts_time) + Number(packet.duration_time || 0)));
      if (!Number.isFinite(packetEnd) || packetEnd <= 2.5) throw new Error('Invalid captured speech timeline');
      audioStartsAtSeconds = packetEnd - 2.5;
      const audio = spawnSync('ffmpeg', ['-y', '-i', capture, '-i', path.join(output, 'speech.wav'),
        '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'libopus',
        '-af', `adelay=${Math.round(audioStartsAtSeconds * 1000)}:all=1,apad`, '-shortest', webm], {encoding: 'utf8'});
      fs.writeFileSync(path.join(output, stem + '-audio.log'), audio.stderr || '');
      if (audio.status !== 0) throw new Error('Cannot attach generated speech audio');
    }
    const ffmpegArgs = ['-y', '-i', webm];
    if (name === 'speech') ffmpegArgs.push('-c:a', 'aac');
    else ffmpegArgs.push('-an');
    ffmpegArgs.push('-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', mp4);
    const encoded = spawnSync('ffmpeg', ffmpegArgs, {encoding: 'utf8'});
    fs.writeFileSync(path.join(output, stem + '-encode.log'), encoded.stderr || '');
    if (encoded.status !== 0) throw new Error(`${name}: ffmpeg failed`);
    exports.push({script: run.script, sourceSha256: run.sha256, cast: run.cast, castSha256: run.castSha256,
      idleTimeLimit: 3, playbackSpeed: 1, playbackEndSeconds,
      files: [webm, mp4, poster].map(file => ({name: path.basename(file), sha256: hash(file)})),
      audio: name === 'speech' ? {file: 'speech.wav', sha256: hash(path.join(output, 'speech.wav')), startsAtSeconds: audioStartsAtSeconds} : null});
    exports.sort((a, b) => a.cast.localeCompare(b.cast));
    fs.writeFileSync(receiptPath, JSON.stringify(exports, null, 2) + '\n');
    console.log(`Exported ${stem}`, {audio: name === 'speech'});
  }
} finally { await browser.close(); }
