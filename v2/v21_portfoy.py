# -*- coding: utf-8 -*-
"""
v2/v21_portfoy.py — Dinamik & Defansif BIST Algoritması v2.1: §4 alım, §5
pozisyon büyüklüğü, §6 çıkış, §7 rutin (davranışsal) kuralları.

Ağ çağrısı YOK, dosya okuma YOK — tüm fonksiyonlar SAF (yalnız aldıkları
parametrelere bakar). Günlük simülasyon döngüsü (emir kuyruğu, mark-to-market
özsermaye, maliyet uygulaması) v2/v21_backtest.py'nin sorumluluğundadır — bu
modül yalnız KARARLARI (fiyat seviyesi, adet, tetiklendi/tetiklenmedi) üretir.

─────────────────────────────────────────────────────────────────────────
POZİSYON SÖZLÜĞÜ ŞEMASI (bu modülün beklediği/güncellediği alanlar)
─────────────────────────────────────────────────────────────────────────
    sembol                : str
    sektor                : str
    giris_tarihi_ilk       : pd.Timestamp
    giris_fiyati_ilk       : float
    adet_ilk               : float
    giris_tarihi_ikinci    : pd.Timestamp | None   # ikinci dilim dolana kadar None
    giris_fiyati_ikinci    : float | None
    adet_ikinci             : float                 # dolmadıysa 0.0
    adet_toplam             : float                  # adet_ilk + adet_ikinci
    maliyet_ortalama        : float                  # ağırlıklı ortalama maliyet
    atr_giris                : float                 # ilk dilimin dolduğu gündeki ATR14
                                                       # (yalnız §5 boyutlandırma tabanı
                                                       # için saklanır; §6 çıkış formülleri
                                                       # GÜNCEL/dinamik ATR14 kullanır — bkz.
                                                       # aşağıdaki YORUM KARARI notu)
    hedef1_alindi           : bool                    # +3xATR hedefi vurulup %40 satıldı mı
    guncel_stop              : float                  # yalnız hedef1_alindi=True iken anlamlı;
                                                        # Donchian alt kanal ile YUKARI ratchet eder
    gun_sayisi                : int                    # ilk dilim girişinden bu yana iş günü
    cmf_ardisik_negatif       : int                     # CMF20 ardışık negatif gün sayacı

YORUM KARARI — ÇIKIŞ FORMÜLLERİNDE "ATR14" HANGİ GÜNÜN ATR'Sİ?
Şartname §6 "Fiyat = Ortalama Maliyet – (2×ATR14)" ve "Maliyet+(3×ATR14)"
diyor, GİRİŞ GÜNÜNÜN ATR'si mi yoksa GÜNCEL (bugünün) ATR'si mi olduğunu
belirtmiyor. Burada GÜNCEL/dinamik ATR14 (her gün yeniden hesaplanan)
kullanıldı — hem sert stop hem +3xATR hedefi İÇİN TUTARLI biçimde — çünkü
§6'daki "Ek: Fiyat MA50'yi hacimli kırarsa ATR stopu BEKLEMEDEN çık" ifadesi,
ATR stopunun sabit bir sayı değil sürüp giden/güncellenen bir eşik olarak
tasarlandığını ima ediyor. atr_giris alanı yalnız kayıt/rapor amaçlıdır,
çıkış kararlarında KULLANILMAZ.

YORUM KARARI — İKİNCİ DİLİM TETİKLEYİCİSİ: Şartname "(2) fiyat o seviyeden
sekip tekrar yukarı ivme kazandığında ikinci parça" diyor, kesin bir formül
vermiyor. Burada: kapanış > MA20 VE kapanış > ilk dilimin dolduğu günün
Yüksek'i (o günü net biçimde yukarı kırmış olmak) "ivme kazandı" kabul
edildi. İkinci dilim bu tetik olmadan _IKINCI_DILIM_MAKS_BEKLEME_GUN iş günü
içinde gerçekleşmezse beklemekten vazgeçilir (pozisyon yalnız ilk dilimle
kalır) — şartname bunun için bir süre vermiyor, sonsuz beklemeyi önlemek
için makul bir sınır konuldu.
"""

