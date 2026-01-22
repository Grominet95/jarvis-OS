const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const root = path.join(__dirname, '..');
const src = root;
const dst = path.join(root, 'resources', 'python-project');

const FILES = ['bot.py', 'pyproject.toml', 'start_bot.py', 'env.example'];

function main() {
  fs.mkdirSync(dst, { recursive: true });
  for (const f of FILES) {
    const s = path.join(src, f);
    const d = path.join(dst, f);
    if (fs.existsSync(s)) {
      fs.copyFileSync(s, d);
      console.log('[prepare-build] Copied', f);
    }
  }
  try {
    execSync('uv lock', { cwd: dst, stdio: 'inherit' });
    console.log('[prepare-build] uv lock done');
  } catch (e) {
    console.warn('[prepare-build] uv lock failed (optional):', e.message);
  }
}

main();
