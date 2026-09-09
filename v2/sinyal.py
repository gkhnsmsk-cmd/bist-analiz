# -*- coding: utf-8 -*-
"""
v2/sinyal.py — Pusula V2 giriş sinyali üretimi (§3).

Tek sorumluluk: bir `tarih` günü için, verilen `evren` içindeki sembollerden
§3.2-3.6'daki BEŞ şartın TAMAMINI (VE mantığı) sağlayan adayları bulmak ve
§3.7'ye göre sıralamak. Ağ çağrısı YOK, dosya okuma YOK — saf fonksiyon.

V1'in en büyük hatası "3 şarttan 2'si yeter" gibi gevşek bir OR mantığıydı;
bu da en çok yükselmiş (artık tepede olan) hisseleri öne çıkarıyordu. V2'de
BEŞ şart da HEPSİ sağlanmalı, özellikle §3.4 aşırı uzama filtresi hiçbir
koşulda atlanamaz — bu filtrenin doğrudan panzehir olduğu hata budur.
"""

from __future__ import annotations

import pandas as pd

# gostergeler()'in ürettiği ve bu modülün okuduğu kolonlar. Biri eksikse o
# sembol değerlendirmeye alınmaz (savunma amaçlı — veri.py çağrılmadan bu
# modül tek başına çalıştırılırsa sessizce yanlış sonuç üretmek yerine
# adayı elemek daha güvenlidir).
_GEREKLI_KOLONLAR = [
    "Open", "High", "Low", "Close", "Volume",
    "EMA20", "EMA50", "MA200", "ATR14", "RSI14",
    "HACIM_ORT20", "HACIM_TL_MEDYAN20", "YUKSEK20", "GETIRI60", "UZAMA",
]

# §3.4 — ZORUNLU aşırı uzama tavanı. Bu sabit hiçbir koşulda gevşetilmez.
_UZAMA_TAVANI = 2.0

# §3.5 — volatilite tavanı.
_ATR_ORAN_TAVANI = 0.06

# §3.2 — göreli güç, evren içinde kesitsel (cross-sectional) yüzdelik eşiği.
_GORELI_GUC_ESIGI = 75.0

# §3.3a — kırılım hacim çarpanı.
_KIRILIM_HACIM_CARPANI = 1.5

# §3.3b — geri çekilmede EMA20'ye yaklaşma toleransı ve RSI bandı.
_GERI_CEKILME_EMA_TOLERANSI = 1.02
_RSI_BANT_ALT = 40.0
_RSI_BANT_UST = 60.0

# §3.6 likidite şartı, "hesaplanan pozisyon büyüklüğü"nü gerektirir; ama bu
# fonksiyonun arayüzü (§11) ozsermaye parametresi ALMAZ. YORUM KARARI: gerçek
# pozisyon boyutu (ve dolayısıyla asıl likidite kısıtı) zaten risk.py'de
# §4 kısıt-2 olarak GERÇEK ozsermaye ile ayrıca uygulanıyor. Burada, sinyal
# aşamasında kabaca elemek için motor.calistir()'in varsayılan sermayesiyle
# (1.000.000 TL, bkz. §11 backtest imzası) tutarlı bir REFERANS sermaye
# kullanılıyor. Bu yalnız bir ön-eleme; nihai/otoriter kontrol risk.py'dedir.
_REFERANS_OZSERMAYE = 1_000_000.0
_RISK_ORANI = 0.01
_STOP_ATR_KATSAYI = 2.5
_LIKIDITE_ORANI = 0.01


def _gecerli_bugun(df: pd.DataFrame, tarih: pd.Timestamp) -> pd.Series | None:
    """`tarih`e kadarki (dahil) veriyi kısıtlar, o güne ait satırı döner.

    Look-ahead yasağı burada uygulanır: tarihten SONRAKİ hiçbir satıra
    bakılmaz. Ayrıca son satırın index'i tam olarak `tarih` değilse (o gün
    için veri yoksa) None döner — böylece eski bir günün verisiyle yanlışlıkla
    "bugünmüş gibi" sinyal üretilmez.
    """
    if df is None or df.empty:
        return None
    for kolon in _GEREKLI_KOLONLAR:
        if kolon not in df.columns:
            return None
    gecmis = df.loc[df.index <= tarih]
    if gecmis.empty or gecmis.index[-1] != tarih:
        return None
    if len(gecmis) < 2:
        return None  # RSI dönüşü için en az bir önceki gün gerekir
    return gecmis


