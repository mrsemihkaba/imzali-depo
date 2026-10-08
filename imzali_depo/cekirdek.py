"""imzali-depo çekirdeği: anahtar, indeks üretimi, imza ve doğrulama.

Biçim ayrıntıları için BICIM.md'ye bakın. Bu modüldeki doğrulama mantığı
docs/dogrulayici.js içinde birebir aynalanır; ikisi aynı sonuç kodlarını üretir.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

BICIM = "imzali-depo/1"
GECIS_BICIMI = "imzali-depo-gecis/1"
ZINCIR_BICIMI = "imzali-depo-zincir/1"
INDEKS_ADI = "index.json"
IMZA_ADI = "index.json.sig"
SAAT_TOLERANSI = timedelta(minutes=5)
_ZAMAN_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

# Sonuç kodları (JS doğrulayıcıyla ortak sözlük)
TAMAM = "TAMAM"
BICIM_HATASI = "BICIM_HATASI"
IMZA_BICIMI = "IMZA_BICIMI"
IMZA_GECERSIZ = "IMZA_GECERSIZ"
ZINCIR_GECERSIZ = "ZINCIR_GECERSIZ"
ZINCIR_GERI_ALINMIS = "ZINCIR_GERI_ALINMIS"
ANAHTAR_UYUSMAZ = "ANAHTAR_UYUSMAZ"
SURE_DOLMUS = "SURE_DOLMUS"
GELECEK_TARIHLI = "GELECEK_TARIHLI"
SURUM_GERI = "SURUM_GERI"
GUVENSIZ_YOL = "GUVENSIZ_YOL"
EKSIK = "EKSIK"
BOYUT_UYUSMAZ = "BOYUT_UYUSMAZ"
OZET_UYUSMAZ = "OZET_UYUSMAZ"
IMZASIZ_DOSYA = "IMZASIZ_DOSYA"


class ImzaliDepoHatasi(Exception):
    """Kullanıcıya gösterilecek, beklenen hata."""


# --------------------------------------------------------------------------
# Zaman ve kodlama yardımcıları
# --------------------------------------------------------------------------

def zaman_yaz(an: datetime) -> str:
    return an.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def zaman_oku(metin: str) -> datetime:
    if not isinstance(metin, str) or not _ZAMAN_RE.match(metin):
        raise ValueError(f"geçersiz zaman: {metin!r}")
    return datetime.strptime(metin, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def simdi_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def b64(veri: bytes) -> str:
    return base64.b64encode(veri).decode("ascii")


def b64_coz(metin: str) -> bytes:
    return base64.b64decode(metin.strip(" \t\n\r"), validate=True)


def sha256_hex(veri: bytes) -> str:
    return hashlib.sha256(veri).hexdigest()


# --------------------------------------------------------------------------
# Anahtarlar
# --------------------------------------------------------------------------

def anahtar_uret(parola: bytes) -> tuple[bytes, bytes]:
    """(şifreli özel anahtar PEM, açık anahtar PEM) döndürür."""
    if not parola:
        raise ImzaliDepoHatasi("parola boş olamaz")
    ozel = Ed25519PrivateKey.generate()
    ozel_pem = ozel.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(parola),
    )
    return ozel_pem, acik_pem(ozel.public_key())


def acik_pem(acik: Ed25519PublicKey) -> bytes:
    return acik.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def ozel_anahtar_yukle(pem: bytes, parola: bytes) -> Ed25519PrivateKey:
    try:
        anahtar = serialization.load_pem_private_key(pem, password=parola)
    except (ValueError, TypeError) as e:
        raise ImzaliDepoHatasi(f"özel anahtar açılamadı (parola yanlış ya da dosya bozuk): {e}") from None
    if not isinstance(anahtar, Ed25519PrivateKey):
        raise ImzaliDepoHatasi("özel anahtar Ed25519 değil")
    return anahtar


def acik_anahtar_yukle(pem: bytes) -> Ed25519PublicKey:
    try:
        anahtar = serialization.load_pem_public_key(pem)
    except ValueError as e:
        raise ImzaliDepoHatasi(f"açık anahtar okunamadı: {e}") from None
    if not isinstance(anahtar, Ed25519PublicKey):
        raise ImzaliDepoHatasi("açık anahtar Ed25519 değil")
    return anahtar


def ham_acik(acik: Ed25519PublicKey) -> bytes:
    return acik.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def anahtar_kimligi(acik: Ed25519PublicKey) -> str:
    """Ham 32 baytlık açık anahtarın SHA-256 özetinin ilk 16 baytı (32 onaltılık)."""
    return sha256_hex(ham_acik(acik))[:32]


def _imza_dogrula(acik: Ed25519PublicKey, imza: bytes, veri: bytes) -> bool:
    try:
        acik.verify(imza, veri)
        return True
    except InvalidSignature:
        return False


def _gecis_imzasi_dogru(aktif: Ed25519PublicKey, imza: bytes, kayit_metni: str) -> bool:
    return _imza_dogrula(aktif, imza, kayit_metni.encode("utf-8"))


def _ozet_tutar(veri: bytes, beklenen: str) -> bool:
    return hmac.compare_digest(sha256_hex(veri), beklenen)


def _sure_doldu(an: datetime, son: datetime) -> bool:
    return an > son


# --------------------------------------------------------------------------
# Yol güvenliği ve dosya tarama
# --------------------------------------------------------------------------

def yol_guvenli(ad: object) -> bool:
    if not isinstance(ad, str) or not ad or len(ad) > 4096:
        return False
    if ad.startswith("/") or "\\" in ad or "\x00" in ad:
        return False
    parcalar = ad.split("/")
    return all(p not in ("", ".", "..") for p in parcalar)


def _dislanan(goreli: str) -> bool:
    if goreli in (INDEKS_ADI, IMZA_ADI):
        return True
    return any(p.startswith(".") for p in goreli.split("/"))


def dosyalari_listele(dizin: Path) -> list[str]:
    """Depo dizinindeki imzalanacak dosyaların göreli adları (sıralı)."""
    dizin = Path(dizin)
    if not dizin.is_dir():
        raise ImzaliDepoHatasi(f"dizin yok: {dizin}")
    adlar = []
    for kok, alt_dizinler, dosyalar in os.walk(dizin, followlinks=False):
        alt_dizinler[:] = sorted(d for d in alt_dizinler if not d.startswith("."))
        for d in alt_dizinler:
            if (Path(kok) / d).is_symlink():
                raise ImzaliDepoHatasi(f"sembolik bağ desteklenmez: {Path(kok) / d}")
        for ad in dosyalar:
            tam = Path(kok) / ad
            goreli = tam.relative_to(dizin).as_posix()
            if _dislanan(goreli):
                continue
            if tam.is_symlink():
                raise ImzaliDepoHatasi(f"sembolik bağ desteklenmez: {goreli}")
            adlar.append(goreli)
    return sorted(adlar)


def dosya_kaydi(dizin: Path, ad: str) -> dict:
    veri = (Path(dizin) / ad).read_bytes()
    return {"ad": ad, "boyut": len(veri), "sha256": sha256_hex(veri)}


# --------------------------------------------------------------------------
# Anahtar döndürme zinciri
# --------------------------------------------------------------------------

def gecis_kaydi_olustur(
    eski_ozel: Ed25519PrivateKey, yeni_acik: Ed25519PublicKey, simdi: datetime | None = None
) -> dict:
    """Yeni anahtarı eski anahtarla onaylayan geçiş kaydı.

    `kayit` alanı JSON METNİ olarak saklanır; imza bu metnin UTF-8 baytları
    üzerindedir. Böylece Python ve tarayıcı aynı baytları doğrular
    (kanonikleştirme gerekmez).
    """
    an = simdi or simdi_utc()
    kayit = {
        "bicim": GECIS_BICIMI,
        "eski_anahtar_kimligi": anahtar_kimligi(eski_ozel.public_key()),
        "yeni_anahtar_kimligi": anahtar_kimligi(yeni_acik),
        "yeni_acik_anahtar": b64(ham_acik(yeni_acik)),
        "tarih": zaman_yaz(an),
    }
    metin = json.dumps(kayit, ensure_ascii=True, separators=(",", ":"))
    return {"kayit": metin, "imza": b64(eski_ozel.sign(metin.encode("utf-8")))}


def zincir_oku(yol: Path) -> list[dict]:
    yol = Path(yol)
    if not yol.exists():
        return []
    try:
        veri = json.loads(yol.read_text("utf-8"))
    except json.JSONDecodeError as e:
        raise ImzaliDepoHatasi(f"zincir dosyası bozuk: {e}") from None
    if not isinstance(veri, dict) or veri.get("bicim") != ZINCIR_BICIMI or not isinstance(veri.get("kayitlar"), list):
        raise ImzaliDepoHatasi("zincir dosyası biçimi tanınmadı")
    return veri["kayitlar"]


def zincir_yaz(yol: Path, kayitlar: list[dict]) -> None:
    Path(yol).write_text(
        json.dumps({"bicim": ZINCIR_BICIMI, "kayitlar": kayitlar}, ensure_ascii=False, indent=2) + "\n",
        "utf-8",
    )


def zinciri_yuru(kok: Ed25519PublicKey, kayitlar: object) -> tuple[Ed25519PublicKey | None, str]:
    """Güvenilen kök anahtardan başlayıp zinciri izler.

    (son geçerli anahtar, "") ya da (None, neden) döndürür.
    """
    if not isinstance(kayitlar, list):
        return None, "anahtar_zinciri bir liste değil"
    aktif = kok
    # Güvenilen anahtar zincirin ortasındaki bir anahtar olabilir (yalnız yeni
    # anahtarı bilen doğrulayıcı): o halkaya kadarki geçmiş atlanır, sonrası yine
    # bu anahtardan başlayarak imzayla doğrulanır.
    kok_kimlik = anahtar_kimligi(kok)
    baslangic = 0
    for i, girdi in enumerate(kayitlar):
        try:
            if json.loads(girdi["kayit"]).get("yeni_anahtar_kimligi") == kok_kimlik:
                baslangic = i + 1
        except (TypeError, KeyError, ValueError, AttributeError):
            pass
    for i, girdi in enumerate(kayitlar[baslangic:], baslangic + 1):
        if not isinstance(girdi, dict) or not isinstance(girdi.get("kayit"), str) or not isinstance(girdi.get("imza"), str):
            return None, f"{i}. geçiş kaydı biçimsiz"
        try:
            imza = b64_coz(girdi["imza"])
        except ValueError:
            return None, f"{i}. geçiş kaydının imzası base64 değil"
        if len(imza) != 64 or not _gecis_imzasi_dogru(aktif, imza, girdi["kayit"]):
            return None, f"{i}. geçiş kaydı önceki anahtarla imzalanmamış"
        try:
            kayit = json.loads(girdi["kayit"])
        except json.JSONDecodeError:
            return None, f"{i}. geçiş kaydı JSON değil"
        if not isinstance(kayit, dict) or kayit.get("bicim") != GECIS_BICIMI:
            return None, f"{i}. geçiş kaydının biçimi tanınmadı"
        if kayit.get("eski_anahtar_kimligi") != anahtar_kimligi(aktif):
            return None, f"{i}. geçiş kaydı başka bir anahtardan geçiş tanımlıyor"
        try:
            ham = b64_coz(kayit.get("yeni_acik_anahtar", ""))
            if len(ham) != 32:
                raise ValueError
            yeni = Ed25519PublicKey.from_public_bytes(ham)
        except (ValueError, TypeError):
            return None, f"{i}. geçiş kaydındaki yeni anahtar geçersiz"
        if kayit.get("yeni_anahtar_kimligi") != anahtar_kimligi(yeni):
            return None, f"{i}. geçiş kaydında anahtar kimliği tutmuyor"
        aktif = yeni
    return aktif, ""


# --------------------------------------------------------------------------
# İmzalama
# --------------------------------------------------------------------------

def indeks_uret(
    dizin: Path,
    ozel: Ed25519PrivateKey,
    *,
    surum: int,
    gecerlilik_gun: float,
    depo_adi: str,
    zincir: list[dict] | None = None,
    simdi: datetime | None = None,
) -> tuple[bytes, bytes]:
    """(index.json baytları, index.json.sig baytları) üretir; diske yazmaz."""
    if not isinstance(surum, int) or surum < 1:
        raise ImzaliDepoHatasi("sürüm 1 ya da daha büyük bir tamsayı olmalı")
    if gecerlilik_gun <= 0:
        raise ImzaliDepoHatasi("geçerlilik süresi pozitif olmalı")
    zincir = list(zincir or [])
    an = simdi or simdi_utc()
    if zincir:
        # Kök bilinmeden zinciri yürüyemeyiz; ama son halkanın bu anahtar olduğunu sınarız.
        son = json.loads(zincir[-1]["kayit"])
        if son.get("yeni_anahtar_kimligi") != anahtar_kimligi(ozel.public_key()):
            raise ImzaliDepoHatasi("zincirin son anahtarı imzalayan anahtar değil; önce anahtar-dondur çalıştırın")
    adlar = dosyalari_listele(dizin)
    for ad in adlar:
        if not yol_guvenli(ad):
            raise ImzaliDepoHatasi(f"güvensiz dosya adı: {ad!r}")
    indeks = {
        "bicim": BICIM,
        "depo": depo_adi,
        "surum": surum,
        "olusturma": zaman_yaz(an),
        "son_gecerlilik": zaman_yaz(an + timedelta(days=gecerlilik_gun)),
        "anahtar_kimligi": anahtar_kimligi(ozel.public_key()),
        "anahtar_zinciri": zincir,
        "dosyalar": [dosya_kaydi(dizin, ad) for ad in adlar],
    }
    baytlar = (json.dumps(indeks, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    imza = (b64(ozel.sign(baytlar)) + "\n").encode("ascii")
    return baytlar, imza


def onceki_surum(dizin: Path) -> int:
    yol = Path(dizin) / INDEKS_ADI
    try:
        s = json.loads(yol.read_text("utf-8")).get("surum")
        return s if isinstance(s, int) and s > 0 else 0
    except (OSError, ValueError, AttributeError):
        return 0


# --------------------------------------------------------------------------
# Doğrulama
# --------------------------------------------------------------------------

@dataclass
class Sonuc:
    gecerli: bool = False
    kod: str = TAMAM
    neden: str = ""
    anahtar_kimligi: str | None = None
    zincir_uzunlugu: int = 0
    surum: int | None = None
    son_gecerlilik: str | None = None
    dosyalar: list[dict] = field(default_factory=list)

    def sozluk(self) -> dict:
        return {
            "gecerli": self.gecerli,
            "indeks": {
                "kod": self.kod,
                "neden": self.neden,
                "anahtar_kimligi": self.anahtar_kimligi,
                "zincir_uzunlugu": self.zincir_uzunlugu,
                "surum": self.surum,
                "son_gecerlilik": self.son_gecerlilik,
            },
            "dosyalar": self.dosyalar,
        }


def dogrula_veri(
    indeks_baytlari: bytes,
    imza_metni: bytes,
    kok: Ed25519PublicKey,
    dosya_getir: Callable[[str], bytes | None],
    mevcut_adlar: Iterable[str],
    *,
    simdi: datetime | None = None,
    bilinen_zincir: list[dict] | None = None,
    en_dusuk_surum: int | None = None,
) -> Sonuc:
    """Bellekteki verilerle tam doğrulama. Sıra JS doğrulayıcıyla aynıdır."""
    an = simdi or simdi_utc()
    s = Sonuc()

    def hata(kod: str, neden: str) -> None:
        if s.kod == TAMAM:
            s.kod, s.neden = kod, neden

    indeks = None
    # 1) İmza biçimi
    try:
        imza = b64_coz(imza_metni.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        imza = b""
    if len(imza) != 64:
        hata(IMZA_BICIMI, "imza dosyası 64 baytlık base64 Ed25519 imzası değil")
    # 2) İndeks JSON
    try:
        indeks = json.loads(indeks_baytlari.decode("utf-8"))
        if not isinstance(indeks, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        indeks = None
        hata(BICIM_HATASI, "index.json çözümlenemedi")

    if indeks is not None and s.kod == TAMAM:
        # 3) Anahtar zinciri
        zincir = indeks.get("anahtar_zinciri", [])
        aktif, neden = zinciri_yuru(kok, zincir)
        if aktif is None:
            hata(ZINCIR_GECERSIZ, neden)
        else:
            s.zincir_uzunlugu = len(zincir)
            s.anahtar_kimligi = anahtar_kimligi(aktif)
            # 4) Bilinen zincir geri alınamaz
            if bilinen_zincir:
                onek = [k.get("kayit") for k in zincir[: len(bilinen_zincir)]]
                if onek != [k.get("kayit") for k in bilinen_zincir]:
                    hata(ZINCIR_GERI_ALINMIS, "indeks, bilinen anahtar zincirini sürdürmüyor (eski anahtarla imza?)")
            # 5) İmza
            if s.kod == TAMAM and not _imza_dogrula(aktif, imza, indeks_baytlari):
                hata(IMZA_GECERSIZ, "imza bu indeks ve anahtarla doğrulanmadı")
            # 6) Anahtar kimliği
            if s.kod == TAMAM and indeks.get("anahtar_kimligi") != s.anahtar_kimligi:
                hata(ANAHTAR_UYUSMAZ, "indeksteki anahtar kimliği imzalayan anahtarla aynı değil")
        # 7) Biçim alanları
        if s.kod == TAMAM:
            if indeks.get("bicim") != BICIM:
                hata(BICIM_HATASI, f"bilinmeyen biçim: {indeks.get('bicim')!r}")
            elif not isinstance(indeks.get("surum"), int) or isinstance(indeks.get("surum"), bool) or indeks["surum"] < 1:
                hata(BICIM_HATASI, "surum pozitif tamsayı değil")
            elif not isinstance(indeks.get("dosyalar"), list):
                hata(BICIM_HATASI, "dosyalar listesi yok")
            else:
                s.surum = indeks["surum"]
        # 8) Zaman
        if s.kod == TAMAM:
            try:
                olusturma = zaman_oku(indeks.get("olusturma"))
                son = zaman_oku(indeks.get("son_gecerlilik"))
            except ValueError as e:
                hata(BICIM_HATASI, str(e))
            else:
                s.son_gecerlilik = indeks["son_gecerlilik"]
                if _sure_doldu(an, son):
                    hata(SURE_DOLMUS, f"indeksin süresi {indeks['son_gecerlilik']} tarihinde doldu")
                elif olusturma > an + SAAT_TOLERANSI:
                    hata(GELECEK_TARIHLI, "indeks gelecekte oluşturulmuş görünüyor")
        # 9) Sürüm geri alma
        if s.kod == TAMAM:
            if en_dusuk_surum is not None and indeks["surum"] < en_dusuk_surum:
                hata(SURUM_GERI, f"sürüm {indeks['surum']} < beklenen en düşük {en_dusuk_surum}")

    # 10) Dosyalar (indeks okunabildiyse her durumda raporlanır)
    dosyalar_gecerli = True
    gorulen: set[str] = set()
    girdiler = indeks.get("dosyalar") if isinstance(indeks, dict) else None
    if isinstance(girdiler, list):
        for g in girdiler:
            ad = g.get("ad") if isinstance(g, dict) else None
            satir = {"ad": ad if isinstance(ad, str) else json.dumps(ad, ensure_ascii=False, separators=(",", ":")),
                     "kod": TAMAM, "neden": ""}
            if not yol_guvenli(ad):
                satir.update(kod=GUVENSIZ_YOL, neden="mutlak yol, '..' ya da boş parça içeriyor")
            elif ad in gorulen:
                satir.update(kod=BICIM_HATASI, neden="aynı ad indekste iki kez geçiyor")
            elif (not isinstance(g.get("boyut"), int) or isinstance(g.get("boyut"), bool)
                  or g["boyut"] < 0 or not isinstance(g.get("sha256"), str) or not _SHA_RE.match(g["sha256"])):
                satir.update(kod=BICIM_HATASI, neden="boyut ya da sha256 alanı biçimsiz")
            else:
                gorulen.add(ad)
                veri = dosya_getir(ad)
                if veri is None:
                    satir.update(kod=EKSIK, neden="dosya bulunamadı")
                elif len(veri) != g["boyut"]:
                    satir.update(kod=BOYUT_UYUSMAZ, neden=f"boyut {len(veri)}, beklenen {g['boyut']}")
                elif not _ozet_tutar(veri, g["sha256"]):
                    satir.update(kod=OZET_UYUSMAZ, neden="SHA-256 özeti indekstekiyle aynı değil")
            gorulen.add(satir["ad"])
            if satir["kod"] != TAMAM:
                dosyalar_gecerli = False
            s.dosyalar.append(satir)
        for ad in sorted(set(mevcut_adlar) - gorulen):
            s.dosyalar.append({"ad": ad, "kod": IMZASIZ_DOSYA, "neden": "indekste olmayan (imzasız) dosya"})
            dosyalar_gecerli = False

    s.gecerli = s.kod == TAMAM and dosyalar_gecerli
    return s


def dogrula_dizin(
    dizin: Path,
    kok: Ed25519PublicKey,
    **secenekler,
) -> Sonuc:
    dizin = Path(dizin)
    try:
        indeks_baytlari = (dizin / INDEKS_ADI).read_bytes()
        imza_metni = (dizin / IMZA_ADI).read_bytes()
    except FileNotFoundError as e:
        raise ImzaliDepoHatasi(f"eksik dosya: {e.filename}") from None
    mevcut = dosyalari_listele(dizin)
    mevcut_kume = set(mevcut)

    def getir(ad: str) -> bytes | None:
        if ad not in mevcut_kume:
            return None
        return (dizin / ad).read_bytes()

    return dogrula_veri(indeks_baytlari, imza_metni, kok, getir, mevcut, **secenekler)
