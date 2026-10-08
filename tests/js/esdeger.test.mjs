// Python CLI ve tarayıcı doğrulayıcısı aynı girdilerde AYNI sonucu veriyor mu?
// 1) docs/ornek/ örnekleri: panelde örnek düğmesine tıklanır, sonuç Python'unkiyle
//    alan alan karşılaştırılır (gerçek kullanıcı yolu, headless Chrome).
// 2) Geçerli örnekten türetilen bozulma matrisi: aynı baytlar Python'a (diskte)
//    ve Chrome'daki dogrulayici.js'e verilir.
import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync, unlinkSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative } from 'node:path';
import { after, before, describe, test } from 'node:test';

import { DOCS, chromeYolu, hatalariTopla, pythonDogrula, sunucuBaslat, tarayiciAc } from './ortak.mjs';

const ORNEK = join(DOCS, 'ornek');
const manifest = JSON.parse(readFileSync(join(ORNEK, 'ornekler.json'), 'utf8'));
const KOK_ANAHTAR = join(ORNEK, manifest.kok_anahtar);

function dosyalariTopla(dizin) {
  const cikti = [];
  const yuru = (d) => {
    for (const ad of readdirSync(d)) {
      const tam = join(d, ad);
      if (statSync(tam).isDirectory()) yuru(tam);
      else cikti.push(relative(dizin, tam).split('\\').join('/'));
    }
  };
  yuru(dizin);
  return cikti.sort();
}

describe('Python ⇄ tarayıcı eşdeğerliği', { skip: !chromeYolu() && 'Chrome bulunamadı' }, () => {
  let sunucu, url, tarayici, sayfa, hatalar;
  const gecici = mkdtempSync(join(tmpdir(), 'imzali-depo-esdeger-'));

  before(async () => {
    ({ sunucu, url } = await sunucuBaslat());
    tarayici = await tarayiciAc();
    sayfa = await tarayici.newPage();
    hatalar = hatalariTopla(sayfa);
    await sayfa.goto(url, { waitUntil: 'networkidle0' });
    await sayfa.waitForFunction(() => window.__panelDurumu === 'hazir');
  });
  after(async () => {
    await tarayici?.close();
    sunucu?.close();
    rmSync(gecici, { recursive: true, force: true });
  });

  for (const o of manifest.ornekler) {
    test(`örnek "${o.id}": panel düğmesi = Python CLI`, async () => {
      const py = pythonDogrula(join(ORNEK, o.dizin), KOK_ANAHTAR);
      await sayfa.evaluate(() => { window.__sonSonuc = null; });
      await sayfa.click(`button[data-ornek="${o.id}"]`);
      await sayfa.waitForFunction(() => window.__sonSonuc && window.__panelDurumu === 'hazir');
      const js = await sayfa.evaluate(() => window.__sonSonuc);
      assert.deepEqual(js, py);
      assert.equal(py.gecerli, o.beklenen === 'gecerli', 'örneğin beklenen sonucu');
      // arayüz de aynı şeyi söylüyor mu?
      const ozet = await sayfa.$eval('#ozet', (e) => e.dataset.durum);
      assert.equal(ozet, py.gecerli ? 'tamam' : 'red');
      const kirmizi = await sayfa.$$eval('#satirlar tr[data-durum="red"]', (t) => t.map((x) => x.dataset.kod));
      const beklenenKirmizi = [py.indeks, ...py.dosyalar].filter((d) => d.kod !== 'TAMAM').map((d) => d.kod);
      assert.deepEqual(kirmizi, beklenenKirmizi);
    });
  }

  // ---- bozulma matrisi (geçerli örnekten) ----
  const BOZULMALAR = {
    'sağlam (kontrol)': () => {},
    'indekste 1 bayt': (d) => {
      const y = join(d, 'index.json');
      const b = readFileSync(y); b[b.indexOf('"surum"') + 10] ^= 1; writeFileSync(y, b);
    },
    'dosyada 1 bit': (d) => {
      const y = join(d, 'paketler/ornek-arac_1.2.0_arm64.bin');
      const b = readFileSync(y); b[7] ^= 0x80; writeFileSync(y, b);
    },
    'dosya kısaltıldı': (d) => {
      const y = join(d, 'SURUMLER.txt'); writeFileSync(y, readFileSync(y).subarray(0, 10));
    },
    'dosya silindi + imzasız eklendi': (d) => {
      unlinkSync(join(d, 'belgeler/kurulum.md')); writeFileSync(join(d, 'zz-ek.txt'), 'ek');
    },
    'imza kesildi': (d) => writeFileSync(join(d, 'index.json.sig'), readFileSync(join(d, 'index.json.sig'), 'utf8').slice(0, 40)),
    'imza başka imzayla değişti': (d) => writeFileSync(join(d, 'index.json.sig'), readFileSync(join(ORNEK, 'dondurulmus', 'index.json.sig'))),
    'indeks JSON değil': (d) => writeFileSync(join(d, 'index.json'), '{bozuk'),
    'yanlış kök anahtar': () => 'ZINCIRSIZ',
  };

  for (const [ad, boz] of Object.entries(BOZULMALAR)) {
    test(`bozulma "${ad}": Python = tarayıcı`, async () => {
      const d = mkdtempSync(join(gecici, 'v-'));
      cpSync(join(ORNEK, 'gecerli'), d, { recursive: true });
      const isaret = boz(d);
      // yanlış anahtar: döndürülmüş örneğin indeksindeki yeni anahtarı kök sanmak yerine,
      // gerçekten ilgisiz bir anahtar: dondurulmus zincirindeki ikinci anahtar
      let anahtarYolu = KOK_ANAHTAR;
      if (isaret === 'ZINCIRSIZ') {
        const kayit = JSON.parse(JSON.parse(readFileSync(join(ORNEK, 'dondurulmus', 'index.json'), 'utf8')).anahtar_zinciri[0].kayit);
        const ham = Buffer.from(kayit.yeni_acik_anahtar, 'base64');
        const der = Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), ham]);
        anahtarYolu = join(d, '..', `yanlis-${Date.now()}.pub`);
        writeFileSync(anahtarYolu, `-----BEGIN PUBLIC KEY-----\n${der.toString('base64')}\n-----END PUBLIC KEY-----\n`);
      }
      const py = pythonDogrula(d, anahtarYolu);
      const adlar = dosyalariTopla(d).filter((a) => a !== 'index.json' && a !== 'index.json.sig');
      const veri = {
        indeks: readFileSync(join(d, 'index.json')).toString('base64'),
        imza: readFileSync(join(d, 'index.json.sig')).toString('base64'),
        anahtar: readFileSync(anahtarYolu, 'utf8'),
        dosyalar: Object.fromEntries(adlar.map((a) => [a, readFileSync(join(d, a)).toString('base64')])),
      };
      const js = await sayfa.evaluate(async (v) => {
        const m = await import('./dogrulayici.js');
        const coz = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
        return m.dogrula({
          indeksBaytlari: coz(v.indeks),
          imzaBaytlari: coz(v.imza),
          kok: await m.AcikAnahtar.pemden(v.anahtar),
          dosyaGetir: async (ad) => (ad in v.dosyalar ? coz(v.dosyalar[ad]) : null),
          mevcutAdlar: Object.keys(v.dosyalar),
        });
      }, veri);
      assert.deepEqual(js, py);
      assert.equal(py.gecerli, ad.startsWith('sağlam'), `beklenmeyen karar: ${JSON.stringify(py.indeks)}`);
    });
  }

  test('konsol hatası yok', () => assert.deepEqual(hatalar, []));
});
