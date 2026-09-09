# -*- coding: utf-8 -*-
"""
v2/veri.py — Pusula V2 veri katmanı.

Tek sorumluluk: yfinance'ten OHLCV indirmek (diske önbellekleyerek) ve
teknik göstergeleri vektörel biçimde hesaplamak. §11 kuralı gereği ağ
çağrısı YALNIZ bu dosyadadır; diğer v2 modülleri saf fonksiyon kalmalıdır.

Bağımlılıklar: pandas, numpy, yfinance (başka hiçbir paket kullanılmaz).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - test ortamında yfinance kurulu olmayabilir
    yf = None

# Önbellek dizini: bu dosyanın yanındaki v2/_onbellek/ — repo kökünden bağımsız,
# v2 modülü nereden çalıştırılırsa çalıştırılsın hep aynı yeri işaret eder.
_ONBELLEK_DIR = Path(__file__).resolve().parent / "_onbellek"
_ONBELLEK_DIR.mkdir(parents=True, exist_ok=True)

# yfinance toplu indirmede tek istekte istenecek sembol sayısı. Çok büyük
# gruplarda yfinance ara sıra bazı sembolleri sessizce atlıyor; 50 pratikte
# güvenilir bulunan bir denge noktası (hız ile güvenilirlik arasında).
_TOPLU_BOYUT = 50

_ZORUNLU_KOLONLAR = ["Open", "High", "Low", "Close", "Volume"]


def _onbellek_yolu(sembol: str, baslangic: str, bitis: str) -> Path:
    """Sembol+tarih aralığına özgü önbellek dosya adı üretir.

    Aralık dosya adına gömülüdür: aksi halde farklı bir [başlangıç, bitiş]
    penceresi istendiğinde eski/kısa bir önbellek yanlışlıkla döndürülebilir
    (örn. backtest 2019'dan başlarken, önbellekte yalnız son 1 yıl varsa).
    """
    guvenli = sembol.replace("/", "_").replace("\\", "_")
    return _ONBELLEK_DIR / f"{guvenli}_{baslangic}_{bitis}.pkl"


def _df_normallestir(df: pd.DataFrame) -> pd.DataFrame:
    """yfinance çıktısını ortak şemaya indirger.

    yfinance toplu indirmede MultiIndex kolon (üst seviye alan adı) verebilir;
    tz-aware index de verebilir (BIST için genelde Europe/Istanbul). Strateji
    tz-naive DatetimeIndex şart koştuğu için burada temizleniyor — aksi halde
    ileride tarih karşılaştırmaları (tarih <= x) tz uyuşmazlığıyla patlar.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    df = df[_ZORUNLU_KOLONLAR].copy()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = "Tarih"
    df = df.sort_index()
    # Aynı güne ait yinelenen satır (nadir de olsa yfinance'te görülüyor) —
    # sonuncusu tutulur, en güncel/son gelen veri esas alınır.
    df = df[~df.index.duplicated(keep="last")]
    return df


def _tek_sembol_indir(sembol: str, baslangic: str, bitis: str) -> pd.DataFrame | None:
    """Tek sembol indirir; başarısızsa None döner.

    Hata toleransı burada sağlanır: bir sembolün API hatası/boş veri vermesi
    tüm toplu işi çökertmemeli, o sembol yalnızca atlanmalı.
    """
    if yf is None:
        return None
    try:
        veri = yf.download(sembol, start=baslangic, end=bitis, progress=False,
                            auto_adjust=False, threads=False)
        if veri is None or veri.empty:
            return None
        return _df_normallestir(veri)
    except Exception:
        return None


def fiyat_indir(semboller: list[str], baslangic: str, bitis: str) -> dict[str, pd.DataFrame]:
    """Verilen semboller için OHLCV indirir (yfinance), disk önbelleği kullanır.

    50'şerli gruplar hâlinde toplu indirir; bir sembol düşerse (boş veri/hata)
    tek tek yeniden denenir, geri kalan semboller etkilenmez. Dönen her
    DataFrame: kolonlar Open/High/Low/Close/Volume, DatetimeIndex tz-naive.
    """
    sonuc: dict[str, pd.DataFrame] = {}
    eksikler: list[str] = []

    # Önce diskten oku — aynı gün içinde tekrar tekrar ağ çağrısı yapmamak için.
    for sembol in semboller:
        onb = _onbellek_yolu(sembol, baslangic, bitis)
        if onb.exists():
            try:
                df = pd.read_pickle(onb)
                if df is not None and not df.empty:
                    sonuc[sembol] = df
                    continue
            except Exception:
                pass  # bozuk önbellek dosyası → aşağıda yeniden indirilecek
        eksikler.append(sembol)

    if not eksikler:
        return sonuc

    if yf is None:
        # yfinance kurulu değilse elimizdeki önbellekle yetinilir; çökme yok.
        return sonuc

    for i in range(0, len(eksikler), _TOPLU_BOYUT):
        grup = eksikler[i:i + _TOPLU_BOYUT]
        toplu = None
        try:
            toplu = yf.download(grup, start=baslangic, end=bitis, progress=False,
                                 group_by="ticker", auto_adjust=False, threads=True)
        except Exception:
            toplu = None  # toplu indirme çökerse aşağıda tek tek denenecek

        for sembol in grup:
            df = None
            if toplu is not None and not toplu.empty:
                try:
                    if isinstance(toplu.columns, pd.MultiIndex):
                        ust_seviye = toplu.columns.get_level_values(0)
                        if sembol in ust_seviye:
                            alt = toplu[sembol].dropna(how="all")
                            if not alt.empty:
                                df = _df_normallestir(alt)
                    elif len(grup) == 1:
                        # Tek sembollük grup düz kolonlarla dönebilir.
                        df = _df_normallestir(toplu)
                except Exception:
                    df = None

            if df is None or df.empty:
                # Toplu indirmede kayıpsa (bazı yfinance sürümleri sessizce
                # atlıyor) son çare olarak tek tek indir — hata toleransı.
                df = _tek_sembol_indir(sembol, baslangic, bitis)

            if df is not None and not df.empty:
                sonuc[sembol] = df
                try:
                    df.to_pickle(_onbellek_yolu(sembol, baslangic, bitis))
                except Exception:
                    pass  # önbelleğe yazılamaması veri akışını durdurmamalı

        # Ardışık gruplar arası kısa bekleme — Yahoo'nun hız sınırına takılmamak için.
        if i + _TOPLU_BOYUT < len(eksikler):
            time.sleep(0.5)

    return sonuc


def _wilder_ortalama(seri: pd.Series, pencere: int) -> pd.Series:
    """Wilder'ın üstel düzeltme yöntemi (ATR ve RSI'nin standart temeli).

    ewm(alpha=1/n, adjust=False), Wilder'ın özyinelemeli formülüyle aynı
    ağırlıklandırmayı üretir (pandas_ta'nın RMA'sıyla aynı yaklaşım) ve
    döngüsüz, tamamen vektörel çalışır.
    """
    return seri.ewm(alpha=1.0 / pencere, adjust=False, min_periods=pencere).mean()


def gostergeler(df: pd.DataFrame) -> pd.DataFrame:
    """Teknik göstergeleri ekler.

    Eklenenler: EMA20, EMA50, MA200, ATR14 (Wilder), RSI14 (Wilder),
    HACIM_ORT20, HACIM_TL_MEDYAN20, YUKSEK20 (BUGÜN HARİÇ), GETIRI60, UZAMA.
    Tamamı vektörel işlemlerle hesaplanır; hiçbir yerde Python döngüsü yoktur.
    """
    out = df.copy()
    close = out["Close"]
    high = out["High"]
    low = out["Low"]
    volume = out["Volume"]

    out["EMA20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()
    out["EMA50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()
    out["MA200"] = close.rolling(200, min_periods=200).mean()

    # True Range: bugünün (Yüksek-Düşük), |Yüksek - dünkü kapanış|,
    # |Düşük - dünkü kapanış| arasındaki en büyüğü. shift(1) kullanılmazsa
    # dünkü kapanış yerine bugünkü kapanış kıyaslanır ve TR sistematik olarak
    # küçük (hatalı) çıkar — özellikle gap günlerinde fark büyür.
    onceki_kapanis = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - onceki_kapanis).abs(),
        (low - onceki_kapanis).abs(),
    ], axis=1).max(axis=1)
    out["ATR14"] = _wilder_ortalama(tr, 14)

    # RSI14 (Wilder): kazanç ve kayıplar AYRI ayrı üstel ortalamayla
    # yumuşatılır; basit hareketli ortalama Wilder'ın tanımına uymaz.
    degisim = close.diff()
    kazanc = degisim.clip(lower=0.0)
    kayip = (-degisim).clip(lower=0.0)
    ort_kazanc = _wilder_ortalama(kazanc, 14)
    ort_kayip = _wilder_ortalama(kayip, 14)
    rs = ort_kazanc / ort_kayip.replace(0.0, np.nan)
    out["RSI14"] = 100 - (100 / (1 + rs))
    # Kayıp sıfırsa (pencerede yalnızca yükseliş var) RSI matematiksel olarak
    # 100 olmalı; rs = kazanç/0 = NaN olduğundan bu durumu ayrıca düzeltiyoruz.
    out.loc[(ort_kayip == 0) & (ort_kazanc > 0), "RSI14"] = 100.0

    out["HACIM_ORT20"] = volume.rolling(20, min_periods=20).mean()

    hacim_tl = close * volume
    out["HACIM_TL_MEDYAN20"] = hacim_tl.rolling(20, min_periods=20).median()

    # YUKSEK20: son 20 günün en yükseği ama BUGÜN HARİÇ. shift(1) olmadan
    # bugünün henüz kapanmamış mumunun kendi Yüksek'i kırılım referansına
    # dahil olur — bu, sinyalin kendi gerçekleşme koşulunu önceden görmesi
    # anlamına gelir (look-ahead'e denk bir mantık hatası).
    out["YUKSEK20"] = high.rolling(20, min_periods=20).max().shift(1)

    out["GETIRI60"] = close.pct_change(60)

    out["UZAMA"] = (close - out["EMA20"]) / out["ATR14"]

    return out


