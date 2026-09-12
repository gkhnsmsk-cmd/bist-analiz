# -*- coding: utf-8 -*-
"""
v2/v21_secim.py — Dinamik & Defansif BIST Algoritması v2.1 §3 hisse seçimi.

Ağ çağrısı YOK, dosya okuma YOK — saf fonksiyon. Girdi: v2/veri.gostergeler()
+ v2/v21_gosterge.ek_gostergeler() uygulanmış {sembol: DataFrame} sözlüğü.

ŞARTNAME §3 (v2.1) — BİREBİR DEĞİL, AGRESİF REVİZYON UYGULANDI (bkz. aşağıdaki
"REVİZYON" notu):
  A. Temel Sağlık Filtresi (Zombi Koruması) — Cari Oran>1.2, Net Borç/FAVÖK<3.5
     — VERİ YOK (KAP API erişilemiyor). BU FİLTRE ATLANDI — hiçbir sert eleme
     yapılmıyor (aşağıda yalnız kod yorumu olarak not düşülüyor).
  B. Teknik Zorunluluklar (fiili/uygulanan hâli, agresif revizyon sonrası):
     - Fiyat > MA200 (MA50>MA200 şartı KALDIRILDI)
     - Son 20 günlük getiri -%10 ile +%60 arasında (eskiden +%5/+%25)
     - CMF(20) > -0.05 (eskiden > 0)
     - Son 5 günlük ortalama hacim, son 20 günlük ortalamanın en az %80'i
       (eskiden en az %120 — artık bir "premium" değil, "kurumamış olsun" testi)
  C. Ek Teyitler (skor artırıcı, ZORUNLU DEĞİL):
     - BIST100'e göre göreceli güç (RS) pozitif
     - Kurumsal/TEFAS fon payı artışı — VERİ YOK, ATLANDI (yalnız not).

NOT — A ve C'deki "kurumsal/TEFAS" maddesi VERİ YOK gerekçesiyle atlanıyor;
şartname bunu zaten "veri kaynağı yok, atlandı" şeklinde not düşmemizi
istiyor. Sert eleme YAPILMIYOR, yalnızca burada belgeleniyor.

REVİZYON (kullanıcı talebi, 2026-09-12): "yüksek risk olsun, yeter ki para
kazansın." §3.B'nin dört koşulu AYNI ANDA (VE mantığıyla) istemesi ve dar
getiri20 penceresi (yalnız %5-%25) adayları çok daraltıyordu — walk-forward
backtest'te bu, evrenin (~120 hisse x haftalık tarama) neredeyse hiç aday
üretmemesine yol açtı. Şartname sınırlarının DIŞINA çıkılarak eşikler
gevşetildi (bilinçli, agresif yorum):
  - GETIRI20 aralığı %5-%25 -> -%10-%60 (hafif düşüşte dip alımına da izin
    verilir; güçlü/uzamış trendler de artık elenmiyor).
  - Hacim teyidi zorunluluğu (5G>=1.2x20G) kaldırıldı, yalnız hacmin
    KURUMAMIŞ olması (>=%80) yeterli.
  - CMF(20)>0 şartı gevşetildi: CMF(20) > -0.05 (hafif negatif de kabul).
  - MA50>MA200 şartı KALDIRILDI — yalnız fiyat>MA200 (temel uzun vade
    trend filtresi) korundu.
Amaç: aday havuzunu büyütüp sistemin daha sık işlem açmasını sağlamak.
"""

from __future__ import annotations

import pandas as pd

# §3.B eşikleri — AGRESİF revizyon (bkz. modül başı notu), şartnamenin
# birebir verdiği %5-%25 aralığının DIŞINA bilinçli olarak çıkıldı.
_GETIRI20_ALT = -0.10
_GETIRI20_UST = 0.60
_HACIM5_HACIM20_CARPAN = 0.80  # eskiden 1.20 ("en az %20 üzerinde") -> artık yalnız "kurumamış olsun"
_CMF20_ALT = -0.05             # eskiden > 0 idi; hafif negatif para akışı da artık kabul

_GEREKLI_KOLONLAR = [
    "Open", "High", "Low", "Close", "Volume",
    "MA20", "MA50", "MA200", "ATR14", "CMF20",
    "DONCHIAN_UST10", "DONCHIAN_ALT10", "GETIRI20",
    "HACIM_ORT5", "HACIM_ORT20", "HACIM_TL_MEDYAN20",
]

_A_NOTU = ("A. Temel Sağlık Filtresi (Cari Oran>1.2, Net Borç/FAVÖK<3.5) VERİ YOK "
           "(KAP API erişilemiyor) — ATLANDI, sert eleme yapılmadı.")
