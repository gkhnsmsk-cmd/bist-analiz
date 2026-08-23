# -*- coding: utf-8 -*-
"""
takas_testi.py — Yabancı takas verisi kaynağı GERÇEKTEN çalışıyor mu?
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR: Takas verisi (veri_katmani.yabanci_orani_gecmisi) şu an SADECE
"Hisse Araştır" sekmesinde kullanılıyor. Taramalarda ve sanal portföy
motorunda yabanci_s=None geçiliyor — yani o tablolardaki "Takas" sütunu
gerçek takas verisi DEĞİL, sadece hacimden türetilmiş vekil göstergeler
(CMF + Toplama/Dağıtım).

Takası taramaya eklemeden ÖNCE şunları ölçmek gerekiyor:
  1) Kaynak (İş Yatırım HisseTekil) hâlâ çalışıyor mu?
  2) Hisse başına kaç saniye sürüyor? (600 hisse için toplam süre)
  3) Kaç hissede veri var, kaç tanesinde boş dönüyor?
  4) Gelen veri anlamlı mı (oranlar 0-100 arası, tarihler güncel mi)?

Bu ölçüm yapılmadan "takası ekleyelim" demek, çalışmayan bir kaynağa
bağlanıp taramayı saatlerce sürdürme riski taşır.

ÇALIŞTIRMA:  TAKAS_TESTI.bat  (veya: py -3.11 takas_testi.py)
"""
from __future__ import annotations

import os
import sys
import time
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import veri_katmani as vk

# Farkli buyuklukte ve sektorden ornekler — bazisinda veri olmamasi normaldir
TEST_HISSELERI = ["THYAO", "ASELS", "GARAN", "EREGL", "SISE",
                  "PGSUS", "CIMSA", "ANSGR", "YKBNK", "AKSEN",
                  "KCAER", "TUPRS", "BIMAS", "TABGD", "CWENE"]


SONUC_DOSYASI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "takas_testi_sonuc.txt")
_CIKTI = []


def yaz(mesaj=""):
    """Hem ekrana hem dosyaya yazar.

    NEDEN: İlk sürüm SADECE ekrana yazıyordu; test çalıştırıldıktan sonra
    sonuç konsol penceresi kapanınca kayboluyordu ve paylaşılamıyordu.
    """
    print(mesaj)
    _CIKTI.append(mesaj)


def cizgi(k="─"):
    yaz(k * 74)


