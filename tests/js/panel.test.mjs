// Panelin kullanıcı yolları: dosya seçme, klavye, Ed25519 desteği olmayan tarayıcı
// ve tarayıcı tarafı kontrol grubu.
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, before, describe, test } from 'node:test';

import { chromeYolu, cli, hatalariTopla, sunucuBaslat, tarayiciAc } from './ortak.mjs';

const bekle = (sayfa) => sayfa.waitForFunction(() => window.__sonSonuc && window.__panelDurumu === 'hazir');

describe('panel', { skip: !chromeYolu() && 'Chrome bulunamadı' }, () => {
  let sunucu, url, tarayici;
  const gecici = mkdtempSync(join(tmpdir(), 'imzali-depo-panel-'));

  before(async () => {
    ({ sunucu, url } = await sunucuBaslat());
    tarayici = await tarayiciAc();
  });
  after(async () => {
    await tarayici?.close();
    sunucu?.close();
    rmSync(gecici, { recursive: true, force: true });
  });

  async function yeniSayfa(onceki) {
    const sayfa = await tarayici.newPage();
    const hatalar = hatalariTopla(sayfa);
    if (onceki) await sayfa.evaluateOnNewDocument(onceki);
    await sayfa.goto(url, { waitUntil: 'networkidle0' });
    await sayfa.waitForFunction(() => window.__panelDurumu === 'hazir');
    return { sayfa, hatalar };
  }

  test('dosya seçerek doğrulama: geçerli → yeşil, 1 bayt bozuk → kırmızı', async () => {
    // CLI ile geçici (düz) bir depo ve test anahtarı üret; özel anahtar tmp'de kalır ve silinir.
    const ortam = { IMZALI_DEPO_PAROLA: 'yalniz-test-' + process.pid };
    const d = join(gecici, 'depo');
    mkdirSync(d);
    writeFileSync(join(d, 'arac.bin'), Buffer.from(Array.from({ length: 5000 }, (_, i) => (i * 31) & 255)));
    writeFileSync(join(d, 'notlar.txt'), 'sentetik içerik\n');
    assert.equal(cli(['anahtar-uret', '--ozel', join(gecici, 't.key'), '--acik', join(gecici, 't.pub')], ortam).status, 0);
    assert.equal(cli(['imzala', d, '--ozel-anahtar', join(gecici, 't.key')], ortam).status, 0);
    const yollar = ['index.json', 'index.json.sig', 'arac.bin', 'notlar.txt'].map((a) => join(d, a));

    const { sayfa, hatalar } = await yeniSayfa();
    const girdi = await sayfa.$('#sec-dosya');
    await girdi.uploadFile(...yollar, join(gecici, 't.pub'));
    await bekle(sayfa);
    let s = await sayfa.evaluate(() => window.__sonSonuc);
    assert.equal(s.gecerli, true, JSON.stringify(s));
    assert.equal(s.dosyalar.length, 2);
    assert.equal(await sayfa.$eval('#ozet', (e) => e.dataset.durum), 'tamam');

    const b = readFileSync(join(d, 'arac.bin')); b[1234] ^= 1; writeFileSync(join(d, 'arac.bin'), b);
    await sayfa.click('#temizle');
    await sayfa.evaluate(() => { window.__sonSonuc = null; });
    await (await sayfa.$('#sec-dosya')).uploadFile(...yollar, join(gecici, 't.pub'));
    await bekle(sayfa);
    s = await sayfa.evaluate(() => window.__sonSonuc);
    assert.equal(s.gecerli, false);
    assert.deepEqual(s.dosyalar.map((x) => [x.ad, x.kod]), [['arac.bin', 'OZET_UYUSMAZ'], ['notlar.txt', 'TAMAM']]);
    assert.equal(await sayfa.$eval('#satirlar tr[data-kod="OZET_UYUSMAZ"] td', (e) => e.textContent), 'arac.bin');
    assert.deepEqual(hatalar, []);
    await sayfa.close();
  });

  test('klavyeyle örnek seçilebilir', async () => {
    const { sayfa, hatalar } = await yeniSayfa();
    await sayfa.focus('button[data-ornek="gecerli"]');
    await sayfa.keyboard.press('Tab'); // → dondurulmus
    await sayfa.keyboard.press('Enter');
    await bekle(sayfa);
    const s = await sayfa.evaluate(() => window.__sonSonuc);
    assert.equal(s.gecerli, true);
    assert.equal(s.indeks.zincir_uzunlugu, 1);
    assert.deepEqual(hatalar, []);
    await sayfa.close();
  });

  test('375 px mobilde yatay taşma yok', async () => {
    const { sayfa, hatalar } = await yeniSayfa();
    await sayfa.setViewport({ width: 375, height: 800, deviceScaleFactor: 1 });
    await sayfa.click('button[data-ornek="bozuk"]');
    await bekle(sayfa);
    const genislik = await sayfa.evaluate(() => document.documentElement.scrollWidth);
    assert.ok(genislik <= 375, `sayfa genişliği ${genislik}px`);
    assert.deepEqual(hatalar, []);
    await sayfa.close();
  });

  test('Ed25519 desteklemeyen tarayıcıda açık hata iletisi', async () => {
    const { sayfa } = await yeniSayfa(() => {
      const ad = (a) => (typeof a === 'string' ? a : a?.name || '').toLowerCase();
      for (const yontem of ['importKey', 'verify']) {
        const asil = SubtleCrypto.prototype[yontem];
        SubtleCrypto.prototype[yontem] = function (...args) {
          const alg = yontem === 'importKey' ? args[2] : args[0];
          if (ad(alg) === 'ed25519') return Promise.reject(new DOMException('Algorithm: Unrecognized name', 'NotSupportedError'));
          return asil.apply(this, args);
        };
      }
    });
    assert.equal(await sayfa.$eval('#destek-uyari', (e) => e.hidden), false);
    assert.match(await sayfa.$eval('#destek-uyari', (e) => e.textContent), /Ed25519 desteklemiyor/);
    await sayfa.click('button[data-ornek="gecerli"]');
    await bekle(sayfa);
    assert.equal(await sayfa.$eval('#ozet', (e) => e.dataset.durum), 'hata');
    assert.match(await sayfa.$eval('#ozet-metin', (e) => e.textContent), /Ed25519 desteklenmiyor/);
    await sayfa.close();
  });

  test('kontrol grubu: tarayıcıda imza doğrulaması kapatılırsa bozuk indeks GEÇER (yani testler gerçekten imzaya dayanıyor)', async () => {
    const kos = async (kapali) => {
      const { sayfa } = await yeniSayfa(kapali ? () => {
        const asil = SubtleCrypto.prototype.verify;
        SubtleCrypto.prototype.verify = async function (...a) {
          // destek sınamasını geçsin ama gerçek kararı yok saysın
          await asil.apply(this, a).catch(() => {});
          return true;
        };
      } : null);
      const sonuc = await sayfa.evaluate(async () => {
        const m = await import('./dogrulayici.js');
        const al = async (y) => new Uint8Array(await (await fetch(y)).arrayBuffer());
        const indeks = await al('ornek/gecerli/index.json');
        indeks[indeks.indexOf(0x37 /* '7' sürüm */)] = 0x39; // sürümü 7 → 9 yap
        const man = await (await fetch('ornek/ornekler.json')).json();
        const o = man.ornekler.find((x) => x.id === 'gecerli');
        return m.dogrula({
          indeksBaytlari: indeks,
          imzaBaytlari: await al('ornek/gecerli/index.json.sig'),
          kok: await m.AcikAnahtar.pemden(new TextDecoder().decode(await al('ornek/' + man.kok_anahtar))),
          dosyaGetir: (ad) => al('ornek/gecerli/' + ad),
          mevcutAdlar: o.dosyalar,
        });
      });
      await sayfa.close();
      return sonuc;
    };
    const normal = await kos(false);
    assert.equal(normal.gecerli, false);
    assert.equal(normal.indeks.kod, 'IMZA_GECERSIZ');
    const mutant = await kos(true);
    assert.equal(mutant.gecerli, true, 'imza kapatılınca bozulma fark edilmemeli — fark ediliyorsa test imzayı ölçmüyor');
  });
});
