# -*- coding: utf-8 -*-
"""
v2/rejim.py — Pusula V2 rejim kapısı (§2).

XU100.IS (BIST100) endeksine göre R1-R4 rejimini ve hedef yatırım oranını
belirler; evrenin genişlik (breadth) durumuna göre rejimi bir kademe aşağı
çekebilir. Ağ çağrısı YAPMAZ — endeks verisi çağıran taraf (motor.py) veya
veri.fiyat_indir("XU100.IS", ...) tarafından önceden indirilip parametre
olarak buraya verilir. Saf fonksiyon → test edilebilir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_HEDEF_ORANLAR = {"R1": 1.00, "R2": 0.60, "R3": 0.25, "R4": 0.00}
_KADEME_SIRASI = ["R1", "R2", "R3", "R4"]

# Genişlik eşiği: evrenin bu oranın altında bir kısmı 50 günlük ortalamanın
# üzerinde kapatıyorsa, endeks başlığı iyi görünse bile piyasanın altı
# çürük demektir (birkaç ağır endeks hissesi taşıyor olabilir) — rejim bir
# kademe aşağı çekilir.
_GENISLIK_ESIGI = 0.35

# §2'deki MA200/MA50, XU100 endeksinin KENDİ kapanışından hesaplanan basit
# (aritmetik) hareketli ortalamalardır — veri.gostergeler()'in ürettiği
# EMA20/EMA50'den bağımsızdır (o fonksiyon üstel ortalama üretir, burada
# şartname harfiyen "MA" dediği için basit ortalama kullanılıyor). Bu yüzden
# rejim.py kendi MA hesaplarını burada, self-contained biçimde yapar.
_MA200_PENCERE = 200
_MA50_PENCERE = 50


def _sma(seri: pd.Series, pencere: int) -> pd.Series:
    """Basit hareketli ortalama (aritmetik), vektörel."""
    return seri.rolling(pencere, min_periods=pencere).mean()


def rejim_hesapla(endeks_df: pd.DataFrame, evren_verileri: dict, tarih) -> dict:
    """XU100'e göre R1-R4 rejimini, hedef yatırım oranını ve genişliği hesaplar.

    Kurallar (§2):
      R1 Risk Açık : Kapanış > MA200 VE MA50 > MA50[-5]      → hedef %100
      R2 Temkinli  : Kapanış > MA200 VE MA50 <= MA50[-5]     → hedef %60
      R3 Savunma   : Kapanış < MA200                          → hedef %25
      R4 Nakit     : Kapanış < MA200 VE Kapanış < MA200[-10]*0.97 (hızlanan düşüş) → hedef %0

    Genişlik teyidi: evrende (evren_verileri) kendi EMA50'sinin üzerinde
    kapatan hisse oranı < %35 ise rejim bir kademe aşağı çekilir
    (R1→R2, R2→R3, R3→R4; R4 zaten en alt kademe, değişmez).

    NOT: Rejim yükselirken kademeli yaklaşma (günde en fazla %25 puan) ve
    rejim düşerken anında uygulama kuralları PORTFÖY YÖNETİMİNİN (motor.py /
    risk.py) sorumluluğundadır; bu fonksiyon yalnız o günün "hedef" durumunu
    saf biçimde hesaplar, geçmiş pozisyon durumuna bakmaz.

    endeks_df: XU100.IS için OHLCV (en azından Close kolonu).
    evren_verileri: {sembol: DataFrame} — veri.gostergeler() uygulanmış,
                    en az Close ve EMA50 kolonlarını içermeli.
    tarih: karar tarihi; SONRASINDAKİ hiçbir veriye bakılmaz (look-ahead yasağı).
    """
    tarih = pd.Timestamp(tarih)
    gecmis = endeks_df.loc[endeks_df.index <= tarih]

    # Yeterli geçmiş yoksa (MA200 + 10 günlük kıyas için en az ~210 gün gerekir)
    # en temkinli varsayımla başlanır. Veri eksikliğini "her şey yolunda" gibi
    # yorumlamak, tam da V1'in "rejim körlüğü" hatasını tekrar eder.
    if gecmis.empty or len(gecmis) < _MA200_PENCERE + 10:
        return {
            "rejim": "R4",
            "hedef_oran": 0.0,
            "genislik": float("nan"),
            "gerekce": ("Yetersiz XU100 geçmişi (MA200 + 10 gün için en az "
                        f"{_MA200_PENCERE + 10} gün gerekir) — güvenli varsayım: nakit."),
        }

    kapanis = gecmis["Close"]
    ma200 = _sma(kapanis, _MA200_PENCERE)
    ma50 = _sma(kapanis, _MA50_PENCERE)

    bugun_kapanis = float(kapanis.iloc[-1])
    bugun_ma200 = ma200.iloc[-1]
    bugun_ma50 = ma50.iloc[-1]
    ma50_5gun_once = ma50.iloc[-6] if len(ma50) >= 6 else np.nan
    ma200_10gun_once = ma200.iloc[-11] if len(ma200) >= 11 else np.nan

    if pd.isna(bugun_ma200) or pd.isna(bugun_ma50):
        return {
            "rejim": "R4",
            "hedef_oran": 0.0,
            "genislik": float("nan"),
            "gerekce": "MA200/MA50 hesaplanamadı (yetersiz veri) — güvenli varsayım: nakit.",
        }

    ust_trend = bugun_kapanis > bugun_ma200
    ma50_yukseliyor = (not pd.isna(ma50_5gun_once)) and (bugun_ma50 > ma50_5gun_once)
    hizlanan_dusus = (
        (not pd.isna(ma200_10gun_once))
        and (bugun_kapanis < bugun_ma200)
        and (bugun_kapanis < ma200_10gun_once * 0.97)
    )

    if hizlanan_dusus:
        rejim = "R4"
        gerekce = (f"XU100 ({bugun_kapanis:.0f}) MA200 ({bugun_ma200:.0f}) altında VE "
                   f"10 gün önceki MA200 seviyesinin %97'sinin de altına hızla düşüyor "
                   f"— hızlanan düşüş, nakde geç.")
    elif not ust_trend:
        rejim = "R3"
        gerekce = f"XU100 ({bugun_kapanis:.0f}) MA200 ({bugun_ma200:.0f}) altında — savunma modu."
    elif ma50_yukseliyor:
        rejim = "R1"
        gerekce = "XU100 MA200 üzerinde, MA50 yükseliyor — risk açık."
    else:
        rejim = "R2"
        gerekce = "XU100 MA200 üzerinde ama MA50 yükselmiyor (yatay/zayıflıyor) — temkinli."

    # Genişlik (breadth): evrendeki hisselerin kaçı kendi EMA50'sinin üzerinde
    # kapanmış. Yalnızca endeksin başını çeken birkaç ağır hisseye bakarak
    # "piyasa sağlıklı" sonucuna varmamak için bu teyit şart (V1'in gözden
    # kaçırdığı bir kırılganlık kaynağıydı).
    ustunde = 0
    toplam = 0
    for df in (evren_verileri or {}).values():
        if df is None or df.empty:
            continue
        gecmis_h = df.loc[df.index <= tarih]
        if gecmis_h.empty:
            continue
        satir = gecmis_h.iloc[-1]
        ema50 = satir.get("EMA50")
        kapanis_h = satir.get("Close")
        if ema50 is None or kapanis_h is None or pd.isna(ema50) or pd.isna(kapanis_h):
            continue
        toplam += 1
        if kapanis_h > ema50:
            ustunde += 1

    genislik = (ustunde / toplam) if toplam > 0 else float("nan")

    if not pd.isna(genislik) and genislik < _GENISLIK_ESIGI:
        idx = _KADEME_SIRASI.index(rejim)
        if idx < len(_KADEME_SIRASI) - 1:
            eski_rejim = rejim
            rejim = _KADEME_SIRASI[idx + 1]
            gerekce += (f" Genişlik teyidi zayıf (evrenin %{genislik * 100:.0f}'i "
                        f"EMA50 üzerinde, eşik %{_GENISLIK_ESIGI * 100:.0f}) — "
                        f"rejim {eski_rejim}'dan {rejim}'a düşürüldü.")

    return {
        "rejim": rejim,
        "hedef_oran": _HEDEF_ORANLAR[rejim],
        "genislik": genislik,
        "gerekce": gerekce,
    }


if __name__ == "__main__":
    # Ağ çağrısı içermeyen kendi kendine kontrol — sentetik XU100 serileriyle
    # R1/R3/R4 ve genişlik-düşürme senaryolarını doğrular.
    tarihler = pd.date_range("2023-01-01", periods=260, freq="B")

    def _endeks_df(kapanislar: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame({
            "Open": kapanislar, "High": kapanislar * 1.001, "Low": kapanislar * 0.999,
            "Close": kapanislar, "Volume": np.full(len(kapanislar), 1_000_000.0),
        }, index=tarihler)

    def _hisse_df(kapanis_sabit: float) -> pd.DataFrame:
        kapanislar = np.full(len(tarihler), kapanis_sabit)
        df = pd.DataFrame({
            "Open": kapanislar, "High": kapanislar, "Low": kapanislar,
            "Close": kapanislar, "Volume": np.full(len(tarihler), 1_000_000.0),
        }, index=tarihler)
        df["EMA50"] = kapanis_sabit  # düz seri → Close ile EMA50 sürekli eşit
        return df

    # Senaryo 1: istikrarlı yükseliş → R1 beklenir (MA50 5 gün önceye göre yukarı).
    yukselis = 100 + np.arange(len(tarihler)) * 0.5
    tarih_son = tarihler[-1]
    evren_yukselen = {f"H{i}": _hisse_df(50.0 * 1.5) for i in range(10)}
    # evren hisseleri de yükselişte olsun ki genişlik teyidi geçsin: Close > EMA50
    for k, df in evren_yukselen.items():
        df["Close"] = df["Close"] * 1.05  # Close, EMA50'nin üzerinde
    sonuc1 = rejim_hesapla(_endeks_df(yukselis), evren_yukselen, tarih_son)
    assert sonuc1["rejim"] == "R1", f"Beklenen R1, gelen: {sonuc1}"
    assert abs(sonuc1["hedef_oran"] - 1.00) < 1e-9

    # Senaryo 2: sabit düşüş trendi → R3 ya da R4 (hıza bağlı).
    dusus = 200 - np.arange(len(tarihler)) * 0.6
    sonuc2 = rejim_hesapla(_endeks_df(dusus), {}, tarih_son)
    assert sonuc2["rejim"] in ("R3", "R4"), f"Beklenen R3/R4, gelen: {sonuc2}"
    assert sonuc2["hedef_oran"] <= 0.25

    # Senaryo 3: yükseliş trendinde ama evren çürük (Close < EMA50) → bir
    # kademe aşağı (R1 yerine R2) düşmeli.
    evren_zayif = {}
    for i in range(10):
        df = _hisse_df(50.0)
        df["Close"] = df["Close"] * 0.90  # Close, EMA50'nin altında → genişlik düşük
        evren_zayif[f"Z{i}"] = df
    sonuc3 = rejim_hesapla(_endeks_df(yukselis), evren_zayif, tarih_son)
    assert sonuc3["rejim"] == "R2", f"Genişlik düşürme beklenirken gelen: {sonuc3}"
    assert sonuc3["genislik"] < _GENISLIK_ESIGI

    # Look-ahead kontrolü: tarihten sonraki satırları bozunca sonuç değişmemeli.
    bozuk = _endeks_df(yukselis).copy()
    gelecek = pd.date_range(tarih_son + pd.Timedelta(days=1), periods=5, freq="B")
    ek = pd.DataFrame({"Open": [1.0]*5, "High": [1.0]*5, "Low": [1.0]*5,
                        "Close": [1.0]*5, "Volume": [0]*5}, index=gelecek)
    bozuk = pd.concat([bozuk, ek])
    sonuc1b = rejim_hesapla(bozuk, evren_yukselen, tarih_son)
    assert sonuc1b["rejim"] == sonuc1["rejim"], "Gelecek veri sonucu değiştirdi — look-ahead riski"

    print("rejim.py kendi kendine kontrol: BAŞARILI")
    print("Senaryo 1 (yükseliş, sağlıklı genişlik):", sonuc1)
    print("Senaryo 2 (düşüş):", sonuc2)
    print("Senaryo 3 (yükseliş, zayıf genişlik → düşürme):", sonuc3)
