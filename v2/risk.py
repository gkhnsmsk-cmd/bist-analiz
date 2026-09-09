# -*- coding: utf-8 -*-
"""
v2/risk.py — Pusula V2 pozisyon boyutu / risk katmanı (§4).

Tek sorumluluk: bir aday için, sabit %1 risk kuralından başlayıp §4'teki
DÖRT kısıtın hepsini uygulayıp EN KÜÇÜĞÜNÜ seçmek. Ağ çağrısı YOK, dosya
okuma YOK — saf fonksiyon; girdiler dışında hiçbir dış duruma bakmaz.

V1'de stop'suz/limitsiz pozisyon açılabiliyordu (bkz. STRATEJI_V2.md §0,
HEDEF -46.98%). V2'de bir pozisyon bu dört kısıttan HİÇBİRİNİ aşamaz ve
kısıt onu sıfıra indiriyorsa (ör. likidite çok düşükse) pozisyon tamamen
reddedilir — red_nedeni Türkçe ve net biçimde belirtilir.
"""

from __future__ import annotations

import math

import pandas as pd

# §4 sabitleri — şartnamede birebir bu değerler.
_RISK_ORANI = 0.01          # işlem başına özsermayenin %1'i
_STOP_ATR_KATSAYI = 2.5      # stop_mesafe = 2.5 x ATR14
_TEK_POZISYON_TAVANI = 0.20  # tek pozisyon değeri <= özsermayenin %20'si
_LIKIDITE_ORANI = 0.01       # pozisyon değeri <= 20g medyan TL hacmin %1'i

# §4 kısıt-3 "Toplam açık risk ≤ özsermayenin %6'sı" ile ilgili YORUM KARARI:
# Bu fonksiyonun §11'de sabitlenmiş imzası (ozsermaye, kapanis, atr,
# hacim_tl_medyan, mevcut_yatirim, hedef_oran) açık pozisyonların risk
# TOPLAMINI bildiren bir parametre TAŞIMIYOR — yalnız "mevcut_yatirim" (TL
# tutar) var, "mevcut açık risk" yok. Dolayısıyla bu kısıt burada dolaylı/
# yapısal olarak sağlanıyor: risk_tutari HER ZAMAN tam olarak
# özsermaye x %1 olacak şekilde sabitlenmiş (aşağıdaki formülde asla
# yükseltilmiyor, yalnız diğer kısıtlarla aşağı çekilebiliyor) VE §6'da
# eşzamanlı pozisyon sayısı 6 ile sınırlı: 6 x %1 = %6 — yani per-trade %1
# sabiti ile maks-6-pozisyon kısıtının BİRLİKTE uygulanması, toplam açık
# riski yapısal olarak %6'nın üzerine ÇIKARAMAZ. Ayrı bir "toplam risk"
# parametresi olmadan bunun ötesi hesaplanamaz; bu nedenle burada ekstra bir
# kırpma YAPILMIYOR (yapılırsa mevcut_yatirim ile karışıp yanlış sonuç
# üretebilirdi). Gerçek zamanlı toplam risk takibi motor.py'nin (açık
# pozisyon listesine erişimi olan) sorumluluğundadır.


