# imzali-depo biçimi (sürüm `imzali-depo/1`)

Bu belge, `imzali-depo` aracının ürettiği ve doğruladığı dosyaları tanımlar.
Python doğrulayıcısı (`imzali_depo/cekirdek.py`) ve tarayıcı doğrulayıcısı
(`docs/dogrulayici.js`) bu belgeye birebir uyar; ikisinin aynı girdide aynı
sonucu verdiği `tests/js/esdeger.test.mjs` ile sınanır.

## 1. Dosyalar

Bir depo dizini şunları içerir:

| Dosya | İçerik |
|---|---|
| `index.json` | Depodaki her dosyanın adı, boyutu ve SHA-256 özeti + üst veri (UTF-8 JSON). |
| `index.json.sig` | `index.json` dosyasının **ham baytları** üzerindeki Ed25519 imzası; 64 bayt, standart base64, tek satır (sondaki satır sonu serbest). |
| diğer her şey | Depo içeriği. `index.json`, `index.json.sig` ve yol parçalarından herhangi biri `.` ile başlayan dosyalar indekse girmez. |

İmza **ayrıktır** (detached) ve kanonikleştirme YOKTUR: doğrulayıcı diskteki
baytları olduğu gibi doğrular. `index.json` dosyasına tek bir boşluk eklemek
bile imzayı bozar. Bu tercih, farklı dillerde JSON kanonikleştirme
uyumsuzluğu riskini tümden ortadan kaldırır.

## 2. Anahtarlar

* Algoritma: **Ed25519** (RFC 8032).
* Özel anahtar: PKCS#8 PEM, parola ile şifreli (PEM başlığı `ENCRYPTED PRIVATE KEY`), dosya kipi `0600`. Parola `--parola-dosyasi`, `IMZALI_DEPO_PAROLA` ortam değişkeni ya da etkileşimli istem ile verilir; hiçbir zaman diske yazılmaz.
* Açık anahtar: SubjectPublicKeyInfo PEM (`-----BEGIN PUBLIC KEY-----`, 44 baytlık DER).
* **Anahtar kimliği**: 32 baytlık ham açık anahtarın SHA-256 özetinin ilk 16 baytı, küçük harf onaltılık (32 karakter).

## 3. `index.json`

```json
{
  "bicim": "imzali-depo/1",
  "depo": "ornek-depo",
  "surum": 7,
  "olusturma": "2026-10-01T09:00:00Z",
  "son_gecerlilik": "2036-09-28T09:00:00Z",
  "anahtar_kimligi": "201fcc45ac0a6f08195aaaef4628ea9b",
  "anahtar_zinciri": [],
  "dosyalar": [
    { "ad": "paketler/ornek-arac_1.2.0_amd64.bin", "boyut": 48000, "sha256": "…64 onaltılık…" }
  ]
}
```

