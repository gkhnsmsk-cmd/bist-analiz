# -*- coding: utf-8 -*-
"""
akd_veri_toplama.py — Favori hisseler için GÜNLÜK AKD verisini otomatik çekip
akd_egitim_verisi.csv'ye ekleyen ve bir gün sonra gerçek fiyat hareketiyle
GERİYE DÖNÜK etiketleyen script.
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR: AKD_Model_Egitim_Rehberi.md'deki makine öğrenmesi modelini eğitmek
için geçmiş (özellik, gerçekleşen getiri) çiftlerinden oluşan bir veri seti
gerekir. Bugün tek bir günün verisiyle model eğitilemez — bu script HER GÜN
çalıştırılıp veri setini büyütmek, VE bir önceki günün kaydını o günün
GERÇEKTE ne yaptığıyla (T+1 getiri) etiketlemek için tasarlandı.

KAPSAM: Telegram botu hız sınırına (flood-wait) takılmamak için SADECE
favoriler.py'deki hisseler için çalışır — 560 hissenin tamamı için ASLA
kullanılmamalı (bkz. telegram_akd.py başındaki uyarı).

ÇALIŞTIRMA:
  - Elle: python akd_veri_toplama.py
  - Otomatik: Windows Görev Zamanlayıcısı'na her gün borsa kapanışından sonra
    (örn. 18:30) eklenebilir — bkz. ARKA_PLAN_TARAMA.bat mantığı.

Her çalıştırmada SIRAYLA şunlar olur:
  1) Önce DÜNKÜ (ve daha eski, hâlâ etiketlenmemiş) kayıtları bugünün
     kapanış fiyatlarıyla etiketler (T+1 getiri hesabı).
  2) Sonra favori hisseler için BUGÜNÜN AKD verisini çeker ve (henüz
     etiketlenmemiş "target_t1_return=" boş satır olarak) veri setine ekler.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
from pathlib import Path

import telegram_akd as takd
import favoriler as fav
import veri_katmani as vk

KLASOR = Path(__file__).parent
CSV_DOSYA = KLASOR / "akd_egitim_verisi.csv"

KOLONLAR = [
    "tarih", "sembol", "kapanis_fiyati",
    "ilk5_alici_yuzde", "ilk5_satici_yuzde", "akd_spread",
    "diger_alici_yuzde", "diger_satici_yuzde", "en_buyuk_alici_yuzde",
    "kurumsal_alim_gucu", "maliyet_fiyat_farki", "akd_hacim_rasyosu",
    "kural_puani", "kural_karari", "guven",
    "target_t1_return", "target_t1_tarih",
]


def _log(msg):
    print(f"[{dt.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}] {msg}")


def _csv_oku() -> list:
    if not CSV_DOSYA.exists():
        return []
    with open(CSV_DOSYA, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _csv_yaz(satirlar: list):
    gecici = CSV_DOSYA.with_suffix(".csv.tmp")
    with open(gecici, "w", encoding="utf-8", newline="") as f:
        yazici = csv.DictWriter(f, fieldnames=KOLONLAR)
        yazici.writeheader()
        for s in satirlar:
            yazici.writerow({k: s.get(k, "") for k in KOLONLAR})
    os.replace(gecici, CSV_DOSYA)


def _ort_hacim_10gun(sembol: str) -> float | None:
    try:
        df = vk.fiyat_gecmisi(sembol, yil=0.5)
        if df is None or len(df) < 5 or "Volume" not in df.columns:
            return None
        return float(df["Volume"].tail(10).mean())
    except Exception:
        return None


def gunluk_topla(semboller: list = None, bekleme_sn: float = 4.0, ilerleme=None):
    """Verilen (veya favorilerdeki) hisseler için bugünün AKD verisini çeker,
    özellik çıkarır, veri setine (henüz etiketlenmemiş satır olarak) ekler."""
    semboller = semboller or fav.getir()
    if not semboller:
        _log("Favori/hedef hisse listesi boş — toplanacak bir şey yok.")
        return []

    mevcut = _csv_oku()
    bugun = dt.date.today().isoformat()
    zaten_bugun = {(s["tarih"], s["sembol"]) for s in mevcut}

    eklenen = []
    for i, sembol in enumerate(semboller):
        sembol = sembol.upper()
        if (bugun, sembol) in zaten_bugun:
            _log(f"{sembol}: bugün için zaten kayıt var, atlanıyor.")
            continue
        try:
            _dosya, veri = takd.akd_getir(sembol)
            tablo = veri.get("tablo")
            if not tablo:
                _log(f"{sembol}: sayısal tablo çıkarılamadı ({veri.get('tablo_hatasi', '?')}), atlanıyor.")
                continue
            kapanis = veri.get("kapanis_fiyati")
            ort_hacim = _ort_hacim_10gun(sembol)
            ozellikler = takd.akd_ozellik_cikar(tablo, kapanis_fiyati=kapanis, ort_hacim_10gun=ort_hacim)
            sinyal = veri.get("sinyal") or {}

            satir = {
                "tarih": bugun, "sembol": sembol, "kapanis_fiyati": kapanis,
                **ozellikler,
                "kural_karari": sinyal.get("karar"),
                "guven": tablo.get("guven"),
                "target_t1_return": "", "target_t1_tarih": "",
            }
            mevcut.append(satir)
            eklenen.append(satir)
            _log(f"{sembol}: eklendi ({sinyal.get('karar', '?')}, puan {sinyal.get('puan', '?')}).")
        except Exception as e:
            _log(f"{sembol}: HATA — {e}")
        if ilerleme:
            ilerleme(i + 1, len(semboller), sembol)
        if i < len(semboller) - 1:
            import time
            time.sleep(bekleme_sn)

    if eklenen:
        _csv_yaz(mevcut)
        _log(f"{len(eklenen)} yeni kayıt eklendi. Toplam kayıt: {len(mevcut)}.")
    return eklenen


def etiketle_gecmis(min_gun: int = 1):
    """target_t1_return boş olan ve en az min_gun eski kayıtları, o tarihten
    SONRAKİ ilk mevcut kapanış fiyatıyla (gerçek T+1 getirisi) etiketler."""
    satirlar = _csv_oku()
    if not satirlar:
        _log("Veri seti boş, etiketlenecek bir şey yok.")
        return 0

    bugun = dt.date.today()
    etiketlenen = 0
    fiyat_onbellek = {}

    for satir in satirlar:
        if satir.get("target_t1_return"):
            continue  # zaten etiketli
        try:
            kayit_tarihi = dt.date.fromisoformat(satir["tarih"])
        except Exception:
            continue
        if (bugun - kayit_tarihi).days < min_gun:
            continue  # henüz yeterince zaman geçmemiş

        sembol = satir["sembol"]
        try:
            kapanis_o_gun = float(satir["kapanis_fiyati"])
        except (TypeError, ValueError):
            continue

        if sembol not in fiyat_onbellek:
            try:
                fiyat_onbellek[sembol] = vk.fiyat_gecmisi(sembol, yil=0.3)
            except Exception:
                fiyat_onbellek[sembol] = None
        df = fiyat_onbellek[sembol]
        if df is None or len(df) == 0:
            continue

        # kayit_tarihi'nden SONRAKİ ilk kapanışı bul (T+1).
        try:
            sonraki = df[df.index.date > kayit_tarihi]
            if len(sonraki) == 0:
                continue
            t1_kapanis = float(sonraki["Close"].iloc[0])
            t1_tarih = sonraki.index[0].date().isoformat()
        except Exception:
            continue

        getiri_pct = round((t1_kapanis - kapanis_o_gun) / kapanis_o_gun * 100, 3)
        satir["target_t1_return"] = getiri_pct
        satir["target_t1_tarih"] = t1_tarih
        etiketlenen += 1
        _log(f"{sembol} ({satir['tarih']}) etiketlendi: T+1 getiri %{getiri_pct:+.2f} ({t1_tarih}).")

    if etiketlenen:
        _csv_yaz(satirlar)
        _log(f"{etiketlenen} kayıt etiketlendi.")
    else:
        _log("Etiketlenecek (yeterince eskimiş, henüz etiketlenmemiş) kayıt bulunamadı.")
    return etiketlenen


def calistir():
    _log("AKD veri toplama başlıyor...")
    etiketle_gecmis()
    gunluk_topla()
    _log("AKD veri toplama tamamlandı ✅")


if __name__ == "__main__":
    calistir()
