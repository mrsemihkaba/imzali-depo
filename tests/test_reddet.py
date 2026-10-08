"""Reddedilmesi gereken durumlar. Kontrol grubu (test_kontrol_grubu.py) bu
dosyayı doğrulama adımları bilerek kapatılmış hâlde koşturup düşmesini bekler."""

import json
from datetime import timedelta

from conftest import T0, imzala
from imzali_depo import cekirdek as c


def kodlar(s):
    return {d["ad"]: d["kod"] for d in s.dosyalar}


def test_bir_bayt_bozuk_dosya_reddedilir(imzali, anahtar):
    yol = imzali / "paketler" / "araç-1.0.0.tar"
    veri = bytearray(yol.read_bytes())
    veri[1000] ^= 0x01  # tek bit, boyut aynı
    yol.write_bytes(bytes(veri))
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0)
    assert not s.gecerli
    assert s.kod == c.TAMAM  # indeks sağlam; sorun dosyada
    assert kodlar(s)["paketler/araç-1.0.0.tar"] == c.OZET_UYUSMAZ


def test_boyutu_degisen_dosya_reddedilir(imzali, anahtar):
    with open(imzali / "BENIOKU.txt", "ab") as f:
        f.write(b"!")
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0)
    assert not s.gecerli and kodlar(s)["BENIOKU.txt"] == c.BOYUT_UYUSMAZ


def test_eksik_ve_imzasiz_dosya_reddedilir(imzali, anahtar):
    (imzali / "BENIOKU.txt").unlink()
    (imzali / "paketler" / "arka-kapi.sh").write_text("echo pwned\n")
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0)
    assert not s.gecerli
    assert kodlar(s)["BENIOKU.txt"] == c.EKSIK
    assert kodlar(s)["paketler/arka-kapi.sh"] == c.IMZASIZ_DOSYA


def test_bozulmus_indeks_reddedilir(imzali, anahtar):
    # Saldırgan dosyayı değiştirip indeksteki özeti de günceller: yalnız imza yakalar.
    hedef = imzali / "BENIOKU.txt"
    hedef.write_text("kötü içerik\n", "utf-8")
    ind = json.loads((imzali / "index.json").read_text("utf-8"))
    for d in ind["dosyalar"]:
        if d["ad"] == "BENIOKU.txt":
            d["boyut"] = hedef.stat().st_size
            d["sha256"] = c.sha256_hex(hedef.read_bytes())
    (imzali / "index.json").write_text(json.dumps(ind, ensure_ascii=False, indent=2) + "\n", "utf-8")
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0)
    assert not s.gecerli
    assert s.kod == c.IMZA_GECERSIZ


def test_indekste_tek_bayt_bozulma_reddedilir(imzali, anahtar):
    yol = imzali / "index.json"
    veri = yol.read_bytes().replace(b'"surum": 1', b'"surum": 9')
    yol.write_bytes(veri)
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0)
    assert not s.gecerli and s.kod == c.IMZA_GECERSIZ


def test_bozuk_imza_dosyasi_reddedilir(imzali, anahtar):
    (imzali / "index.json.sig").write_text("bu bir imza değil")
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0)
    assert not s.gecerli and s.kod == c.IMZA_BICIMI


def test_yanlis_anahtar_reddedilir(imzali, ikinci_anahtar):
    s = c.dogrula_dizin(imzali, ikinci_anahtar.acik, simdi=T0)
    assert not s.gecerli
    assert s.kod == c.IMZA_GECERSIZ


def test_yanlis_anahtarla_imzalanip_kimligi_sahtelenen_indeks(imzali, anahtar, ikinci_anahtar):
    # Saldırgan kendi anahtarıyla imzalar ama kimlik alanına güvenilen anahtarınkini yazar.
    ind = json.loads((imzali / "index.json").read_text("utf-8"))
    ind["anahtar_kimligi"] = c.anahtar_kimligi(anahtar.acik)
    b = (json.dumps(ind, ensure_ascii=False, indent=2) + "\n").encode()
    (imzali / "index.json").write_bytes(b)
    (imzali / "index.json.sig").write_text(c.b64(ikinci_anahtar.ozel.sign(b)) + "\n")
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0)
    assert not s.gecerli and s.kod == c.IMZA_GECERSIZ


def test_suresi_gecmis_indeks_reddedilir(imzali, anahtar):
    assert c.dogrula_dizin(imzali, anahtar.acik, simdi=T0 + timedelta(days=29)).gecerli
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0 + timedelta(days=30, seconds=1))
    assert not s.gecerli and s.kod == c.SURE_DOLMUS


def test_gelecek_tarihli_indeks_reddedilir(imzali, anahtar):
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0 - timedelta(hours=1))
    assert not s.gecerli and s.kod == c.GELECEK_TARIHLI


def test_guvensiz_yol_reddedilir(imzali, anahtar):
    ind = json.loads((imzali / "index.json").read_text("utf-8"))
    ind["dosyalar"].append({"ad": "../../etc/passwd", "boyut": 1, "sha256": "0" * 64})
    b = (json.dumps(ind, ensure_ascii=False, indent=2) + "\n").encode()
    (imzali / "index.json").write_bytes(b)
    (imzali / "index.json.sig").write_text(c.b64(anahtar.ozel.sign(b)) + "\n")
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0)
    assert not s.gecerli and kodlar(s)["../../etc/passwd"] == c.GUVENSIZ_YOL
