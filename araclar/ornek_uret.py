"""docs/ornek/ altındaki örnek depoları imzali-depo CLI'siyle üretir.

Özel anahtarlar geçici bir dizinde oluşturulur ve iş bitince SİLİNİR; depoya
yalnız açık anahtar (docs/ornek/anahtarlar/kok.pub) girer. Bu yüzden örnekler
yeniden üretildiğinde anahtarlar ve imzalar değişir.

Kullanım:  python araclar/ornek_uret.py
"""

from __future__ import annotations

import json
import os
import random
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

from imzali_depo.cli import main as cli  # noqa: E402

ORNEK = KOK / "docs" / "ornek"
ZAMAN = "2026-10-01T09:00:00Z"
UZUN = "3650"  # örnek panelde yıllarca geçerli kalsın


def icerik_yaz(d: Path) -> None:
    rnd = random.Random(20261001)  # sentetik ama sabit ikili içerik
    (d / "paketler").mkdir(parents=True)
    (d / "belgeler").mkdir()
    (d / "paketler" / "ornek-arac_1.2.0_amd64.bin").write_bytes(bytes(rnd.getrandbits(8) for _ in range(48_000)))
    (d / "paketler" / "ornek-arac_1.2.0_arm64.bin").write_bytes(bytes(rnd.getrandbits(8) for _ in range(41_500)))
    (d / "paketler" / "ornek-kutuphane-0.9.3.tar").write_bytes(bytes(rnd.getrandbits(8) for _ in range(12_288)))
    (d / "SURUMLER.txt").write_text(
        "ornek-arac 1.2.0 — kararlı\nornek-kutuphane 0.9.3 — önizleme\n"
        "Bu depo SENTETİKTİR; yalnız imzali-depo doğrulayıcısını göstermek içindir.\n", "utf-8")
    (d / "belgeler" / "kurulum.md").write_text(
        "# Kurulum\n\n1. index.json ve index.json.sig dosyalarını indirin.\n"
        "2. `imzali-depo dogrula . --acik-anahtar kok.pub` çalıştırın.\n"
        "3. Ayna: https://depo.example.com/ (örnek adres)\n", "utf-8")


def listele(d: Path) -> list[str]:
    return sorted(
        p.relative_to(d).as_posix()
        for p in d.rglob("*")
        if p.is_file() and p.name not in ("index.json", "index.json.sig")
    )


def main() -> None:
    os.environ["IMZALI_DEPO_PAROLA"] = secrets.token_urlsafe(24)  # yalnız bu süreçte
    if ORNEK.exists():
        shutil.rmtree(ORNEK)
    (ORNEK / "anahtarlar").mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="imzali-depo-anahtar-") as gecici:
        g = Path(gecici)
        kok_ozel, ikinci_ozel = str(g / "kok.key"), str(g / "ikinci.key")
        kok_acik = str(ORNEK / "anahtarlar" / "kok.pub")
        ikinci_acik = str(g / "ikinci.pub")
        assert cli(["anahtar-uret", "--ozel", kok_ozel, "--acik", kok_acik]) == 0
        assert cli(["anahtar-uret", "--ozel", ikinci_ozel, "--acik", ikinci_acik]) == 0

        def depo(ad: str) -> Path:
            d = ORNEK / ad
            d.mkdir()
            icerik_yaz(d)
            return d

        d = depo("gecerli")
        assert cli(["imzala", str(d), "--ozel-anahtar", kok_ozel, "--surum", "7", "--depo-adi", "ornek-depo",
                    "--gecerlilik-gun", UZUN, "--simdi", ZAMAN]) == 0

        d = depo("dondurulmus")
        zincir = str(g / "zincir.json")
        assert cli(["anahtar-dondur", "--eski-ozel", kok_ozel, "--yeni-acik", ikinci_acik,
                    "--zincir", zincir, "--simdi", ZAMAN]) == 0
        assert cli(["imzala", str(d), "--ozel-anahtar", ikinci_ozel, "--zincir", zincir, "--surum", "8",
                    "--depo-adi", "ornek-depo", "--gecerlilik-gun", UZUN, "--simdi", ZAMAN]) == 0

        d = depo("bozuk")
        assert cli(["imzala", str(d), "--ozel-anahtar", kok_ozel, "--surum", "7", "--depo-adi", "ornek-depo",
                    "--gecerlilik-gun", UZUN, "--simdi", ZAMAN]) == 0
        hedef = d / "paketler" / "ornek-arac_1.2.0_amd64.bin"
        veri = bytearray(hedef.read_bytes())
        veri[31337] ^= 0x01  # tek bit: boyut aynı, özet farklı
        hedef.write_bytes(bytes(veri))
        (d / "paketler" / "arka-kapi.sh").write_text("#!/bin/sh\necho 'imzasız eklenti'\n")

        d = depo("suresi-gecmis")
        assert cli(["imzala", str(d), "--ozel-anahtar", kok_ozel, "--surum", "3", "--depo-adi", "ornek-depo",
                    "--gecerlilik-gun", "30", "--simdi", "2026-01-01T09:00:00Z"]) == 0
    # geçici dizin silindi: özel anahtarlar artık hiçbir yerde yok

    ornekler = [
        {"id": "gecerli", "baslik": "Geçerli depo", "beklenen": "gecerli",
         "aciklama": "Kök anahtarla imzalı, tüm dosyalar sağlam."},
        {"id": "dondurulmus", "baslik": "Anahtar döndürülmüş", "beklenen": "gecerli",
         "aciklama": "Yeni anahtarla imzalı; kök → yeni geçiş kaydı indekse gömülü."},
        {"id": "bozuk", "baslik": "Bilerek bozulmuş", "beklenen": "red",
         "aciklama": "Bir pakette tek bit değişti ve imzasız bir betik eklendi."},
        {"id": "suresi-gecmis", "baslik": "Süresi geçmiş", "beklenen": "red",
         "aciklama": "İmza sağlam ama indeksin son geçerlilik tarihi geçti (yeniden oynatma)."},
    ]
    for o in ornekler:
        o["dizin"] = o["id"]
        o["dosyalar"] = listele(ORNEK / o["id"])
    (ORNEK / "ornekler.json").write_text(
        json.dumps({"kok_anahtar": "anahtarlar/kok.pub", "ornekler": ornekler}, ensure_ascii=False, indent=2) + "\n",
        "utf-8")
    print("örnekler yazıldı:", ", ".join(o["id"] for o in ornekler))


if __name__ == "__main__":
    main()
