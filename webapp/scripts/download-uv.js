const fs = require('fs');
const path = require('path');
const https = require('https');
const { createGunzip } = require('zlib');
const { pipeline } = require('stream/promises');

const UV_VERSION = '0.4.40';
const BASE = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}`;

const PLATFORMS = {
  'win32-x64': { artifact: `uv-x86_64-pc-windows-msvc.zip`, ext: 'zip', name: 'uv.exe' },
  'linux-x64': { artifact: `uv-x86_64-unknown-linux-gnu.tar.gz`, ext: 'tgz', name: 'uv' },
  'linux-arm64': { artifact: `uv-aarch64-unknown-linux-gnu.tar.gz`, ext: 'tgz', name: 'uv' },
  'darwin-x64': { artifact: `uv-x86_64-apple-darwin.tar.gz`, ext: 'tgz', name: 'uv' },
  'darwin-arm64': { artifact: `uv-aarch64-apple-darwin.tar.gz`, ext: 'tgz', name: 'uv' }
};

function download(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { redirect: true, headers: { 'User-Agent': 'curl/7.68.0' } }, (res) => {
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
    }).on('error', reject);
  });
}

function extractTarball(buf, outDir) {
  const tar = require('tar');
  return tar.extract({
    cwd: outDir,
    file: path.join(outDir, 'uv.tar.gz'),
    strip: 1
  }).catch(() => {
    fs.writeFileSync(path.join(outDir, 'uv.tar.gz'), buf);
    return tar.extract({
      cwd: outDir,
      file: path.join(outDir, 'uv.tar.gz'),
      strip: 1
    }).finally(() => {
      try { fs.unlinkSync(path.join(outDir, 'uv.tar.gz')); } catch (_) {}
    });
  });
}

async function extractZip(buf, outDir) {
  const AdmZip = require('adm-zip');
  const zip = new AdmZip(buf);
  const entries = zip.getEntries();
  const uvEntry = entries.find(e => e.entryName.endsWith('uv.exe'));
  if (!uvEntry) throw new Error('uv.exe not found in zip');
  fs.mkdirSync(outDir, { recursive: true });
  zip.extractEntryTo(uvEntry, outDir, false, true);
  const extracted = path.join(outDir, path.basename(uvEntry.entryName));
  const dest = path.join(outDir, 'uv.exe');
  if (extracted !== dest) fs.renameSync(extracted, dest);
}

async function main() {
  const root = path.join(__dirname, '..');
  const resourcesDir = path.join(root, 'resources', 'bin');
  const buildAll = process.argv.includes('--all');

  const platforms = buildAll
    ? Object.keys(PLATFORMS)
    : [process.platform === 'win32' ? 'win32-x64' : process.platform + '-' + process.arch];

  for (const key of platforms) {
    const cfg = PLATFORMS[key];
    if (!cfg) {
      console.warn(`[download-uv] Skip unknown platform: ${key}`);
      continue;
    }
    const [plat, arch] = key.split('-');
    const outDir = path.join(resourcesDir, plat);
    if (plat === 'darwin') {
      const sub = path.join(outDir, arch === 'arm64' ? 'arm64' : 'x64');
      fs.mkdirSync(sub, { recursive: true });
    }
    const targetDir = path.join(outDir, plat === 'darwin' ? (arch === 'arm64' ? 'arm64' : 'x64') : '');
    if (plat !== 'darwin') fs.mkdirSync(outDir, { recursive: true });

    const url = `${BASE}/${cfg.artifact}`;
    console.log(`[download-uv] Fetching ${cfg.artifact}...`);
    const buf = await download(url);

    const extractDir = path.join(outDir, 'tmp');
    fs.mkdirSync(extractDir, { recursive: true });
    try {
      if (cfg.ext === 'zip') {
        await extractZip(buf, extractDir);
      } else {
        fs.writeFileSync(path.join(extractDir, 'uv.tar.gz'), buf);
        const tar = require('tar');
        await tar.extract({
          cwd: extractDir,
          file: path.join(extractDir, 'uv.tar.gz'),
          strip: 1
        });
      }
      const src = path.join(extractDir, cfg.name);
      const destDir = plat === 'darwin' ? path.join(outDir, arch === 'arm64' ? 'arm64' : 'x64') : outDir;
      const dest = path.join(destDir, cfg.name);
      fs.mkdirSync(destDir, { recursive: true });
      fs.renameSync(src, dest);
    } finally {
      try { fs.rmSync(extractDir, { recursive: true }); } catch (_) {}
    }
    console.log(`[download-uv] ${key} -> ${path.relative(root, destDir)}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
