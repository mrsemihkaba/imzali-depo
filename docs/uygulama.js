// imzali-depo paneli: sürükle-bırak + örnek depolar + sonuç tablosu.
import { AcikAnahtar, Ed25519DesteklenmiyorHatasi, KOD, dogrula, ed25519Destekli } from './dogrulayici.js';

const $ = (s) => document.querySelector(s);

const ETIKET = {
  TAMAM: 'Doğrulandı',
  BICIM_HATASI: 'Biçim hatası',
  IMZA_BICIMI: 'İmza dosyası bozuk',
  IMZA_GECERSIZ: 'İmza geçersiz',
  ZINCIR_GECERSIZ: 'Anahtar zinciri geçersiz',
  ZINCIR_GERI_ALINMIS: 'Zincir geri alınmış',
  ANAHTAR_UYUSMAZ: 'Anahtar uyuşmuyor',
  SURE_DOLMUS: 'Süresi dolmuş',
  GELECEK_TARIHLI: 'Gelecek tarihli',
  SURUM_GERI: 'Eski sürüm',
  GUVENSIZ_YOL: 'Güvensiz yol',
  EKSIK: 'Eksik',
  BOYUT_UYUSMAZ: 'Boyut farklı',
  OZET_UYUSMAZ: 'Özet farklı',
  IMZASIZ_DOSYA: 'İmzasız dosya',
};

/** Bırakılan/seçilen öğeler: yol → { boyut, oku() } */
const durum = {
  ogeler: new Map(),
  acikAnahtarMetni: null, // "Açık anahtar seç" ile ya da örnekle verilen
  acikAnahtarAdi: null,
  kaynak: '—',
  destek: null,
};
window.__sonSonuc = null;
window.__panelDurumu = 'yukleniyor';

// ---------------------------------------------------------------- girdiler
function dosyaOgesi(file, yol) {
  return { yol, boyut: file.size, oku: async () => new Uint8Array(await file.arrayBuffer()) };
}
function baytOgesi(baytlar, yol) {
  return { yol, boyut: baytlar.length, oku: async () => baytlar };
}

async function girisKlasoru(entry, cikti) {
  if (entry.isFile) {
    const file = await new Promise((ok, red) => entry.file(ok, red));
    cikti.push(dosyaOgesi(file, entry.fullPath.replace(/^\/+/, '')));
  } else if (entry.isDirectory) {
    const okuyucu = entry.createReader();
    for (;;) {
      const parti = await new Promise((ok, red) => okuyucu.readEntries(ok, red));
      if (!parti.length) break;
      for (const e of parti) await girisKlasoru(e, cikti);
    }
  }
}

async function ogeleriEkle(liste, kaynak) {
  for (const o of liste) durum.ogeler.set(o.yol, o);
  durum.kaynak = kaynak;
  await rolleriGuncelle();
}

const adi = (yol) => yol.split('/').pop();
const dizini = (yol) => (yol.includes('/') ? yol.slice(0, yol.lastIndexOf('/') + 1) : '');
const anahtarAdayi = (o) => /\.(pub|pem)$/i.test(o.yol) && o.boyut < 8192;

/**
 * Öğeleri rollere ayırır: kök dizindeki index.json, yanındaki .sig, açık anahtar,
 * kök dizin altındaki depo dosyaları. (CLI: index.json/.sig ve '.' ile başlayan
 * yollar indekse girmez; burada da aynı dışlama uygulanır.)
 */
