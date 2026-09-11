# -*- coding: utf-8 -*-
"""
v2/v21_gosterge.py — Dinamik & Defansif BIST Algoritması v2.1 gösterge katmanı.

v2/veri.py'ye DOKUNULMADI (şartname gereği). Bu dosya, veri.gostergeler()
uygulanmış bir DataFrame'i girdi alıp v2.1'in ihtiyaç duyduğu EK göstergeleri
üretir: CMF(20), Donchian(10) üst/alt kanal, MA20/MA50 (BASİT ortalama —
v2/rejim.py'deki YORUM KARARI ile aynı gerekçe: şartname düz "MA" dediğinde
basit hareketli ortalama kullanılır, EMA değil — veri.py'nin EMA20/EMA50'si
v2.1 için KULLANILMAZ), GETIRI20, HACIM_ORT5. ATR14 zaten veri.gostergeler()
içinde var (Wilder yöntemiyle) — burada YENİDEN hesaplanmaz; yalnız eksik
olma ihtimaline karşı bir yedek (fallback) fonksiyonu sağlanır.

Ağ çağrısı YOK, dosya okuma YOK — saf fonksiyonlar, vektörel, döngüsüz.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_MA20_PENCERE = 20
_MA50_PENCERE = 50
_CMF_PENCERE = 20
_DONCHIAN_PENCERE = 10
_GETIRI20_PENCERE = 20
_HACIM_ORT5_PENCERE = 5


def _wilder_ortalama(seri: pd.Series, pencere: int) -> pd.Series:
    """veri.py::_wilder_ortalama ile AYNI formül — burada bağımsız/kendi
    kendine yeten bir kopya (v2/veri.py'ye dokunmamak ve bu modülü tek
    başına test edilebilir/ağ gerektirmez tutmak için)."""
    return seri.ewm(alpha=1.0 / pencere, adjust=False, min_periods=pencere).mean()


def atr14_yedek(df: pd.DataFrame) -> pd.Series:
    """ATR14 zaten yoksa (örn. bu modül veri.gostergeler() uygulanmamış ham
    bir df ile çağrılırsa) hesaplanacak yedek. veri.py'deki formülle birebir
    aynıdır — iki modül arasında tutarsız bir ATR üretmemek için."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    onceki_kapanis = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - onceki_kapanis).abs(),
        (low - onceki_kapanis).abs(),
    ], axis=1).max(axis=1)
    return _wilder_ortalama(tr, 14)


def cmf(df: pd.DataFrame, pencere: int = _CMF_PENCERE) -> pd.Series:
    """Chaikin Money Flow(pencere).

    CMF = sum(MFV, n) / sum(Volume, n), MFV = MFM * Volume,
    MFM = ((Close-Low) - (High-Close)) / (High-Low).
    High==Low olan günlerde (nadir, tavan/taban kilidi vb.) MFM tanımsız
    (0/0) olacağından 0.0 kabul edilir — o günün parayı ne alıcı ne satıcı
    yönünde taşımadığı varsayılır (nötr), NaN'in pencere toplamını
    bozmasındansa bu güvenli varsayım tercih edildi.
    """
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    volume = df["Volume"]

    aralik = (high - low)
    mfm = ((close - low) - (high - close)) / aralik.replace(0.0, np.nan)
    mfm = mfm.fillna(0.0)
    mfv = mfm * volume

    pay = mfv.rolling(pencere, min_periods=pencere).sum()
    payda = volume.rolling(pencere, min_periods=pencere).sum()
    return pay / payda.replace(0.0, np.nan)


def donchian(df: pd.DataFrame, pencere: int = _DONCHIAN_PENCERE) -> tuple[pd.Series, pd.Series]:
    """Donchian üst/alt kanal(pencere) — BUGÜN HARİÇ (shift(1)).

    v2/veri.py::YUKSEK20 ile AYNI look-ahead-güvenli desen izlenir: bugünün
    henüz oluşmakta olan barının kendi Yüksek/Düşük'ü kanala DAHİL EDİLMEZ.
    Bunun iki nedeni var: (a) §4'teki giriş bölgesi referansı ("son 10 günlük
    zirve") kendi gerçekleşme koşulunu önceden görmemeli, (b) §6'daki iz
    süren stop (alt kanal) bugünün kendi Düşük'üne bakarak "bugün için" bir
    stop seviyesi üretip aynı gün o seviyeye çarpması gibi döngüsel/kendi
    kendini besleyen bir mantığa düşmemeli.
    """
    ust = df["High"].rolling(pencere, min_periods=pencere).max().shift(1)
    alt = df["Low"].rolling(pencere, min_periods=pencere).min().shift(1)
    return ust, alt


