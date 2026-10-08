// imzali-depo tarayıcı doğrulayıcısı.
// imzali_depo/cekirdek.py içindeki dogrula_veri() ile birebir aynı sırayı ve
// aynı sonuç kodlarını uygular. Yalnız WebCrypto kullanır (Ed25519 + SHA-256);
// tarayıcıda ve Node 20+ ortamında çalışır.

export const BICIM = 'imzali-depo/1';
export const GECIS_BICIMI = 'imzali-depo-gecis/1';
export const SAAT_TOLERANSI_MS = 5 * 60 * 1000;
const ZAMAN_RE = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/;
const SHA_RE = /^[0-9a-f]{64}$/;
const B64_RE = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
// Ed25519 SubjectPublicKeyInfo DER öneki (RFC 8410)
const SPKI_ONEK = [0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00];

export const KOD = Object.freeze({
  TAMAM: 'TAMAM',
  BICIM_HATASI: 'BICIM_HATASI',
  IMZA_BICIMI: 'IMZA_BICIMI',
  IMZA_GECERSIZ: 'IMZA_GECERSIZ',
  ZINCIR_GECERSIZ: 'ZINCIR_GECERSIZ',
  ZINCIR_GERI_ALINMIS: 'ZINCIR_GERI_ALINMIS',
  ANAHTAR_UYUSMAZ: 'ANAHTAR_UYUSMAZ',
  SURE_DOLMUS: 'SURE_DOLMUS',
  GELECEK_TARIHLI: 'GELECEK_TARIHLI',
  SURUM_GERI: 'SURUM_GERI',
  GUVENSIZ_YOL: 'GUVENSIZ_YOL',
  EKSIK: 'EKSIK',
  BOYUT_UYUSMAZ: 'BOYUT_UYUSMAZ',
  OZET_UYUSMAZ: 'OZET_UYUSMAZ',
  IMZASIZ_DOSYA: 'IMZASIZ_DOSYA',
});

export class Ed25519DesteklenmiyorHatasi extends Error {}

const subtle = () => globalThis.crypto?.subtle;
const metin = new TextEncoder();

export function b64Coz(s) {
  if (typeof s !== 'string') throw new Error('base64 değil');
  const t = s.replace(/^[ \t\n\r]+|[ \t\n\r]+$/g, '');
  if (!B64_RE.test(t)) throw new Error('base64 değil');
  const ikili = atob(t);
  const cikti = new Uint8Array(ikili.length);
  for (let i = 0; i < ikili.length; i++) cikti[i] = ikili.charCodeAt(i);
  return cikti;
}

export function hex(baytlar) {
  return Array.from(new Uint8Array(baytlar), (b) => b.toString(16).padStart(2, '0')).join('');
}

export async function sha256Hex(baytlar) {
  return hex(await subtle().digest('SHA-256', baytlar));
}

/** Tarayıcı Ed25519'u WebCrypto'da destekliyor mu? (gerçek bir doğrulamayla sınar) */
export async function ed25519Destekli() {
  try {
    if (!subtle()) return false;
    // RFC 8032 test vektörü 1 (boş ileti)
    const acik = hexCoz('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a');
    const imza = hexCoz('e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b');
    const anahtar = await subtle().importKey('raw', acik, { name: 'Ed25519' }, false, ['verify']);
    return await subtle().verify({ name: 'Ed25519' }, anahtar, imza, new Uint8Array(0));
  } catch {
    return false;
  }
}

function hexCoz(h) {
  const c = new Uint8Array(h.length / 2);
  for (let i = 0; i < c.length; i++) c[i] = parseInt(h.substr(i * 2, 2), 16);
  return c;
}

/** PEM (SubjectPublicKeyInfo) → ham 32 baytlık Ed25519 açık anahtar */
export function pemdenHamAnahtar(pem) {
  const m = /-----BEGIN PUBLIC KEY-----([\s\S]*?)-----END PUBLIC KEY-----/.exec(pem || '');
  if (!m) throw new Error('PEM "PUBLIC KEY" bloğu bulunamadı');
  const der = b64Coz(m[1].replace(/\s+/g, ''));
  if (der.length !== 44 || SPKI_ONEK.some((b, i) => der[i] !== b)) {
    throw new Error('açık anahtar Ed25519 değil');
  }
  return der.slice(12);
}

