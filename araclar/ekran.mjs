// docs/ekran.png: panelin gerçek headless Chrome ekran görüntüsü (1280×800).
// Kullanım: npm run ekran   (ya da: node araclar/ekran.mjs [ornek-id] [mobil])
import { join } from 'node:path';
import { DOCS, hatalariTopla, sunucuBaslat, tarayiciAc } from '../tests/js/ortak.mjs';

const ornek = process.argv[2] || 'bozuk';
const mobil = process.argv[3] === 'mobil';
const { sunucu, url } = await sunucuBaslat();
const tarayici = await tarayiciAc();
try {
  const sayfa = await tarayici.newPage();
  const hatalar = hatalariTopla(sayfa);
  await sayfa.setViewport(mobil ? { width: 375, height: 812, deviceScaleFactor: 2 } : { width: 1280, height: 800, deviceScaleFactor: 1 });
  await sayfa.goto(url, { waitUntil: 'networkidle0' });
  await sayfa.waitForFunction(() => window.__panelDurumu === 'hazir');
  await sayfa.click(`button[data-ornek="${ornek}"]`);
  await sayfa.waitForFunction(() => window.__sonSonuc && window.__panelDurumu === 'hazir');
  // Sonuç bölümü görünsün diye başlığın biraz altından başlat
  await sayfa.evaluate(() => document.querySelector('#b-ornek').scrollIntoView());
  const hedef = mobil ? process.argv[4] || 'ekran-mobil.png' : join(DOCS, 'ekran.png');
  await sayfa.screenshot({ path: hedef });
  console.log(`yazıldı: ${hedef} · konsol hataları: ${hatalar.length}`);
  if (hatalar.length) { console.error(hatalar); process.exitCode = 1; }
} finally {
  await tarayici.close();
  sunucu.close();
}