_C_KURUMSAL_NOTU = ("C. Kurumsal/TEFAS fon payı artışı VERİ YOK — ATLANDI, "
                     "skor artırıcı olarak değerlendirilmedi.")


def _gecerli_bugun(df: pd.DataFrame, tarih: pd.Timestamp) -> pd.Series | None:
    """Look-ahead güvenli: tarihten SONRAKİ hiçbir satıra bakılmaz."""
    if df is None or df.empty:
        return None
    for kolon in _GEREKLI_KOLONLAR:
        if kolon not in df.columns:
            return None
    gecmis = df.loc[df.index <= tarih]
    if gecmis.empty or gecmis.index[-1] != tarih:
        return None
    return gecmis.iloc[-1]


def secim_yap(veriler: dict, evren: list[str], tarih,
              endeks_df: pd.DataFrame | None = None) -> list[dict]:
    """§3'e göre hisse seçim adaylarını üretir.

    veriler: {sembol: DataFrame} — veri.gostergeler() + v21_gosterge.ek_gostergeler()
             uygulanmış olmalı.
    evren: evren.evren_olustur()'dan gelen o tarihte işlem yapılabilir semboller.
    tarih: karar tarihi. Bu tarihten SONRAKİ hiçbir veriye bakılmaz.
    endeks_df: BIST100 (XU100.IS) OHLCV — §3.C göreceli güç (RS) hesabı için
               opsiyonel; verilmezse RS teyidi hesaplanamaz (skor artırıcı,
               zorunlu olmadığından sistem çökmez, yalnız o bonus atlanır).

    Döner: [{'sembol','kapanis','atr','cmf','getiri20','hacim_orani',
             'rs_pozitif','skor'}] — skora göre AZALAN sırada.
    B şartlarının TAMAMINI (VE mantığı) sağlamayan aday listeye GİRMEZ.
    """
    tarih = pd.Timestamp(tarih)

    endeks_getiri20 = None
    if endeks_df is not None and not endeks_df.empty:
        endeks_gecmis = endeks_df.loc[endeks_df.index <= tarih]
        if not endeks_gecmis.empty and endeks_gecmis.index[-1] == tarih and len(endeks_gecmis) > 20:
            endeks_kapanis = endeks_gecmis["Close"]
            endeks_getiri20 = float(endeks_kapanis.iloc[-1] / endeks_kapanis.iloc[-21] - 1.0) \
                if len(endeks_kapanis) > 20 else None

    adaylar: list[dict] = []
    for sembol in evren or []:
        df = (veriler or {}).get(sembol)
        bugun = _gecerli_bugun(df, tarih)
        if bugun is None:
            continue

        kapanis = bugun["Close"]
        ma50 = bugun["MA50"]
        ma200 = bugun["MA200"]
        atr = bugun["ATR14"]
        cmf20 = bugun["CMF20"]
        getiri20 = bugun["GETIRI20"]
        hacim_ort5 = bugun["HACIM_ORT5"]
        hacim_ort20 = bugun["HACIM_ORT20"]

        gerekli_degerler = (kapanis, ma50, ma200, atr, cmf20, getiri20, hacim_ort5, hacim_ort20)
        if any(pd.isna(x) for x in gerekli_degerler):
            continue
        if atr <= 0:
            continue

        # §3.B — Teknik zorunluluklar — AGRESİF revizyon (bkz. modül başı
        # notu): MA50>MA200 şartı kaldırıldı, eşikler gevşetildi.
        if not (kapanis > ma200):
            continue
        if not (_GETIRI20_ALT <= getiri20 <= _GETIRI20_UST):
            continue
        if not (cmf20 > _CMF20_ALT):
            continue
        if hacim_ort20 <= 0 or not (hacim_ort5 >= _HACIM5_HACIM20_CARPAN * hacim_ort20):
            continue

        # §3.C — Ek teyit: göreceli güç (RS) pozitif (skor artırıcı, zorunlu değil).
        rs_pozitif = False
        if endeks_getiri20 is not None:
            rs_pozitif = bool(getiri20 > endeks_getiri20)

        # Skor: getiri20 (temel momentum) + CMF (para akışı gücü) + RS bonus.
        # YORUM KARARI: şartname bir skor formülü VERMİYOR — yalnız RS'nin
        # "skor artırıcı" olduğunu söylüyor. Burada basit/şeffaf bir toplam
        # kuruldu: getiri20 (yüzde puan olarak) + CMF20*10 (CMF -1..1
        # aralığında, ağırlığı küçük tutuldu) + RS pozitifse +5 puan bonus.
        skor = (getiri20 * 100.0) + (cmf20 * 10.0) + (5.0 if rs_pozitif else 0.0)

        adaylar.append({
            "sembol": sembol,
            "kapanis": float(kapanis),
            "atr": float(atr),
            "cmf": float(cmf20),
            "getiri20": float(getiri20),
            "hacim_orani": float(hacim_ort5 / hacim_ort20),
            "rs_pozitif": rs_pozitif,
            "skor": float(skor),
        })

    adaylar.sort(key=lambda a: a["skor"], reverse=True)
    return adaylar


