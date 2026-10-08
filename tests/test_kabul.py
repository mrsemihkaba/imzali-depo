"""Geçerli durumlar ve biçim/CLI davranışı."""

import json

from conftest import PAROLA, T0, imzala
from imzali_depo import cekirdek as c
from imzali_depo.cli import main


def test_gecerli_imza(imzali, anahtar):
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0)
    assert s.gecerli, s.sozluk()
    assert s.kod == c.TAMAM
    assert [d["ad"] for d in s.dosyalar] == ["BENIOKU.txt", "paketler/araç-1.0.0.tar", "paketler/araç-1.0.1.tar"]
    assert all(d["kod"] == c.TAMAM for d in s.dosyalar)


def test_indeks_alanlari(imzali, anahtar):
    ind = json.loads((imzali / "index.json").read_text("utf-8"))
    assert ind["bicim"] == "imzali-depo/1"
    assert ind["surum"] == 1
    assert ind["olusturma"] == "2026-01-15T12:00:00Z"
    assert ind["son_gecerlilik"] == "2026-02-14T12:00:00Z"
    assert ind["anahtar_kimligi"] == c.anahtar_kimligi(anahtar.acik)
    assert len(ind["anahtar_kimligi"]) == 32
    d = ind["dosyalar"][0]
    assert set(d) == {"ad", "boyut", "sha256"}
    assert ".gizli" not in [x["ad"] for x in ind["dosyalar"]]
    # ayrık imza: tek satır base64, 64 bayt
    assert len(c.b64_coz((imzali / "index.json.sig").read_text())) == 64


def test_ozel_anahtar_parolali(anahtar):
    assert b"ENCRYPTED PRIVATE KEY" in anahtar.ozel_pem
    try:
        c.ozel_anahtar_yukle(anahtar.ozel_pem, b"yanlis")
    except c.ImzaliDepoHatasi:
        pass
    else:
        raise AssertionError("yanlış parola kabul edildi")


def test_cli_uctan_uca(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("IMZALI_DEPO_PAROLA", PAROLA.decode())
    d = tmp_path / "d"
    d.mkdir()
    (d / "a.txt").write_text("a")
    k, p = str(tmp_path / "k.key"), str(tmp_path / "k.pub")
    assert main(["anahtar-uret", "--ozel", k, "--acik", p]) == 0
    assert oct((tmp_path / "k.key").stat().st_mode & 0o777) == "0o600"
    assert main(["imzala", str(d), "--ozel-anahtar", k]) == 0
    assert main(["imzala", str(d), "--ozel-anahtar", k]) == 0  # sürüm otomatik artar
    assert json.loads((d / "index.json").read_text())["surum"] == 2
    capsys.readouterr()
    assert main(["dogrula", str(d), "--acik-anahtar", p, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["gecerli"] is True
    (d / "a.txt").write_text("b")
    assert main(["dogrula", str(d), "--acik-anahtar", p]) == 1
    # var olan anahtarı ezmez
    assert main(["anahtar-uret", "--ozel", k, "--acik", p]) == 2


def test_en_dusuk_surum(imzali, anahtar):
    assert c.dogrula_dizin(imzali, anahtar.acik, simdi=T0, en_dusuk_surum=1).gecerli
    s = c.dogrula_dizin(imzali, anahtar.acik, simdi=T0, en_dusuk_surum=2)
    assert not s.gecerli and s.kod == c.SURUM_GERI