def _rsi_donusu_var_mi(bugun: pd.Series, dun: pd.Series) -> bool:
    """§3.3b: 'RSI(14) 40-60 bandından yukarı dönüş'.

    YORUM KARARI: Şartname bu ifadeyi tam formülize etmiyor. Burada RSI14'ün
    BUGÜN 40-60 bandında olması VE dünkü değerinden YÜKSEK olması (yani bant
    içinde yukarı ivme kazanması) 'dönüş' olarak kabul edildi — RSI'nin
    bandın altından gelip yukarı kesmesi kadar, bant içinde zayıflayıp
    toparlanması da aynı 'geri çekilmeden dönüş' hikayesine uyar.
    """
    rsi_bugun = bugun["RSI14"]
    rsi_dun = dun["RSI14"]
    if pd.isna(rsi_bugun) or pd.isna(rsi_dun):
        return False
    bantta = _RSI_BANT_ALT <= rsi_bugun <= _RSI_BANT_UST
    yukari_ivme = rsi_bugun > rsi_dun
    return bool(bantta and yukari_ivme)


def _kurulum_belirle(bugun: pd.Series, dun: pd.Series) -> str | None:
    """§3.3: kırılım (a) veya geri çekilme (b). İkisi de sağlanmıyorsa None.

    İkisi birden sağlanırsa 'kirilim' tercih edilir (daha güçlü/az öznel bir
    tetik: fiyat+hacim teyitli, geri çekilmedeki 'dönüş' yorumundan daha
    nesnel) — bu bir sıralama tercihi, ikisi de zaten VE mantığındaki diğer
    dört şartla birlikte aday listesine giriyor.
    """
    close = bugun["Close"]
    yuksek20 = bugun["YUKSEK20"]
    hacim = bugun["Volume"]
    hacim_ort20 = bugun["HACIM_ORT20"]
    if (not pd.isna(yuksek20)) and (not pd.isna(hacim_ort20)) and hacim_ort20 > 0:
        kirilim = (close > yuksek20) and (hacim >= _KIRILIM_HACIM_CARPANI * hacim_ort20)
        if kirilim:
            return "kirilim"

    ema20 = bugun["EMA20"]
    low = bugun["Low"]
    openf = bugun["Open"]
    if not pd.isna(ema20):
        yaklasma = low <= ema20 * _GERI_CEKILME_EMA_TOLERANSI
        yesil_mum = close > openf
        if yaklasma and yesil_mum and _rsi_donusu_var_mi(bugun, dun):
            return "geri_cekilme"

    return None