def main():
    yaz()
    cizgi("═")
    yaz("  YABANCI TAKAS VERİSİ — KAYNAK TESTİ")
    yaz(f"  {dt.datetime.now():%d.%m.%Y %H:%M}")
    cizgi("═")
    yaz(f"  Kaynak: İş Yatırım HisseTekil (veri_katmani.yabanci_orani_gecmisi)")
    yaz(f"  Test edilen: {len(TEST_HISSELERI)} hisse\n")

    basarili, bos, hatali = [], [], []
    sureler = []

    yaz(f"  {'Hisse':8s}{'Süre':>8s}{'Kayıt':>8s}{'İlk tarih':>13s}"
          f"{'Son tarih':>13s}{'Güncel %':>10s}{'1 ay Δ':>9s}")
    cizgi()

    for s in TEST_HISSELERI:
        t0 = time.perf_counter()
        try:
            seri = vk.yabanci_orani_gecmisi(s, 1.0)
            sure = time.perf_counter() - t0
            sureler.append(sure)
            if seri is None or len(seri) == 0:
                bos.append(s)
                yaz(f"  {s:8s}{sure:>7.2f}s{'—':>8s}{'VERİ YOK':>13s}")
                continue
            ilk, son = seri.index[0], seri.index[-1]
            guncel = float(seri.iloc[-1])
            ay1 = float(seri.iloc[-22]) if len(seri) > 22 else float(seri.iloc[0])
            delta = guncel - ay1
            basarili.append((s, guncel, delta, len(seri), son))
            yaz(f"  {s:8s}{sure:>7.2f}s{len(seri):>8d}"
                  f"{ilk:%d.%m.%y:>13}{son:%d.%m.%y:>13}"
                  f"{guncel:>9.2f}%{delta:>+8.2f}")
        except Exception as e:
            sureler.append(time.perf_counter() - t0)
            hatali.append((s, str(e)[:60]))
            yaz(f"  {s:8s}{'HATA':>8s}  {str(e)[:45]}")

    cizgi("═")
    n = len(TEST_HISSELERI)
    yaz(f"\n  SONUÇ")
    cizgi()
    yaz(f"    Veri gelen      : {len(basarili)}/{n}")
    yaz(f"    Boş dönen       : {len(bos)}/{n}" + (f"  ({', '.join(bos)})" if bos else ""))
    yaz(f"    Hata veren      : {len(hatali)}/{n}")
    for s, e in hatali:
        yaz(f"        {s}: {e}")

    if sureler:
        ort = sum(sureler) / len(sureler)
        yaz(f"\n    Hisse başına ort: {ort:.2f} saniye")
        yaz(f"    600 hisse için  : {ort * 600 / 60:.1f} DAKİKA")
        if ort * 600 / 60 > 45:
            yaz("      ⚠️  Çok uzun — arka plan taramasına eklenirse gece")
            yaz("          çalışması saatler sürebilir. Paralel istek veya")
            yaz("          sadece BIST100 ile sınırlama gerekebilir.")
        else:
            yaz("      ✓  Arka plan taraması için kabul edilebilir süre.")

    # ── Veri MANTIKLI mı? ────────────────────────────────────────────────────
    if basarili:
        yaz(f"\n  VERİ TUTARLILIK KONTROLÜ")
        cizgi()
        sorun = []
        for s, guncel, delta, adet, son_tarih in basarili:
            if not (0 <= guncel <= 100):
                sorun.append(f"{s}: oran %{guncel:.1f} — 0-100 aralığı dışında!")
            yas = (dt.date.today() - son_tarih.date()).days
            if yas > 10:
                sorun.append(f"{s}: son veri {yas} gün önce ({son_tarih:%d.%m.%Y}) — bayat")
            if adet < 30:
                sorun.append(f"{s}: sadece {adet} kayıt — trend hesabı için az")
        if sorun:
            for x in sorun:
                yaz(f"    ⚠️  {x}")
        else:
            yaz("    ✓ Oranlar 0-100 arasında, veriler güncel, kayıt sayısı yeterli.")

        hareketli = [x for x in basarili if abs(x[2]) > 0.5]
        yaz(f"\n    Son 1 ayda takas oranı belirgin değişen: "
              f"{len(hareketli)}/{len(basarili)}")
        for s, guncel, delta, _, _ in sorted(hareketli, key=lambda x: -abs(x[2]))[:5]:
            yon = "yabancı GİRİŞİ" if delta > 0 else "yabancı ÇIKIŞI"
            yaz(f"      {s:7s} %{guncel:6.2f}  ({delta:+.2f} puan) — {yon}")

    yaz()
    cizgi("═")
    if len(basarili) >= n * 0.6:
        yaz("  ✅ KAYNAK ÇALIŞIYOR — takas verisi taramaya eklenebilir.")
    elif basarili:
        yaz("  ⚠️  KAYNAK KISMEN ÇALIŞIYOR — bazı hisselerde veri yok.")
        yaz("     Takas eklenirse veri olmayan hisseler için puan bozulmamalı.")
    else:
        yaz("  ❌ KAYNAK ÇALIŞMIYOR — takas verisi hiç alınamıyor.")
        yaz("     Taramaya eklemek anlamsız; önce alternatif kaynak bulunmalı.")
    cizgi("═")
    yaz()


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            with open(SONUC_DOSYASI, "w", encoding="utf-8") as f:
                f.write("\n".join(_CIKTI))
            print(f"\n  Sonuç kaydedildi: {os.path.basename(SONUC_DOSYASI)}")
        except Exception as _e:
            print(f"\n  UYARI: sonuç dosyaya yazılamadı: {_e}")