if __name__ == "__main__":
    # Ağ çağrısı içermeyen kendi kendine kontrol.
    import sys
    from pathlib import Path
    import numpy as np

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from veri import gostergeler as _veri_gostergeler
    from v21_gosterge import ek_gostergeler

    tarihler = pd.date_range("2023-01-01", periods=260, freq="B")
    tarih_son = tarihler[-1]

    def _df_kur(kapanis, hacim):
        openf = kapanis - 0.05
        high = np.maximum(kapanis, openf) + 0.1
        low = np.minimum(kapanis, openf) - 0.1
        return pd.DataFrame({"Open": openf, "High": high, "Low": low,
                              "Close": kapanis, "Volume": hacim}, index=tarihler)

    def _hazirla(kapanis, hacim):
        return ek_gostergeler(_veri_gostergeler(_df_kur(kapanis, hacim)))

    # Senaryo A: temiz, tüm B şartlarını sağlayan bir kurulum.
    rng = np.random.default_rng(3)
    taban = 50 + np.cumsum(rng.normal(0.05, 0.2, 260))
    kapanis_a = taban.copy()
    kapanis_a[-20:] = kapanis_a[-21] * (1 + np.linspace(0, 0.12, 20))  # +%12 getiri20
    hacim_a = np.full(260, 2_000_000.0)
    hacim_a[-5:] = 3_000_000.0  # son 5 gün ort > son 20 gün ort * 1.2
    df_a = _hazirla(kapanis_a, hacim_a)

    # Senaryo B: getiri20 aralık dışı (+%90 -> AGRESİF revizyonda bile
    # reddedilmeli; eşik artık %60 üst sınır — bkz. _GETIRI20_UST).
    kapanis_b = taban.copy()
    kapanis_b[-20:] = kapanis_b[-21] * (1 + np.linspace(0, 0.90, 20))
    hacim_b = hacim_a.copy()
    df_b = _hazirla(kapanis_b, hacim_b)

    endeks_kapanis = 5000 + np.cumsum(rng.normal(0.5, 5.0, 260))
    endeks_df = pd.DataFrame({
        "Open": endeks_kapanis, "High": endeks_kapanis * 1.001, "Low": endeks_kapanis * 0.999,
        "Close": endeks_kapanis, "Volume": np.full(260, 1e9),
    }, index=tarihler)

    veriler = {"TEMIZ": df_a, "ASIRI_GETIRI": df_b}
    evren = ["TEMIZ", "ASIRI_GETIRI"]

    sonuc = secim_yap(veriler, evren, tarih_son, endeks_df=endeks_df)
    semboller = {a["sembol"] for a in sonuc}

    assert "ASIRI_GETIRI" not in semboller, (
        f"GETIRI20 aralık dışı (+%90) olan aday elenmedi! sonuc={sonuc}"
    )

    # Look-ahead kontrolü.
    df_a_bozuk = df_a.copy()
    gelecek = pd.date_range(tarih_son + pd.Timedelta(days=1), periods=5, freq="B")
    ek = pd.DataFrame({c: [0.01] * 5 for c in df_a_bozuk.columns}, index=gelecek)
    df_a_bozuk = pd.concat([df_a_bozuk, ek])
    veriler_bozuk = dict(veriler)
    veriler_bozuk["TEMIZ"] = df_a_bozuk
    sonuc_bozuk = secim_yap(veriler_bozuk, evren, tarih_son, endeks_df=endeks_df)
    assert {a["sembol"] for a in sonuc_bozuk} == semboller, (
        "Gelecek tarihli veri sonucu değiştirdi — look-ahead riski var"
    )

    assert secim_yap({}, [], tarih_son) == []

    print("v21_secim.py kendi kendine kontrol: BAŞARILI")
    print("Adaylar:", sonuc)
    print(_A_NOTU)
    print(_C_KURUMSAL_NOTU)