from __future__ import annotations

import math

import pandas as pd

# ── §5 pozisyon büyüklüğü sabitleri (şartnameyle birebir) ──────────────────
_RISK_ORANI = 0.015              # tek işlemde riske edilen max sermaye: %1.5
_TEK_HISSE_TAVAN = 0.15           # tek hisse max ağırlık: %15
_SEKTOR_TAVAN = 0.30               # aynı sektör max ağırlık: %30
# Risk-On döneminde toplam hisse ağırlığı %75'i geçmez — bu üst sınır,
# rejimin kendi hedef_hisse_orani'sı (v21_rejim.py) üzerinden zaten
# uygulanıyor (Risk-On hedefi hiçbir zaman %75'i aşmaz); burada AYRICA
# ekstra bir sabit tanımlanmadı, çağıran taraf hedef_hisse_orani'yi kapasite
# tavanı olarak geçirir.

# ── §4/§6 ATR katsayıları ────────────────────────────────────────────────
_STOP_ATR_KATSAYI = 2.0            # Sert Stop = Maliyet - 2xATR14
_HEDEF1_ATR_KATSAYI = 3.0          # Hedef 1 = Maliyet + 3xATR14
_HEDEF1_SATIS_ORANI = 0.40         # Hedef 1'de satılan oran

# ── §6 zaman/momentum stopu ─────────────────────────────────────────────
_ZAMAN_STOPU_GUN = 25

# ── §6 "MA50'yi hacimli kırma" — kirilim hacim çarpanı v2/sinyal.py'deki
# §3.3a ile AYNI (1.5x) tutuldu; şartname v2.1'de somut bir sayı vermiyor,
# projede zaten yerleşik olan "hacimli" tanımıyla tutarlılık tercih edildi.
_MA50_KIRILIM_HACIM_CARPAN = 1.5

# YORUM KARARI: "CMF kalıcı negatif" — şartname bir gün sayısı vermiyor.
# 5 ARDIŞIK gün CMF20<0 "kalıcı" kabul edildi (bir haftalık işlem günü).
_CMF_KALICI_NEGATIF_GUN = 5

# §4 sinyal geçerlilik penceresi.
_SINYAL_GECERLILIK_GUN = 3
# YORUM KARARI: ikinci dilim için makul bir üst bekleme süresi (bkz. modül
# başındaki not) — şartnamede yok, sonsuz bekleyişi önlemek için eklendi.
_IKINCI_DILIM_MAKS_BEKLEME_GUN = 15

# §7 — "3 ay üst üste risksiz altında kalırsa yeni alım durdurulur".
# Varsayım: mevduat/PPF getirisi yıllık %40 sabit -> aylık bileşik ~%2.84.
_RISKSIZ_AYLIK_GETIRI = 1.40 ** (1.0 / 12.0) - 1.0  # ~0.02844


# ═══════════════════════════════════════════════════════════════════════
# §4 — Alım: limit seviyesi + 2 dilim mantığı
# ═══════════════════════════════════════════════════════════════════════
def limit_seviyesi(satir: pd.Series) -> float:
    """§4: Alım bölgesi = MA20 seviyesi VEYA (son 10 günlük zirve - 1xATR).

    Fiyat yukarıdan aşağı geldiğinde bu iki seviyeden HANGİSİNE önce
    değerse tetiklenir — pratikte bu, ikisinin arasında FİYATA DAHA YAKIN
    (yani BÜYÜK) olanıdır (düşen fiyat önce ona çarpar). Bu yüzden burada
    max(MA20, DONCHIAN_UST10 - ATR14) hesaplanır. Girdiler eksikse NaN döner
    (çağıran taraf bunu "sinyal oluşturulamadı" olarak yorumlamalı).
    """
    ma20 = satir.get("MA20")
    donchian_ust10 = satir.get("DONCHIAN_UST10")
    atr = satir.get("ATR14")

    adaylar = []
    if ma20 is not None and not pd.isna(ma20):
        adaylar.append(float(ma20))
    if (donchian_ust10 is not None and not pd.isna(donchian_ust10)
            and atr is not None and not pd.isna(atr)):
        adaylar.append(float(donchian_ust10 - atr))

    if not adaylar:
        return float("nan")
    return max(adaylar)