async function sinifla() {
  const ogeler = [...durum.ogeler.values()];
  const indeksler = ogeler.filter((o) => adi(o.yol) === 'index.json')
    .sort((a, b) => a.yol.split('/').length - b.yol.split('/').length || a.yol.localeCompare(b.yol));
  const indeks = indeksler[0] || null;
  const kok = indeks ? dizini(indeks.yol) : '';
  const imza = durum.ogeler.get(kok + 'index.json.sig') || ogeler.find((o) => /\.sig$/i.test(o.yol)) || null;

  let listelenen = new Set();
  if (indeks) {
    try {
      const j = JSON.parse(new TextDecoder().decode(await indeks.oku()));
      if (Array.isArray(j.dosyalar)) listelenen = new Set(j.dosyalar.map((d) => d && d.ad));
    } catch { /* doğrulayıcı raporlar */ }
  }

  let anahtar = null;
  let anahtarMetni = durum.acikAnahtarMetni;
  let anahtarAdi = durum.acikAnahtarAdi;
  if (!anahtarMetni) {
    for (const o of ogeler.filter(anahtarAdayi)) {
      const goreli = o.yol.startsWith(kok) ? o.yol.slice(kok.length) : null;
      if (goreli !== null && listelenen.has(goreli)) continue; // depo içeriğidir, anahtar değil
      const t = new TextDecoder().decode(await o.oku());
      if (t.includes('BEGIN PUBLIC KEY')) { anahtar = o; anahtarMetni = t; anahtarAdi = o.yol; break; }
    }
  }

  const dosyalar = new Map();
  for (const o of ogeler) {
    if (!o.yol.startsWith(kok) || o === indeks || o === imza || o === anahtar) continue;
    const goreli = o.yol.slice(kok.length);
    if (goreli === 'index.json' || goreli === 'index.json.sig') continue;
    if (goreli.split('/').some((p) => p.startsWith('.'))) continue;
    dosyalar.set(goreli, o);
  }
  return { indeks, imza, anahtarMetni, anahtarAdi, dosyalar };
}

async function rolleriGuncelle() {
  const r = await sinifla();
  const yaz = (rol, deger, var_) => {
    const li = document.querySelector(`#roller [data-rol="${rol}"]`);
    li.dataset.durum = var_ ? 'tamam' : 'bekliyor';
    li.querySelector('b').textContent = deger;
    li.querySelector('b').title = deger;
  };
  yaz('indeks', r.indeks ? r.indeks.yol : '—', !!r.indeks);
  yaz('imza', r.imza ? r.imza.yol : '—', !!r.imza);
  yaz('anahtar', r.anahtarAdi || '—', !!r.anahtarMetni);
  yaz('dosya', String(r.dosyalar.size), r.dosyalar.size > 0);
  $('#dogrula').disabled = !(r.indeks && r.imza && r.anahtarMetni) || durum.destek === false;
  return r;
}

// ---------------------------------------------------------------- doğrulama
function ozetYaz(durumAdi, metin) {
  const o = $('#ozet');
  o.dataset.durum = durumAdi;
  $('#ozet-metin').textContent = metin;
  $('#genel-isik').dataset.durum = durumAdi === 'hata' ? 'red' : durumAdi;
}

async function calistir() {
  const r = await sinifla();
  window.__panelDurumu = 'calisiyor';
  ozetYaz('calisiyor', 'Doğrulanıyor…');
  try {
    if (!r.indeks || !r.imza || !r.anahtarMetni) throw new Error('index.json, index.json.sig ve açık anahtar gerekli.');
    if (durum.destek === false) throw new Ed25519DesteklenmiyorHatasi('Bu tarayıcı WebCrypto Ed25519 desteklemiyor; imza doğrulanamaz.');
    const kok = await AcikAnahtar.pemden(r.anahtarMetni);
    const enDusuk = $('#en-dusuk').value.trim();
    const sonuc = await dogrula({
      indeksBaytlari: await r.indeks.oku(),
      imzaBaytlari: await r.imza.oku(),
      kok,
      dosyaGetir: async (ad) => (r.dosyalar.has(ad) ? r.dosyalar.get(ad).oku() : null),
      mevcutAdlar: [...r.dosyalar.keys()],
      enDusukSurum: enDusuk ? Number(enDusuk) : undefined,
    });
    sonucCiz(sonuc, r);
    window.__sonSonuc = sonuc;
  } catch (e) {
    window.__sonSonuc = { hata: e.message };
    $('#bilgi').hidden = true;
    $('#tablo').hidden = true;
    ozetYaz('hata', (e instanceof Ed25519DesteklenmiyorHatasi ? 'Ed25519 desteklenmiyor: ' : 'Doğrulama yapılamadı: ') + e.message);
  }
  window.__panelDurumu = 'hazir';
}

