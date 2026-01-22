const fs = require('fs');
const path = require('path');
const https = require('https');

const UV_VERSION = '0.4.30';
const BASE = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}`;

const PLATFORMS = {
  'win32-x64': { artifact: 'uv-x86_64-pc-windows-msvc.zip', ext: 'zip', name: 'uv.exe' },
  'linux-x64': { artifact: 'uv-x86_64-unknown-linux-gnu.tar.gz', ext: 'tgz', name: 'uv' },
  'linux-arm64': { artifact: 'uv-aarch64-unknown-linux-gnu.tar.gz', ext: 'tgz', name: 'uv' },
  'darwin-x64': { artifact: 'uv-x86_64-apple-darwin.tar.gz', ext: 'tgz', name: 'uv' },
  'darwin-arm64': { artifact: 'uv-aarch64-apple-darwin.tar.gz', ext: 'tgz', name: 'uv' }
};

function download(url) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': 'Node' } }, (res) => {
      if (res.statusCode === 301 || res.statusCode === 302) {
        download(res.headers.location).then(resolve).catch(reject);
        return;
      }
      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode}: ${url}`));
        return;
      }
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => resolve(Buffer.concat(chunks)));
      res.on('error', reject);
    });
    req.on('error', reject);
  });
}

function findUvInDir(dir, name) {
  if (!fs.existsSync(dir)) return null;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isFile() && e.name === name) return full;
    if (e.isDirectory()) {
      const found = findUvInDir(full, name);
      if (found) return found;
    }
  }
  return null;
}

async function main() {
  const root = path.join(__dirname, '..');
  const resourcesDir = path.join(root, 'resources', 'bin');
  const buildAll = process.argv.includes('--all');
  const key = process.platform === 'win32' ? 'win32-x64' : process.platform + '-' + process.arch;
  const platforms = buildAll ? Object.keys(PLATFORMS) : (PLATFORMS[key] ? [key] : []);

  if (platforms.length === 0) {
    console.warn('[download-uv] No platform to download for:', process.platform, process.arch);
    return;
  }

  const tar = require('tar');
  const extractZip = require('extract-zip');

  for (const k of platforms) {
    const cfg = PLATFORMS[k];
    const outDir = path.join(resourcesDir, k);
    fs.mkdirSync(outDir, { recursive: true });
    const url = `${BASE}/${cfg.artifact}`;
    console.log('[download-uv] Fetching', cfg.artifact);
    const buf = await download(url);

    const tmpDir = path.join(outDir, '.tmp');
    fs.mkdirSync(tmpDir, { recursive: true });
    try {
      if (cfg.ext === 'zip') {
        const zipPath = path.join(tmpDir, 'uv.zip');
        fs.writeFileSync(zipPath, buf);
        await extractZip(zipPath, { dir: tmpDir });
        const src = findUvInDir(tmpDir, 'uv.exe');
        if (!src) throw new Error('uv.exe not found in zip');
        fs.renameSync(src, path.join(outDir, 'uv.exe'));
      } else {
        const tgz = path.join(tmpDir, 'uv.tar.gz');
        fs.writeFileSync(tgz, buf);
        await tar.extract({ cwd: tmpDir, file: tgz, strip: 1 });
        const src = findUvInDir(tmpDir, 'uv');
        if (!src) throw new Error('uv not found in tarball');
        fs.chmodSync(src, 0o755);
        fs.renameSync(src, path.join(outDir, 'uv'));
      }
      console.log('[download-uv]', k, '->', path.join('resources', 'bin', k));
    } finally {
      try { fs.rmSync(tmpDir, { recursive: true }); } catch (_) {}
    }
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
