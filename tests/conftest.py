"""Ortak fikstürler: sentetik depo ve test anahtarları (yalnız bellekte/tmp'de)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from imzali_depo import cekirdek as c

PAROLA = b"yalniz-test-parolasi"
T0 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class Anahtar:
    def __init__(self) -> None:
        self.ozel_pem, self.acik_pem = c.anahtar_uret(PAROLA)
        self.ozel = c.ozel_anahtar_yukle(self.ozel_pem, PAROLA)
        self.acik = c.acik_anahtar_yukle(self.acik_pem)


@pytest.fixture
def anahtar():
    return Anahtar()


@pytest.fixture
def ikinci_anahtar():
    return Anahtar()


def depo_kur(kok: Path) -> Path:
    (kok / "paketler").mkdir(parents=True)
    (kok / "paketler" / "araç-1.0.0.tar").write_bytes(bytes(range(256)) * 8)
    (kok / "paketler" / "araç-1.0.1.tar").write_bytes(b"\x00\x01ikili\xff" * 100)
    (kok / "BENIOKU.txt").write_text("Örnek depo — sentetik içerik.\n", "utf-8")
    (kok / ".gizli").write_text("indekse girmemeli\n")
    return kok


def imzala(dizin: Path, ozel, *, surum=1, gun=30, zincir=None, simdi=T0) -> None:
    baytlar, imza = c.indeks_uret(dizin, ozel, surum=surum, gecerlilik_gun=gun,
                                  depo_adi="ornek", zincir=zincir, simdi=simdi)
    (dizin / c.INDEKS_ADI).write_bytes(baytlar)
    (dizin / c.IMZA_ADI).write_bytes(imza)


@pytest.fixture
def depo(tmp_path):
    return depo_kur(tmp_path / "depo")


@pytest.fixture
def imzali(depo, anahtar):
    imzala(depo, anahtar.ozel)
    return depo