function satir(ad, kod, neden, ek = '') {
  const tr = document.createElement('tr');
  tr.dataset.durum = kod === KOD.TAMAM ? 'tamam' : 'red';
  tr.dataset.kod = kod;
  if (ek) tr.className = ek;
  const td1 = document.createElement('td');
  td1.textContent = ad;
  const td2 = document.createElement('td');
  const k = document.createElement('span');
  k.className = 'kod';
  k.innerHTML = '<span class="isik" aria-hidden="true"></span>';
  k.append(`${kod === KOD.TAMAM ? '✓' : '✗'} ${ETIKET[kod] || kod}`);
  k.title = kod;
  k.querySelector('.isik').dataset.durum = tr.dataset.durum;
  const alt = document.createElement('span');
  alt.className = 'alt-neden';
  alt.textContent = neden;
  td2.append(k, alt);
  const td3 = document.createElement('td');
  td3.className = 'neden';
  td3.textContent = kod === KOD.TAMAM ? neden : `${neden} (${kod})`;
  tr.append(td1, td2, td3);
  return tr;
}

function sonucCiz(s, r) {
  const g = s.indeks;
  const tbody = $('#satirlar');
  tbody.replaceChildren();
  tbody.append(satir('index.json · imza + zincir + süre', g.kod,
    g.kod === KOD.TAMAM ? 'Ed25519 imzası ve indeks alanları doğrulandı' : g.neden, 'indeks-satiri'));
  for (const d of s.dosyalar) tbody.append(satir(d.ad, d.kod, d.kod === KOD.TAMAM ? 'SHA-256 ve boyut eşleşti' : d.neden));
  $('#tablo').hidden = false;

  $('#bilgi').hidden = false;
  $('#b-kaynak').textContent = durum.kaynak;
  $('#b-kimlik').textContent = g.anahtar_kimligi || '—';
  $('#b-zincir').textContent = g.anahtar_kimligi
    ? (g.zincir_uzunlugu ? `${g.zincir_uzunlugu} geçiş (kök → … → imzalayan)` : 'döndürme yok (kök anahtar)') : '—';
  $('#b-surum').textContent = g.surum ?? '—';
  $('#b-son').textContent = g.son_gecerlilik || '—';

  const bozuk = s.dosyalar.filter((d) => d.kod !== KOD.TAMAM).length;
  if (s.gecerli) {
    ozetYaz('tamam', `GEÇERLİ — imza doğrulandı, ${s.dosyalar.length} dosyanın tamamı indeksle eşleşti.`);
  } else {
    const parca = [];
    if (g.kod !== KOD.TAMAM) parca.push(`${ETIKET[g.kod] || g.kod}: ${g.neden}`);
    if (bozuk) parca.push(`${bozuk} dosya sorunlu`);
    ozetYaz('red', `REDDEDİLDİ — ${parca.join(' · ')}`);
  }
}

// ---------------------------------------------------------------- örnekler
let manifest = null;
async function ornekleriKur() {
  const kap = $('#ornekler');
  try {
    const yanit = await fetch('ornek/ornekler.json');
    if (!yanit.ok) throw new Error(`HTTP ${yanit.status}`);
    manifest = await yanit.json();
  } catch (e) {
    kap.innerHTML = '';
    const p = document.createElement('p');
    p.className = 'soluk';
    p.textContent = `Örnekler yüklenemedi (${e.message}). Panel dosya:// yerine bir HTTP sunucusundan açılmalı.`;
    kap.append(p);
    return;
  }
  kap.replaceChildren();
  for (const o of manifest.ornekler) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'ornek';
    b.dataset.ornek = o.id;
    b.innerHTML = '<span class="ust-satir"><span class="ad"></span><span class="rozet"></span></span><small></small>';
    b.querySelector('.ad').textContent = o.baslik;
    const rz = b.querySelector('.rozet');
    rz.textContent = o.beklenen === 'gecerli' ? 'GEÇERLİ' : 'RED';
    rz.title = 'Beklenen sonuç';
    rz.classList.add(o.beklenen === 'gecerli' ? 'gecerli' : 'red');
    b.querySelector('small').textContent = o.aciklama;
    b.addEventListener('click', () => ornekYukle(o));
    kap.append(b);
  }
}

async function getirBayt(yol) {
  const y = await fetch(yol, { cache: 'no-store' });
  if (!y.ok) throw new Error(`${yol}: HTTP ${y.status}`);
  return new Uint8Array(await y.arrayBuffer());
}