| Alan | Tür | Anlam |
|---|---|---|
| `bicim` | dize | Her zaman `imzali-depo/1`. Başka değer → `BICIM_HATASI`. |
| `depo` | dize | Bilgi amaçlı depo adı. |
| `surum` | pozitif tamsayı | Her yayında artar. Doğrulayıcı `--en-dusuk-surum` ile geri almayı reddeder. |
| `olusturma` | `YYYY-AA-GGTSS:DD:ssZ` (UTC) | İmzalama anı. Doğrulama anından 5 dakikadan fazla ilerideyse → `GELECEK_TARIHLI`. |
| `son_gecerlilik` | aynı biçim | Bu andan sonra indeks reddedilir (`SURE_DOLMUS`). Varsayılan: oluşturma + 30 gün. |
| `anahtar_kimligi` | 32 onaltılık | İndeksi imzalayan anahtarın kimliği; zincirin son anahtarıyla aynı olmalı. |
| `anahtar_zinciri` | dizi | Anahtar döndürme geçiş kayıtları (bkz. §4). Döndürme yoksa boş. |
| `dosyalar` | dizi | Ada göre (kod noktası sırası) sıralı dosya kayıtları. |
| `dosyalar[].ad` | dize | `/` ayraçlı göreli yol. Mutlak yol, `\`, NUL, boş parça, `.` ya da `..` içeremez (`GUVENSIZ_YOL`). |
| `dosyalar[].boyut` | negatif olmayan tamsayı | Bayt cinsinden boyut. |
| `dosyalar[].sha256` | 64 küçük onaltılık | İçeriğin SHA-256 özeti. |

## 4. Anahtar döndürme zinciri

Anahtar değiştiğinde (`imzali-depo anahtar-dondur`), **eski özel anahtar**
yeni açık anahtarı onaylayan bir geçiş kaydı imzalar. Kayıtlar bir zincir
dosyasında (`{"bicim":"imzali-depo-zincir/1","kayitlar":[…]}`) birikir ve
`imzala --zincir` ile her indekse gömülür:

```json
{
  "kayit": "{\"bicim\":\"imzali-depo-gecis/1\",\"eski_anahtar_kimligi\":\"…\",\"yeni_anahtar_kimligi\":\"…\",\"yeni_acik_anahtar\":\"<32 bayt base64>\",\"tarih\":\"2026-10-01T09:00:00Z\"}",
  "imza": "<eski anahtarın 64 baytlık Ed25519 imzası, base64>"
}
```

`kayit` bir JSON **metnidir** (iç içe nesne değil); imza bu metnin UTF-8
baytları üzerindedir. Böylece kayıt, indeks yeniden biçimlendirilse bile
bayt-bayt aynı kalır.

Doğrulayıcı, kullanıcının **güvendiği kök açık anahtardan** başlar ve her
kaydı sırayla izler: kayıt etkin anahtarla imzalı olmalı, `eski_anahtar_kimligi`
etkin anahtarın kimliği olmalı, `yeni_anahtar_kimligi` gömülü yeni anahtarın
kimliğiyle tutmalı; ardından etkin anahtar yeni anahtar olur. Zincirin sonunda
kalan anahtar indeksin imzasını doğrulamalıdır. Güvenilen anahtar zincirin
ortasındaki bir anahtarsa, o halkaya kadarki geçmiş atlanır.

**Eski anahtarın çalınması**: zinciri bilmeyen bir doğrulayıcı, eski kök
anahtarla imzalanmış zincirsiz yeni bir indeksi kabul eder. Buna karşı
doğrulayıcı daha önce gördüğü zinciri `--bilinen-zincir` ile verir; indeks
o zinciri önek olarak sürdürmüyorsa `ZINCIR_GERI_ALINMIS` ile reddedilir.

## 5. Doğrulama sırası ve sonuç kodları

İndeks düzeyindeki ilk hata raporlanır; dosyalar, indeks okunabildiği sürece
her durumda tek tek raporlanır (ama indeks hatası varsa sonuç geçersizdir).

1. `index.json.sig` 64 baytlık base64 değilse → `IMZA_BICIMI`
2. `index.json` UTF-8 JSON nesnesi değilse → `BICIM_HATASI`
3. Anahtar zinciri yürünemiyorsa → `ZINCIR_GECERSIZ`
4. `--bilinen-zincir` verilmişse ve indeks onu sürdürmüyorsa → `ZINCIR_GERI_ALINMIS`
5. Ed25519 imzası zincirin son anahtarıyla doğrulanmıyorsa → `IMZA_GECERSIZ`
6. `anahtar_kimligi` imzalayan anahtarınki değilse → `ANAHTAR_UYUSMAZ`
7. `bicim` / `surum` / `dosyalar` biçimsizse → `BICIM_HATASI`
8. Zamanlar biçimsizse → `BICIM_HATASI`; süre dolmuşsa → `SURE_DOLMUS`; gelecek tarihliyse → `GELECEK_TARIHLI`
9. `surum` < `--en-dusuk-surum` ise → `SURUM_GERI`
10. Her dosya kaydı için: `GUVENSIZ_YOL`, yinelenen ad (`BICIM_HATASI`), `EKSIK`, `BOYUT_UYUSMAZ`, `OZET_UYUSMAZ`; indekste olmayan her dosya → `IMZASIZ_DOSYA`

Sonuç ancak indeks `TAMAM` **ve** her dosya `TAMAM` ise geçerlidir.
`imzali-depo dogrula --json` çıktısı ve panelin `window.__sonSonuc` nesnesi
aynı yapıdadır:

```json
{
  "gecerli": false,
  "indeks": { "kod": "TAMAM", "neden": "", "anahtar_kimligi": "…", "zincir_uzunlugu": 0,
              "surum": 7, "son_gecerlilik": "2036-09-28T09:00:00Z" },
  "dosyalar": [ { "ad": "paketler/arka-kapi.sh", "kod": "IMZASIZ_DOSYA", "neden": "indekste olmayan (imzasız) dosya" } ]
}
```

## 6. Tehdit modeli ve sınırlar

* **Korunur**: dosya içeriğinin ya da indeksin değiştirilmesi, imzasız dosya eklenmesi, dosya silinmesi, yol geçişi (`../`), başka anahtarla imzalama, eski indeksin süresi dolduktan sonra yeniden oynatılması, sürüm geri alma (`--en-dusuk-surum`), çalınmış eski anahtarla zincirsiz indeks (`--bilinen-zincir`).
* **Korunmaz**: süre dolmadan önceki yeniden oynatma (doğrulayıcı sürüm durumunu kendisi saklamaz; `--en-dusuk-surum` ile kullanıcı verir), doğrulayıcının saatinin yanlış olması, güvenilen kök anahtarın kendisinin çalınması (iptal listesi yok), dondurma saldırısına karşı çevrimiçi zaman damgası (TUF'taki `timestamp` rolü yok).
* Sembolik bağlar imzalanmaz; `imzala` bunları görünce durur.
