# -*- coding: utf-8 -*-
"""
v2/deney_lab.py — "Hisse seçimi mi, piyasada olma zamanlaması mı?" deneyi.

NEDEN VAR: V2 (stop'lu swing) ve V3 (momentum rotasyonu) mimarilerinin İKİSİ
de BIST100'ü al-tut etmekten daha kötü sonuç verdi. Ortaya çıkan hipotez şu:
değer kaynağı HANGİ HİSSEYİ seçtiğin değil, PİYASADA OLUP OLMAMA
ZAMANLAMAN olabilir. Bu dosya o hipotezi, mevcut altyapıyı yeniden kullanarak
(kod kopyalamadan) 7 varyant üzerinde AYNI dönem + AYNI maliyet modeliyle
sınar.

VARYANTLAR
  1) AL_TUT              : XU100 al ve tut (referans).
  2) REJIM_MA200         : Kapanış > MA200 iken tam yatırım, altındayken nakit.
  3) REJIM_MA200_TAMPON  : Aynısı ama %3 tamponlu (whipsaw azaltma).
  4) REJIM_MA50_200      : MA50 > MA200 iken yatırımda (golden/death cross).
  5) ROTASYON_REJIMSIZ   : V3 rotasyonu, rejim kapısı KAPALI.
  6) ROTASYON_SEYREK     : V3 rotasyonu, rebalans 60 gün (20 yerine).
  7) ROTASYON_20POZ      : V3 rotasyonu, 20 pozisyon (10 yerine).

Varyant 5-7 için V3 motoru KOPYALANMAZ; v3_backtest.calistir()'e sonradan
eklenen opsiyonel parametrelerle (rejim_kapisi_aktif / rebalans_gun /
pozisyon_sayisi) çağrılır. O parametrelerin varsayılanları mevcut V3
davranışını birebir korur.

ZORUNLU KURALLAR (tüm varyantlarda AYNI, V2/V3 ile tutarlı):
  - Sinyal gün T KAPANIŞINDA üretilir, emir gün T+1 AÇILIŞINDA gerçekleşir.
  - Her emir maliyet modelinden geçer: komisyon %0.15 + kayma %0.10 (tek yön).
    Endeks işlemlerine de uygulanır (endeksi izleyen bir ETF varsayımı).
  - Özsermaye eğrisi GÜNLÜK tutulur (mark-to-market).

ÇIKTI: v2/sonuclar_lab/ozet.md  ve  v2/sonuclar_lab/sonuc.json
Çalıştırma: v2 klasöründen `python deney_lab.py` (harici girdi istemez).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

_V2_DIR = Path(__file__).resolve().parent
if str(_V2_DIR) not in sys.path:
    sys.path.insert(0, str(_V2_DIR))

import veri
import v3_backtest

SONUC_DIZINI = _V2_DIR / "sonuclar_lab"

# ─────────────────────────────────────────────────────────────────────────
# Sabitler — maliyet modeli v3_backtest'ten OKUNUR (iki yerde ayrı sayı
# tutmak, ileride biri değişince deneyi sessizce geçersiz kılardı).
# ─────────────────────────────────────────────────────────────────────────
_ENDEKS_MALIYET_ORANI = v3_backtest._KOMISYON_ORANI + v3_backtest._KAYMA_NORMAL  # %0.25 tek yön
_YIL_ISLEM_GUNU = v3_backtest._YIL_ISLEM_GUNU

_MA200_PENCERE = 200
_MA50_PENCERE = 50
_TAMPON_ORANI = 0.03      # REJIM_MA200_TAMPON: %3 üstünde gir, %3 altında çık

_ENDEKS_SEMBOL = "XU100.IS"
# MA200'ün geliştirme döneminin İLK gününde bile hazır olması için ~2.5 yıllık
# ısınma verisi indiriliyor (200 işlem günü ≈ 290 takvim günü; buradaki marj
# fazlasıyla yeterli). rejim.py de aynı gerekçeyle MA200+10 gün şartı koyar.
_ENDEKS_VERI_BASLANGIC = "2016-06-01"

_GELISTIRME_BASLANGIC = "2019-01-01"
_GELISTIRME_BITIS = "2023-12-31"
_TEST_BASLANGIC = "2024-01-01"


# ═════════════════════════════════════════════════════════════════════════
# Yardımcılar
# ═════════════════════════════════════════════════════════════════════════
def _temiz(deger):
    """NaN/Inf/Timestamp değerlerini JSON'a yazılabilir hâle getirir.

    json.dump varsayılan olarak NaN yazar; bu GEÇERSİZ JSON'dur ve dosyayı
    okuyan her araç patlar (calistir_v3.py'de de AYNI önlem alınmış).
    """
    if isinstance(deger, dict):
        return {k: _temiz(v) for k, v in deger.items()}
    if isinstance(deger, (list, tuple)):
        return [_temiz(v) for v in deger]
    if isinstance(deger, (pd.Timestamp,)):
        return deger.strftime("%Y-%m-%d")
    if isinstance(deger, (np.integer,)):
        return int(deger)
    if isinstance(deger, (np.floating, float)):
        d = float(deger)
        return None if (math.isnan(d) or math.isinf(d)) else d
    if isinstance(deger, (np.bool_,)):
        return bool(deger)
    return deger


def _gecerli(x) -> bool:
    return isinstance(x, (int, float)) and not pd.isna(x) and not math.isinf(float(x))


def _yuzde(deger, basamak: int = 2) -> str:
    if not _gecerli(deger):
        return "yok"
    return f"%{float(deger) * 100:.{basamak}f}"


def _sayi(deger, basamak: int = 2) -> str:
    if not _gecerli(deger):
        return "yok"
    return f"{float(deger):.{basamak}f}"


def _seri_metrikleri(egri: list[dict]) -> dict:
    """Günlük özsermaye eğrisinden CAGR / maksimum düşüş / yıllık Sharpe.

    Formüller v3_backtest._metrikleri_hesapla ile BİREBİR aynı (CAGR ve
    maksimum düşüş), böylece endeks varyantları ile rotasyon varyantları
    gerçekten kıyaslanabilir olur. dropna() ZORUNLU: son günün barı eksikse
    tek bir NaN CAGR'ı sessizce nan yapar (bkz. v3_backtest'teki aynı not).
    """
    bos = {"cagr": float("nan"), "maks_dusus": float("nan"), "sharpe": float("nan")}
    if not egri:
        return bos
    seri = pd.Series({e["tarih"]: e["ozsermaye"] for e in egri}).sort_index().dropna()
    if len(seri) < 2 or seri.iloc[0] <= 0:
        return bos

    dusus_serisi = (seri / seri.cummax()) - 1.0
    maks_dusus = float(dusus_serisi.min())

    gun_araligi = (seri.index[-1] - seri.index[0]).days
    yil = max(gun_araligi / 365.25, 1e-9)
    cagr = float((seri.iloc[-1] / seri.iloc[0]) ** (1.0 / yil) - 1.0)

    getiriler = seri.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    sharpe = float("nan")
    if len(getiriler) > 2:
        std = float(getiriler.std(ddof=1))
        if std > 0:
            # Risksiz faiz = 0 varsayımı (bkz. ozet.md'deki uyarı notu).
            sharpe = float(getiriler.mean() / std * math.sqrt(_YIL_ISLEM_GUNU))
    return {"cagr": cagr, "maks_dusus": maks_dusus, "sharpe": sharpe}


def _piyasada_kalma(egri: list[dict]) -> float:
    """Ortalama yatırım oranı = mean(pozisyon_deger / ozsermaye).

    Endeks varyantlarında bu değer gün bazında 0 ya da 1 olduğundan doğrudan
    "yatırımda geçirilen gün yüzdesi"ne eşittir. Rotasyon varyantlarında ise
    kısmi maruziyet (rejim %30/%80 gibi) mümkün olduğu için ORTALAMA MARUZİYET
    anlamına gelir — iki aile için de aynı sayı, aynı anlamda: "paranın ne
    kadarı, ne kadar süre piyasadaydı".
    """
    paylar: list[float] = []
    for e in egri:
        oz = e.get("ozsermaye")
        poz = e.get("pozisyon_deger")
        if oz is None or poz is None or pd.isna(oz) or pd.isna(poz) or oz <= 0:
            continue
        paylar.append(min(max(float(poz) / float(oz), 0.0), 1.0))
    return float(np.mean(paylar)) if paylar else float("nan")


# ═════════════════════════════════════════════════════════════════════════
# Endeks verisi + rejim sinyalleri
# ═════════════════════════════════════════════════════════════════════════
def _endeks_hazirla(bitis: str) -> pd.DataFrame:
    """XU100'ü ısınma payıyla indirir ve MA200/MA50 kolonlarını ekler.

    MA'lar rejim.py ile AYNI biçimde BASİT (aritmetik) hareketli ortalamadır
    ve min_periods=pencere ile hesaplanır — yani ilk 199 günde NaN kalır,
    "yarım veriyle" sahte bir sinyal üretilmez.
    """
    ham = veri.fiyat_indir([_ENDEKS_SEMBOL], _ENDEKS_VERI_BASLANGIC, bitis)
    df = ham.get(_ENDEKS_SEMBOL)
    if df is None or df.empty:
        raise RuntimeError(
            f"{_ENDEKS_SEMBOL} verisi indirilemedi — deney çalıştırılamaz. "
            "(İnternet erişimi ve yfinance kurulumunu kontrol edin.)"
        )
    df = df.sort_index().copy()
    df["MA200"] = df["Close"].rolling(_MA200_PENCERE, min_periods=_MA200_PENCERE).mean()
    df["MA50"] = df["Close"].rolling(_MA50_PENCERE, min_periods=_MA50_PENCERE).mean()
    return df


def _sinyal_serisi(endeks_df: pd.DataFrame, tur: str) -> pd.Series:
    """Gün T KAPANIŞINDA verilen "yatırımda olmalı mıyım?" kararı (bool seri).

    Look-ahead yok: her gün yalnız o günün ve öncesinin kapanışını kullanır.
    Seri TÜM geçmiş üzerinde üretilir (yalnız test dönemi üzerinde değil), ki
    tamponlu varyantın dönem başındaki durumu geçmişten doğal olarak gelsin,
    yapay bir "dönem başında nakitte" varsayımıyla başlamasın.

    MA hesaplanamıyorsa (ilk 199 gün) karar NAKİT'tir — rejim.py'nin "veri
    eksikliğini iyimser yorumlama" kuralıyla aynı temkinli varsayım.
    """
    kapanis = endeks_df["Close"]
    ma200 = endeks_df["MA200"]
    ma50 = endeks_df["MA50"]

    if tur == "al_tut":
        return pd.Series(True, index=endeks_df.index)

    if tur == "ma200":
        return (kapanis > ma200).fillna(False)

    if tur == "ma50_200":
        return (ma50 > ma200).fillna(False)

    if tur == "ma200_tampon":
        ust = ma200 * (1.0 + _TAMPON_ORANI)
        alt = ma200 * (1.0 - _TAMPON_ORANI)
        gir = (kapanis > ust).fillna(False).to_numpy()
        cik = (kapanis < alt).fillna(False).to_numpy()
        # MA200 yoksa hiçbir koşul tetiklenmez; "gir" de "çık" da False olur
        # ve durum korunur — ama başlangıç durumu NAKİT olduğundan ilk geçerli
        # "gir" sinyaline kadar piyasa dışında kalınır (temkinli varsayım).
        gecerli = ma200.notna().to_numpy()
        durum = np.zeros(len(endeks_df), dtype=bool)
        acik = False
        for i in range(len(endeks_df)):
            if gecerli[i]:
                if not acik and gir[i]:
                    acik = True
                elif acik and cik[i]:
                    acik = False
            durum[i] = acik
        return pd.Series(durum, index=endeks_df.index)

    raise ValueError(f"Bilinmeyen sinyal türü: {tur}")


# ═════════════════════════════════════════════════════════════════════════
# Endeks zamanlama motoru (varyant 1-4)
# ═════════════════════════════════════════════════════════════════════════
def _endeks_zamanlama(endeks_df: pd.DataFrame, sinyal: pd.Series,
                       baslangic: str, bitis: str, ozsermaye: float) -> dict:
    """Tek varlıklı (XU100) zamanlama simülasyonu — T kapanış sinyali, T+1 açılış emri.

    Muhasebe kuralları v3_backtest._calistir_ic ile bilinçli olarak AYNI:
      - gün içi sıra: (1) dünkü emri bugünün AÇILIŞINDA gerçekleştir,
        (2) bugünün KAPANIŞIYLA mark-to-market, (3) bugünün kapanış sinyaline
        göre YARININ emrini kuyruğa al.
      - tam adet (math.floor) alınır, maliyet her iki yönde de uygulanır.
      - kapanış verisi eksikse pozisyon SON BİLİNEN kapanışla değerlenir
        (asla 0 sayılmaz — bkz. v3_backtest'teki "KRİTİK MUHASEBE DÜZELTMESİ").
    """
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    takvim = endeks_df.loc[(endeks_df.index >= baslangic_ts)
                           & (endeks_df.index <= bitis_ts)].index
    if len(takvim) < 2:
        return {"ozsermaye_egrisi": [], "emir_sayisi": 0}

    cash = float(ozsermaye)
    adet = 0.0
    oran = _ENDEKS_MALIYET_ORANI
    emir_sayisi = 0
    egri: list[dict] = []
    son_kapanis: float | None = None

    # Dönemin İLK günündeki açılışta işlem yapılabilmesi için, kararın dönem
    # başlamadan ÖNCEKİ son kapanışta verilmiş olması gerekir (T kapanış ->
    # T+1 açılış kuralı dönem sınırında da bozulmaz). Bu, AL_TUT'un ilk gün
    # açılışında girmesini sağlar; look-ahead değildir, geçmiş veridir.
    onceki = endeks_df.loc[endeks_df.index < takvim[0]]
    if len(onceki) > 0 and bool(sinyal.get(onceki.index[-1], False)):
        bekleyen = "gir"
    else:
        bekleyen = None

    for T in takvim:
        satir = endeks_df.loc[T]
        acilis = satir.get("Open")
        kapanis = satir.get("Close")
        if acilis is None or pd.isna(acilis) or float(acilis) <= 0:
            acilis = kapanis  # açılış boşsa kapanışla işle (nadir veri boşluğu)

        # ── 1) Dünün emrini bugünün AÇILIŞINDA gerçekleştir. ──
        if acilis is not None and not pd.isna(acilis) and float(acilis) > 0:
            acilis_f = float(acilis)
            if bekleyen == "gir" and adet <= 0:
                alinacak = math.floor(cash / (acilis_f * (1.0 + oran)))
                if alinacak > 0:
                    cash -= alinacak * acilis_f * (1.0 + oran)
                    adet = float(alinacak)
                    emir_sayisi += 1
            elif bekleyen == "cik" and adet > 0:
                cash += adet * acilis_f * (1.0 - oran)
                adet = 0.0
                emir_sayisi += 1
            bekleyen = None
        # (açılış fiyatı yoksa emir bugün düşer; koşul yarın hâlâ geçerliyse
        #  aşağıdaki 3. adım onu yeniden kuyruğa alır — idempotent.)

        # ── 2) Mark-to-market. ──
        if kapanis is not None and not pd.isna(kapanis):
            son_kapanis = float(kapanis)
        deger_fiyati = son_kapanis
        if deger_fiyati is None:
            pozisyon_deger = float("nan")
            guncel = float("nan")
        else:
            pozisyon_deger = adet * deger_fiyati
            guncel = cash + pozisyon_deger
        egri.append({"tarih": T, "ozsermaye": guncel,
                     "nakit": cash, "pozisyon_deger": pozisyon_deger})

        # ── 3) Bugünün KAPANIŞ sinyaline göre yarının emri. ──
        istenen = bool(sinyal.get(T, False))
        if istenen and adet <= 0:
            bekleyen = "gir"
        elif (not istenen) and adet > 0:
            bekleyen = "cik"

    return {"ozsermaye_egrisi": egri, "emir_sayisi": emir_sayisi}


# ═════════════════════════════════════════════════════════════════════════
# Varyant tanımları ve koşturucu
# ═════════════════════════════════════════════════════════════════════════
# (kod, açıklama, aile, ayar)
_VARYANTLAR = [
    ("AL_TUT", "XU100 al ve tut (referans)", "endeks", {"sinyal": "al_tut"}),
    ("REJIM_MA200", "Kapanış > MA200 -> yatırımda, altı -> %100 nakit", "endeks",
     {"sinyal": "ma200"}),
    ("REJIM_MA200_TAMPON", "MA200 %+3 üstünde gir, %-3 altında çık", "endeks",
     {"sinyal": "ma200_tampon"}),
    ("REJIM_MA50_200", "MA50 > MA200 -> yatırımda (golden/death cross)", "endeks",
     {"sinyal": "ma50_200"}),
    ("ROTASYON_REJIMSIZ", "V3 momentum rotasyonu, rejim kapısı KAPALI", "rotasyon",
     {"rejim_kapisi_aktif": False}),
    ("ROTASYON_SEYREK", "V3 rotasyonu, rebalans 60 gün (20 yerine)", "rotasyon",
     {"rebalans_gun": 60}),
    ("ROTASYON_20POZ", "V3 rotasyonu, 20 pozisyon (10 yerine)", "rotasyon",
     {"pozisyon_sayisi": 20}),
]


def _donem_calistir(donem_adi: str, baslangic: str, bitis: str,
                     endeks_df: pd.DataFrame, ozsermaye: float) -> list[dict]:
    """Bir dönem için 7 varyantı da koşturur, satır listesi döner."""
    satirlar: list[dict] = []

    for kod, aciklama, aile, ayar in _VARYANTLAR:
        print("─" * 70)
        print(f"[deney_lab] {donem_adi} | {kod}: {aciklama}")
        print("─" * 70)
        satir = {
            "donem": donem_adi, "baslangic": baslangic, "bitis": bitis,
            "varyant": kod, "aciklama": aciklama, "aile": aile,
            "cagr": float("nan"), "maks_dusus": float("nan"), "sharpe": float("nan"),
            "islem_sayisi": 0, "piyasada_kalma_yuzde": float("nan"), "hata": None,
        }
        try:
            if aile == "endeks":
                sinyal = _sinyal_serisi(endeks_df, ayar["sinyal"])
                sonuc = _endeks_zamanlama(endeks_df, sinyal, baslangic, bitis, ozsermaye)
                egri = sonuc["ozsermaye_egrisi"]
                # Endeks ailesinde "işlem sayısı" = GERÇEKLEŞEN EMİR sayısı
                # (giriş + çıkış ayrı sayılır); rotasyon ailesinde ise motorun
                # kendi tanımı olan KAPANAN POZİSYON sayısıdır. Bu fark
                # ozet.md'de dipnotla açıkça belirtiliyor.
                satir["islem_sayisi"] = int(sonuc["emir_sayisi"])
            else:
                sonuc = v3_backtest.calistir(baslangic, bitis, ozsermaye, **ayar)
                egri = sonuc["ozsermaye_egrisi"]
                satir["islem_sayisi"] = int(sonuc["metrikler"].get("islem_sayisi", 0))

            metrikler = _seri_metrikleri(egri)
            satir.update(metrikler)
            satir["piyasada_kalma_yuzde"] = _piyasada_kalma(egri)
        except Exception as hata:  # tek varyantın çökmesi TÜM deneyi düşürmesin
            satir["hata"] = f"{type(hata).__name__}: {hata}"
            print(f"[deney_lab] HATA ({kod}): {satir['hata']}")
            traceback.print_exc()

        print(f"[deney_lab] {kod} -> CAGR {_yuzde(satir['cagr'])} | "
              f"maks düşüş {_yuzde(satir['maks_dusus'])} | "
              f"Sharpe {_sayi(satir['sharpe'])} | "
              f"işlem {satir['islem_sayisi']} | "
              f"piyasada {_yuzde(satir['piyasada_kalma_yuzde'], 1)}")
        satirlar.append(satir)

    return satirlar


def _kazananlar(satirlar: list[dict]) -> list[str]:
    """Al-tut'u HEM CAGR'da HEM maksimum düşüşte geçen varyantların kodları.

    "Maks düşüşte geçmek" = mutlak değeri DAHA KÜÇÜK olmak (daha az düşmek).
    Bu liste ELLE yazılmaz; ozet.md'nin en üstündeki sonuç cümlesi doğrudan
    bu fonksiyonun çıktısından üretilir.
    """
    referans = next((s for s in satirlar if s["varyant"] == "AL_TUT"), None)
    if referans is None or not (_gecerli(referans["cagr"]) and _gecerli(referans["maks_dusus"])):
        return []
    kazanan: list[str] = []
    for s in satirlar:
        if s["varyant"] == "AL_TUT" or s.get("hata"):
            continue
        if not (_gecerli(s["cagr"]) and _gecerli(s["maks_dusus"])):
            continue
        cagr_ustun = s["cagr"] > referans["cagr"]
        dusus_ustun = abs(s["maks_dusus"]) < abs(referans["maks_dusus"])
        if cagr_ustun and dusus_ustun:
            kazanan.append(s["varyant"])
    return kazanan


# ═════════════════════════════════════════════════════════════════════════
# Raporlama
# ═════════════════════════════════════════════════════════════════════════
def _tablo(satirlar: list[dict]) -> str:
    basliklar = ("| Varyant | CAGR | Maks düşüş | Sharpe (yıllık) | İşlem sayısı "
                 "| Piyasada kalma % |
"
                 "|---|---:|---:|---:|---:|---:|
")
    govde = ""
    for s in satirlar:
        ad = s["varyant"] + (" (referans)" if s["varyant"] == "AL_TUT" else "")
        if s.get("hata"):
            govde += f"| {ad} | HATA | HATA | HATA | - | - |
"
            continue
        govde += (f"| {ad} | {_yuzde(s['cagr'])} | {_yuzde(s['maks_dusus'])} | "
                  f"{_sayi(s['sharpe'])} | {s['islem_sayisi']} | "
                  f"{_yuzde(s['piyasada_kalma_yuzde'], 1)} |
")
    return basliklar + govde


def _sonuc_cumlesi(donem_adi: str, satirlar: list[dict]) -> str:
    kazanan = _kazananlar(satirlar)
    if kazanan:
        return (f"**{donem_adi}**: al-tut'u HEM CAGR'da HEM maksimum düşüşte geçen "
                f"varyant(lar): **{', '.join(kazanan)}**.")
    return (f"**{donem_adi}**: al-tut'u HEM CAGR'da HEM maksimum düşüşte geçen "
            f"varyant **HİÇBİRİ** yok.")


def _ozet_yaz(gelistirme: list[dict], test: list[dict], bugun: str,
              ozsermaye: float) -> str:
    test_kazanan = _kazananlar(test)
    if test_kazanan:
        manset = ("SONUÇ: TEST döneminde al-tut'u HEM CAGR'da HEM maksimum düşüşte geçen "
                  f"varyant(lar): {', '.join(test_kazanan)}.")
    else:
        manset = ("SONUÇ: TEST döneminde al-tut'u HEM CAGR'da HEM maksimum düşüşte geçen "
                  "varyant HİÇBİRİ.")

    satirlar = [
        f"# {manset}",
        "",
        _sonuc_cumlesi(f"Geliştirme ({_GELISTIRME_BASLANGIC} → {_GELISTIRME_BITIS})",
                       gelistirme),
        "",
        _sonuc_cumlesi(f"Test — DOKUNULMAMIŞ ({_TEST_BASLANGIC} → {bugun})", test),
        "",
        "> Bu manşet ve iki cümle ELLE yazılmadı; `_kazananlar()` fonksiyonu her",
        "> koşuda AL_TUT satırıyla karşılaştırma yaparak otomatik üretir.",
        "",
        "---",
        "",
        "## Deney sorusu",
        "",
        "V2 (stop'lu swing) ve V3 (momentum rotasyonu) mimarilerinin ikisi de BIST100'ü",
        "al-tut etmekten daha kötü sonuç verdi. Sınanan hipotez: değer kaynağı HANGİ",
        "HİSSEYİ seçtiğin değil, PİYASADA OLUP OLMAMA ZAMANLAMAN olabilir.",
        "",
        f"- Başlangıç özsermayesi: {ozsermaye:,.0f} TL",
        f"- Maliyet (TÜM varyantlarda aynı): komisyon %{v3_backtest._KOMISYON_ORANI * 100:.2f}"
        f" + kayma %{v3_backtest._KAYMA_NORMAL * 100:.2f} = "
        f"%{_ENDEKS_MALIYET_ORANI * 100:.2f} tek yön. Endeks işlemlerine de uygulandı"
        " (endeksi izleyen bir ETF varsayımı).",
        "- Sinyal gün T KAPANIŞINDA üretilir, emir gün T+1 AÇILIŞINDA gerçekleşir.",
        "",
        "## Varyantlar",
        "",
    ]
    for kod, aciklama, aile, _ayar in _VARYANTLAR:
        satirlar.append(f"- **{kod}** ({aile}): {aciklama}")

    satirlar += [
        "",
        f"## Geliştirme dönemi: {_GELISTIRME_BASLANGIC} → {_GELISTIRME_BITIS}",
        "",
        _tablo(gelistirme),
        f"## Test dönemi (DOKUNULMAMIŞ): {_TEST_BASLANGIC} → {bugun}",
        "",
        _tablo(test),
        "## Metrik notları (dürüstlük şartı)",
        "",
        "- **Maks düşüş**: günlük mark-to-market özsermaye eğrisi üzerinden; negatif",
        "  sayı, mutlak değeri KÜÇÜK olan daha iyidir.",
        "- **Sharpe (yıllık)**: günlük getirilerin ortalaması / standart sapması ×",
        f"  √{_YIL_ISLEM_GUNU}, **risksiz faiz = 0** varsayımıyla. Türkiye'de mevduat/",
        "  repo faizi sıfırdan çok uzak olduğu için bu Sharpe MUTLAK bir kalite ölçüsü",
        "  DEĞİLDİR; yalnız varyantları birbirine göre sıralamak için kullanılmalıdır.",
        "- **İşlem sayısı**: endeks varyantlarında GERÇEKLEŞEN EMİR sayısı (giriş ve",
        "  çıkış ayrı sayılır); rotasyon varyantlarında V3 motorunun kendi tanımı olan",
        "  KAPANAN POZİSYON sayısı. İki aile arasında doğrudan kıyaslanamaz.",
        "- **Piyasada kalma %**: ortalama yatırım oranı = mean(pozisyon değeri /",
        "  özsermaye). Endeks varyantlarında gün başına 0 veya 1 olduğu için",
        "  \"yatırımda geçirilen gün yüzdesi\"ne eşittir; rotasyon varyantlarında",
        "  kısmi maruziyet mümkün olduğundan ORTALAMA MARUZİYET anlamına gelir.",
        "- Tüm dönemler **nominal TL** üzerinden hesaplanmıştır; enflasyon",
        "  düzeltmesi YAPILMAMIŞTIR. Al-tut referansı da aynı ölçekte olduğu için",
        "  KIYAS geçerlidir, ama mutlak CAGR rakamları reel getiri değildir.",
        "",
        f"_Üretim: `v2/deney_lab.py` — {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
    ]
    return "\n".join(satirlar)


# ═════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════
def main() -> int:
    ayristirici = argparse.ArgumentParser(
        description="Rejim/zamanlama deney laboratuvarı (7 varyant, 2 dönem)."
    )
    ayristirici.add_argument("--ozsermaye", type=float, default=1_000_000.0,
                             help="Başlangıç özsermayesi (TL). Varsayılan: 1.000.000")
    argumanlar = ayristirici.parse_args()
    ozsermaye = float(argumanlar.ozsermaye)

    os.makedirs(SONUC_DIZINI, exist_ok=True)
    bugun = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")

    print("=" * 70)
    print("DENEY LAB — hisse seçimi mi, piyasada olma zamanlaması mı?")
    print(f"Geliştirme: {_GELISTIRME_BASLANGIC} → {_GELISTIRME_BITIS}")
    print(f"Test (dokunulmamış): {_TEST_BASLANGIC} → {bugun}")
    print(f"Maliyet: %{_ENDEKS_MALIYET_ORANI * 100:.2f} tek yön (tüm varyantlarda)")
    print("=" * 70)

    endeks_df = _endeks_hazirla(bugun)
    print(f"[deney_lab] XU100 verisi hazır: {len(endeks_df)} gün "
          f"({endeks_df.index[0].date()} → {endeks_df.index[-1].date()})")

    gelistirme = _donem_calistir("gelistirme", _GELISTIRME_BASLANGIC,
                                  _GELISTIRME_BITIS, endeks_df, ozsermaye)
    test = _donem_calistir("test", _TEST_BASLANGIC, bugun, endeks_df, ozsermaye)

    kayit = {
        "uretim_zamani": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ozsermaye": ozsermaye,
        "maliyet_tek_yon": _ENDEKS_MALIYET_ORANI,
        "komisyon_orani": v3_backtest._KOMISYON_ORANI,
        "kayma_orani": v3_backtest._KAYMA_NORMAL,
        "donemler": {
            "gelistirme": {"baslangic": _GELISTIRME_BASLANGIC, "bitis": _GELISTIRME_BITIS},
            "test": {"baslangic": _TEST_BASLANGIC, "bitis": bugun},
        },
        "sonuclar": gelistirme + test,
        "al_tutu_hem_cagr_hem_dususte_gecenler": {
            "gelistirme": _kazananlar(gelistirme),
            "test": _kazananlar(test),
        },
    }
    json_yolu = SONUC_DIZINI / "sonuc.json"
    with open(json_yolu, "w", encoding="utf-8") as dosya:
        json.dump(_temiz(kayit), dosya, ensure_ascii=False, indent=1)

    ozet = _ozet_yaz(gelistirme, test, bugun, ozsermaye)
    ozet_yolu = SONUC_DIZINI / "ozet.md"
    with open(ozet_yolu, "w", encoding="utf-8") as dosya:
        dosya.write(ozet)

    print("=" * 70)
    print(ozet)
    print("=" * 70)
    print(f"[deney_lab] Yazıldı: {ozet_yolu}")
    print(f"[deney_lab] Yazıldı: {json_yolu}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
