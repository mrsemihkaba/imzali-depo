"""Kontrol grubu (mutasyon testi).

Reddetme testleri yalnızca doğrulama gerçekten çalıştığı için mi geçiyor?
Bunu göstermek için her doğrulama adımını tek tek bilerek kapatıp
test_reddet.py + test_zincir.py'yi alt süreçte koşturuyoruz: ilgili testler
DÜŞMELİ. Mutasyonsuz koşu ise (kontrol) tamamen geçmeli.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
HEDEFLER = ["tests/test_reddet.py", "tests/test_zincir.py"]


def kos(mutasyon: str | None) -> tuple[int, str]:
    ortam = dict(os.environ)
    ortam.pop("IMZALI_DEPO_MUTASYON", None)
    if mutasyon:
        ortam["IMZALI_DEPO_MUTASYON"] = mutasyon
    ortam["PYTHONPATH"] = os.pathsep.join([str(KOK / "tests"), str(KOK), ortam.get("PYTHONPATH", "")])
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rf", "-p", "mutasyon_eklentisi", "-p", "no:cacheprovider", *HEDEFLER],
        cwd=KOK, env=ortam, capture_output=True, text=True, timeout=300,
    )
    return r.returncode, r.stdout + r.stderr


def test_kontrol_mutasyonsuz_hepsi_gecer():
    kod, cikti = kos(None)
    assert kod == 0, cikti


@pytest.mark.parametrize("mutasyon, dusmesi_gerekenler", [
    ("imza_kapali", ["test_bozulmus_indeks_reddedilir", "test_indekste_tek_bayt_bozulma_reddedilir",
                     "test_yanlis_anahtar_reddedilir", "test_sahte_gecis_kaydi_reddedilir"]),
    ("ozet_kapali", ["test_bir_bayt_bozuk_dosya_reddedilir"]),
    ("sure_kapali", ["test_suresi_gecmis_indeks_reddedilir"]),
    ("zincir_kapali", ["test_sahte_gecis_kaydi_reddedilir", "test_gecis_kaydi_kurcalanirsa_reddedilir"]),
])
def test_dogrulama_kapatilinca_testler_duser(mutasyon, dusmesi_gerekenler):
    kod, cikti = kos(mutasyon)
    assert kod != 0, f"{mutasyon} mutasyonu hiçbir testi düşürmedi:\n{cikti}"
    dusenler = [satir for satir in cikti.splitlines() if satir.startswith("FAILED ")]
    for ad in dusmesi_gerekenler:
        assert any(f"::{ad}" in satir for satir in dusenler), f"{mutasyon}: {ad} düşmedi\n{cikti}"
