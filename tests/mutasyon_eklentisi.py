"""Kontrol grubu için pytest eklentisi: IMZALI_DEPO_MUTASYON ortam değişkenine
göre doğrulamanın BİR adımını bilerek kapatır. Yalnız testlerde yüklenir
(`-p mutasyon_eklentisi`); ürün kodunda hiçbir kapatma anahtarı yoktur."""

import os

from imzali_depo import cekirdek as c

MUTASYONLAR = {
    # Ed25519 imza doğrulaması her zaman "doğru" der
    "imza_kapali": ("_imza_dogrula", lambda *a, **k: True),
    # dosya özeti karşılaştırması her zaman "tutar" der
    "ozet_kapali": ("_ozet_tutar", lambda *a, **k: True),
    # süre sonu hiç dolmaz
    "sure_kapali": ("_sure_doldu", lambda *a, **k: False),
    # geçiş kayıtlarının imzası denetlenmez
    "zincir_kapali": ("_gecis_imzasi_dogru", lambda *a, **k: True),
}


def pytest_configure(config):
    ad = os.environ.get("IMZALI_DEPO_MUTASYON")
    if ad:
        hedef, sahte = MUTASYONLAR[ad]
        setattr(c, hedef, sahte)
