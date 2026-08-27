# -*- coding: utf-8 -*-
"""
analiz_motoru.py — Teknik göstergeler, takas/para akışı analizi,
kısa-orta-uzun vade sinyaller ve 0-100 puanlama.
"""

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Göstergeler (saf pandas — ek kütüphane gerektirmez)
# ─────────────────────────────────────────────────────────────────────────────
def sma(s, n):  return s.rolling(n).mean()
def ema(s, n):  return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    d = close.diff()
    kazanc = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    kayip = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = kazanc / kayip.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(close, hizli=12, yavas=26, sinyal=9):
    m = ema(close, hizli) - ema(close, yavas)
    s = ema(m, sinyal)
    return m, s, m - s


def bollinger(close, n=20, k=2.0):
    """Bollinger bantları.

    ddof=0 (ANAKÜTLE standart sapması) kullanılır — bu, John Bollinger'ın
    orijinal tanımı ve TradingView/çoğu grafik programının hesabıdır.
    pandas'ın `.std()` varsayılanı ddof=1'dir (örneklem); önceden o
    kullanılıyordu ve bantlar grafik programlarındakinden ~%0,1 daha geniş
    çıkıyordu. Fark küçük olsa da "fiyat üst bandın üstünde mi?" gibi eşik
    karşılaştırmalarında ara sıra farklı sinyal üretebilir; kullanıcı
    grafikle karşılaştırdığında tutarsızlık görmesin diye standarda çekildi.
    """
    orta = sma(close, n)
    std = close.rolling(n).std(ddof=0)
    return orta + k * std, orta, orta - k * std


def stochastic(df, n=14, d=3):
    """YAVAŞ (slow) stokastik.

    Dönüş: (%K, %D) — burada %K, ham stokastiğin d-periyotluk ortalamasıdır
    (yani "yavaş %K"), %D ise onun bir kez daha ortalamasıdır. Bu bilinçli
    bir tercihtir: ham (hızlı) %K çok gürültülüdür ve tek günlük sıçramalarda
    yanlış sinyal üretir. Grafik programlarında "Stochastic Slow" ayarının
    karşılığıdır.
    """
    en_dusuk = df["Low"].rolling(n).min()
    en_yuksek = df["High"].rolling(n).max()
    ham_k = 100 * (df["Close"] - en_dusuk) / (en_yuksek - en_dusuk).replace(0, np.nan)
    yavas_k = ham_k.rolling(d).mean()
    return yavas_k, yavas_k.rolling(d).mean()


def atr(df, n=14):
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def obv(df):
    yon = np.sign(df["Close"].diff()).fillna(0)
    return (yon * df["Volume"]).cumsum()


def mfi(df, n=14):
    tipik = (df["High"] + df["Low"] + df["Close"]) / 3
    akis = tipik * df["Volume"]
    poz = akis.where(tipik > tipik.shift(), 0.0).rolling(n).sum()
    neg = akis.where(tipik < tipik.shift(), 0.0).rolling(n).sum()
    oran = poz / neg.replace(0, np.nan)
    return 100 - 100 / (1 + oran)


def cmf(df, n=20):
    """Chaikin Money Flow — para giriş/çıkışının en bilinen ölçüsü."""
    aralik = (df["High"] - df["Low"]).replace(0, np.nan)
    carpan = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / aralik
    hacim_akisi = carpan * df["Volume"]
    return hacim_akisi.rolling(n).sum() / df["Volume"].rolling(n).sum()