def ikinci_dilim_tetiklendi_mi(satir_bugun: pd.Series, ilk_dolum_yuksek: float) -> bool:
    """§4 ikinci dilim tetiği (bkz. modül başındaki YORUM KARARI)."""
    kapanis = satir_bugun.get("Close")
    ma20 = satir_bugun.get("MA20")
    if kapanis is None or ma20 is None or pd.isna(kapanis) or pd.isna(ma20):
        return False
    if ilk_dolum_yuksek is None or pd.isna(ilk_dolum_yuksek):
        return False
    return bool(kapanis > ma20 and kapanis > ilk_dolum_yuksek)


# ═══════════════════════════════════════════════════════════════════════
# §5 — Pozisyon büyüklüğü
# ═══════════════════════════════════════════════════════════════════════
def pozisyon_boyutu_hesapla(ozsermaye: float, fiyat: float, atr: float,
                             sektor_toplam_deger: float, hisse_toplam_deger: float,
                             hedef_hisse_orani: float) -> dict:
    """§5'e göre TOPLAM (2 dilim birlikte) pozisyon büyüklüğünü hesaplar.

    Dört kısıtın (risk %1.5, tek hisse %15, sektör %30, rejim hedef
    kapasitesi) EN KÜÇÜĞÜ seçilir — v2/risk.py'deki desenle AYNI yaklaşım.
    Döner: {'adet_toplam','stop_mesafe','deger','risk_tl','red_nedeni'}
    """
    if ozsermaye is None or pd.isna(ozsermaye) or ozsermaye <= 0:
        return {"adet_toplam": 0.0, "stop_mesafe": float("nan"), "deger": 0.0,
                "risk_tl": 0.0, "red_nedeni": "Özsermaye geçersiz."}
    if fiyat is None or pd.isna(fiyat) or fiyat <= 0:
        return {"adet_toplam": 0.0, "stop_mesafe": float("nan"), "deger": 0.0,
                "risk_tl": 0.0, "red_nedeni": "Limit fiyatı geçersiz."}
    if atr is None or pd.isna(atr) or atr <= 0:
        return {"adet_toplam": 0.0, "stop_mesafe": float("nan"), "deger": 0.0,
                "risk_tl": 0.0, "red_nedeni": "ATR14 geçersiz — stop mesafesi hesaplanamıyor."}

    stop_mesafe = _STOP_ATR_KATSAYI * atr
    risk_tutari = ozsermaye * _RISK_ORANI
    adet_risk = risk_tutari / stop_mesafe

    deger_tavan_tek_hisse = ozsermaye * _TEK_HISSE_TAVAN
    adet_tek_hisse = deger_tavan_tek_hisse / fiyat

    sektor_guvenli = 0.0 if (sektor_toplam_deger is None or pd.isna(sektor_toplam_deger)) else sektor_toplam_deger
    deger_tavan_sektor = max(0.0, ozsermaye * _SEKTOR_TAVAN - sektor_guvenli)
    adet_sektor = deger_tavan_sektor / fiyat

    hisse_guvenli = 0.0 if (hisse_toplam_deger is None or pd.isna(hisse_toplam_deger)) else hisse_toplam_deger
    hedef_guvenli = 0.0 if (hedef_hisse_orani is None or pd.isna(hedef_hisse_orani)) else hedef_hisse_orani
    deger_tavan_rejim = max(0.0, hedef_guvenli * ozsermaye - hisse_guvenli)
    adet_rejim = deger_tavan_rejim / fiyat

    adaylar = {
        "risk_%1.5": adet_risk,
        "tek_hisse_%15": adet_tek_hisse,
        "sektor_%30": adet_sektor,
        "rejim_hedef_kapasitesi": adet_rejim,
    }
    bağlayan = min(adaylar, key=lambda k: adaylar[k])
    adet_nihai = float(math.floor(max(0.0, adaylar[bağlayan])))

    if adet_nihai < 1.0:
        nedenler = {
            "risk_%1.5": "Risk kuralına (%1.5) göre hesaplanan büyüklük 1 paydan küçük.",
            "tek_hisse_%15": "Tek hisse tavanı (%15) 1 payı bile karşılamıyor.",
            "sektor_%30": "Sektör tavanı (%30) dolmuş/1 payı karşılamıyor.",
            "rejim_hedef_kapasitesi": "Rejimin hedef hisse kapasitesi dolmuş — yeni pozisyon için yer yok.",
        }
        return {"adet_toplam": 0.0, "stop_mesafe": float(stop_mesafe), "deger": 0.0,
                "risk_tl": 0.0, "red_nedeni": nedenler[bağlayan]}

    deger = adet_nihai * fiyat
    risk_tl = adet_nihai * stop_mesafe
    return {"adet_toplam": adet_nihai, "stop_mesafe": float(stop_mesafe),
            "deger": float(deger), "risk_tl": float(risk_tl), "red_nedeni": None}


