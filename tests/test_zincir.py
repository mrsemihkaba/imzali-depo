"""Anahtar döndürme zinciri."""

import json

from conftest import T0, Anahtar, imzala
from imzali_depo import cekirdek as c


def test_anahtar_dondurme_zinciri(depo, anahtar):
    k2, k3 = Anahtar(), Anahtar()
    zincir = [c.gecis_kaydi_olustur(anahtar.ozel, k2.acik, T0)]
    zincir.append(c.gecis_kaydi_olustur(k2.ozel, k3.acik, T0))
    imzala(depo, k3.ozel, surum=3, zincir=zincir)
    # Yalnız kök anahtarı bilen doğrulayıcı iki halkayı izleyip kabul eder
    s = c.dogrula_dizin(depo, anahtar.acik, simdi=T0)
    assert s.gecerli, s.sozluk()
    assert s.zincir_uzunlugu == 2 and s.anahtar_kimligi == c.anahtar_kimligi(k3.acik)
    # Ara anahtarı güvenilen kabul eden doğrulayıcı da kabul eder
    assert c.dogrula_dizin(depo, k2.acik, simdi=T0).gecerli
    # Zincirle ilgisiz bir anahtar reddedilir
    assert c.dogrula_dizin(depo, Anahtar().acik, simdi=T0).kod == c.ZINCIR_GECERSIZ


def test_sahte_gecis_kaydi_reddedilir(depo, anahtar):
    saldirgan, k2 = Anahtar(), Anahtar()
    # saldırgan kendi anahtarını kökten geçiyormuş gibi gösterir ama kendisi imzalar
    sahte = c.gecis_kaydi_olustur(saldirgan.ozel, k2.acik, T0)
    kayit = json.loads(sahte["kayit"])
    kayit["eski_anahtar_kimligi"] = c.anahtar_kimligi(anahtar.acik)
    metin = json.dumps(kayit, separators=(",", ":"))
    sahte = {"kayit": metin, "imza": c.b64(saldirgan.ozel.sign(metin.encode()))}
    imzala(depo, k2.ozel, zincir=[sahte])
    s = c.dogrula_dizin(depo, anahtar.acik, simdi=T0)
    assert not s.gecerli and s.kod == c.ZINCIR_GECERSIZ


def test_gecis_kaydi_kurcalanirsa_reddedilir(depo, anahtar):
    k2, saldirgan = Anahtar(), Anahtar()
    g = c.gecis_kaydi_olustur(anahtar.ozel, k2.acik, T0)
    # imzalı kayıttaki yeni anahtarı saldırganınkiyle değiştir
    kayit = json.loads(g["kayit"])
    kayit["yeni_acik_anahtar"] = c.b64(c.ham_acik(saldirgan.acik))
    kayit["yeni_anahtar_kimligi"] = c.anahtar_kimligi(saldirgan.acik)
    g = {"kayit": json.dumps(kayit, separators=(",", ":")), "imza": g["imza"]}
    imzala(depo, saldirgan.ozel, zincir=[g])
    assert c.dogrula_dizin(depo, anahtar.acik, simdi=T0).kod == c.ZINCIR_GECERSIZ


def test_eski_anahtarla_geri_alma_bilinen_zincirle_reddedilir(depo, anahtar):
    k2 = Anahtar()
    zincir = [c.gecis_kaydi_olustur(anahtar.ozel, k2.acik, T0)]
    # Eski (belki çalınmış) kök anahtarla, zincirsiz yeni bir indeks:
    imzala(depo, anahtar.ozel)
    assert c.dogrula_dizin(depo, anahtar.acik, simdi=T0).gecerli  # zinciri bilmeyen kabul eder
    s = c.dogrula_dizin(depo, anahtar.acik, simdi=T0, bilinen_zincir=zincir)
    assert not s.gecerli and s.kod == c.ZINCIR_GERI_ALINMIS
    # Zinciri sürdüren meşru indeks kabul edilir
    imzala(depo, k2.ozel, surum=2, zincir=zincir)
    assert c.dogrula_dizin(depo, anahtar.acik, simdi=T0, bilinen_zincir=zincir).gecerli


def test_imzala_zincir_sonu_uyusmazsa_reddeder(depo, anahtar):
    k2 = Anahtar()
    zincir = [c.gecis_kaydi_olustur(anahtar.ozel, k2.acik, T0)]
    try:
        imzala(depo, anahtar.ozel, zincir=zincir)
    except c.ImzaliDepoHatasi:
        return
    raise AssertionError("zincir sonu uyuşmazlığı fark edilmedi")