async function ornekYukle(o) {
  window.__panelDurumu = 'calisiyor';
  ozetYaz('calisiyor', `“${o.baslik}” yükleniyor…`);
  try {
    temizle(false);
    const taban = `ornek/${o.dizin}/`;
    const adlar = ['index.json', 'index.json.sig', ...o.dosyalar];
    const ogeler = await Promise.all(adlar.map(async (ad) => baytOgesi(await getirBayt(taban + ad), `${o.dizin}/${ad}`)));
    durum.acikAnahtarMetni = new TextDecoder().decode(await getirBayt(`ornek/${manifest.kok_anahtar}`));
    durum.acikAnahtarAdi = manifest.kok_anahtar;
    await ogeleriEkle(ogeler, `Örnek: ${o.baslik}`);
  } catch (e) {
    ozetYaz('hata', `Örnek yüklenemedi: ${e.message}`);
    window.__panelDurumu = 'hazir';
    return;
  }
  await calistir();
}

// ---------------------------------------------------------------- olaylar
function temizle(cizimiSifirla = true) {
  durum.ogeler.clear();
  durum.acikAnahtarMetni = null;
  durum.acikAnahtarAdi = null;
  durum.kaynak = '—';
  if (cizimiSifirla) {
    $('#tablo').hidden = true;
    $('#bilgi').hidden = true;
    ozetYaz('bekliyor', 'Henüz doğrulama yapılmadı.');
    window.__sonSonuc = null;
  }
  return rolleriGuncelle();
}

function secimdenOgeler(files) {
  return [...files].map((f) => dosyaOgesi(f, (f.webkitRelativePath || f.name).replace(/^\/+/, '')));
}

async function secimSonrasi(ogeler, kaynak) {
  await ogeleriEkle(ogeler, kaynak);
  const r = await sinifla();
  if (r.indeks && r.imza && r.anahtarMetni) await calistir();
}

function olaylariBagla() {
  const birak = $('#birak');
  ['dragenter', 'dragover'].forEach((t) => birak.addEventListener(t, (e) => {
    e.preventDefault();
    birak.classList.add('uzerinde');
  }));
  ['dragleave', 'drop'].forEach((t) => birak.addEventListener(t, () => birak.classList.remove('uzerinde')));
  // pencerenin herhangi bir yerine bırakılan dosya sayfayı terk ettirmesin
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => e.preventDefault());
  birak.addEventListener('drop', async (e) => {
    e.preventDefault();
    const ogeler = [];
    const items = [...(e.dataTransfer.items || [])];
    const girisler = items.map((i) => (i.kind === 'file' && i.webkitGetAsEntry ? i.webkitGetAsEntry() : null));
    if (girisler.length && girisler.every(Boolean)) {
      for (const g of girisler) await girisKlasoru(g, ogeler);
    } else {
      ogeler.push(...secimdenOgeler(e.dataTransfer.files));
    }
    await secimSonrasi(ogeler, 'Bırakılan dosyalar');
  });
  const ac = () => $('#gizli-sec').click();
  birak.addEventListener('click', ac);
  birak.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ac(); }
  });
  for (const id of ['#gizli-sec', '#sec-dosya', '#sec-klasor']) {
    $(id).addEventListener('change', async (e) => {
      await secimSonrasi(secimdenOgeler(e.target.files), 'Seçilen dosyalar');
      e.target.value = '';
    });
  }
  $('#sec-anahtar').addEventListener('change', async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    durum.acikAnahtarMetni = await f.text();
    durum.acikAnahtarAdi = f.name;
    e.target.value = '';
    const r = await rolleriGuncelle();
    if (r.indeks && r.imza) await calistir();
  });
  $('#temizle').addEventListener('click', () => temizle());
  $('#dogrula').addEventListener('click', calistir);
}

async function basla() {
  olaylariBagla();
  durum.destek = await ed25519Destekli();
  if (!durum.destek) {
    $('#destek-uyari').hidden = false;
    $('#genel-isik').dataset.durum = 'red';
  } else {
    $('#genel-isik').dataset.durum = 'tamam';
  }
  await Promise.all([ornekleriKur(), rolleriGuncelle()]);
  window.__panelDurumu = 'hazir';
}

basla();