def pozisyon_boyutu(ozsermaye, kapanis, atr, hacim_tl_medyan,
                     mevcut_yatirim, hedef_oran) -> dict:
    """§4'e göre pozisyon boyutunu hesaplar; dört kısıtın en küçüğünü seçer.

    Adımlar:
      1) Ham (yalnız %1 risk kuralına göre) adet hesaplanır.
      2) Üç ayrı DEĞER tavanı çıkarılır: tek pozisyon tavanı (özsermaye x %20),
         likidite tavanı (medyan hacim x %1), rejim kapasitesi tavanı
         (hedef_oran x özsermaye - mevcut_yatirim).
      3) Dört "adet" adayının (ham + üç tavanın kapanışa bölünmüşü) EN
         KÜÇÜĞÜ seçilir. Negatifse/anlamsızsa 0'a çekilir.
      4) Sonuç 1 lottan (1 paydan) küçükse pozisyon REDDEDİLİR; red_nedeni
         Türkçe ve hangi kısıtın bağlayıcı olduğunu açıkça belirtir.

    Döner: {'adet','stop','deger','risk_tl','red_nedeni'}
    red_nedeni: kabul edilirse None, reddedilirse Türkçe açıklama metni.
    """
    # --- Girdi doğrulama -------------------------------------------------
    if ozsermaye is None or pd.isna(ozsermaye) or ozsermaye <= 0:
        return {"adet": 0.0, "stop": float("nan"), "deger": 0.0, "risk_tl": 0.0,
                "red_nedeni": "Özsermaye geçersiz (sıfır veya negatif)."}
    if kapanis is None or pd.isna(kapanis) or kapanis <= 0:
        return {"adet": 0.0, "stop": float("nan"), "deger": 0.0, "risk_tl": 0.0,
                "red_nedeni": "Kapanış fiyatı geçersiz (sıfır veya negatif)."}
    if atr is None or pd.isna(atr) or atr <= 0:
        return {"adet": 0.0, "stop": kapanis, "deger": 0.0, "risk_tl": 0.0,
                "red_nedeni": "ATR14 geçersiz (sıfır/NaN) — stop mesafesi hesaplanamıyor."}

    stop_mesafe = _STOP_ATR_KATSAYI * atr
    stop_fiyati = kapanis - stop_mesafe

    # --- 1) Ham adet: yalnız %1 risk kuralına göre ------------------------
    risk_tutari = ozsermaye * _RISK_ORANI
    adet_ham = risk_tutari / stop_mesafe

    # --- 2) Üç değer tavanı -------------------------------------------
    deger_tavan_pozisyon = ozsermaye * _TEK_POZISYON_TAVANI

    if hacim_tl_medyan is None or pd.isna(hacim_tl_medyan) or hacim_tl_medyan <= 0:
        deger_tavan_likidite = 0.0
        likidite_bilgi_yok = True
    else:
        deger_tavan_likidite = hacim_tl_medyan * _LIKIDITE_ORANI
        likidite_bilgi_yok = False

    mevcut_yatirim_guvenli = 0.0 if (mevcut_yatirim is None or pd.isna(mevcut_yatirim)) else mevcut_yatirim
    hedef_oran_guvenli = 0.0 if (hedef_oran is None or pd.isna(hedef_oran)) else hedef_oran
    kalan_hedef_kapasite = hedef_oran_guvenli * ozsermaye - mevcut_yatirim_guvenli
    deger_tavan_rejim = max(0.0, kalan_hedef_kapasite)

    # --- 3) Dört "adet" adayının en küçüğü ---------------------------------
    adet_tavan_pozisyon = deger_tavan_pozisyon / kapanis
    adet_tavan_likidite = deger_tavan_likidite / kapanis
    adet_tavan_rejim = deger_tavan_rejim / kapanis

    adaylar = {
        "risk_kurali_%1": adet_ham,
        "tek_pozisyon_%20": adet_tavan_pozisyon,
        "likidite_%1_hacim": adet_tavan_likidite,
        "rejim_hedef_kapasitesi": adet_tavan_rejim,
    }
    bağlayan_kisit = min(adaylar, key=lambda k: adaylar[k])
    adet_nihai = max(0.0, adaylar[bağlayan_kisit])

    # BIST'te asgari işlem birimi 1 paydır; kesirli pay alınamaz.
    adet_nihai = float(math.floor(adet_nihai))

    if adet_nihai < 1.0:
        if likidite_bilgi_yok:
            neden = "20 günlük medyan TL hacim bilgisi eksik/geçersiz — likidite kısıtı değerlendirilemedi."
        elif bağlayan_kisit == "likidite_%1_hacim":
            neden = ("Hesaplanan pozisyon büyüklüğü günlük hacmin %1'ini aşıyor "
                      "(20g medyan TL hacim çok düşük) — 1 pay bile alınamıyor.")
        elif bağlayan_kisit == "rejim_hedef_kapasitesi":
            neden = ("Mevcut yatırım zaten rejimin hedef yatırım oranına ulaşmış/aşmış "
                      "— yeni pozisyon için kapasite kalmadı.")
        elif bağlayan_kisit == "tek_pozisyon_%20":
            neden = "Tek pozisyon tavanı (özsermayenin %20'si) 1 payı bile karşılamıyor."
        else:
            neden = "Hesaplanan pozisyon büyüklüğü (%1 risk kuralına göre) 1 paydan küçük çıktı."
        return {"adet": 0.0, "stop": float(stop_fiyati), "deger": 0.0, "risk_tl": 0.0,
                "red_nedeni": neden}

    deger = adet_nihai * kapanis
    risk_tl = adet_nihai * stop_mesafe  # gerçekleşen risk; kısıtlar adet'i kırptıysa %1'den az olabilir

    return {
        "adet": adet_nihai,
        "stop": float(stop_fiyati),
        "deger": float(deger),
        "risk_tl": float(risk_tl),
        "red_nedeni": None,
    }