# ═══════════════════════════════════════════════════════════════════════
# §6 — Çıkış: sayaç güncelleme + çıkış hiyerarşisi
# ═══════════════════════════════════════════════════════════════════════
def sayaclari_guncelle(pozisyon: dict, satir: pd.Series) -> dict:
    """Günlük 'bookkeeping': gun_sayisi, cmf_ardisik_negatif, guncel_stop
    (yalnız hedef1_alindi=True iken, Donchian alt kanalla YUKARI ratchet).
    cikis_kontrol'den ÖNCE, her gün bir kez çağrılmalı (pozisyon.py::
    trailing_guncelle deseniyle aynı ayrım: bu fonksiyon state değiştirir,
    cikis_kontrol saf okuma kalır).
    """
    yeni = dict(pozisyon)
    yeni["gun_sayisi"] = pozisyon.get("gun_sayisi", 0) + 1

    cmf_bugun = satir.get("CMF20")
    if cmf_bugun is not None and not pd.isna(cmf_bugun) and cmf_bugun < 0:
        yeni["cmf_ardisik_negatif"] = pozisyon.get("cmf_ardisik_negatif", 0) + 1
    else:
        yeni["cmf_ardisik_negatif"] = 0

    if pozisyon.get("hedef1_alindi", False):
        donchian_alt = satir.get("DONCHIAN_ALT10")
        onceki_stop = pozisyon.get("guncel_stop")
        if onceki_stop is None or pd.isna(onceki_stop):
            onceki_stop = pozisyon["maliyet_ortalama"] - _STOP_ATR_KATSAYI * pozisyon.get("atr_giris", 0.0)
        if donchian_alt is not None and not pd.isna(donchian_alt):
            yeni["guncel_stop"] = max(onceki_stop, float(donchian_alt))
        else:
            yeni["guncel_stop"] = onceki_stop

    return yeni


def hedef1_kontrol(pozisyon: dict, satir: pd.Series) -> dict | None:
    """§6 Hedef 1: Fiyat >= Maliyet + 3xATR14(güncel) -> pozisyonun %40'ı satılır.
    Yalnız hedef1_alindi henüz False iken kontrol edilir (tek seferlik)."""
    if pozisyon.get("hedef1_alindi", False):
        return None
    atr_bugun = satir.get("ATR14")
    high = satir.get("High")
    if atr_bugun is None or pd.isna(atr_bugun) or high is None or pd.isna(high):
        return None
    hedef_seviye = pozisyon["maliyet_ortalama"] + _HEDEF1_ATR_KATSAYI * atr_bugun
    if high >= hedef_seviye:
        return {"neden": "hedef1_kar_al", "fiyat": float(hedef_seviye), "oran": _HEDEF1_SATIS_ORANI}
    return None