def ek_gostergeler(df: pd.DataFrame) -> pd.DataFrame:
    """v2.1'in ihtiyaç duyduğu tüm ek kolonları ekler.

    Girdi: v2/veri.py::gostergeler() uygulanmış DataFrame (ATR14 sütunu
    zaten mevcut olmalı; yoksa yedek fonksiyonla hesaplanır).
    Eklenen kolonlar: MA20, MA50 (basit ortalama), CMF20, DONCHIAN_UST10,
    DONCHIAN_ALT10, GETIRI20, HACIM_ORT5, ATR14 (yalnız eksikse).
    """
    out = df.copy()
    close = out["Close"]
    volume = out["Volume"]

    out["MA20"] = close.rolling(_MA20_PENCERE, min_periods=_MA20_PENCERE).mean()
    out["MA50"] = close.rolling(_MA50_PENCERE, min_periods=_MA50_PENCERE).mean()

    if "ATR14" not in out.columns:
        out["ATR14"] = atr14_yedek(out)

    out["CMF20"] = cmf(out, _CMF_PENCERE)

    donchian_ust, donchian_alt = donchian(out, _DONCHIAN_PENCERE)
    out["DONCHIAN_UST10"] = donchian_ust
    out["DONCHIAN_ALT10"] = donchian_alt

    out["GETIRI20"] = close.pct_change(_GETIRI20_PENCERE)
    out["HACIM_ORT5"] = volume.rolling(_HACIM_ORT5_PENCERE, min_periods=_HACIM_ORT5_PENCERE).mean()

    return out


if __name__ == "__main__":
    # Ağ çağrısı içermeyen kendi kendine kontrol — sentetik veriyle.
    tarihler = pd.date_range("2023-01-01", periods=300, freq="B")
    rng = np.random.default_rng(7)
    fiyat = 100 + np.cumsum(rng.normal(0, 1, size=len(tarihler)))
    sentetik = pd.DataFrame({
        "Open": fiyat + rng.normal(0, 0.2, len(tarihler)),
        "High": fiyat + np.abs(rng.normal(0.5, 0.3, len(tarihler))),
        "Low": fiyat - np.abs(rng.normal(0.5, 0.3, len(tarihler))),
        "Close": fiyat,
        "Volume": rng.integers(1_000_000, 5_000_000, len(tarihler)),
    }, index=tarihler)

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from veri import gostergeler as _veri_gostergeler

    temel = _veri_gostergeler(sentetik)
    sonuc = ek_gostergeler(temel)

    beklenen = {"MA20", "MA50", "CMF20", "DONCHIAN_UST10", "DONCHIAN_ALT10",
                "GETIRI20", "HACIM_ORT5", "ATR14"}
    eksik = beklenen - set(sonuc.columns)
    assert not eksik, f"Eksik kolonlar: {eksik}"

    cmf_gecerli = sonuc["CMF20"].dropna()
    assert cmf_gecerli.between(-1.0001, 1.0001).all(), "CMF20 [-1,1] aralığı dışına taştı"

    # Look-ahead kontrolü: DONCHIAN_UST10, bugünün kendi High'ını İÇERMEMELİ.
    kontrol_ust = sentetik["High"].rolling(10, min_periods=10).max().shift(1)
    fark = (sonuc["DONCHIAN_UST10"].dropna() - kontrol_ust.dropna()).abs()
    assert (fark < 1e-9).all(), "DONCHIAN_UST10 shift(1) ile uyuşmuyor — look-ahead riski var"

    kontrol_alt = sentetik["Low"].rolling(10, min_periods=10).min().shift(1)
    fark2 = (sonuc["DONCHIAN_ALT10"].dropna() - kontrol_alt.dropna()).abs()
    assert (fark2 < 1e-9).all(), "DONCHIAN_ALT10 shift(1) ile uyuşmuyor — look-ahead riski var"

    print("v21_gosterge.py kendi kendine kontrol: BAŞARILI")
    print(sonuc.tail(3)[["Close", "MA20", "MA50", "CMF20", "DONCHIAN_UST10", "DONCHIAN_ALT10"]])
