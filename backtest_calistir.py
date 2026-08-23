# -*- coding: utf-8 -*-
"""
backtest_calistir.py — Streamlit ARAYÜZÜ OLMADAN çalışan TAM/ÇOK YILLI backtest.
════════════════════════════════════════════════════════════════════════════
BIST 100 kapsamında (varsayılan), çok yıllık geçmiş veri üzerinde
analiz_motoru.hizli_puan puanlamasının gerçekten ileri getiriyi öngörüp
öngörmediğini test eder. Uygulamadaki "🧪 Backtest / Doğrulama" sekmesindeki
hızlı tek-hisse testinin aksine, bu script YÜZLERCE hisse × BİNLERCE gün
işlediği için birkaç dakika sürebilir — bu yüzden uygulamayı açık tutmaya
gerek kalmadan, tek seferlik veya Görev Zamanlayıcısı ile çalıştırılmak
üzere ayrı bir script olarak tasarlandı.

ÇIKTI:
  - backtest_sonuc.txt  → okunabilir Türkçe özet rapor
  - backtest_sonuc.csv  → ham puan/ileri-getiri verisi (Excel'de kendi
                          analizinizi yapmak isterseniz)

ÇALIŞTIRMA:
  - Elle: BACKTEST_CALISTIR.bat dosyasına çift tıklayın.
  - Kapsamı/süreyi değiştirmek isterseniz aşağıdaki KAPSAM / YIL sabitlerini
    düzenleyin.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import veri_katmani as vk
import backtest_motoru as bt

KLASOR = os.path.dirname(os.path.abspath(__file__))
RAPOR_DOSYASI = os.path.join(KLASOR, "backtest_sonuc.txt")
CSV_DOSYASI = os.path.join(KLASOR, "backtest_sonuc.csv")

KAPSAM = "TUM"       # "TUM" | "XU100" | "XU030" — bu script arka planda/gece çalıştırılmak
                     # üzere tasarlandığı için varsayılan en geniş kapsamdır (TUM); daha
                     # hızlı bir deneme isterseniz "XU100" veya "XU030" yapabilirsiniz.
YIL = 5.0            # kaç yıllık geçmiş indirilsin
ADIM = 5             # kaç iş gününde bir yeniden puanlama (5 ≈ haftalık)
ILERI_GUNLER = (5, 10, 20)
# Puanlama penceresi: canlı kullanımda kaç günlük geçmişle puan hesaplandığını
# taklit eder. 500 ≈ sanal portföy motoru & "Hisse Araştır" (yil=2.0),
# 375 ≈ "Öne Çıkan Hisseler" taraması (yil=1.5). Pencere puanı DEĞİŞTİRİR,
# bu yüzden hangi kullanımı test ettiğinizi bilerek seçin (bkz. backtest_motoru).
PENCERE = bt.PENCERE_VARSAYILAN


def _ilerleme_yaz(prefix):
    def _f(i, n, s):
        if i % 10 == 0 or i == n - 1:
            print(f"  {prefix}: {i + 1}/{n} ({s})", flush=True)
    return _f


def calistir():
    zaman = dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"[{zaman}] Backtest başlıyor — kapsam={KAPSAM}, yıl={YIL}")

    semboller = vk.sembol_listesi(KAPSAM)
    print(f"{len(semboller)} hisse için {YIL} yıllık veri indiriliyor (toplu)...")
    veriler = vk.toplu_fiyat(semboller, yil=YIL,
                              ilerleme=lambda x: print(f"  indirme: %{x*100:.0f}", flush=True)
                              if int(x * 100) % 20 == 0 else None)
    print(f"{len(veriler)} hissenin verisi indirildi.")

    try:
        endeks = vk.endeks_gecmisi(YIL)
    except Exception as e:
        print(f"UYARI: Endeks verisi alınamadı ({e}), göreceli güç sinyali olmadan devam.")
        endeks = None

    print("Backtest çalıştırılıyor (bu birkaç dakika sürebilir)...")
    sonuc_df = bt.backtest_evren(veriler, endeks_df=endeks, adim=ADIM, pencere=PENCERE,
                                  ileri_gunler=ILERI_GUNLER,
                                  ilerleme=_ilerleme_yaz("puanlama"))

    if sonuc_df.empty:
        rapor = ("Backtest için yeterli veri üretilemedi. İnternet bağlantısını "
                  "kontrol edin veya YIL/KAPSAM ayarlarını gözden geçirin.")
        print(rapor)
        with open(RAPOR_DOSYASI, "w", encoding="utf-8") as f:
            f.write(rapor)
        return

    ozet = bt.backtest_ozet(sonuc_df, ILERI_GUNLER, adim=ADIM)
    yarilama = bt.backtest_yarilama(sonuc_df, ILERI_GUNLER, adim=ADIM)
    rapor = bt.metin_raporu(ozet, yarilama, ILERI_GUNLER)

    baslik = (f"BIST Analiz Platformu — Backtest Raporu\n"
              f"Çalıştırma zamanı: {zaman}\n"
              f"Kapsam: {KAPSAM} · Geçmiş: {YIL} yıl · Adım: {ADIM} iş günü · "
              f"Puanlama penceresi: {PENCERE} iş günü\n"
              f"Hisse sayısı: {len(veriler)}\n" + "=" * 70 + "\n\n")

    with open(RAPOR_DOSYASI, "w", encoding="utf-8") as f:
        f.write(baslik + rapor + "\n")
    sonuc_df.to_csv(CSV_DOSYASI, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 70)
    print(rapor)
    print("=" * 70)
    print(f"\nRapor kaydedildi: {RAPOR_DOSYASI}")
    print(f"Ham veri kaydedildi: {CSV_DOSYASI}")


if __name__ == "__main__":
    calistir()
