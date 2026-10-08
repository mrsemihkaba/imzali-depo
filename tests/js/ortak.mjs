// Ortak test altyapısı: statik sunucu (alt yol taklidi), Chrome, Python CLI.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const KOK = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
export const DOCS = join(KOK, 'docs');
export const ALT_YOL = '/imzali-depo/';

export function python() {
  if (process.env.IMZALI_DEPO_PYTHON) return process.env.IMZALI_DEPO_PYTHON;
  const venv = join(KOK, '.venv', 'bin', 'python');
  return existsSync(venv) ? venv : 'python3';
}

export function cli(args, ortam = {}) {
  const r = spawnSync(python(), ['-m', 'imzali_depo', ...args], {
    cwd: KOK, encoding: 'utf8', env: { ...process.env, PYTHONPATH: KOK, ...ortam },
  });
  if (r.error) throw r.error;
  return r;
}

/** Python doğrulayıcısının JSON sonucu */
export function pythonDogrula(dizin, anahtar, ek = []) {
  const r = cli(['dogrula', dizin, '--acik-anahtar', anahtar, '--json', ...ek]);
  if (r.status !== 0 && r.status !== 1) throw new Error(`CLI çöktü (${r.status}): ${r.stderr}`);
  return JSON.parse(r.stdout);
}

export function chromeYolu() {
  const adaylar = [process.env.CHROME_YOLU, '/usr/bin/google-chrome-stable', '/usr/bin/google-chrome', '/usr/bin/chromium'];
  return adaylar.find((a) => a && existsSync(a));
}

const TURLER = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml',
};

/** docs/ klasörünü GitHub Pages gibi /imzali-depo/ alt yolunda sunar. */
export function sunucuBaslat(kok = DOCS) {
  const sunucu = createServer((istek, yanit) => {
    const url = new URL(istek.url, 'http://x');
    if (!url.pathname.startsWith(ALT_YOL)) { yanit.writeHead(404).end('alt yol dışı'); return; }
    let yol = decodeURIComponent(url.pathname.slice(ALT_YOL.length)) || 'index.html';
    const tam = normalize(join(kok, yol));
    if (!tam.startsWith(kok)) { yanit.writeHead(403).end(); return; }
    let hedef = tam;
    try { if (statSync(hedef).isDirectory()) hedef = join(hedef, 'index.html'); } catch { /* 404 */ }
    if (!existsSync(hedef)) { yanit.writeHead(404).end('yok'); return; }
    yanit.writeHead(200, { 'content-type': TURLER[extname(hedef)] || 'application/octet-stream' });
    yanit.end(readFileSync(hedef));
  });
  return new Promise((ok) => sunucu.listen(0, '127.0.0.1', () => ok({
    sunucu, url: `http://127.0.0.1:${sunucu.address().port}${ALT_YOL}`,
  })));
}

export async function tarayiciAc() {
  const puppeteer = (await import('puppeteer-core')).default;
  return puppeteer.launch({
    executablePath: chromeYolu(),
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check'],
  });
}

/** Konsol hatalarını ve sayfa istisnalarını toplar. */
export function hatalariTopla(sayfa) {
  const hatalar = [];
  sayfa.on('console', (m) => { if (m.type() === 'error') hatalar.push(m.text()); });
  sayfa.on('pageerror', (e) => hatalar.push(String(e)));
  sayfa.on('requestfailed', (r) => hatalar.push(`istek başarısız: ${r.url()}`));
  return hatalar;
}