def cikis_kontrol(pozisyon: dict, satir: pd.Series, rejim: dict | None = None) -> dict | None:
    """§6 TAM kapama hiyerarşisi — SIRAYLA, ilk tetiklenen kazanır:
      1) Sert stop: Low <= Maliyet - 2xATR14(güncel)
      2) MA50'yi hacimli kırma (ATR stopu beklemeden)
      3) CMF kalıcı negatif (>= _CMF_KALICI_NEGATIF_GUN ardışık gün) + fiyat MA50 altı
      4) İz süren (Donchian) stop — yalnız hedef1_alindi=True iken aktif
      5) Zaman/momentum stopu: 25 gün sonra kârda değil VEYA CMF negatif

    rejim: v21_rejim.rejim_hesapla() çıktısı; Risk-Off'a geçişte mevcut
    pozisyonların "kademeli küçültülmesi" PORTFÖY SEVİYESİNDE bir karardır
    (v2/backtest.py'deki R3 deseniyle aynı YORUM KARARI) — bu fonksiyon tek
    başına rejim kapatması YAPMAZ; çağıran taraf (v21_backtest.py) Risk-Off
    altında en zayıf pozisyonları ayrıca seçip kapatabilir. Burada rejim
    parametresi yalnız ileride/opsiyonel bir bayrak için tutulur, şu anki
    mantık onu KULLANMAZ (döngüsel bağımlılığı önlemek için).
    """
    low = satir.get("Low")
    close = satir.get("Close")
    openf = satir.get("Open")
    if low is None or close is None or pd.isna(low) or pd.isna(close):
        return None

    maliyet = pozisyon["maliyet_ortalama"]

    # 1) Sert stop (dinamik ATR14).
    atr_bugun = satir.get("ATR14")
    if atr_bugun is not None and not pd.isna(atr_bugun):
        stop_seviye = maliyet - _STOP_ATR_KATSAYI * atr_bugun
        if low <= stop_seviye:
            fiyat = min(openf, stop_seviye) if (openf is not None and not pd.isna(openf) and openf < stop_seviye) else stop_seviye
            return {"neden": "sert_stop", "fiyat": float(fiyat), "oran": 1.0}

    # 2) MA50'yi hacimli kırma.
    ma50 = satir.get("MA50")
    hacim = satir.get("Volume")
    hacim_ort20 = satir.get("HACIM_ORT20")
    if (ma50 is not None and not pd.isna(ma50) and hacim is not None and not pd.isna(hacim)
            and hacim_ort20 is not None and not pd.isna(hacim_ort20) and hacim_ort20 > 0):
        if close < ma50 and hacim >= _MA50_KIRILIM_HACIM_CARPAN * hacim_ort20:
            return {"neden": "ma50_kirilim_hacimli", "fiyat": float(close), "oran": 1.0}

    # 3) CMF kalıcı negatif + fiyat MA50 altı.
    if (pozisyon.get("cmf_ardisik_negatif", 0) >= _CMF_KALICI_NEGATIF_GUN
            and ma50 is not None and not pd.isna(ma50) and close < ma50):
        return {"neden": "cmf_kalici_negatif_ma50_alti", "fiyat": float(close), "oran": 1.0}

    # 4) İz süren (Donchian) stop — yalnız Hedef 1 alındıktan sonra aktif.
    if pozisyon.get("hedef1_alindi", False):
        guncel_stop = pozisyon.get("guncel_stop")
        if guncel_stop is not None and not pd.isna(guncel_stop) and low <= guncel_stop:
            fiyat = min(openf, guncel_stop) if (openf is not None and not pd.isna(openf) and openf < guncel_stop) else guncel_stop
            return {"neden": "iz_suren_donchian_stop", "fiyat": float(fiyat), "oran": 1.0}

    # 5) Zaman/momentum stopu.
    gun_sayisi = pozisyon.get("gun_sayisi", 0)
    if gun_sayisi >= _ZAMAN_STOPU_GUN and maliyet:
        getiri = (close - maliyet) / maliyet
        cmf_bugun = satir.get("CMF20")
        cmf_negatif = cmf_bugun is not None and not pd.isna(cmf_bugun) and cmf_bugun < 0
        # "hâlâ kârda değilse" = getiri > 0 DEĞİLSE (breakeven de "kârda değil" sayılır).
        if getiri <= 0 or cmf_negatif:
            return {"neden": "zaman_momentum_stopu", "fiyat": float(close), "oran": 1.0}

    return None


