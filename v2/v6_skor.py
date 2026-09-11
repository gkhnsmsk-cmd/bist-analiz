# -*- coding: utf-8 -*-
"""
v2/v6_skor.py — Pusula V6 YOĞUNLAŞTIRILMIŞ sinyal skoru (§ konsantre yaklaşım).

V2 (10+ pozisyona dağıtılmış swing) ve V3 (10 pozisyonlu aylık momentum
rotasyonu) ikisi de düşük/negatif CAGR verdi — ORTALAMA kalitede sinyalleri
ÇOK SAYIDA pozisyona dağıtmak getiriyi seyreltiyor (bkz. proje notları).
V6'nın cevabı: sinyal kalitesini SERTLEŞTİR (dört sert şart BİRLİKTE
sağlanmalı), aday sayısını doğal olarak azalt, kalan az sayıdaki adaya
v6_portfoy.py'de YÜKSEK ağırlık ver.

Dört sert şart (HEPSİ VE mantığıyla, `uygun` bayrağı bunlara bağlı):
  1) Trend hizalaması : Kapanış > EMA20 VE Kapanış > EMA50 VE Kapanış > MA200
  2) Hacim patlaması   : bugünün hacmi, ÖNCEKİ 20 günün ortalama hacminin
                          (bugün HARİÇ) >= 2 katı
  3) 52 hafta zirvesine yakınlık : Kapanış, son ~252 işlem gününün en yüksek
                          kapanışının >= %95'i
  4) Pozitif mutlak momentum (mom6 > 0) + aşırı oynaklık filtresi
     (ATR14/Kapanış <= %9) — aşırı oynak isimler yüksek ağırlıkla
     alınamayacak kadar risklidir (konsantre portföyde tek isim riski büyür).

Skor: risk-düzeltilmiş 6-1/12-1 momentum (v3_skor.py ile aynı akademik
temel) + hacim patlaması ve zirve yakınlığı için küçük bonus terimler —
sıralama YİNE esas olarak momentumla belirlenir, bonuslar yalnız EŞİT
güçteki adaylar arasında "daha temiz kırılım" olanı öne çıkarır.

Ağ çağrısı YOK, dosya okuma YOK — saf fonksiyon. LOOK-AHEAD YASAĞI:
`tarih`ten SONRAKİ hiçbir satıra bakılmaz (v3_skor.py ile aynı desen:
`gecmis = df.loc[df.index <= tarih]`, tüm pencereler bu kesilmiş seriden
hesaplanır).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────
# Momentum pencereleri — v3_skor.py ile AYNI (akademik "12-1" standardı,
# son 1 ay her iki pencereden de dışlanır).
# ─────────────────────────────────────────────────────────────────────────
_MOM_GECIKME = 21
_MOM6_PENCERE = 126
_MOM12_PENCERE = 252
_VOL_PENCERE = 126
_YIL_ISLEM_GUNU = 252

# ─────────────────────────────────────────────────────────────────────────
# V6'ya özgü sert şart eşikleri.
# ─────────────────────────────────────────────────────────────────────────
_HACIM_PATLAMA_ESIGI = 1.6     # bugünün hacmi >= önceki-20g-ortalamanın 1.6 katı
_ZIRVE_PENCERE = 252           # ~52 hafta işlem günü
_ZIRVE_PENCERE_MIN = 200       # en az bu kadar günlük geçmişle hesaplanabilir
_ZIRVE_YAKINLIK_ESIGI = 0.92   # kapanış, 52 hafta zirvesinin >= %92'sinde
_ATR_ORAN_TAVANI = 0.10        # ATR14/Kapanış bu oranı aşarsa çok oynak

# v6.1 İNCE AYAR (ilk çalıştırma sonucu: test CAGR %19.2 << hedef %55, maksimum
# düşüş %29.0 > hedef %25). Tanı: sinyal dört şartı BİRLİKTE arıyordu ama eşikler
# (2.0x hacim, %95 zirve) o kadar sertti ki aday sayısı çok azaldı — sermaye çoğu
# zaman nakitte/az pozisyonda bekledi (düşük CAGR) VE eldeki az sayıdaki pozisyon
# yine de büyük ağırlıkla (%20-33) açılıp tek isim hareketiyle sert düşüşe
# girebiliyordu (yüksek düşüş). Eşikler hafifçe gevşetildi (1.6x / %92) — daha
# sık, hâlâ seçici, sinyal üretsin diye. Stop/kâr hedefi tarafındaki ayarlar için
# bkz. v6_portfoy.py.

# Likidite ön-eleme (v3_skor.py'deki AYNI YORUM KARARI mantığı, ama
# konsantre portföy N=3-5 pozisyon + tavan ağırlık %33 varsayımıyla):
# referans pozisyon değeri, 20g medyan TL hacmin %1'ini aşarsa aday elenir.
# NİHAİ/OTORİTER likidite kontrolü v6_portfoy.py'de GERÇEK ağırlıkla tekrar
# yapılır (bu yalnız kaba bir ön filtre).
_REFERANS_OZSERMAYE = 1_000_000.0
_REFERANS_MAKS_AGIRLIK = 0.33  # en yüksek beklenen tek-pozisyon ağırlığı
_LIKIDITE_ORANI = 0.01

_GEREKLI_KOLONLAR = ["Close", "EMA20", "EMA50", "MA200", "ATR14",
                     "HACIM_ORT20", "HACIM_TL_MEDYAN20", "Volume"]


def _bugun_satiri(df: pd.DataFrame | None, tarih: pd.Timestamp) -> pd.DataFrame | None:
    """`tarih`e kadarki veriyi kısıtlar; tam o güne ait satır yoksa None döner."""
    if df is None or df.empty:
        return None
    gecmis = df.loc[df.index <= tarih]
    if gecmis.empty or gecmis.index[-1] != tarih:
        return None
    return gecmis


def skorla(veriler: dict, evren: list[str], tarih) -> list[dict]:
    """V6 yoğunlaştırılmış skor + dört sert şartı uygular.

    veriler: {sembol: DataFrame} — veri.gostergeler() uygulanmış olmalı.
    evren: evren.evren_olustur() çıktısı, o tarihte işlem yapılabilir semboller.
    tarih: karar tarihi. SONRASINDAKİ hiçbir veriye bakılmaz.

    Döner: [{'sembol','skor','mom6','mom12','hacim_orani','zirve_oran',
             'atr_oran','uygun','red_nedeni'}] — skora göre AZALAN sırada.
    """
    tarih = pd.Timestamp(tarih)
    sonuclar: list[dict] = []

    for sembol in evren or []:
        df = (veriler or {}).get(sembol)
        gecmis = _bugun_satiri(df, tarih)
        if gecmis is None:
            continue
        eksik_kolon = False
        for kolon in _GEREKLI_KOLONLAR:
            if kolon not in gecmis.columns:
                eksik_kolon = True
                break
        if eksik_kolon:
            continue

        close = gecmis["Close"]
        if len(close) < _MOM12_PENCERE:
            continue  # 12 aylık geçmiş yok -> skor/zirve güvenilir hesaplanamaz

        kapanis_gecikmeli = close.iloc[-_MOM_GECIKME]
        kapanis_6ay = close.iloc[-_MOM6_PENCERE]
        kapanis_12ay = close.iloc[-_MOM12_PENCERE]
        if (pd.isna(kapanis_gecikmeli) or pd.isna(kapanis_6ay) or pd.isna(kapanis_12ay)
                or kapanis_6ay <= 0 or kapanis_12ay <= 0):
            continue

        mom6 = float(kapanis_gecikmeli / kapanis_6ay - 1.0)
        mom12 = float(kapanis_gecikmeli / kapanis_12ay - 1.0)

        gunluk_getiri = close.pct_change().iloc[-_VOL_PENCERE:]
        if len(gunluk_getiri.dropna()) < _VOL_PENCERE // 2:
            continue
        vol_yillik = float(gunluk_getiri.std() * np.sqrt(_YIL_ISLEM_GUNU))
        if pd.isna(vol_yillik) or vol_yillik <= 0:
            continue

        bugun = gecmis.iloc[-1]
        kapanis_bugun = float(bugun["Close"])
        ema20_bugun = bugun["EMA20"]
        ema50_bugun = bugun["EMA50"]
        ma200_bugun = bugun["MA200"]
        atr_bugun = bugun["ATR14"]
        hacim_medyan = bugun["HACIM_TL_MEDYAN20"]
        hacim_bugun = bugun["Volume"]

        # 1) Trend hizalaması: kapanış üç ortalamanın da üstünde.
        if pd.isna(ema20_bugun) or pd.isna(ema50_bugun) or pd.isna(ma200_bugun):
            trend_hizali = False
        else:
            trend_hizali = (kapanis_bugun > ema20_bugun
                             and kapanis_bugun > ema50_bugun
                             and kapanis_bugun > ma200_bugun)

        # 2) Hacim patlaması: bugünün hacmi, ÖNCEKİ 20 günün (bugün hariç,
        #    shift(1) ile) ortalamasının >= 2 katı. HACIM_ORT20 zaten
        #    veri.gostergeler()'de bugünü DAHİL eden 20g ortalama; shift(1)
        #    ile "dünkü" değeri (yani bugünü içermeyen önceki pencere)
        #    referans alınır — aksi halde bugünün kendi hacmi, karşılaştırma
        #    ölçütünü de şişirip oranı yapay biçimde küçültür.
        hacim_ort20_onceki = gecmis["HACIM_ORT20"].shift(1).iloc[-1]
        if pd.isna(hacim_ort20_onceki) or hacim_ort20_onceki <= 0 or pd.isna(hacim_bugun):
            hacim_orani = float("nan")
            patlama = False
        else:
            hacim_orani = float(hacim_bugun / hacim_ort20_onceki)
            patlama = hacim_orani >= _HACIM_PATLAMA_ESIGI

        # 3) 52 hafta zirvesine yakınlık — yalnız GEÇMİŞE (gecmis, tarih'e
        #    kadar kesilmiş) bakan bir rolling max; look-ahead riski yok.
        if len(close) >= _ZIRVE_PENCERE_MIN:
            zirve_252 = close.rolling(_ZIRVE_PENCERE, min_periods=_ZIRVE_PENCERE_MIN).max().iloc[-1]
        else:
            zirve_252 = float("nan")
        if pd.isna(zirve_252) or zirve_252 <= 0:
            zirve_oran = float("nan")
            zirveye_yakin = False
        else:
            zirve_oran = float(kapanis_bugun / zirve_252)
            zirveye_yakin = zirve_oran >= _ZIRVE_YAKINLIK_ESIGI

        atr_oran = float(atr_bugun / kapanis_bugun) if (not pd.isna(atr_bugun) and kapanis_bugun) else float("nan")

        # ── §4-benzeri uygunluk zinciri — İLK tetiklenen red nedeni. ────────
        red_nedeni: str | None = None
        if not trend_hizali:
            red_nedeni = "Kapanış EMA20/EMA50/MA200 üçünün de üstünde değil (trend hizası yok)."
        elif mom6 <= 0:
            red_nedeni = f"mom6 pozitif değil (mom6={mom6:.4f}) — mutlak momentum şartı sağlanmıyor."
        elif not patlama:
            hacim_metni = f"{hacim_orani:.2f}x" if not pd.isna(hacim_orani) else "hesaplanamadı"
            red_nedeni = (f"Hacim patlaması yok (oran={hacim_metni}, eşik="
                          f"{_HACIM_PATLAMA_ESIGI:.1f}x).")
        elif not zirveye_yakin:
            zirve_metni = f"%{zirve_oran * 100:.1f}" if not pd.isna(zirve_oran) else "hesaplanamadı"
            red_nedeni = (f"52 hafta zirvesine yeterince yakın değil ({zirve_metni}, eşik "
                          f"%{_ZIRVE_YAKINLIK_ESIGI * 100:.0f}).")
        elif pd.isna(atr_oran) or atr_oran > _ATR_ORAN_TAVANI:
            atr_metni = f"{atr_oran:.4f}" if not pd.isna(atr_oran) else "hesaplanamadı"
            red_nedeni = f"ATR14/Kapanış çok yüksek ({atr_metni} > {_ATR_ORAN_TAVANI}) — aşırı oynak."
        elif pd.isna(hacim_medyan) or hacim_medyan <= 0:
            red_nedeni = "20g medyan TL hacim bilgisi eksik/geçersiz — likidite değerlendirilemedi."
        else:
            deger_ref = _REFERANS_OZSERMAYE * _REFERANS_MAKS_AGIRLIK
            if deger_ref > _LIKIDITE_ORANI * hacim_medyan:
                red_nedeni = ("Beklenen konsantre pozisyon değeri 20g medyan TL hacmin %1'ini "
                              "aşıyor — likidite riski (kaba ön-eleme; nihai kontrol "
                              "v6_portfoy.py'de gerçek ağırlıkla yapılır).")

        # ── Skor: risk-düzeltilmiş momentum + küçük bonus terimler. ─────────
        ham_mom = 0.6 * mom6 + 0.4 * mom12
        skor = ham_mom / vol_yillik
        if not pd.isna(hacim_orani):
            skor += 0.15 * min(hacim_orani, 5.0)
        if not pd.isna(zirve_oran):
            skor += 0.10 * zirve_oran

        sonuclar.append({
            "sembol": sembol,
            "skor": float(skor),
            "mom6": mom6,
            "mom12": mom12,
            "hacim_orani": hacim_orani,
            "zirve_oran": zirve_oran,
            "atr_oran": atr_oran,
            "uygun": red_nedeni is None,
            "red_nedeni": red_nedeni,
        })

    sonuclar.sort(key=lambda s: s["skor"], reverse=True)
    return sonuclar


if __name__ == "__main__":
    # Ağ çağrısı / dosya okuma içermeyen kendi kendine kontrol.
    import sys
    from pathlib import Path

    _V2_DIR = Path(__file__).resolve().parent
    if str(_V2_DIR) not in sys.path:
        sys.path.insert(0, str(_V2_DIR))
    import veri  # aynı dizindeki veri.py

    n_gun = 320
    tarihler = pd.date_range("2023-01-02", periods=n_gun, freq="B")
    tarih_son = tarihler[-1]

    def _df_kur(kapanis: np.ndarray, hacim: np.ndarray) -> pd.DataFrame:
        openf = kapanis - 0.05
        high = np.maximum(kapanis, openf) + 0.1
        low = np.minimum(kapanis, openf) - 0.1
        return pd.DataFrame({
            "Open": openf, "High": high, "Low": low, "Close": kapanis, "Volume": hacim,
        }, index=tarihler)

    # --- Senaryo KIRILIM: güçlü istikrarlı yükseliş + son günde hacim
    # patlaması + 52 hafta zirvesine yakın -> TÜM şartları geçmeli. ---------
    rng = np.random.default_rng(7)
    guclu = 50.0 + np.arange(n_gun) * 0.18 + rng.normal(0, 0.2, n_gun)
    hacim_kirilim = np.full(n_gun, 5_000_000.0)
    hacim_kirilim[-1] = 15_000_000.0  # bugün 3x patlama
    df_kirilim = veri.gostergeler(_df_kur(guclu, hacim_kirilim))

    # --- Senaryo SAKİN: aynı yükseliş ama hacim patlaması YOK -> yalnızca
    # hacim şartı yüzünden elenmeli (diğer üç şart sağlanıyor). ------------
    df_sakin = veri.gostergeler(_df_kur(guclu.copy(), np.full(n_gun, 5_000_000.0)))

    # --- Senaryo ZAYIF: düşüş trendi -> trend hizası ve mom6 şartlarından
    # elenmeli. --------------------------------------------------------------
    rng2 = np.random.default_rng(9)
    zayif = 80.0 - np.arange(n_gun) * 0.04 + rng2.normal(0, 0.3, n_gun)
    zayif = np.maximum(zayif, 5.0)
    df_zayif = veri.gostergeler(_df_kur(zayif, np.full(n_gun, 5_000_000.0)))

    veriler = {"KIRILIM": df_kirilim, "SAKIN": df_sakin, "ZAYIF": df_zayif}
    evren = list(veriler.keys())

    sonuc = skorla(veriler, evren, tarih_son)
    harita = {s["sembol"]: s for s in sonuc}

    assert set(harita.keys()) == set(evren), f"Beklenmeyen sembol kümesi: {harita.keys()}"
    assert harita["KIRILIM"]["uygun"] is True, harita["KIRILIM"]
    assert harita["SAKIN"]["uygun"] is False, harita["SAKIN"]
    assert "patlama" in harita["SAKIN"]["red_nedeni"].lower() or "hacim" in harita["SAKIN"]["red_nedeni"].lower(), harita["SAKIN"]
    assert harita["ZAYIF"]["uygun"] is False, harita["ZAYIF"]

    skorlar = [s["skor"] for s in sonuc]
    assert skorlar == sorted(skorlar, reverse=True), "Sıralama azalan değil"
    assert sonuc[0]["sembol"] == "KIRILIM", sonuc

    # ── Look-ahead kontrolü. ─────────────────────────────────────────────
    df_kirilim_bozuk = df_kirilim.copy()
    gelecek_tarihler = pd.date_range(tarih_son + pd.Timedelta(days=1), periods=10, freq="B")
    ek = pd.DataFrame({c: [0.01] * 10 for c in df_kirilim_bozuk.columns}, index=gelecek_tarihler)
    df_kirilim_bozuk = pd.concat([df_kirilim_bozuk, ek])
    veriler_bozuk = dict(veriler)
    veriler_bozuk["KIRILIM"] = df_kirilim_bozuk
    sonuc_bozuk = skorla(veriler_bozuk, evren, tarih_son)
    harita_bozuk = {s["sembol"]: s for s in sonuc_bozuk}
    assert abs(harita_bozuk["KIRILIM"]["skor"] - harita["KIRILIM"]["skor"]) < 1e-9, (
        "Gelecek tarihli veri skoru değiştirdi — look-ahead riski var"
    )

    assert skorla({}, [], tarih_son) == []
    assert skorla(veriler, [], tarih_son) == []

    print("v6_skor.py kendi kendine kontrol: BAŞARILI")
    for s in sonuc:
        print(f"  {s['sembol']}: skor={s['skor']:.3f} uygun={s['uygun']} "
              f"hacim_orani={s['hacim_orani']} zirve_oran={s['zirve_oran']} "
              f"red_nedeni={s['red_nedeni']}")