export class AcikAnahtar {
  constructor(ham, cryptoAnahtar, kimlik) {
    this.ham = ham;
    this.anahtar = cryptoAnahtar;
    this.kimlik = kimlik;
  }
  static async hamdan(ham) {
    let k;
    try {
      k = await subtle().importKey('raw', ham, { name: 'Ed25519' }, false, ['verify']);
    } catch (e) {
      if (!(await ed25519Destekli())) {
        throw new Ed25519DesteklenmiyorHatasi('Bu tarayıcı WebCrypto Ed25519 desteklemiyor.');
      }
      throw new Error('açık anahtar içe aktarılamadı: ' + e.message);
    }
    return new AcikAnahtar(ham, k, (await sha256Hex(ham)).slice(0, 32));
  }
  static async pemden(pem) {
    return AcikAnahtar.hamdan(pemdenHamAnahtar(pem));
  }
  async dogrula(imza, veri) {
    try {
      return await subtle().verify({ name: 'Ed25519' }, this.anahtar, imza, veri);
    } catch {
      return false;
    }
  }
}

export function yolGuvenli(ad) {
  if (typeof ad !== 'string' || !ad || ad.length > 4096) return false;
  if (ad.startsWith('/') || ad.includes('\\') || ad.includes('\0')) return false;
  return ad.split('/').every((p) => p !== '' && p !== '.' && p !== '..');
}

function zamanOku(s) {
  if (typeof s !== 'string' || !ZAMAN_RE.test(s)) throw new Error(`geçersiz zaman: ${JSON.stringify(s)}`);
  const [t, z] = s.slice(0, -1).split('T');
  const [y, a, g] = t.split('-').map(Number);
  const [sa, d, sn] = z.split(':').map(Number);
  const ms = Date.UTC(y, a - 1, g, sa, d, sn);
  const geri = new Date(ms);
  if (geri.getUTCFullYear() !== y || geri.getUTCMonth() !== a - 1 || geri.getUTCDate() !== g || sa > 23 || d > 59 || sn > 59) {
    throw new Error(`geçersiz zaman: ${JSON.stringify(s)}`);
  }
  return ms;
}

const tamsayi = (x) => typeof x === 'number' && Number.isInteger(x);
// Python sorted() ile aynı sıra (kod noktası)
const kodNoktasiSirala = (a, b) => {
  const x = Array.from(a), y = Array.from(b);
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = x[i].codePointAt(0) - y[i].codePointAt(0);
    if (d) return d;
  }
  return x.length - y.length;
};

/** cekirdek.zinciri_yuru() aynası */
export async function zinciriYuru(kok, kayitlar) {
  if (!Array.isArray(kayitlar)) return [null, 'anahtar_zinciri bir liste değil'];
  let aktif = kok;
  let baslangic = 0;
  kayitlar.forEach((g, i) => {
    try {
      if (JSON.parse(g.kayit).yeni_anahtar_kimligi === kok.kimlik) baslangic = i + 1;
    } catch { /* yok say */ }
  });
  for (let i = baslangic; i < kayitlar.length; i++) {
    const n = i + 1;
    const g = kayitlar[i];
    if (!g || typeof g !== 'object' || Array.isArray(g) || typeof g.kayit !== 'string' || typeof g.imza !== 'string') {
      return [null, `${n}. geçiş kaydı biçimsiz`];
    }
    let imza;
    try { imza = b64Coz(g.imza); } catch { return [null, `${n}. geçiş kaydının imzası base64 değil`]; }
    if (imza.length !== 64 || !(await aktif.dogrula(imza, metin.encode(g.kayit)))) {
      return [null, `${n}. geçiş kaydı önceki anahtarla imzalanmamış`];
    }
    let kayit;
    try { kayit = JSON.parse(g.kayit); } catch { return [null, `${n}. geçiş kaydı JSON değil`]; }
    if (!kayit || typeof kayit !== 'object' || Array.isArray(kayit) || kayit.bicim !== GECIS_BICIMI) {
      return [null, `${n}. geçiş kaydının biçimi tanınmadı`];
    }
    if (kayit.eski_anahtar_kimligi !== aktif.kimlik) {
      return [null, `${n}. geçiş kaydı başka bir anahtardan geçiş tanımlıyor`];
    }
    let yeni;
    try {
      const ham = b64Coz(kayit.yeni_acik_anahtar ?? '');
      if (ham.length !== 32) throw new Error();
      yeni = await AcikAnahtar.hamdan(ham);
    } catch (e) {
      if (e instanceof Ed25519DesteklenmiyorHatasi) throw e;
      return [null, `${n}. geçiş kaydındaki yeni anahtar geçersiz`];
    }
    if (kayit.yeni_anahtar_kimligi !== yeni.kimlik) {
      return [null, `${n}. geçiş kaydında anahtar kimliği tutmuyor`];
    }
    aktif = yeni;
  }
  return [aktif, ''];
}