# ═══════════════════════════════════════════════════════════════════════
# §7 — Rutin: "3 ay üst üste risksiz altında kalırsa yeni alım durdurulur"
# ═══════════════════════════════════════════════════════════════════════
def risksiz_altinda_mi_son_uc_ay(tamamlanan_aylik_getiriler: list[float]) -> bool:
    """Son 3 TAMAMLANMIŞ ayın HER BİRİ risksiz aylık getiriden (~%2.84)
    düşükse True döner (bu ay yeni pozisyon açılmamalı). Yeterli geçmiş
    (< 3 ay) yoksa güvenli varsayım: False (engelleme yok, sistem henüz
    "3 ay üst üste" kanıtı biriktirmedi)."""
    if not tamamlanan_aylik_getiriler or len(tamamlanan_aylik_getiriler) < 3:
        return False
    son_uc = tamamlanan_aylik_getiriler[-3:]
    return all((g is not None and not pd.isna(g) and g < _RISKSIZ_AYLIK_GETIRI) for g in son_uc)


if __name__ == "__main__":
    # Ağ çağrısı / dosya okuma içermeyen kendi kendine kontrol.

    # ── limit_seviyesi: iki adayın BÜYÜĞÜ (fiyata en yakın) seçiliyor mu? ──
    satir1 = pd.Series({"MA20": 100.0, "DONCHIAN_UST10": 120.0, "ATR14": 5.0})  # aday2=115 > aday1=100
    assert abs(limit_seviyesi(satir1) - 115.0) < 1e-9
    satir2 = pd.Series({"MA20": 130.0, "DONCHIAN_UST10": 120.0, "ATR14": 5.0})  # aday1=130 > aday2=115
    assert abs(limit_seviyesi(satir2) - 130.0) < 1e-9

    # ── pozisyon_boyutu_hesapla: risk_tl her zaman ozsermaye*%1.5'i aşmamalı ──
    for oz in (500_000.0, 1_000_000.0, 2_000_000.0):
        s = pozisyon_boyutu_hesapla(ozsermaye=oz, fiyat=20.0, atr=0.5,
                                     sektor_toplam_deger=0.0, hisse_toplam_deger=0.0,
                                     hedef_hisse_orani=1.0)
        assert s["risk_tl"] <= oz * _RISK_ORANI + 1e-6, s

    # Sektör tavanı bağlayıcı olduğunda reddetmeli.
    s_sektor = pozisyon_boyutu_hesapla(ozsermaye=1_000_000.0, fiyat=50.0, atr=1.0,
                                        sektor_toplam_deger=300_000.0,  # zaten %30'da
                                        hisse_toplam_deger=0.0, hedef_hisse_orani=1.0)
    assert s_sektor["red_nedeni"] is not None

    # ── Sert stop tetiklenmesi (dinamik ATR ile) ──
    poz = {"sembol": "TEST", "maliyet_ortalama": 100.0, "atr_giris": 4.0,
           "hedef1_alindi": False, "gun_sayisi": 5, "cmf_ardisik_negatif": 0}
    bugun_dusus = pd.Series({"Open": 93.0, "High": 94.0, "Low": 91.0, "Close": 92.0,
                              "ATR14": 4.0, "MA50": 95.0, "Volume": 1_000_000, "HACIM_ORT20": 1_000_000,
                              "CMF20": 0.1})
    sonuc_stop = cikis_kontrol(poz, bugun_dusus)
    assert sonuc_stop is not None and sonuc_stop["neden"] == "sert_stop", sonuc_stop
    assert abs(sonuc_stop["fiyat"] - 92.0) < 1e-9  # 100-2*4=92, low=91<=92, open=93>92 -> fiyat=92

    # ── Hedef 1 tetiklenmesi (High hedefi geçiyor) ──
    poz2 = {"sembol": "TEST2", "maliyet_ortalama": 100.0, "atr_giris": 4.0, "hedef1_alindi": False}
    bugun_hedef = pd.Series({"Open": 111.0, "High": 115.0, "Low": 110.0, "Close": 113.0, "ATR14": 4.0})
    h1 = hedef1_kontrol(poz2, bugun_hedef)
    assert h1 is not None and abs(h1["fiyat"] - 112.0) < 1e-9  # 100+3*4=112
    assert abs(h1["oran"] - _HEDEF1_SATIS_ORANI) < 1e-9

    # ── Trailing stop ASLA aşağı inmiyor (sayaclari_guncelle ile) ──
    poz3 = {"sembol": "TR", "maliyet_ortalama": 100.0, "atr_giris": 4.0,
            "hedef1_alindi": True, "guncel_stop": 105.0, "gun_sayisi": 10, "cmf_ardisik_negatif": 0}
    gecmis_stop = [poz3["guncel_stop"]]
    for donchian_alt in (108.0, 106.0, 112.0, 110.0):  # geri çekilen değerler dahil
        satir = pd.Series({"CMF20": 0.05, "DONCHIAN_ALT10": donchian_alt})
        poz3 = sayaclari_guncelle(poz3, satir)
        gecmis_stop.append(poz3["guncel_stop"])
    for i in range(1, len(gecmis_stop)):
        assert gecmis_stop[i] >= gecmis_stop[i - 1] - 1e-9, f"Trailing stop geriledi! {gecmis_stop}"

    # ── CMF kalıcı negatif sayacı ve tetiklenmesi ──
    poz4 = {"sembol": "CMFNEG", "maliyet_ortalama": 100.0, "atr_giris": 4.0,
            "hedef1_alindi": False, "gun_sayisi": 3, "cmf_ardisik_negatif": 0}
    for _ in range(_CMF_KALICI_NEGATIF_GUN):
        satir = pd.Series({"CMF20": -0.1, "DONCHIAN_ALT10": float("nan")})
        poz4 = sayaclari_guncelle(poz4, satir)
    assert poz4["cmf_ardisik_negatif"] == _CMF_KALICI_NEGATIF_GUN
    bugun_cmfneg = pd.Series({"Open": 99.0, "High": 100.0, "Low": 98.0, "Close": 99.0,
                               "ATR14": 4.0, "MA50": 100.0, "Volume": 500_000, "HACIM_ORT20": 1_000_000,
                               "CMF20": -0.1})
    sonuc_cmf = cikis_kontrol(poz4, bugun_cmfneg)
    assert sonuc_cmf is not None and sonuc_cmf["neden"] == "cmf_kalici_negatif_ma50_alti", sonuc_cmf

    # ── Zaman/momentum stopu: 25. günde hâlâ kârda değilse kapat ──
    poz5 = {"sembol": "DURGUN", "maliyet_ortalama": 100.0, "atr_giris": 4.0,
            "hedef1_alindi": False, "gun_sayisi": 25, "cmf_ardisik_negatif": 0}
    bugun_durgun = pd.Series({"Open": 100.0, "High": 101.0, "Low": 99.5, "Close": 100.0,
                               "ATR14": 4.0, "MA50": 95.0, "Volume": 500_000, "HACIM_ORT20": 1_000_000,
                               "CMF20": 0.1})
    sonuc_zaman = cikis_kontrol(poz5, bugun_durgun)
    assert sonuc_zaman is not None and sonuc_zaman["neden"] == "zaman_momentum_stopu", sonuc_zaman

    # ── §7 risksiz-altı kontrolü ──
    assert risksiz_altinda_mi_son_uc_ay([0.01, 0.01]) is False  # yetersiz geçmiş
    assert risksiz_altinda_mi_son_uc_ay([0.10, 0.01, 0.005, 0.00]) is True  # son 3 ay hep altında
    assert risksiz_altinda_mi_son_uc_ay([0.10, 0.05, 0.005, 0.00]) is False  # 3.'sü sınırda değil ama 2.'si üstte -> False

    print("v21_portfoy.py kendi kendine kontrol: BAŞARILI")
    print(f"Risksiz aylık getiri varsayımı: %{_RISKSIZ_AYLIK_GETIRI*100:.3f}")