def ad_cizgisi(df):
    """Accumulation/Distribution — toplama/dağıtım çizgisi."""
    aralik = (df["High"] - df["Low"]).replace(0, np.nan)
    carpan = (((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / aralik).fillna(0)
    return (carpan * df["Volume"]).cumsum()


def egim(s, n):
    """Son n gündeki normalize eğim (yüzde/gün).

    NORMALİZASYON NOTU: Eğim, serinin kendi ölçeğine bölünerek normalize edilir.
    Fiyat serilerinde ortalama (mean) doğru ölçektir. Ancak OBV / A-D çizgisi
    gibi KÜMÜLATİF ve sıfır civarında salınabilen serilerde ortalama sıfıra
    yaklaşır ve bölme sonucu astronomik değerlere (örn. 2e+17) fırlayarak
    eşik karşılaştırmalarını (egim > 0.15 gibi) tamamen bozar.
    Bu yüzden payda olarak |ortalama| ile standart sapmanın BÜYÜĞÜ kullanılır:
      • Fiyat serilerinde ortalama >> std olduğundan davranış eskisiyle aynıdır.
      • Sıfır merkezli osilatörlerde std devreye girip anlamlı bir ölçek sağlar.
    """
    s = s.dropna().tail(n)
    if len(s) < max(5, n // 2):
        return np.nan
    x = np.arange(len(s))
    katsayi = np.polyfit(x, s.values, 1)[0]
    olcek = max(abs(float(s.mean())), float(s.std()))
    if not np.isfinite(olcek) or olcek <= 1e-9:
        return np.nan
    return 100 * katsayi / olcek


# ─────────────────────────────────────────────────────────────────────────────
# Sinyal üretimi — her vade için (puan 0-100, sinyal listesi)
# ─────────────────────────────────────────────────────────────────────────────
def _ekle(liste, etiket, yon, aciklama):
    liste.append({"etiket": etiket, "yon": yon, "aciklama": aciklama})


def trend_baglami(df) -> dict:
    """Hissenin ANA TREND yönünü belirler: 'yukselis' / 'dusus' / 'yatay'.

    ═══════════════════════════════════════════════════════════════════════════
    NEDEN VAR (kritik): RSI, Stokastik ve Bollinger gibi OSİLATÖRLER tek başına
    "aşırı satım = AL" diye okunursa DÜŞEN BIÇAĞI yakalamaya çalışırsınız.
    Sert düşüş trendindeki bir hisse haftalarca RSI 20-30 arasında kalabilir ve
    her gün "aşırı satım, tepki potansiyeli" sinyali üretir — hâlbuki düşmeye
    devam eder. Tersi de doğrudur: güçlü yükseliş trendindeki bir hissede
    RSI 75+ olması "sat" demek değildir, GÜÇ işaretidir (momentum).

    Bu yüzden osilatör sinyalleri ARTIK TREND BAĞLAMINA GÖRE yorumlanır:
      • Yükseliş trendinde aşırı satım  → gerçek ALIM fırsatı (düzeltme)
      • Düşüş trendinde aşırı satım     → ALIM SİNYALİ DEĞİL (düşen bıçak)
      • Yükseliş trendinde aşırı alım   → ceza YOK (momentum gücü)
      • Düşüş trendinde aşırı alım      → SATIŞ (ayı piyasası ralli bitişi)

    Dönüş: {"yon", "skor", "ma50_ustu", "ma200_ustu", "ma50_yukseliyor"}
    """
    c = df["Close"]
    son = float(c.iloc[-1])
    skor = 0
    ma50_s = sma(c, 50)
    ma50 = float(ma50_s.iloc[-1]) if len(c) >= 50 and not np.isnan(ma50_s.iloc[-1]) else np.nan
    ma200_s = sma(c, 200)
    ma200 = float(ma200_s.iloc[-1]) if len(c) >= 200 and not np.isnan(ma200_s.iloc[-1]) else np.nan

    ma50_ustu = bool(son > ma50) if not np.isnan(ma50) else None
    ma200_ustu = bool(son > ma200) if not np.isnan(ma200) else None
    if ma50_ustu is True:
        skor += 1
    elif ma50_ustu is False:
        skor -= 1
    if ma200_ustu is True:
        skor += 1
    elif ma200_ustu is False:
        skor -= 1

    # MA50'nin KENDİ eğimi — fiyat ortalamanın altında olsa bile ortalama
    # yükseliyorsa trend hâlâ yukarı olabilir (ve tersi).
    ma50_egim = egim(ma50_s.dropna(), 20) if len(ma50_s.dropna()) >= 20 else np.nan
    ma50_yukseliyor = None
    if not np.isnan(ma50_egim):
        if ma50_egim > 0.02:
            skor += 1; ma50_yukseliyor = True
        elif ma50_egim < -0.02:
            skor -= 1; ma50_yukseliyor = False

    if skor >= 2:
        yon = "yukselis"
    elif skor <= -2:
        yon = "dusus"
    else:
        yon = "yatay"
    return {"yon": yon, "skor": skor, "ma50_ustu": ma50_ustu,
            "ma200_ustu": ma200_ustu, "ma50_yukseliyor": ma50_yukseliyor}


def kisa_vade(df, baglam: dict = None) -> tuple:
    """1-4 hafta perspektifi.

    baglam: trend_baglami() çıktısı. Verilmezse burada hesaplanır. Osilatör
    sinyalleri bu bağlama göre yorumlanır (bkz. trend_baglami docstring'i).
    """
    p, sinyaller = 50.0, []
    c = df["Close"]
    son = c.iloc[-1]
    if baglam is None:
        baglam = trend_baglami(df)
    _yukselis = baglam["yon"] == "yukselis"
    _dusus = baglam["yon"] == "dusus"

    r = rsi(c).iloc[-1]
    if r < 30:
        if _dusus:
            # DÜŞEN BIÇAK: düşüş trendinde aşırı satım alım sinyali DEĞİLDİR.
            p -= 2; _ekle(sinyaller, "RSI", "SAT",
                          f"RSI {r:.0f} — aşırı satım AMA ana trend AŞAĞI. Bu bir alım "
                          "sinyali değil, düşüşün sürdüğünün işaretidir (düşen bıçak).")
        elif _yukselis:
            p += 12; _ekle(sinyaller, "RSI", "AL",
                           f"RSI {r:.0f} — YÜKSELİŞ trendinde aşırı satım: klasik düzeltme/alım fırsatı")
        else:
            p += 4; _ekle(sinyaller, "RSI", "AL",
                          f"RSI {r:.0f} — aşırı satım (trend yatay, temkinli)")
    elif r < 45:
        if _dusus:
            _ekle(sinyaller, "RSI", "NÖTR", f"RSI {r:.0f} — düşük ama trend aşağı, acele etme")
        else:
            p += 4; _ekle(sinyaller, "RSI", "AL", f"RSI {r:.0f} — düşük bölge")
    elif r > 75:
        if _yukselis:
            # Güçlü trendde RSI 75+ zayıflık değil GÜÇ göstergesidir.
            p += 3; _ekle(sinyaller, "RSI", "NÖTR",
                          f"RSI {r:.0f} — aşırı alım ama trend YUKARI: momentum gücü "
                          "(tek başına satış gerekçesi değil)")
        else:
            p -= 10; _ekle(sinyaller, "RSI", "SAT",
                           f"RSI {r:.0f} — aşırı alım ve trend desteklemiyor, geri çekilme riski")
    elif r > 60:
        p += 3; _ekle(sinyaller, "RSI", "NÖTR", f"RSI {r:.0f} — güçlü ama aşırı değil")

    m, ms, hist = macd(c)
    if hist.iloc[-1] > 0 and hist.iloc[-2] <= 0:
        p += 12; _ekle(sinyaller, "MACD", "AL", "MACD yeni AL kesişimi yaptı")
    elif hist.iloc[-1] > 0:
        p += 6; _ekle(sinyaller, "MACD", "AL", "MACD pozitif bölgede")
    elif hist.iloc[-1] < 0 and hist.iloc[-2] >= 0:
        p -= 12; _ekle(sinyaller, "MACD", "SAT", "MACD yeni SAT kesişimi yaptı")
    else:
        p -= 5; _ekle(sinyaller, "MACD", "SAT", "MACD negatif bölgede")

    k, d = stochastic(df)
    if not np.isnan(k.iloc[-1]):
        if k.iloc[-1] < 20:
            if _dusus:
                _ekle(sinyaller, "Stokastik", "NÖTR",
                      f"Stokastik {k.iloc[-1]:.0f} — dipte ama düşüş trendinde dip kalıcı olabilir")
            else:
                p += 7; _ekle(sinyaller, "Stokastik", "AL", f"Stokastik {k.iloc[-1]:.0f} — dipte")
        elif k.iloc[-1] > 80:
            if _yukselis:
                _ekle(sinyaller, "Stokastik", "NÖTR",
                      f"Stokastik {k.iloc[-1]:.0f} — tepede ama trend yukarı (güçlü trendde normal)")
            else:
                p -= 7; _ekle(sinyaller, "Stokastik", "SAT", f"Stokastik {k.iloc[-1]:.0f} — tepede")

    s20 = sma(c, 20).iloc[-1]
    if son > s20:
        p += 6; _ekle(sinyaller, "MA20", "AL", "Fiyat 20 günlük ortalamanın üzerinde")
    else:
        p -= 6; _ekle(sinyaller, "MA20", "SAT", "Fiyat 20 günlük ortalamanın altında")

    ust, orta, alt = bollinger(c)
    if son < alt.iloc[-1]:
        if _dusus:
            # Düşüş trendinde alt bandın DELİNMESİ aşırı satım değil, ÇÖKÜŞTÜR.
            p -= 4; _ekle(sinyaller, "Bollinger", "SAT",
                          "Fiyat alt bandı aşağı deldi ve trend zaten aşağı — çöküş devam sinyali")
        else:
            p += 6; _ekle(sinyaller, "Bollinger", "AL", "Fiyat alt bandın altında — aşırı satım")
    elif son > ust.iloc[-1]:
        if _yukselis:
            p += 3; _ekle(sinyaller, "Bollinger", "AL",
                          "Fiyat üst bandın üzerinde ve trend yukarı — güçlü çıkış (breakout)")
        else:
            p -= 5; _ekle(sinyaller, "Bollinger", "SAT", "Fiyat üst bandın üzerinde — ısınmış")

    hacim_oran = df["Volume"].tail(5).mean() / max(df["Volume"].tail(60).mean(), 1)
    getiri_5g = 100 * (son / c.iloc[-6] - 1) if len(c) > 6 else 0
    if hacim_oran > 1.8 and getiri_5g > 0:
        p += 8; _ekle(sinyaller, "Hacim", "AL",
                      f"Hacim son 5 günde ortalamanın {hacim_oran:.1f} katı + fiyat yükselişte")
    elif hacim_oran > 1.8 and getiri_5g < -3:
        p -= 6; _ekle(sinyaller, "Hacim", "SAT", "Yüksek hacimli satış baskısı")

    mom = 100 * (son / c.iloc[-11] - 1) if len(c) > 11 else 0
    if mom > 8:
        p += 5; _ekle(sinyaller, "Momentum", "AL", f"10 günlük momentum +%{mom:.1f}")
    elif mom < -8:
        p -= 5; _ekle(sinyaller, "Momentum", "SAT", f"10 günlük momentum %{mom:.1f}")

    return float(np.clip(p, 0, 100)), sinyaller


def orta_vade(df, endeks_df=None) -> tuple:
    """1-6 ay perspektifi."""
    p, sinyaller = 50.0, []
    c = df["Close"]
    son = c.iloc[-1]

    s50, s100 = sma(c, 50).iloc[-1], sma(c, 100).iloc[-1]
    if son > s50 > s100:
        p += 12; _ekle(sinyaller, "Trend", "AL", "Fiyat > MA50 > MA100 — sağlam yükseliş trendi")
    elif son > s50:
        p += 6; _ekle(sinyaller, "Trend", "AL", "Fiyat 50 günlük ortalamanın üzerinde")
    elif son < s50 < s100:
        p -= 12; _ekle(sinyaller, "Trend", "SAT", "Fiyat < MA50 < MA100 — düşüş trendi")
    else:
        p -= 4; _ekle(sinyaller, "Trend", "NÖTR", "Trend kararsız")

    # Golden / death cross
    s50_s, s200_s = sma(c, 50), sma(c, 200)
    if len(c) > 210 and not np.isnan(s200_s.iloc[-1]):
        if s50_s.iloc[-1] > s200_s.iloc[-1] and s50_s.iloc[-21] <= s200_s.iloc[-21]:
            p += 10; _ekle(sinyaller, "Golden Cross", "AL", "MA50, MA200'ü yukarı kesti (son 1 ay)")
        elif s50_s.iloc[-1] < s200_s.iloc[-1] and s50_s.iloc[-21] >= s200_s.iloc[-21]:
            p -= 10; _ekle(sinyaller, "Death Cross", "SAT", "MA50, MA200'ü aşağı kesti (son 1 ay)")

    e = egim(c, 60)
    if not np.isnan(e):
        if e > 0.15:
            p += 8; _ekle(sinyaller, "Eğim", "AL", "Son 3 ayın fiyat eğimi belirgin pozitif")
        elif e < -0.15:
            p -= 8; _ekle(sinyaller, "Eğim", "SAT", "Son 3 ayın fiyat eğimi belirgin negatif")

    # Göreceli güç (XU100'e karşı)
    if endeks_df is not None and len(endeks_df) > 70:
        try:
            ort = c.tail(63); end = endeks_df["Close"].reindex(ort.index).ffill()
            hisse_g = ort.iloc[-1] / ort.iloc[0] - 1
            endeks_g = end.iloc[-1] / end.iloc[0] - 1
            fark = 100 * (hisse_g - endeks_g)
            if fark > 10:
                p += 10; _ekle(sinyaller, "Göreceli Güç", "AL",
                               f"Son 3 ayda BIST100'den %{fark:.0f} daha iyi performans")
            elif fark > 3:
                p += 5; _ekle(sinyaller, "Göreceli Güç", "AL",
                              f"BIST100'den %{fark:.0f} daha güçlü")
            elif fark < -10:
                p -= 8; _ekle(sinyaller, "Göreceli Güç", "SAT",
                              f"BIST100'ün %{abs(fark):.0f} gerisinde")
        except Exception:
            pass

    m_haftalik = c.resample("W").last()
    if len(m_haftalik) > 30:
        mh, msh, histh = macd(m_haftalik)
        if histh.iloc[-1] > 0:
            p += 6; _ekle(sinyaller, "Haftalık MACD", "AL", "Haftalık MACD pozitif")
        else:
            p -= 6; _ekle(sinyaller, "Haftalık MACD", "SAT", "Haftalık MACD negatif")

    # Zirveden uzaklık (taban yapma / momentum dengesi)
    zirve52 = c.tail(252).max()
    uzaklik = 100 * (son / zirve52 - 1)
    if uzaklik > -5:
        p += 5; _ekle(sinyaller, "52H Zirve", "AL", "52 haftalık zirveye çok yakın — güç işareti")
    elif uzaklik < -40:
        _ekle(sinyaller, "52H Zirve", "NÖTR", f"Zirveden %{abs(uzaklik):.0f} aşağıda — ucuzlamış ama trend zayıf")

    return float(np.clip(p, 0, 100)), sinyaller


def uzun_vade(df, temel: dict) -> tuple:
    """6 ay+ perspektifi: uzun trend + temel değerleme."""
    p, sinyaller = 50.0, []
    c = df["Close"]
    son = c.iloc[-1]

    s200 = sma(c, 200).iloc[-1]
    if not np.isnan(s200):
        if son > s200:
            p += 10; _ekle(sinyaller, "MA200", "AL", "Fiyat 200 günlük ortalamanın üzerinde")
        else:
            p -= 10; _ekle(sinyaller, "MA200", "SAT", "Fiyat 200 günlük ortalamanın altında")

    yillik = 100 * (son / c.iloc[0] - 1) if len(c) > 400 else None
    if yillik is not None:
        if yillik > 50:
            p += 5; _ekle(sinyaller, "Uzun Trend", "AL", f"2 yıllık getiri +%{yillik:.0f}")
        elif yillik < -20:
            p -= 5; _ekle(sinyaller, "Uzun Trend", "SAT", f"2 yıllık getiri %{yillik:.0f}")

    fk = temel.get("fk")
    if fk is not None:
        try:
            fk = float(fk)
            if 0 < fk < 8:
                p += 10; _ekle(sinyaller, "F/K", "AL", f"F/K {fk:.1f} — düşük çarpan, ucuz değerleme")
            elif 0 < fk < 15:
                p += 5; _ekle(sinyaller, "F/K", "AL", f"F/K {fk:.1f} — makul değerleme")
            elif fk > 35:
                p -= 8; _ekle(sinyaller, "F/K", "SAT", f"F/K {fk:.1f} — pahalı değerleme")
            elif fk < 0:
                p -= 8; _ekle(sinyaller, "F/K", "SAT", "Şirket zarar ediyor (negatif F/K)")
        except Exception:
            pass

    pddd = temel.get("pddd")
    if pddd is not None:
        try:
            pddd = float(pddd)
            if 0 < pddd < 1:
                p += 8; _ekle(sinyaller, "PD/DD", "AL", f"PD/DD {pddd:.2f} — defter değerinin altında")
            elif 0 < pddd < 2.5:
                p += 3; _ekle(sinyaller, "PD/DD", "AL", f"PD/DD {pddd:.2f} — makul")
            elif pddd > 6:
                p -= 6; _ekle(sinyaller, "PD/DD", "SAT", f"PD/DD {pddd:.2f} — yüksek")
        except Exception:
            pass

    tem = temel.get("temettu_verimi")
    if tem:
        try:
            tem = float(tem)
            tem = tem * 100 if tem < 1 else tem
            if tem > 4:
                p += 5; _ekle(sinyaller, "Temettü", "AL", f"Temettü verimi %{tem:.1f}")
        except Exception:
            pass

    # Volatilite cezası (uzun vade için aşırı oynak hisse risklidir)
    vol = c.pct_change().tail(252).std() * np.sqrt(252) * 100
    if vol > 80:
        p -= 5; _ekle(sinyaller, "Volatilite", "SAT", f"Yıllık volatilite %{vol:.0f} — çok oynak")

    return float(np.clip(p, 0, 100)), sinyaller


def takas_analizi(df, temel: dict, yabanci_s: pd.Series) -> tuple:
    """Takas puanı: yabancı takas oranı (MKK kaynaklı) + para akışı (toplama/dağıtım)."""
    p, sinyaller = 50.0, []

    # 1) Yabancı takas oranı geçmişi (gerçek takas verisi)
    if yabanci_s is not None and len(yabanci_s) > 10:
        simdiki = yabanci_s.iloc[-1]
        ay1 = yabanci_s.iloc[-22] if len(yabanci_s) > 22 else yabanci_s.iloc[0]
        ay3 = yabanci_s.iloc[-66] if len(yabanci_s) > 66 else yabanci_s.iloc[0]
        d1, d3 = simdiki - ay1, simdiki - ay3
        if d1 > 0.5:
            p += 12; _ekle(sinyaller, "Yabancı Takas", "AL",
                           f"Yabancı oranı son 1 ayda +{d1:.1f} puan arttı (%{simdiki:.1f}) — yabancı alıyor")
        elif d1 < -0.5:
            p -= 12; _ekle(sinyaller, "Yabancı Takas", "SAT",
                           f"Yabancı oranı son 1 ayda {d1:.1f} puan düştü (%{simdiki:.1f}) — yabancı satıyor")
        else:
            _ekle(sinyaller, "Yabancı Takas", "NÖTR", f"Yabancı oranı yatay (%{simdiki:.1f})")
        if d3 > 1.5:
            p += 6; _ekle(sinyaller, "Yabancı Takas (3 ay)", "AL", f"3 aylık değişim +{d3:.1f} puan — istikrarlı giriş")
        elif d3 < -1.5:
            p -= 6; _ekle(sinyaller, "Yabancı Takas (3 ay)", "SAT", f"3 aylık değişim {d3:.1f} puan — istikrarlı çıkış")
    elif temel.get("yabanci_orani") is not None:
        _ekle(sinyaller, "Yabancı Takas", "NÖTR",
              f"Güncel yabancı oranı %{float(temel['yabanci_orani']):.1f} (geçmiş veri alınamadı)")

    # 2) Para akışı — CMF
    c_cmf = cmf(df).iloc[-1]
    if not np.isnan(c_cmf):
        if c_cmf > 0.10:
            p += 10; _ekle(sinyaller, "Para Akışı (CMF)", "AL",
                           f"CMF {c_cmf:+.2f} — hisseye belirgin para girişi var")
        elif c_cmf > 0.03:
            p += 5; _ekle(sinyaller, "Para Akışı (CMF)", "AL", f"CMF {c_cmf:+.2f} — ılımlı para girişi")
        elif c_cmf < -0.10:
            p -= 10; _ekle(sinyaller, "Para Akışı (CMF)", "SAT",
                           f"CMF {c_cmf:+.2f} — hisseden para çıkışı var")
        elif c_cmf < -0.03:
            p -= 5; _ekle(sinyaller, "Para Akışı (CMF)", "SAT", f"CMF {c_cmf:+.2f} — ılımlı para çıkışı")

    # 3) Toplama/Dağıtım çizgisi eğilimi vs fiyat (gizli toplama tespiti)
    ad = ad_cizgisi(df)
    ad_egim, fiyat_egim = egim(ad, 40), egim(df["Close"], 40)
    if not np.isnan(ad_egim) and not np.isnan(fiyat_egim):
        if ad_egim > 0.1 and fiyat_egim < 0.05:
            p += 10; _ekle(sinyaller, "Toplama/Dağıtım", "AL",
                           "Fiyat yatay/zayıfken A/D çizgisi yükseliyor — sessiz TOPLAMA işareti")
        elif ad_egim < -0.1 and fiyat_egim > -0.05:
            p -= 10; _ekle(sinyaller, "Toplama/Dağıtım", "SAT",
                           "Fiyat dirençliyken A/D çizgisi düşüyor — sessiz DAĞITIM işareti")
        elif ad_egim > 0.1:
            p += 5; _ekle(sinyaller, "Toplama/Dağıtım", "AL", "A/D çizgisi yükseliş trendinde")

    # 4) MFI
    m = mfi(df).iloc[-1]
    if not np.isnan(m):
        if m < 20:
            p += 6; _ekle(sinyaller, "MFI", "AL", f"MFI {m:.0f} — para akışı aşırı satımda, dönüş potansiyeli")
        elif m > 80:
            p -= 6; _ekle(sinyaller, "MFI", "SAT", f"MFI {m:.0f} — para akışı aşırı ısınmış")

    # 5) OBV trendi
    o = obv(df)
    o_egim = egim(o, 40)
    if not np.isnan(o_egim):
        if o_egim > 0.15:
            p += 6; _ekle(sinyaller, "OBV", "AL", "OBV yükseliyor — hacim alıcılardan yana")
        elif o_egim < -0.15:
            p -= 6; _ekle(sinyaller, "OBV", "SAT", "OBV düşüyor — hacim satıcılardan yana")

    return float(np.clip(p, 0, 100)), sinyaller


def fon_kurumsal_analizi(etf_df, tefas_s) -> tuple:
    """Kurumsal sahiplik sinyalleri: ETF (yabancı kurumsal) + TEFAS (yerli fonlar)."""
    p, sinyaller = 50.0, []

    if etf_df is not None and len(etf_df) > 0:
        try:
            adet = len(etf_df)
            toplam_usd = float(pd.to_numeric(etf_df.get("market_cap_usd"),
                                             errors="coerce").sum())
            if adet >= 15:
                p += 10; _ekle(sinyaller, "ETF Sahipliği", "AL",
                               f"{adet} uluslararası ETF bu hisseyi taşıyor "
                               f"(~{toplam_usd/1e6:.0f}M $) — güçlü yabancı kurumsal ilgi")
            elif adet >= 5:
                p += 5; _ekle(sinyaller, "ETF Sahipliği", "AL",
                              f"{adet} uluslararası ETF pozisyonda (~{toplam_usd/1e6:.0f}M $)")
            else:
                _ekle(sinyaller, "ETF Sahipliği", "NÖTR",
                      f"Yalnızca {adet} ETF pozisyonda — yabancı kurumsal ilgi sınırlı")
        except Exception:
            pass
    else:
        _ekle(sinyaller, "ETF Sahipliği", "NÖTR", "ETF sahiplik verisi alınamadı")

    if tefas_s is not None and len(tefas_s) >= 3:
        d = tefas_s.iloc[-1] - tefas_s.iloc[0]
        if d > 1.0:
            p += 8; _ekle(sinyaller, "Yerli Fonlar (TEFAS)", "AL",
                          f"Fonların hisse ağırlığı son dönemde +{d:.1f} puan — "
                          "yerli kurumsal para borsaya giriyor (tüm piyasa için olumlu)")
        elif d < -1.0:
            p -= 8; _ekle(sinyaller, "Yerli Fonlar (TEFAS)", "SAT",
                          f"Fonların hisse ağırlığı {d:.1f} puan azaldı — "
                          "yerli kurumsal para borsadan çıkıyor")
        else:
            _ekle(sinyaller, "Yerli Fonlar (TEFAS)", "NÖTR",
                  f"Fonların hisse ağırlığı yatay (%{tefas_s.iloc[-1]:.1f})")

    return float(np.clip(p, 0, 100)), sinyaller


def piyasa_rejimi(xu100_df, usdtry_df, tefas_s=None) -> dict:
    """Genel piyasa ortamı: risk açık mı kapalı mı?
    Siyasi/makro gerilim fiyata önce XU100 trendi, dolar bazlı BIST ve
    USDTRY oynaklığından yansır. 0-100 skor üretir."""
    p, sinyaller = 50.0, []

    if xu100_df is not None and len(xu100_df) > 210:
        c = xu100_df["Close"]
        son = c.iloc[-1]
        if son > sma(c, 50).iloc[-1]:
            p += 10; _ekle(sinyaller, "BIST100 Trendi", "AL", "Endeks MA50 üzerinde")
        else:
            p -= 10; _ekle(sinyaller, "BIST100 Trendi", "SAT", "Endeks MA50 altında")
        if son > sma(c, 200).iloc[-1]:
            p += 8; _ekle(sinyaller, "BIST100 Uzun Trend", "AL", "Endeks MA200 üzerinde")
        else:
            p -= 8; _ekle(sinyaller, "BIST100 Uzun Trend", "SAT", "Endeks MA200 altında")
        g3 = 100 * (son / c.iloc[-66] - 1) if len(c) > 66 else 0
        if g3 > 10:
            p += 6; _ekle(sinyaller, "BIST100 Momentum", "AL", f"3 aylık getiri +%{g3:.0f}")
        elif g3 < -10:
            p -= 6; _ekle(sinyaller, "BIST100 Momentum", "SAT", f"3 aylık getiri %{g3:.0f}")

        # Dolar bazlı BIST (yabancının gördüğü tablo)
        if usdtry_df is not None and len(usdtry_df) > 70:
            try:
                kur = usdtry_df["Close"].reindex(c.index).ffill()
                usd_bist = c / kur
                g3u = 100 * (usd_bist.iloc[-1] / usd_bist.iloc[-66] - 1)
                if g3u > 5:
                    p += 8; _ekle(sinyaller, "Dolar Bazlı BIST", "AL",
                                  f"Dolar bazında 3 ayda +%{g3u:.0f} — yabancı için cazip trend")
                elif g3u < -5:
                    p -= 8; _ekle(sinyaller, "Dolar Bazlı BIST", "SAT",
                                  f"Dolar bazında 3 ayda %{g3u:.0f} — TL getirisi kur karşısında eriyor")
            except Exception:
                pass

    if usdtry_df is not None and len(usdtry_df) > 30:
        kur = usdtry_df["Close"]
        aylik_artis = 100 * (kur.iloc[-1] / kur.iloc[-22] - 1) if len(kur) > 22 else 0
        oynaklik = kur.pct_change().tail(30).std() * 100
        if aylik_artis > 4 or oynaklik > 0.8:
            p -= 10; _ekle(sinyaller, "USDTRY", "SAT",
                           f"Kurda hızlanma/oynaklık (aylık +%{aylik_artis:.1f}) — "
                           "siyasi/makro gerilim işareti, risk iştahı düşük")
        elif aylik_artis < 2 and oynaklik < 0.4:
            p += 6; _ekle(sinyaller, "USDTRY", "AL", "Kur sakin — makro ortam destekleyici")

    if tefas_s is not None and len(tefas_s) >= 3:
        d = tefas_s.iloc[-1] - tefas_s.iloc[0]
        if d > 1.0:
            p += 6; _ekle(sinyaller, "Fon Akımları", "AL", "Yerli fonlar hisse ağırlığını artırıyor")
        elif d < -1.0:
            p -= 6; _ekle(sinyaller, "Fon Akımları", "SAT", "Yerli fonlar hisse ağırlığını azaltıyor")

    p = float(np.clip(p, 0, 100))
    if p >= 62:
        durum, emoji = "RİSK AÇIK — Boğa ortamı", "🟢"
    elif p >= 45:
        durum, emoji = "NÖTR — Seçici olun", "🟡"
    else:
        durum, emoji = "RİSK KAPALI — Savunma modu", "🔴"
    return {"puan": p, "durum": durum, "emoji": emoji, "sinyaller": sinyaller}


def rejim_duzeltmesi(genel_puan: float, rejim_puani: float) -> tuple:
    """Riskli piyasa ortamında hisse puanlarını kısar, güçlü ortamda hafif destekler.
    Dönüş: (düzeltilmiş puan, düzeltme miktarı)"""
    duzeltme = (rejim_puani - 50.0) * 0.16   # ±8 puana kadar
    yeni = float(np.clip(genel_puan + duzeltme, 0, 100))
    return yeni, round(duzeltme, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Bileşik puan ve karar
# ─────────────────────────────────────────────────────────────────────────────
AGIRLIKLAR = {"kisa": 0.25, "orta": 0.30, "uzun": 0.20, "takas": 0.25}
AGIRLIKLAR_FON = {"kisa": 0.22, "orta": 0.28, "uzun": 0.18, "takas": 0.22, "fon": 0.10}


def karar_ver(puan: float) -> tuple:
    if puan >= 72:  return "GÜÇLÜ AL", "🟢"
    if puan >= 62:  return "AL", "🟢"
    if puan >= 52:  return "İZLE / TUT", "🟡"
    if puan >= 40:  return "ZAYIF / BEKLE", "🟠"
    return "UZAK DUR / SAT", "🔴"


def vade_karari(puan) -> str:
    """Tek bir vade puanını (0-100) kısa bir karar metnine çevirir."""
    if puan is None:
        return "⚪ Veri yok"
    if puan >= 70:
        return "🟢 GÜÇLÜ AL"
    if puan >= 60:
        return "🟢 AL"
    if puan >= 50:
        return "🟡 İZLE"
    if puan >= 40:
        return "🟠 ZAYIF"
    return "🔴 UZAK DUR"


def vade_taramasi(veri_sozlugu: dict, ust_sinir: int = 40, endeks_df=None,
                   ilerleme=None, min_hacim_milyon_tl: float = 5.0) -> pd.DataFrame:
    """TEKNİK tabanlı Kısa/Orta/Uzun vade taraması.

    ═══════════════════════════════════════════════════════════════════════════
    NEDEN BÖYLE: Bu fonksiyon, eskiden oruntu_motoru.vade_taramasi'nın yaptığı
    işi yapar ama GEÇMİŞ ÖRÜNTÜ analizine hiç dayanmaz. Örüntü sinyali
    kullanıcı deneyiminde yanıltıcı bulunduğu için sistemden tamamen
    çıkarılmıştır (bkz. OKU_BENI.txt). Artık her vade, o vadeye ait TEKNİK
    puandan (hizli_puan'ın Kısa/Orta/Uzun bileşenleri) türetilir; bu puanlar
    doğrudan fiyat/hacim/trend göstergelerine dayanır ve "geçmişte benzer
    durumlar şöyle olmuştu" gibi istatistiksel bir varsayım içermez.

    Dönüş: Genel Puan'a göre azalan sıralı DataFrame.
    """
    sonuclar = []
    toplam = len(veri_sozlugu)
    # ─────────────────────────────────────────────────────────────────────
    # İLERLEME GERİ ÇAĞRISI — İKİ FARKLI İMZAYI DA DESTEKLER
    # NEDEN: Bu fonksiyon eski oruntu_motoru.vade_taramasi'nın yerine geçti.
    # Eski sürüm geri çağrıyı TEK argümanla (0..1 arası oran) çağırıyordu ve
    # app.py'deki mevcut çağrı da öyle bir lambda geçiriyor. Yeni sürüm ise
    # (sayac, toplam, sembol) üçlüsüyle çağırınca canlı taramada
    # "TypeError: <lambda>() takes 1 positional argument but 3 were given"
    # hatası alınıyordu. Artık hangi imza verilirse verilsin çalışır; ayrıca
    # geri çağrıdaki bir hata TÜM TARAMAYI düşürmez (sadece ilerleme çubuğu
    # güncellenmez) — tarama sonucu ilerleme göstergesinden daha önemlidir.
    def _ilerlet(sayac):
        if not ilerleme:
            return
        oran = sayac / toplam if toplam else 1.0
        try:
            ilerleme(oran)                      # eski/tek argümanlı imza
        except TypeError:
            try:
                ilerleme(sayac, toplam, sembol)  # yeni/üç argümanlı imza
            except Exception:
                pass
        except Exception:
            pass

    for i, (sembol, df) in enumerate(veri_sozlugu.items()):
        _ilerlet(i + 1)
        try:
            if df is None or df.empty or "Close" not in df.columns:
                continue
            # Çok düşük hacimli hisselerde teknik göstergeler gürültüye boğulur.
            ort_hacim_tl = float((df["Close"] * df["Volume"]).tail(20).mean()) / 1e6
            if ort_hacim_tl < min_hacim_milyon_tl:
                continue
            satir = hizli_puan(df, endeks_df)
            if satir.get("Puan") is None:
                continue
            kayit = {
                "Hisse": sembol,
                "Kısa": vade_karari(satir.get("Kısa")),
                "Orta": vade_karari(satir.get("Orta")),
                "Uzun": vade_karari(satir.get("Uzun")),
                "Genel Puan": satir["Puan"],
                "Fiyat": satir.get("Fiyat"),
                "Kısa Puan": satir.get("Kısa"),
                "Orta Puan": satir.get("Orta"),
                "Uzun Puan": satir.get("Uzun"),
                "Takas Puan": satir.get("Takas"),
                "1 Ay %": satir.get("1 Ay %"),
                "3 Ay %": satir.get("3 Ay %"),
                "Hacim(M₺)": satir.get("Hacim(M₺)"),
            }
            sonuclar.append(kayit)
        except Exception:
            continue

    if not sonuclar:
        return pd.DataFrame()
    tablo = pd.DataFrame(sonuclar).sort_values("Genel Puan", ascending=False)
    tablo = tablo.head(ust_sinir).reset_index(drop=True)
    tablo.index += 1
    return tablo


# ─────────────────────────────────────────────────────────────────────────────
# SATIŞ / RİSK ALARMLARI — "elimdeki hisseyi ne zaman satmalıyım?"
# ─────────────────────────────────────────────────────────────────────────────
# NEDEN VAR: Puanlama sistemi "almaya değer mi?" sorusunu yanıtlar; ancak
# elde TUTULAN bir hissede asıl kritik soru "çıkmalı mıyım?"dur ve bu, puanın
# yavaşça düşmesini beklemekten daha HIZLI bir uyarı gerektirir. Bir hisse
# 70 puandan 55'e inene kadar %20 değer kaybedebilir. Aşağıdaki alarmlar,
# klasik risk yönetimi kurallarını doğrudan kontrol eder ve TEK TEK açık
# gerekçe üretir. Amaç erken çıkış — sermayeyi korumak.
def risk_alarmlari(df: pd.DataFrame, alis_fiyati: float = None) -> dict:
    """Düşüş/satış uyarılarını üretir.

    alis_fiyati verilirse zarar-kes (stop-loss) mesafesi de hesaplanır.

    Dönüş: {"seviye": "yok|izle|dikkat|acil", "alarmlar": [...],
            "risk_puani": 0-100, "stop_seviyesi": float|None,
            "zarar_yuzde": float|None}
    """
    alarmlar = []
    risk = 0
    c = df["Close"]
    son = float(c.iloc[-1])

    def _al(baslik, mesaj, agirlik):
        nonlocal risk
        alarmlar.append({"baslik": baslik, "mesaj": mesaj, "agirlik": agirlik})
        risk += agirlik

    # 1) TREND KIRILIMI — en temel çıkış kuralı
    if len(c) >= 50:
        ma50 = sma(c, 50)
        if not np.isnan(ma50.iloc[-1]):
            if son < float(ma50.iloc[-1]):
                # Yeni mi kırdı, yoksa uzun süredir altında mı?
                onceki = c.iloc[-6] if len(c) > 6 else c.iloc[0]
                ma50_onceki = ma50.iloc[-6] if len(ma50) > 6 else ma50.iloc[-1]
                if not np.isnan(ma50_onceki) and float(onceki) >= float(ma50_onceki):
                    _al("MA50 kırıldı",
                        "Fiyat 50 günlük ortalamanın ALTINA yeni indi — orta vadeli "
                        "trend bozuluyor. Klasik ilk çıkış uyarısıdır.", 25)
                else:
                    _al("MA50 altında",
                        "Fiyat bir süredir 50 günlük ortalamanın altında — trend zayıf.", 12)
    if len(c) >= 200:
        ma200 = sma(c, 200)
        if not np.isnan(ma200.iloc[-1]) and son < float(ma200.iloc[-1]):
            _al("MA200 altında",
                "Fiyat 200 günlük ortalamanın altında — uzun vadeli trend AŞAĞI. "
                "Kurumsal yatırımcılar bu seviyeyi ana ayrım çizgisi sayar.", 20)

    # 2) DEATH CROSS (son 1 ay içinde)
    if len(c) > 210:
        s50, s200 = sma(c, 50), sma(c, 200)
        if (not np.isnan(s200.iloc[-1]) and s50.iloc[-1] < s200.iloc[-1]
                and s50.iloc[-21] >= s200.iloc[-21]):
            _al("Death Cross",
                "MA50, MA200'ü AŞAĞI kesti (son 1 ay) — uzun vadeli düşüş sinyali.", 20)

    # 3) ATR ZARAR-KES seviyesi (oynaklığa göre)
    a = atr(df).iloc[-1]
    stop_seviyesi = None
    if not np.isnan(a) and a > 0:
        zirve20 = float(c.tail(20).max())
        stop_seviyesi = round(zirve20 - 2.5 * float(a), 2)
        if son < stop_seviyesi:
            _al("Zarar-kes seviyesi delindi",
                f"Fiyat, son 20 günün zirvesinden 2.5×ATR ({stop_seviyesi:.2f}) "
                "aşağı indi — oynaklığa göre anlamlı bir bozulma.", 25)

    # 4) YENİ DİP — yapı bozulması
    if len(c) >= 66:
        if son <= float(c.tail(66).min()) * 1.001:
            _al("3 aylık yeni dip",
                "Fiyat son 3 ayın en düşük seviyesinde — alıcı yok, düşüş yapısı sürüyor.", 18)

    # 5) YÜKSEK HACİMLİ SATIŞ (dağıtım)
    if len(df) >= 60:
        hacim_oran = float(df["Volume"].tail(5).mean()) / max(float(df["Volume"].tail(60).mean()), 1)
        getiri_5g = 100 * (son / float(c.iloc[-6]) - 1) if len(c) > 6 else 0.0
        if hacim_oran > 1.8 and getiri_5g < -4:
            _al("Yüksek hacimli satış",
                f"Son 5 günde hacim ortalamanın {hacim_oran:.1f} katı ve fiyat "
                f"%{getiri_5g:.1f} düştü — kurumsal çıkış olabilir.", 22)

    # 6) SESSİZ DAĞITIM (fiyat dayanıyor ama para çıkıyor)
    ad = ad_cizgisi(df)
    ad_e, fiyat_e = egim(ad, 40), egim(c, 40)
    if not np.isnan(ad_e) and not np.isnan(fiyat_e) and ad_e < -0.1 and fiyat_e > -0.05:
        _al("Sessiz dağıtım",
            "Fiyat dirençli görünürken A/D çizgisi düşüyor — birileri sessizce "
            "dağıtıyor olabilir. Fiyat genelde bunu gecikmeli takip eder.", 20)

    # 7) MOMENTUM ÇÖKÜŞÜ
    if len(c) > 22:
        ay1 = 100 * (son / float(c.iloc[-22]) - 1)
        if ay1 < -15:
            _al("Sert değer kaybı",
                f"Son 1 ayda %{ay1:.1f} — kayıp hızlanıyor.", 15)

    # 8) ZARAR-KES (kullanıcının kendi alış fiyatına göre)
    zarar_yuzde = None
    if alis_fiyati:
        try:
            zarar_yuzde = 100 * (son / float(alis_fiyati) - 1)
            if zarar_yuzde <= -15:
                _al("Zarar %15'i aştı",
                    f"Alış fiyatına göre %{zarar_yuzde:.1f} zarardasınız. Disiplinli "
                    "risk yönetiminde bu seviye genellikle çıkış noktasıdır.", 25)
            elif zarar_yuzde <= -8:
                _al("Zarar büyüyor",
                    f"Alış fiyatına göre %{zarar_yuzde:.1f} zarardasınız — "
                    "planınızı gözden geçirin.", 12)
        except Exception:
            zarar_yuzde = None

    # ── AŞIRI UZAMA (ŞİŞKİNLİK) RİSKİ ────────────────────────────────────
    # NEDEN EKLENDİ: Bu fonksiyon yalnızca "fiyat DÜŞTÜ mü?" tipi alarmlar
    # üretiyordu. Oysa en sık zarar ettiren durumlardan biri, fiyat HÂLÂ
    # YÜKSELİRKEN ortalamalarından aşırı uzaklaşmasıdır — geri çekilme
    # geldiğinde sert olur. Kullanıcının "önceden düşüş sinyalini de görmek
    # istiyorum" isteğinin eksik kalan yarısı buydu: düşüş başlamadan ÖNCE
    # uyarmak. Bu alarm, fiyat düşmemiş olsa bile tetiklenebilir.
    try:
        _uz = asiri_uzama_skoru(df)
        if _uz["skor"] >= 65:
            _al("Aşırı şişmiş — geri çekilme riski",
                f"Fiyat ortalamalarından çok uzaklaşmış (şişkinlik {_uz['skor']:.0f}/100"
                + (f", MA50'nin %{_uz['ma50_uzaklik']:.0f} üzerinde" if _uz.get("ma50_uzaklik") else "")
                + "). Trend hâlâ yukarı olabilir ama bu mesafeler kalıcı olmaz; "
                  "kâr korumayı (kısmi satış veya takip eden stop) düşünün.", 22)
        elif _uz["skor"] >= 45:
            _al("Gerilmiş fiyat",
                f"Şişkinlik {_uz['skor']:.0f}/100 — fiyat ortalamalarının bir hayli "
                "üzerinde. Yeni alım için uygun bir nokta değil.", 10)
    except Exception:
        pass

    risk = int(np.clip(risk, 0, 100))
    if risk >= 60:
        seviye = "acil"
    elif risk >= 35:
        seviye = "dikkat"
    elif risk >= 15:
        seviye = "izle"
    else:
        seviye = "yok"
    return {"seviye": seviye, "alarmlar": alarmlar, "risk_puani": risk,
            "stop_seviyesi": stop_seviyesi, "zarar_yuzde": zarar_yuzde}


SATIS_SEVIYE_METNI = {
    "acil": ("🔴 ACİL — ÇIKIŞ DÜŞÜN", "#ef4444"),
    "dikkat": ("🟠 DİKKAT — pozisyonu azaltmayı düşün", "#f97316"),
    "izle": ("🟡 İZLE — henüz acil değil", "#eab308"),
    "yok": ("🟢 Satış sinyali yok", "#22c55e"),
}


# ═════════════════════════════════════════════════════════════════════════════
# AŞIRI UZAMA (OVEREXTENSION) ve ERKEN GİRİŞ (EARLY ENTRY) SKORLARI
# ═════════════════════════════════════════════════════════════════════════════
# NEDEN EKLENDİ — ölçülmüş bir hata:
# Kullanıcının tavsiye kayıtları incelendiğinde, verilen tavsiyelerin %91'inin
# ZATEN yükselmiş hisseler olduğu görüldü (son 1 ayda ortalama +%19,7; %24'ü
# son 3 ayda %50+ yükselmiş). Kodda sebebi bulundu: orta_vade()'deki 8 pozitif
# kuralın 8'i de trend takibi; ortalamaya dönüş lehine tek pozitif puan yok.
# Daha kötüsü, HİÇBİR YERDE aşırı uzama cezası yoktu: MA50'nin %2 üstündeki
# hisse ile %33 üstündeki hisse aynı +6 puanı alıyordu. Sentetik testte
# parabolik şişmiş bir hisse (71,5), sağlıklı yükselen hisseden (70,0) DAHA
# YÜKSEK puan aldı.
#
# ÇÖZÜM (tasarım dokümanı §2.1, §4, §48-2 ile uyumlu):
# "Güçlü hisse" ile "iyi giriş noktası" AYRI ölçülür:
#   • asiri_uzama_skoru : 0=sakin, 100=parabolik/şişmiş
#   • erken_giris_skoru : 0=geç kalınmış, 100=hareketin başı → AYRI sütun
#
# ╔════════════════════════════════════════════════════════════════════════╗
# ║  ⚠️  GERÇEK VERİ HİPOTEZİ ÇÜRÜTTÜ — CEZA KAPATILDI (15.08.2026)         ║
# ╠════════════════════════════════════════════════════════════════════════╣
# ║  Başlangıçta şişkinliğe puan CEZASI uygulanıyordu ("şişmiş hisse geri  ║
# ║  çekilir" varsayımı). 539 hisse × 5 yıl × 94.144 puanlama noktası      ║
# ║  üzerinde yapılan backtest bunu ÇÜRÜTTÜ:                                ║
# ║                                                                        ║
# ║    Sıralama gücü : +0,0268 → +0,0218   (ceza ile DAHA KÖTÜ)            ║
# ║    Üst-alt farkı : %+1,41 → %+1,00     (ceza ile DAHA KÖTÜ)            ║
# ║    Şişkinlik ↔ ileri getiri: +0,0496   (POZİTİF! şişmişler daha İYİ)   ║
# ║    En şişkin %20: %+3,52  ·  En sakin %20: %+1,61                      ║
# ║                                                                        ║
# ║  Yani BIST'te (2021-2026) aşırı uzama bir risk değil, momentumun       ║
# ║  DEVAM sinyali olmuş. Dahası şişkinlik (+0,0496), puanlama motorunun   ║
# ║  kendisinden (+0,012) daha güçlü bir öngörücü çıkmış.                  ║
# ║                                                                        ║
# ║  KARAR: Ceza katsayısı 0'a çekildi — yani ceza YOK. Skor hesaplanmaya  ║
# ║  devam ediyor çünkü BİLGİ olarak değerli (tabloda "Şişkinlik" sütunu   ║
# ║  ve risk uyarısı olarak gösteriliyor), ama puanı DÜŞÜRMÜYOR.           ║
# ║                                                                        ║
# ║  NOT: Bulgu tersine çevrilip "şişkinliğe BONUS verelim" denmedi —      ║
# ║  bu, tek bir backtest üzerinde veri madenciliği olurdu. Böyle bir      ║
# ║  değişiklik ancak ayrı bir out-of-sample dönemde doğrulanırsa          ║
# ║  yapılmalıdır. Ayrıca bu 5 yıl BIST'in güçlü momentum dönemini içerir; ║
# ║  farklı bir rejimde sonuç değişebilir.                                 ║
# ╚════════════════════════════════════════════════════════════════════════╝
#
# Cezayı yeniden denemek isterseniz bu katsayıyı büyütüp BACKTEST_CALISTIR.bat
# ile önce/sonra karşılaştırmasını tekrar çalıştırın. Rapor kendi kararını
# yazar; körlemesine değiştirmeyin.
ASIRI_UZAMA_CEZA_KATSAYISI = 0.0     # 0 = ceza yok (backtest kararı)

def asiri_uzama_skoru(df: pd.DataFrame) -> dict:
    """Fiyatın kendi ortalamalarından ne kadar 'şişmiş' olduğunu ölçer.

    Dönüş: {"skor": 0-100, "ceza": puandan düşülecek, "gerekceler": [...],
            "ma50_uzaklik": %, "ma20_uzaklik": %, "hizlanma": %}
    100'e yaklaştıkça geri çekilme riski artar.
    """
    bos = {"skor": 0.0, "ceza": 0.0, "gerekceler": [], "ma50_uzaklik": None,
           "ma20_uzaklik": None, "hizlanma": None}
    if df is None or len(df) < 60:
        return bos

    c = df["Close"]
    son = float(c.iloc[-1])
    skor, gerekceler = 0.0, []

    def uzaklik(n):
        m = sma(c, n).iloc[-1]
        if np.isnan(m) or m <= 0:
            return None
        return 100.0 * (son / float(m) - 1)

    u20, u50 = uzaklik(20), uzaklik(50)

    # 1) MA50'den uzaklık — ana ölçüt. Kademeli, sert eşik yok.
    if u50 is not None and u50 > 10:
        # %10 → 0 puan, %40 → 45 puan (doğrusal, üst sınırlı)
        katki = min(45.0, (u50 - 10) * 1.5)
        skor += katki
        if u50 > 25:
            gerekceler.append(f"Fiyat 50 günlük ortalamanın %{u50:.0f} üzerinde — "
                              "tarihsel olarak bu mesafeler kalıcı olmaz")
        elif u50 > 15:
            gerekceler.append(f"Fiyat MA50'nin %{u50:.0f} üzerinde — bir miktar gerilmiş")

    # 2) MA20'den uzaklık — kısa vadeli gerilme
    if u20 is not None and u20 > 8:
        skor += min(25.0, (u20 - 8) * 1.8)
        if u20 > 15:
            gerekceler.append(f"Fiyat 20 günlük ortalamanın %{u20:.0f} üzerinde — "
                              "kısa vadede aşırı gerilmiş")

    # 3) Parabolik hızlanma: son 20 günün hızı, önceki 60 güne göre kaç kat?
    hizlanma = None
    if len(c) > 85:
        try:
            son20 = abs(float(c.iloc[-1] / c.iloc[-21] - 1)) / 20
            onceki60 = abs(float(c.iloc[-21] / c.iloc[-81] - 1)) / 60
            if onceki60 > 1e-6:
                hizlanma = son20 / onceki60
                if hizlanma > 2.5:
                    skor += min(20.0, (hizlanma - 2.5) * 8)
                    gerekceler.append(
                        f"Yükseliş hızı son 1 ayda {hizlanma:.1f} katına çıkmış — "
                        "parabolik hareket; sert geri dönüş riski taşır")
        except Exception:
            pass

    # 4) Bollinger üst bandının ÜZERİNDE kapanış (istatistiksel uçdeğer)
    try:
        ust, _orta, _alt = bollinger(c)
        if son > float(ust.iloc[-1]):
            skor += 10
            gerekceler.append("Fiyat Bollinger üst bandının dışında — "
                              "istatistiksel olarak uç bölgede")
    except Exception:
        pass

    skor = float(np.clip(skor, 0, 100))
    # Ceza katsayısı backtest sonucuna göre 0'a çekildi (bkz. yukarıdaki
    # kutulu not). Skor yine de hesaplanır ve raporlanır — sadece puanı
    # etkilemez.
    ceza = round(ASIRI_UZAMA_CEZA_KATSAYISI * (skor / 100.0), 2)
    return {"skor": round(skor, 1), "ceza": ceza, "gerekceler": gerekceler,
            "ma50_uzaklik": round(u50, 2) if u50 is not None else None,
            "ma20_uzaklik": round(u20, 2) if u20 is not None else None,
            "hizlanma": round(hizlanma, 2) if hizlanma is not None else None}


def erken_giris_skoru(df: pd.DataFrame, uzama: dict = None) -> dict:
    """'Hareketin başında mıyız, yoksa geç mi kaldık?' sorusunu ölçer.

    Trend gücünden BAĞIMSIZDIR: çok güçlü bir hisse kötü bir giriş noktasında
    olabilir; orta güçte bir hisse mükemmel giriş noktasında olabilir.

    ⚠️ DOĞRULANMAMIŞ — BİLGİ AMAÇLIDIR, PUANI ETKİLEMEZ:
    Bu skorun dayandığı varsayım ("geç girmek kötüdür, şişkinlik düşürücüdür")
    BIST verisinde DOĞRULANMADI. 94.144 noktalık backtestte şişkinlik ile
    ileri getiri arasındaki ilişki POZİTİF çıktı (+0,0496) — yani geç
    görünen girişler ortalamada daha iyi performans göstermiş. Bu yüzden
    skor yalnızca tabloda bilgi olarak gösterilir; genel puana KATILMAZ.
    Kullanmadan önce kendi backtestinizle doğrulayın.

    Dönüş: {"skor": 0-100, "yorum": str, "gerekceler": [...]}
    """
    bos = {"skor": 50.0, "yorum": "değerlendirilemedi", "gerekceler": []}
    if df is None or len(df) < 120:
        return bos

    c = df["Close"]
    son = float(c.iloc[-1])
    p, gerekceler = 50.0, []
    uzama = uzama or asiri_uzama_skoru(df)

    # 1) Şişkinlik doğrudan erken girişin ZIDDIDIR — en ağırlıklı bileşen
    p -= 0.35 * uzama["skor"]
    if uzama["skor"] > 50:
        gerekceler.append("Fiyat ortalamalarından çok uzaklaşmış — giriş için geç")

    # 2) Trend YUKARI ama fiyat MA50'ye yakın/geri çekilmiş → ideal giriş
    try:
        ma50 = float(sma(c, 50).iloc[-1])
        ma200 = float(sma(c, 200).iloc[-1]) if len(c) > 200 else np.nan
        yukselis = son > ma50 and (np.isnan(ma200) or ma50 > ma200)
        u50 = 100 * (son / ma50 - 1) if ma50 > 0 else None
        if yukselis and u50 is not None and -2 <= u50 <= 8:
            p += 18
            gerekceler.append(f"Trend yukarı ve fiyat MA50'ye yakın (%{u50:.0f}) — "
                              "klasik geri çekilme alım bölgesi")
    except Exception:
        pass

    # 3) Taban yapma: uzun süre dar bantta gezinip yeni yeni kıpırdanma
    try:
        pencere = c.tail(60)
        genislik = 100 * (float(pencere.max()) / float(pencere.min()) - 1)
        if genislik < 18:
            p += 12
            gerekceler.append(f"Son 3 ayda dar bantta sıkışmış (%{genislik:.0f}) — "
                              "taban yapıyor olabilir")
    except Exception:
        pass

    # 4) YENİ kırılım (son 5 gün): geç kalınmamış kırılım değerlidir
    try:
        zirve60_onceki = float(c.iloc[-65:-5].max())
        if son > zirve60_onceki and float(c.iloc[-6]) <= zirve60_onceki:
            p += 15
            gerekceler.append("3 aylık zirveyi YENİ kırdı (son 5 gün) — "
                              "hareketin başlangıcı olabilir")
    except Exception:
        pass

    # 5) Zirveden çok uzaktaysa: ucuz ama hareket henüz başlamamış olabilir
    try:
        zirve52 = float(c.tail(252).max())
        uzaklik52 = 100 * (son / zirve52 - 1)
        if uzaklik52 < -35:
            ma50_egim = egim(sma(c, 50).dropna(), 20)
            if not np.isnan(ma50_egim) and ma50_egim > 0:
                p += 10
                gerekceler.append(f"52 haftalık zirvenin %{abs(uzaklik52):.0f} altında "
                                  "AMA MA50 yukarı dönmüş — dipten dönüş adayı")
            else:
                gerekceler.append(f"Zirveden %{abs(uzaklik52):.0f} aşağıda ama henüz "
                                  "dönüş işareti yok — erken")
    except Exception:
        pass

    # 6) Çok yükselmiş olmak erken girişi düşürür (momentum kovalama)
    try:
        if len(c) > 22:
            ay1 = 100 * (son / float(c.iloc[-22]) - 1)
            if ay1 > 25:
                p -= 12
                gerekceler.append(f"Son 1 ayda %{ay1:.0f} yükselmiş — "
                                  "bu noktadan girmek geç kalmak olabilir")
    except Exception:
        pass

    p = float(np.clip(p, 0, 100))
    if p >= 70:
        yorum = "İyi giriş bölgesi"
    elif p >= 55:
        yorum = "Makul giriş"
    elif p >= 40:
        yorum = "Zamanlama ideal değil"
    else:
        yorum = "Geç kalınmış — girmek için uygun değil"
    return {"skor": round(p, 1), "yorum": yorum, "gerekceler": gerekceler}


def tam_analiz(sembol: str, df: pd.DataFrame, temel: dict,
               yabanci_s: pd.Series = None, endeks_df: pd.DataFrame = None,
               etf_df: pd.DataFrame = None, tefas_s: pd.Series = None,
               rejim: dict = None) -> dict:
    """Bir hissenin komple analizi. Tüm puanlar, sinyaller ve karar."""
    baglam = trend_baglami(df)
    kp, ks = kisa_vade(df, baglam)
    op, osig = orta_vade(df, endeks_df)
    up, us = uzun_vade(df, temel)
    tp, ts = takas_analizi(df, temel, yabanci_s)

    fon_var = etf_df is not None or (tefas_s is not None and len(tefas_s) >= 3)
    if fon_var:
        fp, fs = fon_kurumsal_analizi(etf_df, tefas_s)
        w = AGIRLIKLAR_FON
        genel = (w["kisa"] * kp + w["orta"] * op + w["uzun"] * up +
                 w["takas"] * tp + w["fon"] * fp)
    else:
        fp, fs = None, []
        genel = (AGIRLIKLAR["kisa"] * kp + AGIRLIKLAR["orta"] * op +
                 AGIRLIKLAR["uzun"] * up + AGIRLIKLAR["takas"] * tp)

    # ── AŞIRI UZAMA CEZASI ───────────────────────────────────────────────
    # Rejim düzeltmesinden ÖNCE uygulanır: önce hissenin kendi durumu
    # düzeltilir, sonra piyasa geneli. Sıra önemlidir, aksi halde riskli
    # piyasada zaten kısılmış puan bir kez daha kısılırdı.
    uzama = asiri_uzama_skoru(df)
    genel = float(np.clip(genel - uzama["ceza"], 0, 100))
    erken = erken_giris_skoru(df, uzama)

    rejim_d = 0.0
    if rejim is not None:
        genel, rejim_d = rejim_duzeltmesi(genel, rejim["puan"])

    karar, emoji = karar_ver(genel)

    c = df["Close"]
    a = atr(df).iloc[-1]
    son = c.iloc[-1]

    return {
        "sembol": sembol,
        "son_fiyat": float(son),
        "genel_puan": round(genel, 1),
        "karar": karar, "emoji": emoji,
        "puanlar": {**{"Kısa Vade (1-4 hafta)": round(kp, 1),
                       "Orta Vade (1-6 ay)": round(op, 1),
                       "Uzun Vade (6 ay+)": round(up, 1),
                       "Takas / Para Akışı": round(tp, 1)},
                    **({"Fon / Kurumsal": round(fp, 1)} if fp is not None else {})},
        "sinyaller": {**{"Kısa Vade": ks, "Orta Vade": osig,
                         "Uzun Vade": us, "Takas / Para Akışı": ts},
                      **({"Fon / Kurumsal": fs} if fs else {})},
        "rejim_duzeltmesi": rejim_d,
        "trend_yonu": baglam["yon"],
        # ── Tasarım dokümanı §4: "güçlü hisse" ≠ "iyi giriş" ──
        "asiri_uzama": uzama,
        "erken_giris": erken,
        "risk": risk_alarmlari(df),
        "stop_oneri": round(son - 2 * a, 2) if not np.isnan(a) else None,
        "hedef_oneri": round(son + 3 * a, 2) if not np.isnan(a) else None,
        "getiri_1a": round(100 * (son / c.iloc[-22] - 1), 1) if len(c) > 22 else None,
        "getiri_3a": round(100 * (son / c.iloc[-66] - 1), 1) if len(c) > 66 else None,
        "getiri_1y": round(100 * (son / c.iloc[-252] - 1), 1) if len(c) > 252 else None,
    }


def hizli_puan(df: pd.DataFrame, endeks_df: pd.DataFrame = None,
               temel: dict = None, yabanci_s: pd.Series = None,
               rejim: dict = None, ayrinti: bool = False) -> dict:
    """Tarama için hızlı puan.
    Varsayılan (temel/yabanci_s verilmezse): sadece fiyat/hacim verisi kullanır
    (ağ çağrısı yok) — Uzun vade sadece MA200/2yıl trend, Takas sadece hacim
    tabanlı akış göstergeleriyle sınırlı kalır (F/K, PD/DD, gerçek yabancı
    takas oranı YOKTUR).
    `temel` (vk.temel_veriler çıktısı) ve `yabanci_s` (vk.yabanci_orani_gecmisi
    çıktısı) VERİLİRSE, Uzun ve Takas puanları bu gerçek verilerle zenginleşir
    — daha ayrıştırıcı ama ek ağ isteği gerektirir (bkz. app.py'deki opt-in
    'Temel oranları dahil et' seçeneği).

    `rejim` (piyasa_rejimi çıktısı) VERİLİRSE puan, piyasa ortamına göre
    düzeltilir — tam_analiz ile BİREBİR aynı sonucu verir.
    ═══════════════════════════════════════════════════════════════════════════
    NEDEN ÖNEMLİ: Bu parametre eskiden YOKTU. tam_analiz (Hisse Araştır sekmesi)
    rejim düzeltmesi uygularken hizli_puan (tüm tarama tabloları + sanal portföy
    motoru) uygulamıyordu; aynı hisse iki ekranda ~5 puan FARKLI görünüyordu.
    Ayrıca sanal_yatirimci'nin "puanlar zaten rejim düzeltmesini içerir"
    açıklaması gerçeği yansıtmıyordu — riskli piyasada olması gereken koruma
    fiilen çalışmıyordu. Artık çağıranlar rejimi geçirebilir."""
    # Savunma: boş/çok kısa veri geldiğinde IndexError ile çökmek yerine
    # açıkça "veri yok" sonucu döndür. Çağıranların çoğu zaten df.empty
    # kontrolü yapıyor, ancak tek bir eksik kontrol tüm taramayı düşürebildiği
    # için burada da güvence altına alınır. 30 iş günü, MA20/RSI gibi temel
    # göstergelerin anlamlı olması için gereken asgari eşiktir.
    if df is None or df.empty or len(df) < 30 or "Close" not in df.columns:
        return {
            "Puan": None, "Karar": "⚫ VERİ YOK",
            "Kısa": None, "Orta": None, "Uzun": None, "Takas": None,
            "Şişkinlik": None, "Giriş": None,
            "Fiyat": None, "1 Hafta %": None, "1 Ay %": None, "3 Ay %": None,
            "1 Yıl %": None, "Hacim(M₺)": None,
        }
    baglam = trend_baglami(df)
    kp, kp_sinyaller = kisa_vade(df, baglam)
    op, op_sinyaller = orta_vade(df, endeks_df)
    tp, tp_sinyaller = takas_analizi(df, temel or {}, yabanci_s)
    up, up_sinyaller = uzun_vade(df, temel or {})
    genel = (AGIRLIKLAR["kisa"] * kp + AGIRLIKLAR["orta"] * op +
             AGIRLIKLAR["uzun"] * up + AGIRLIKLAR["takas"] * tp)
    # Aşırı uzama cezası — tam_analiz ile AYNI sırada uygulanmalıdır
    # (önce hisse bazlı ceza, sonra piyasa rejimi), yoksa iki ekran farklı
    # puan gösterir. Bu tutarlılık daha önce bir kez bozulmuştu.
    uzama = asiri_uzama_skoru(df)
    genel = float(np.clip(genel - uzama["ceza"], 0, 100))
    erken = erken_giris_skoru(df, uzama)
    if rejim is not None:
        genel, _ = rejim_duzeltmesi(genel, rejim["puan"])
    karar, emoji = karar_ver(genel)
    c = df["Close"]
    sonuc = {
        "Puan": round(genel, 1), "Karar": f"{emoji} {karar}",
        "Kısa": round(kp), "Orta": round(op), "Uzun": round(up), "Takas": round(tp),
        # Yeni sütunlar: "güçlü hisse" ile "iyi giriş" ayrımı (§4)
        "Şişkinlik": round(uzama["skor"]),
        "Giriş": round(erken["skor"]),
        "Fiyat": round(float(c.iloc[-1]), 2),
        # 1 Hafta / 1 Yıl: Pusula'nın hisse detay ekranında "anlık, haftalık,
        # aylık, yıllık değişim" tablosu için eklendi — kullanıcı isteği.
        # ~5 iş günü = 1 hafta, ~252 iş günü = 1 yıl (BIST işlem günleri).
        "1 Hafta %": round(100 * (c.iloc[-1] / c.iloc[-6] - 1), 1) if len(c) > 6 else None,
        "1 Ay %": round(100 * (c.iloc[-1] / c.iloc[-22] - 1), 1) if len(c) > 22 else None,
        "3 Ay %": round(100 * (c.iloc[-1] / c.iloc[-66] - 1), 1) if len(c) > 66 else None,
        "1 Yıl %": round(100 * (c.iloc[-1] / c.iloc[-252] - 1), 1) if len(c) > 252 else None,
        "Hacim(M₺)": round(float((df["Close"] * df["Volume"]).tail(20).mean()) / 1e6, 1),
    }
    # ayrinti=True: iç hesapları da döndür. SADECE backtest gibi toplu
    # işlemler kullanır. NEDEN VAR: backtest daha önce asiri_uzama_skoru ve
    # erken_giris_skoru'nu BİR KEZ DAHA çağırıyordu (hizli_puan zaten
    # hesaplamıştı) — satır başına %13 gereksiz yük demekti. Tablo çizen
    # kodlar bu parametreyi geçmez, dolayısıyla arayüzde fazladan sütun
    # BELİRMEZ.
    if ayrinti:
        sonuc["_uzama"] = uzama
        sonuc["_erken"] = erken
        # Görev #128: "gösterge tek başına vs. trend/hacim teyitli" sorusunu
        # ampirik olarak test edebilmek için, ÖNCEDEN her hesaplandığı halde
        # atılan (kp/op/tp/up'ın ikinci elemanı, kısa_vade vb. içindeki
        # _ekle() çağrılarıyla dolan) sinyal listelerini burada topluyoruz.
        # trend_baglami().yon (yukselis/dusus/yatay) ile birlikte kaydedilirse,
        # backtest_motoru "AL sinyali + yukselis trendi" ile "AL sinyali +
        # dusus/yatay trendi" satırlarını ayrı ayrı gruplayıp getiriyle
        # karşılaştırabilir — YENİ analiz kodu yazmadan, ekstra hesap
        # maliyeti olmadan (sinyaller zaten hesaplanmıştı, sadece atılmıyor).
        sonuc["_sinyaller"] = kp_sinyaller + op_sinyaller + tp_sinyaller + up_sinyaller
        sonuc["_trendYonu"] = baglam.get("yon")
    return sonuc


# ═══════════════════════════════════════════════════════════════════════════
# SEÇİM SKORU — sanal portföyün ALIM kararı için (23.08.2026)
# ═══════════════════════════════════════════════════════════════════════════
# NEDEN AYRI BİR SKOR: Motorun genel puanı (hizli_puan) 20+ göstergenin
# ağırlıklı ortalamasıdır ve 94.144 noktalık backtestte ileri getiriyle
# korelasyonu +0,012 çıktı — pratikte yön öngörmüyor.
#
# 22.732 gözlemlik ayrı bir çalışmada CMF (Chaikin Money Flow) TEK BAŞINA
# tüm sağlamlık testlerini geçti:
#     korelasyon      : +0,0791  (genel puanın ~6 katı)
#     desil monotonluğu: +0,926   (10 desilde düzenli artış)
#     anlamlılık      : p = 0,022
#     N duyarlılığı   : N=3'ten 40'a düzgün azalıyor (gerçek etki imzası)
#     walk-forward    : iki yarıda da pozitif
#     momentumdan bağımsızlık: çift sıralamada 5 momentum grubunun
#                       HEPSİNDE yüksek-CMF, düşük-CMF'yi ~%2,3 geçti
#
# Yani motor işe yarayan bir sinyali (CMF) yaramayanlarla SEYRELTİYORDU.
# Bu fonksiyon o sinyali saf haliyle kullanır.
#
# MA200 FİLTRESİ: Sadece kendi 200 günlük ortalamasının üstündeki hisseler
# aday olur (Antonacci'nin "mutlak momentum" fikri). Ayar setinde %+3,88,
# sınav setinde %+1,72 endeks üstü getirdi.
#
# ⚠️ DÜRÜSTLÜK NOTU: Ayar/sınav farkı (%+3,88 → %+1,72) aşırı uyumun bir
# kısmının hâlâ mevcut olduğunu gösterir. Gerçek beklenti sınav rakamına
# yakın olmalıdır: endeks üstü ~%1-2/ay. Bu, hisse seçmenin endekse göre
# küçük ama pozitif bir katkısıdır — büyük vaat DEĞİLDİR.
# ═══════════════════════════════════════════════════════════════════════════

SECIM_MIN_GECMIS = 210          # MA200 + pay için gereken asgari gün


# ═══════════════════════════════════════════════════════════════════════════
# DİPTEN DÖNÜŞ GÜVENLİK KONTROLÜ — "düşeni kıran hisseler" göstergesi
# ═══════════════════════════════════════════════════════════════════════════
# NEDEN VAR: Dip dönüşü filtresi (bkz. pusula_veri_uret._dip_donusu_satirlari)
# sadece Kısa/Orta/Uzun PUAN farkına bakıyor — bu, "fiyat 2-3 gün toparladı"
# demek, ama bunun GERÇEK bir dönüş mü yoksa düşüşün içindeki bir "ölü kedi
# sıçraması" (dead cat bounce) mı olduğunu ayırt etmiyor.
#
# NEDEN GOLDEN CROSS KULLANILMADI: MA50'nin MA200'ü yukarı kesmesi çok GEÇ
# kalan bir teyittir — bu gösterge özellikle ERKEN/sürpriz dönüşleri
# yakalamak için var; golden cross'u beklemek, o zamana kadar zaten hareketin
# büyük kısmının kaçırılması anlamına gelir ve göstergenin amacını boşa
# çıkarır.
#
# BUNUN YERİNE İKİ KANITLANMIŞ FİLTRE KULLANILDI (bu depoda backtest'le
# doğrulanmış tek şeyler bunlar — bkz. secim_skoru() ve takas_kaynak_avi):
#   1) CMF (para akışı) pozitife DÖNMÜŞ mü — CMF, bu projede tek başına en
#      güçlü öngörü gücüne sahip gösterge (korelasyon ~0.079, genel puanın
#      ~6 katı). Negatiften pozitife dönüş = birikim başlamış olabilir.
#   2) Hacim teyidi — toparlanma DÜŞÜK hacimle mi (güvenilmez, ilgisiz)
#      yoksa ortalamanın belirgin üzerinde hacimle mi (katılım var) oluyor.
# Art arda 3 günlük kapanış şartı da eklendi: TEK günlük sıçramayı "dönüş"
# saymamak için (whipsaw/tuzak riskini azaltır).
#
# ÖNEMLİ: Bu HENÜZ sert bir filtre (eleme) değil — sadece rozet/uyarı olarak
# gösteriliyor. Sandbox'ta ağ erişimi olmadığı için gerçek veriyle
# doğrulanamadı; gerçek sonuçlar birkaç hafta biriktikten sonra backtest'e
# eklenip sert filtreye çevrilip çevrilmeyeceğine KANITLA karar verilecek.
# ═══════════════════════════════════════════════════════════════════════════

def dip_guvenlik_kontrolu(df: pd.DataFrame) -> dict:
    """Dip dönüşü adaylarına ek güvenlik/teyit bilgisi.

    Dönüş: {"cmfDonus": bool|None, "hacimTeyit": bool|None,
            "ardArdaYukselis": bool|None, "guvenliDonus": bool|None,
            "neden": str}
    Veri yetersizse tüm alanlar None ve neden açıklanır — ÇAĞIRAN taraf
    bunu "eleme" olarak değil "bilgi yok" olarak yorumlamalı.
    """
    bos = {"cmfDonus": None, "hacimTeyit": None, "ardArdaYukselis": None,
           "guvenliDonus": None, "neden": "veri yetersiz"}
    if df is None or len(df) < 40:
        return bos
    if not {"High", "Low", "Close", "Volume"}.issubset(getattr(df, "columns", [])):
        return bos
    try:
        c = df["Close"]
        cmf_s = cmf(df, n=20)
        if len(cmf_s.dropna()) < 6:
            return bos
        cmf_son = float(cmf_s.iloc[-1])
        cmf_5g_once = float(cmf_s.iloc[-6])
        cmf_donus = bool(np.isfinite(cmf_son) and np.isfinite(cmf_5g_once)
                          and cmf_son > 0 and cmf_5g_once <= cmf_son - 0.02)

        hacim_oran = float(df["Volume"].tail(5).mean() / max(df["Volume"].tail(60).mean(), 1))
        hacim_teyit = bool(np.isfinite(hacim_oran) and hacim_oran >= 1.15)

        son3 = c.tail(4).values
        ard_arda = bool(len(son3) == 4 and son3[3] > son3[2] > son3[1])

        guvenli = bool(cmf_donus and hacim_teyit and ard_arda)
        parcalar = []
        parcalar.append("para akışı dönüyor" if cmf_donus else "para akışı henüz dönmedi")
        parcalar.append("hacim teyitli" if hacim_teyit else "hacim teyidi yok")
        parcalar.append("art arda yükseliyor" if ard_arda else "tek günlük sıçrama olabilir")
        neden = ", ".join(parcalar)
        return {"cmfDonus": cmf_donus, "hacimTeyit": hacim_teyit,
                "ardArdaYukselis": ard_arda, "guvenliDonus": guvenli,
                "neden": neden}
    except Exception as e:
        return {**bos, "neden": f"hata: {type(e).__name__}"}


def secim_skoru(df: pd.DataFrame) -> dict:
    """Sanal portföyün ALIM seçimi için skor.

    Dönüş: {"skor": float|None, "cmf": float|None, "ma200_ustunde": bool,
            "uygun": bool, "neden": str}
    `uygun=False` ise hisse aday havuzuna ALINMAZ.
    Skor = CMF (yüksek = birikim var). Karşılaştırma kesitseldir: aynı gün
    içindeki diğer hisselerle sıralanır, mutlak bir eşiği yoktur.
    """
    bos = {"skor": None, "cmf": None, "ma200_ustunde": False,
           "uygun": False, "neden": "veri yetersiz"}
    if df is None or len(df) < SECIM_MIN_GECMIS:
        return bos
    if not {"High", "Low", "Close", "Volume"}.issubset(getattr(df, "columns", [])):
        return bos
    try:
        c = pd.to_numeric(df["Close"], errors="coerce")
        son = float(c.iloc[-1])
        if not np.isfinite(son) or son <= 0:
            return bos

        ma200 = float(c.tail(200).mean())
        ustunde = bool(np.isfinite(ma200) and son > ma200)

        deger = float(cmf(df).iloc[-1])
        if not np.isfinite(deger):
            return {**bos, "ma200_ustunde": ustunde, "neden": "CMF hesaplanamadı"}

        if not ustunde:
            return {"skor": None, "cmf": round(deger, 4), "ma200_ustunde": False,
                    "uygun": False,
                    "neden": f"fiyat MA200'ün altında ({son:.2f} < {ma200:.2f})"}
        return {"skor": deger, "cmf": round(deger, 4), "ma200_ustunde": True,
                "uygun": True, "neden": f"CMF {deger:+.3f}, MA200 üstünde"}
    except Exception as e:
        return {**bos, "neden": f"hata: {type(e).__name__}"}