if __name__ == "__main__":
    # Ağ çağrısı / dosya okuma içermeyen kendi kendine kontrol.

    # --- Senaryo 1: normal kabul — hiçbir kısıt bağlayıcı olmadan ----------
    sonuc1 = pozisyon_boyutu(
        ozsermaye=1_000_000.0, kapanis=50.0, atr=1.0,
        hacim_tl_medyan=500_000_000.0,  # çok likit, likidite kısıtı bağlamaz
        mevcut_yatirim=0.0, hedef_oran=1.0,
    )
    assert sonuc1["red_nedeni"] is None, sonuc1
    assert sonuc1["adet"] > 0
    # Ham risk kuralı: risk_tutari=10.000, stop_mesafe=2.5 -> adet_ham=4000
    # Ama tek pozisyon tavanı: 1.000.000*0.20/50 = 4000 -> ikisi eşit çıkabilir,
    # en azından adet mantıklı bir aralıkta olmalı.
    assert sonuc1["adet"] <= 1_000_000.0 * 0.20 / 50.0 + 1e-6
    assert abs(sonuc1["stop"] - (50.0 - 2.5 * 1.0)) < 1e-9

    # --- Senaryo 2: likidite kısıtı bağlayıcı ve pozisyonu REDDETMELİ ------
    sonuc2 = pozisyon_boyutu(
        ozsermaye=1_000_000.0, kapanis=50.0, atr=1.0,
        hacim_tl_medyan=1_000.0,  # aşırı düşük hacim -> %1'i = 10 TL -> 0 pay
        mevcut_yatirim=0.0, hedef_oran=1.0,
    )
    assert sonuc2["red_nedeni"] is not None
    assert sonuc2["adet"] == 0.0
    assert "hacm" in sonuc2["red_nedeni"].lower() or "hacim" in sonuc2["red_nedeni"].lower()

    # --- Senaryo 3: rejim kapasitesi dolmuş -> reddetmeli ------------------
    sonuc3 = pozisyon_boyutu(
        ozsermaye=1_000_000.0, kapanis=50.0, atr=1.0,
        hacim_tl_medyan=500_000_000.0,
        mevcut_yatirim=1_000_000.0,  # zaten hedefin üstünde yatırılmış
        hedef_oran=0.60,
    )
    assert sonuc3["red_nedeni"] is not None
    assert sonuc3["adet"] == 0.0

    # --- Senaryo 4: ATR geçersiz -> reddetmeli, çökmemeli ------------------
    sonuc4 = pozisyon_boyutu(
        ozsermaye=1_000_000.0, kapanis=50.0, atr=0.0,
        hacim_tl_medyan=500_000_000.0, mevcut_yatirim=0.0, hedef_oran=1.0,
    )
    assert sonuc4["red_nedeni"] is not None

    # --- Senaryo 5: risk_tl her zaman ozsermaye x %1'i aşmamalı (yapısal
    # %6 toplam risk kısıtının dayandığı öncül) ----------------------------
    for oz in (500_000.0, 1_000_000.0, 2_000_000.0):
        s = pozisyon_boyutu(ozsermaye=oz, kapanis=20.0, atr=0.5,
                             hacim_tl_medyan=500_000_000.0,
                             mevcut_yatirim=0.0, hedef_oran=1.0)
        assert s["risk_tl"] <= oz * _RISK_ORANI + 1e-6, s

    print("risk.py kendi kendine kontrol: BAŞARILI")
    print("Senaryo 1 (kabul):", sonuc1)
    print("Senaryo 2 (likidite reddi):", sonuc2)
    print("Senaryo 3 (rejim kapasitesi reddi):", sonuc3)