def giris_adaylari(veriler: dict, evren: list[str], tarih) -> list[dict]:
    """§3'e göre giriş adaylarını üretir.

    veriler: {sembol: DataFrame} — veri.gostergeler() uygulanmış olmalı.
    evren: evren.evren_olustur()'dan gelen, o tarihte işlem yapılabilir
           sembol listesi. Göreli güç yüzdeliği (§3.2) TAM OLARAK bu evrene
           göre kesitsel hesaplanır — sabit bir eşik DEĞİL, o günkü evrenin
           GETIRI60 dağılımı içindeki sıra.
    tarih: karar tarihi (pd.Timestamp'e çevrilir). Bu tarihten SONRAKİ hiçbir
           veriye bakılmaz.

    Döner: [{'sembol','kurulum','skor','kapanis','atr','uzama','goreli_guc'}]
    skora göre AZALAN sırada. §3.2-3.6'nın TAMAMINI geçmeyen aday listeye
    GİRMEZ (VE mantığı — herhangi biri eksikse eleme kesin).
    """
    tarih = pd.Timestamp(tarih)

    # 1) Adım: evrendeki her sembol için o günün satırını çıkar (look-ahead
    #    güvenli). Kesitsel göreli güç hesap edebilmek için önce TÜM evrenin
    #    GETIRI60 değerlerini toplamamız gerekiyor — tek bir sembole bakıp
    #    karar veremeyiz, o yüzden bu iki adıma bölünmüş durumda.
    bugunler: dict[str, pd.Series] = {}
    dunler: dict[str, pd.Series] = {}
    for sembol in evren or []:
        df = (veriler or {}).get(sembol)
        gecmis = _gecerli_bugun(df, tarih)
        if gecmis is None:
            continue
        bugunler[sembol] = gecmis.iloc[-1]
        dunler[sembol] = gecmis.iloc[-2]

    if not bugunler:
        return []

    # 2) Kesitsel (cross-sectional) göreli güç yüzdeliği: evren içindeki
    #    GETIRI60 dağılımına göre bu sembolün sırası. rank(pct=True) NaN'leri
    #    otomatik dışlar (o sembol zaten diğer şartlarda da NaN'den elenir).
    getiri60_serisi = pd.Series({s: b["GETIRI60"] for s, b in bugunler.items()})
    yuzdelik_serisi = getiri60_serisi.rank(pct=True, na_option="keep") * 100.0

    adaylar: list[dict] = []
    for sembol, bugun in bugunler.items():
        dun = dunler[sembol]
        kapanis = bugun["Close"]
        ema20 = bugun["EMA20"]
        ema50 = bugun["EMA50"]
        ma200 = bugun["MA200"]
        atr = bugun["ATR14"]

        if any(pd.isna(x) for x in (kapanis, ema20, ema50, ma200, atr)):
            continue
        if atr <= 0:
            continue  # ATR<=0 hem UZAMA hem stop hesaplarını anlamsızlaştırır

        # Şart 1 — Trend: Kapanış > EMA20 > EMA50 > MA200
        if not (kapanis > ema20 > ema50 > ma200):
            continue

        # Şart 2 — Göreli güç: evren içi yüzdelik >= 75
        goreli_guc = yuzdelik_serisi.get(sembol, float("nan"))
        if pd.isna(goreli_guc) or goreli_guc < _GORELI_GUC_ESIGI:
            continue

        # Şart 3 — Kurulum (a: kırılım VEYA b: geri çekilme)
        kurulum = _kurulum_belirle(bugun, dun)
        if kurulum is None:
            continue

        # Şart 4 — AŞIRI UZAMA YOK (ZORUNLU, asla atlanmaz)
        uzama = bugun["UZAMA"]
        if pd.isna(uzama) or uzama > _UZAMA_TAVANI:
            continue
        # Şart 1 zaten Kapanış > EMA20 zorunlu kıldığından uzama > 0 olmalı;
        # negatifse (teorik/veri hatası ihtimali) güvenli tarafta kalıp elenir.
        if uzama <= 0:
            continue

        # Şart 5 — Volatilite tavanı
        if (atr / kapanis) > _ATR_ORAN_TAVANI:
            continue

        # Şart 6 — Likidite (bkz. modül başındaki YORUM KARARI notu):
        # referans sermayeyle hesaplanan pozisyon değeri, 20g medyan TL
        # hacmin %1'ini aşmamalı. Nihai/otoriter kontrol risk.py'dedir.
        hacim_tl_medyan = bugun["HACIM_TL_MEDYAN20"]
        if pd.isna(hacim_tl_medyan) or hacim_tl_medyan <= 0:
            continue
        stop_mesafe = _STOP_ATR_KATSAYI * atr
        risk_tutari_ref = _REFERANS_OZSERMAYE * _RISK_ORANI
        adet_ref = risk_tutari_ref / stop_mesafe
        deger_ref = adet_ref * kapanis
        if deger_ref > _LIKIDITE_ORANI * hacim_tl_medyan:
            continue

        # §3.7 — sıralama skoru: en yüksek skor = en temiz kurulum (en çok
        # yükselmiş değil). uzama 0..2 aralığında olduğundan (1 - uzama/4)
        # her zaman 0.5..1.0 arasında kalır; uzama arttıkça skor cezalanır.
        skor = goreli_guc * (1.0 - uzama / 4.0)

        adaylar.append({
            "sembol": sembol,
            "kurulum": kurulum,
            "skor": float(skor),
            "kapanis": float(kapanis),
            "atr": float(atr),
            "uzama": float(uzama),
            "goreli_guc": float(goreli_guc),
        })

    adaylar.sort(key=lambda a: a["skor"], reverse=True)
    return adaylar