/**
 * Tam doğrulama. cekirdek.dogrula_veri() aynası.
 * @param {object} p
 * @param {Uint8Array} p.indeksBaytlari  index.json baytları
 * @param {Uint8Array} p.imzaBaytlari    index.json.sig baytları
 * @param {AcikAnahtar} p.kok            güvenilen kök açık anahtar
 * @param {(ad:string)=>Promise<Uint8Array|null>} p.dosyaGetir
 * @param {string[]} p.mevcutAdlar       elde bulunan depo dosyalarının göreli adları
 * @param {number} [p.simdi]             ms (varsayılan Date.now())
 * @param {object[]} [p.bilinenZincir]
 * @param {number} [p.enDusukSurum]
 */
export async function dogrula(p) {
  const an = p.simdi ?? Date.now();
  const s = {
    gecerli: false,
    indeks: { kod: KOD.TAMAM, neden: '', anahtar_kimligi: null, zincir_uzunlugu: 0, surum: null, son_gecerlilik: null },
    dosyalar: [],
  };
  const hata = (kod, neden) => {
    if (s.indeks.kod === KOD.TAMAM) { s.indeks.kod = kod; s.indeks.neden = neden; }
  };
  const ok = () => s.indeks.kod === KOD.TAMAM;

  // 1) İmza biçimi
  let imza = new Uint8Array(0);
  try {
    const t = new TextDecoder('ascii', { fatal: true }).decode(p.imzaBaytlari);
    if (/[^\x00-\x7f]/.test(t)) throw new Error();
    imza = b64Coz(t);
  } catch { imza = new Uint8Array(0); }
  if (imza.length !== 64) hata(KOD.IMZA_BICIMI, 'imza dosyası 64 baytlık base64 Ed25519 imzası değil');

  // 2) İndeks JSON
  let indeks = null;
  try {
    indeks = JSON.parse(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(p.indeksBaytlari));
    if (!indeks || typeof indeks !== 'object' || Array.isArray(indeks)) throw new Error();
  } catch {
    indeks = null;
    hata(KOD.BICIM_HATASI, 'index.json çözümlenemedi');
  }

  if (indeks !== null && ok()) {
    // 3) Anahtar zinciri
    const zincir = 'anahtar_zinciri' in indeks ? indeks.anahtar_zinciri : [];
    const [aktif, neden] = await zinciriYuru(p.kok, zincir);
    if (aktif === null) {
      hata(KOD.ZINCIR_GECERSIZ, neden);
    } else {
      s.indeks.zincir_uzunlugu = zincir.length;
      s.indeks.anahtar_kimligi = aktif.kimlik;
      // 4) Bilinen zincir
      if (p.bilinenZincir && p.bilinenZincir.length) {
        const onek = zincir.slice(0, p.bilinenZincir.length).map((k) => k?.kayit);
        const bilinen = p.bilinenZincir.map((k) => k?.kayit);
        if (onek.length !== bilinen.length || onek.some((k, i) => k !== bilinen[i])) {
          hata(KOD.ZINCIR_GERI_ALINMIS, 'indeks, bilinen anahtar zincirini sürdürmüyor (eski anahtarla imza?)');
        }
      }
      // 5) İmza
      if (ok() && !(await aktif.dogrula(imza, p.indeksBaytlari))) {
        hata(KOD.IMZA_GECERSIZ, 'imza bu indeks ve anahtarla doğrulanmadı');
      }
      // 6) Anahtar kimliği
      if (ok() && indeks.anahtar_kimligi !== s.indeks.anahtar_kimligi) {
        hata(KOD.ANAHTAR_UYUSMAZ, 'indeksteki anahtar kimliği imzalayan anahtarla aynı değil');
      }
    }
    // 7) Biçim alanları
    if (ok()) {
      if (indeks.bicim !== BICIM) hata(KOD.BICIM_HATASI, `bilinmeyen biçim: ${JSON.stringify(indeks.bicim)}`);
      else if (!tamsayi(indeks.surum) || indeks.surum < 1) hata(KOD.BICIM_HATASI, 'surum pozitif tamsayı değil');
      else if (!Array.isArray(indeks.dosyalar)) hata(KOD.BICIM_HATASI, 'dosyalar listesi yok');
      else s.indeks.surum = indeks.surum;
    }
    // 8) Zaman
    if (ok()) {
      let olusturma, son;
      try {
        olusturma = zamanOku(indeks.olusturma);
        son = zamanOku(indeks.son_gecerlilik);
      } catch (e) {
        hata(KOD.BICIM_HATASI, e.message);
      }
      if (ok()) {
        s.indeks.son_gecerlilik = indeks.son_gecerlilik;
        if (an > son) hata(KOD.SURE_DOLMUS, `indeksin süresi ${indeks.son_gecerlilik} tarihinde doldu`);
        else if (olusturma > an + SAAT_TOLERANSI_MS) hata(KOD.GELECEK_TARIHLI, 'indeks gelecekte oluşturulmuş görünüyor');
      }
    }
    // 9) Sürüm geri alma
    if (ok()) {
      if (p.enDusukSurum != null && indeks.surum < p.enDusukSurum) {
        hata(KOD.SURUM_GERI, `sürüm ${indeks.surum} < beklenen en düşük ${p.enDusukSurum}`);
      }
    }
  }

  // 10) Dosyalar
  let dosyalarGecerli = true;
  const gorulen = new Set();
  const girdiler = indeks && typeof indeks === 'object' ? indeks.dosyalar : null;
  if (Array.isArray(girdiler)) {
    for (const g of girdiler) {
      const nesne = g && typeof g === 'object' && !Array.isArray(g);
      const ad = nesne ? g.ad : undefined;
      const satir = { ad: typeof ad === 'string' ? ad : (ad === undefined ? 'null' : JSON.stringify(ad)), kod: KOD.TAMAM, neden: '' };
      if (!yolGuvenli(ad)) {
        Object.assign(satir, { kod: KOD.GUVENSIZ_YOL, neden: "mutlak yol, '..' ya da boş parça içeriyor" });
      } else if (gorulen.has(ad)) {
        Object.assign(satir, { kod: KOD.BICIM_HATASI, neden: 'aynı ad indekste iki kez geçiyor' });
      } else if (!tamsayi(g.boyut) || g.boyut < 0 || typeof g.sha256 !== 'string' || !SHA_RE.test(g.sha256)) {
        Object.assign(satir, { kod: KOD.BICIM_HATASI, neden: 'boyut ya da sha256 alanı biçimsiz' });
      } else {
        gorulen.add(ad);
        const veri = await p.dosyaGetir(ad);
        if (veri == null) {
          Object.assign(satir, { kod: KOD.EKSIK, neden: 'dosya bulunamadı' });
        } else if (veri.length !== g.boyut) {
          Object.assign(satir, { kod: KOD.BOYUT_UYUSMAZ, neden: `boyut ${veri.length}, beklenen ${g.boyut}` });
        } else if ((await sha256Hex(veri)) !== g.sha256) {
          Object.assign(satir, { kod: KOD.OZET_UYUSMAZ, neden: 'SHA-256 özeti indekstekiyle aynı değil' });
        }
      }
      gorulen.add(satir.ad);
      if (satir.kod !== KOD.TAMAM) dosyalarGecerli = false;
      s.dosyalar.push(satir);
    }
    const fazla = [...new Set(p.mevcutAdlar)].filter((a) => !gorulen.has(a)).sort(kodNoktasiSirala);
    for (const ad of fazla) {
      s.dosyalar.push({ ad, kod: KOD.IMZASIZ_DOSYA, neden: 'indekste olmayan (imzasız) dosya' });
      dosyalarGecerli = false;
    }
  }

  s.gecerli = ok() && dosyalarGecerli;
  return s;
}