if __name__ == "__main__":
    # Ağ çağrısı içermeyen kendi kendine kontrol — GitHub Actions gibi izole
    # ortamlarda da çalışabilmesi için sentetik veri kullanılır.
    tarihler = pd.date_range("2023-01-01", periods=300, freq="B")
    rng = np.random.default_rng(42)
    fiyat = 100 + np.cumsum(rng.normal(0, 1, size=len(tarihler)))
    sentetik = pd.DataFrame({
        "Open": fiyat + rng.normal(0, 0.2, len(tarihler)),
        "High": fiyat + np.abs(rng.normal(0.5, 0.3, len(tarihler))),
        "Low": fiyat - np.abs(rng.normal(0.5, 0.3, len(tarihler))),
        "Close": fiyat,
        "Volume": rng.integers(1_000_000, 5_000_000, len(tarihler)),
    }, index=tarihler)

    sonuc = gostergeler(sentetik)

    beklenen_kolonlar = {
        "EMA20", "EMA50", "MA200", "ATR14", "RSI14", "HACIM_ORT20",
        "HACIM_TL_MEDYAN20", "YUKSEK20", "GETIRI60", "UZAMA",
    }
    eksik = beklenen_kolonlar - set(sonuc.columns)
    assert not eksik, f"Eksik kolonlar: {eksik}"

    rsi_gecerli = sonuc["RSI14"].dropna()
    assert rsi_gecerli.between(0, 100).all(), "RSI14 0-100 aralığı dışında değer üretti"

    atr_gecerli = sonuc["ATR14"].dropna()
    assert (atr_gecerli >= 0).all(), "ATR14 negatif olamaz"

    # Look-ahead kontrolü: YUKSEK20, bir önceki günün son-20-gün-en-yükseği
    # olmalı (bugünün kendi High'ı dahil EDİLMEMELİ).
    kontrol = sentetik["High"].rolling(20, min_periods=20).max().shift(1)
    fark = (sonuc["YUKSEK20"].dropna() - kontrol.dropna()).abs()
    assert (fark < 1e-9).all(), "YUKSEK20 shift(1) ile uyuşmuyor — look-ahead riski var"

    # UZAMA tutarlılık kontrolü.
    uzama_kontrol = (sonuc["Close"] - sonuc["EMA20"]) / sonuc["ATR14"]
    fark2 = (sonuc["UZAMA"].dropna() - uzama_kontrol.dropna()).abs()
    assert (fark2 < 1e-9).all(), "UZAMA formülü tutarsız"

    print("veri.py kendi kendine kontrol: BAŞARILI")
    print(sonuc.tail(3)[["Close", "EMA20", "EMA50", "ATR14", "RSI14", "UZAMA"]])