if __name__ == "__main__":
    # Ağ çağrısı / dosya okuma içermeyen kendi kendine kontrol. Sentetik
    # veriyle özellikle §3.4 uzama filtresinin GERÇEKTEN eleme yaptığını
    # doğruluyoruz (V1'in en büyük hatasının panzehiri burada).
    import numpy as np

    tarihler = pd.date_range("2023-01-01", periods=260, freq="B")
    tarih_son = tarihler[-1]

    def _temel_seri(n, baslangic=100.0, egim=0.15, gurultu=0.3, tohum=1):
        rng = np.random.default_rng(tohum)
        egilim = baslangic + np.arange(n) * egim
        return egilim + rng.normal(0, gurultu, n)

    def _df_kur(kapanis: np.ndarray, hacim: np.ndarray) -> pd.DataFrame:
        openf = kapanis - 0.05
        high = np.maximum(kapanis, openf) + 0.1
        low = np.minimum(kapanis, openf) - 0.1
        return pd.DataFrame({
            "Open": openf, "High": high, "Low": low, "Close": kapanis, "Volume": hacim,
        }, index=tarihler)

    from veri import gostergeler  # aynı dizindeki veri.py

    # --- Senaryo A: temiz kırılım kurulumu (tüm şartları sağlamalı) -------
    kapanis_a = _temel_seri(260, baslangic=50.0, egim=0.12, gurultu=0.15, tohum=7)
    # Kırılım günü: son günü belirgin şekilde yukarı sıçrat + hacmi patlat.
    kapanis_a[-1] = kapanis_a[-2] * 1.02
    hacim_a = np.full(260, 2_000_000.0)
    hacim_a[-1] = 6_000_000.0  # 1.5x ortalamanın üstü
    df_a = gostergeler(_df_kur(kapanis_a, hacim_a))

    # --- Senaryo B: Senaryo A ile AYNI temiz trend, ama son günlerde çok
    # sert bir sıçrama ile aşırı uzamış (UZAMA > 2.0 olmalı) -------------
    kapanis_b = kapanis_a.copy()
    kapanis_b[-5:] = kapanis_b[-6] * np.array([1.05, 1.09, 1.14, 1.20, 1.27])
    hacim_b = hacim_a.copy()
    df_b = gostergeler(_df_kur(kapanis_b, hacim_b))

    # --- Doldurucu semboller: kesitsel (cross-sectional) göreli güç
    # yüzdeliğinin anlamlı çalışması için evrende TEMIZ/ASIRI'den daha
    # zayıf performanslı birkaç sembol daha olması gerekir (aksi halde
    # 2 sembollük bir evrende yüzdelik hesabı gerçekçi olmaz).
    dolgu = {}
    for i, tohum in enumerate((11, 12, 13)):
        kapanis_d = _temel_seri(260, baslangic=50.0, egim=0.0, gurultu=0.4, tohum=tohum)
        dolgu[f"DUSUK{i+1}"] = gostergeler(_df_kur(kapanis_d, np.full(260, 2_000_000.0)))

    veriler = {"TEMIZ": df_a, "ASIRI": df_b, **dolgu}
    evren = ["TEMIZ", "ASIRI", *dolgu.keys()]

    sonuc = giris_adaylari(veriler, evren, tarih_son)
    semboller = {a["sembol"] for a in sonuc}

    # (a) Uzama filtresi gerçekten eleme yapıyor mu?
    assert "ASIRI" not in semboller, (
        f"UZAMA > {_UZAMA_TAVANI} olan aday elenmedi — §3.4 filtresi çalışmıyor! sonuc={sonuc}"
    )

    if "TEMIZ" in semboller:
        temiz_aday = next(a for a in sonuc if a["sembol"] == "TEMIZ")
        assert temiz_aday["uzama"] <= _UZAMA_TAVANI

    # Look-ahead kontrolü: tarihten sonraki satırları bozunca sonuç değişmemeli.
    df_a_bozuk = df_a.copy()
    gelecek = pd.date_range(tarih_son + pd.Timedelta(days=1), periods=5, freq="B")
    ek = pd.DataFrame({c: [0.01] * 5 for c in df_a_bozuk.columns}, index=gelecek)
    df_a_bozuk = pd.concat([df_a_bozuk, ek])
    veriler_bozuk = dict(veriler)
    veriler_bozuk["TEMIZ"] = df_a_bozuk
    sonuc_bozuk = giris_adaylari(veriler_bozuk, evren, tarih_son)
    assert {a["sembol"] for a in sonuc_bozuk} == semboller, (
        "Gelecek tarihli veri sonucu değiştirdi — look-ahead riski var"
    )

    # Boş evren / boş veri güvenli şekilde boş liste dönmeli.
    assert giris_adaylari({}, [], tarih_son) == []
    assert giris_adaylari(veriler, [], tarih_son) == []

    print("sinyal.py kendi kendine kontrol: BAŞARILI")
    print("Adaylar:", sonuc)
