"""imzali-depo komut satırı arayüzü."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import __version__
from . import cekirdek as c

PAROLA_ORTAM = "IMZALI_DEPO_PAROLA"


def _parola(args, onayla: bool = False) -> bytes:
    if getattr(args, "parola_dosyasi", None):
        p = Path(args.parola_dosyasi).read_text("utf-8").rstrip("\r\n")
    elif os.environ.get(PAROLA_ORTAM):
        p = os.environ[PAROLA_ORTAM]
    else:
        p = getpass.getpass("Özel anahtar parolası: ")
        if onayla and getpass.getpass("Parola (tekrar): ") != p:
            raise c.ImzaliDepoHatasi("parolalar eşleşmiyor")
    if not p:
        raise c.ImzaliDepoHatasi("parola boş olamaz")
    return p.encode("utf-8")


def _zaman(metin: str | None):
    if metin is None:
        return None
    try:
        return c.zaman_oku(metin)
    except ValueError:
        raise c.ImzaliDepoHatasi("--simdi biçimi YYYY-AA-GGTSS:DD:ssZ olmalı") from None


def _yaz(yol: Path, veri: bytes, uzerine: bool, kip: int | None = None) -> None:
    if yol.exists() and not uzerine:
        raise c.ImzaliDepoHatasi(f"{yol} zaten var (üzerine yazmak için --uzerine-yaz)")
    yol.parent.mkdir(parents=True, exist_ok=True)
    if kip is not None:
        fd = os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, kip)
        with os.fdopen(fd, "wb") as f:
            f.write(veri)
        os.chmod(yol, kip)
    else:
        yol.write_bytes(veri)


def komut_anahtar_uret(args) -> int:
    ozel_pem, acik_pem = c.anahtar_uret(_parola(args, onayla=True))
    _yaz(Path(args.ozel), ozel_pem, args.uzerine_yaz, 0o600)
    _yaz(Path(args.acik), acik_pem, args.uzerine_yaz)
    kimlik = c.anahtar_kimligi(c.acik_anahtar_yukle(acik_pem))
    print(f"özel anahtar (parolalı): {args.ozel}")
    print(f"açık anahtar:            {args.acik}")
    print(f"anahtar kimliği:         {kimlik}")
    return 0


def komut_imzala(args) -> int:
    dizin = Path(args.dizin)
    ozel = c.ozel_anahtar_yukle(Path(args.ozel_anahtar).read_bytes(), _parola(args))
    zincir = c.zincir_oku(Path(args.zincir)) if args.zincir else []
    surum = args.surum if args.surum is not None else c.onceki_surum(dizin) + 1
    baytlar, imza = c.indeks_uret(
        dizin,
        ozel,
        surum=surum,
        gecerlilik_gun=args.gecerlilik_gun,
        depo_adi=args.depo_adi or dizin.resolve().name,
        zincir=zincir,
        simdi=_zaman(args.simdi),
    )
    (dizin / c.INDEKS_ADI).write_bytes(baytlar)
    (dizin / c.IMZA_ADI).write_bytes(imza)
    indeks = json.loads(baytlar)
    print(f"{len(indeks['dosyalar'])} dosya imzalandı · sürüm {surum} · "
          f"son geçerlilik {indeks['son_gecerlilik']} · anahtar {indeks['anahtar_kimligi']}")
    return 0


def komut_anahtar_dondur(args) -> int:
    eski = c.ozel_anahtar_yukle(Path(args.eski_ozel).read_bytes(), _parola(args))
    yeni = c.acik_anahtar_yukle(Path(args.yeni_acik).read_bytes())
    zincir_yolu = Path(args.zincir)
    kayitlar = c.zincir_oku(zincir_yolu)
    eski_kimlik = c.anahtar_kimligi(eski.public_key())
    if kayitlar:
        son = json.loads(kayitlar[-1]["kayit"])
        if son.get("yeni_anahtar_kimligi") != eski_kimlik:
            raise c.ImzaliDepoHatasi("eski anahtar zincirin son anahtarı değil")
    if c.anahtar_kimligi(yeni) == eski_kimlik:
        raise c.ImzaliDepoHatasi("yeni anahtar eskisiyle aynı")
    kayitlar.append(c.gecis_kaydi_olustur(eski, yeni, _zaman(args.simdi)))
    c.zincir_yaz(zincir_yolu, kayitlar)
    print(f"geçiş kaydedildi: {eski_kimlik} → {c.anahtar_kimligi(yeni)} ({len(kayitlar)} halka) · {zincir_yolu}")
    return 0


def komut_dogrula(args) -> int:
    kok = c.acik_anahtar_yukle(Path(args.acik_anahtar).read_bytes())
    bilinen = c.zincir_oku(Path(args.bilinen_zincir)) if args.bilinen_zincir else None
    s = c.dogrula_dizin(
        Path(args.dizin),
        kok,
        simdi=_zaman(args.simdi),
        bilinen_zincir=bilinen,
        en_dusuk_surum=args.en_dusuk_surum,
    )
    if args.json:
        print(json.dumps(s.sozluk(), ensure_ascii=False, indent=2))
    else:
        isaret = "GEÇERLİ" if s.gecerli else "REDDEDİLDİ"
        print(f"[{isaret}] indeks: {s.kod}" + (f" — {s.neden}" if s.neden else ""))
        if s.anahtar_kimligi:
            print(f"  anahtar {s.anahtar_kimligi} · zincir {s.zincir_uzunlugu} halka · sürüm {s.surum} · "
                  f"son geçerlilik {s.son_gecerlilik}")
        for d in s.dosyalar:
            print(f"  {'✓' if d['kod'] == c.TAMAM else '✗'} {d['kod']:<15} {d['ad']}"
                  + (f" — {d['neden']}" if d["neden"] else ""))
    return 0 if s.gecerli else 1


def ayristirici() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="imzali-depo", description="Ed25519 imzalı depo indeksi üretir ve doğrular.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    alt = p.add_subparsers(dest="komut", required=True)

    def parola_secenegi(a):
        a.add_argument("--parola-dosyasi", help=f"parolayı bu dosyadan oku (yoksa ${PAROLA_ORTAM}, yoksa sorulur)")

    a = alt.add_parser("anahtar-uret", help="parolayla şifreli Ed25519 anahtar çifti üret")
    a.add_argument("--ozel", default="imza.key", help="özel anahtar PEM (varsayılan: imza.key)")
    a.add_argument("--acik", default="imza.pub", help="açık anahtar PEM (varsayılan: imza.pub)")
    a.add_argument("--uzerine-yaz", action="store_true")
    parola_secenegi(a)
    a.set_defaults(fn=komut_anahtar_uret)

    a = alt.add_parser("imzala", help="dizin için index.json + index.json.sig üret")
    a.add_argument("dizin")
    a.add_argument("--ozel-anahtar", required=True)
    a.add_argument("--surum", type=int, help="indeks sürümü (varsayılan: önceki + 1)")
    a.add_argument("--gecerlilik-gun", type=float, default=30.0, help="kaç gün geçerli (varsayılan 30)")
    a.add_argument("--depo-adi")
    a.add_argument("--zincir", help="anahtar döndürme zinciri dosyası (indekse gömülür)")
    a.add_argument("--simdi", help="oluşturma anı (test/yeniden üretim için, YYYY-AA-GGTSS:DD:ssZ)")
    parola_secenegi(a)
    a.set_defaults(fn=komut_imzala)

    a = alt.add_parser("anahtar-dondur", help="yeni anahtarı eskisiyle imzalayan geçiş kaydı ekle")
    a.add_argument("--eski-ozel", required=True)
    a.add_argument("--yeni-acik", required=True)
    a.add_argument("--zincir", required=True, help="zincir dosyası (yoksa oluşturulur)")
    a.add_argument("--simdi")
    parola_secenegi(a)
    a.set_defaults(fn=komut_anahtar_dondur)

    a = alt.add_parser("dogrula", help="imzayı ve tüm dosya özetlerini doğrula")
    a.add_argument("dizin")
    a.add_argument("--acik-anahtar", required=True, help="güvenilen KÖK açık anahtar (PEM)")
    a.add_argument("--bilinen-zincir", help="daha önce görülen zincir; indeks bunu sürdürmeli")
    a.add_argument("--en-dusuk-surum", type=int, help="bundan düşük sürümü reddet (geri alma koruması)")
    a.add_argument("--simdi", help="doğrulama anı (varsayılan: şimdi)")
    a.add_argument("--json", action="store_true", help="makine okunur çıktı")
    a.set_defaults(fn=komut_dogrula)
    return p


def main(argv: list[str] | None = None) -> int:
    args = ayristirici().parse_args(argv)
    try:
        return args.fn(args)
    except (c.ImzaliDepoHatasi, OSError) as e:
        print(f"hata: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
