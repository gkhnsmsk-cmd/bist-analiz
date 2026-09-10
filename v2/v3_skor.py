# -*- coding: utf-8 -*-
"""
v2/v3_skor.py — Pusula V3 göreli güç skoru + uygunluk filtreleri (§3, §4).

Tek sorumluluk: bir `tarih` günü için, verilen `evren` içindeki her sembol
için risk-düzeltilmiş 12-1/6-1 momentum skorunu hesaplamak ve §4'teki DÖRT
uygunluk şartının hepsini (VE mantığı) kontrol etmek. Ağ çağrısı YOK, dosya
okuma YOK — saf fonksiyon; `veri.gostergeler()` uygulanmış DataFrame'leri
girdi olarak alır (Close/MA200/ATR14/HACIM_TL_MEDYAN20 kolonlarını yeniden
kullanır, kendi kolon üretmez).

LOOK-AHEAD YASAĞI: `tarih`ten SONRAKİ hiçbir satıra bakılmaz. Momentum
pencereleri son 1 ayı (yaklaşık 21 işlem günü) BİLEREK dışlar (bkz. §3'teki
"12-1" notu) — bu bir look-ahead önlemi değil, akademik bir tasarım kararı;
21 günlük gecikme yine de tamamen `tarih`e kadarki geçmişten hesaplanır.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────
# §3 — Momentum pencereleri (işlem günü cinsinden, yaklaşık takvim karşılığı
# parantez içinde). Son 1 ay (21 gün) HER İKİ pencereden de dışlanır —
# short-term reversal etkisini bastırmak için akademik "12-1" standardı.
# ─────────────────────────────────────────────────────────────────────────
_MOM_GECIKME = 21     # ~1 ay — son 1 ay dışlanıyor
_MOM6_PENCERE = 126   # ~6 ay
_MOM12_PENCERE = 252  # ~12 ay

# YORUM KARARI — "yıllık volatilite" penceresi: şartname §3 bu pencereyi
# sayıca belirtmiyor. mom6 ile aynı 126 günlük (6 aylık) pencere seçildi:
# hem momentum sinyaliyle aynı zaman ufkunda kalır (tutarlılık) hem de 252
# günden daha responsive'dir (rejim/volatilite değişimini daha çabuk yakalar)
# ama 21-30 günlük kısa pencerelerden daha az gürültülüdür. Günlük getirilerin
# std sapması yıllıklandırılırken standart sqrt(252) çarpanı kullanılır.
_VOL_PENCERE = 126
_YIL_ISLEM_GUNU = 252

# §4 uygunluk filtreleri — sabitler şartnameyle birebir.
_ATR_ORAN_TAVANI = 0.08

# §4 madde 4 (pozisyon değeri <= 20g medyan TL hacmin %1'i) bu aşamada
# GERÇEK pozisyon büyüklüğünü bilmiyoruz (o, v3_portfoy.hedef_portfoy'daki
# ters-volatilite ağırlıklandırmasından SONRA belli olur). YORUM KARARI:
# v2/sinyal.py'deki ile aynı desen izlenir — burada YAKLAŞIK bir ön-eleme
# yapılır (referans özsermaye + eşit ağırlık varsayımı, en fazla 10
# pozisyon olduğu için %10 varsayılan pay); NİHAİ/OTORİTER likidite kontrolü
# v3_portfoy.hedef_portfoy()'da GERÇEK ağırlıkla tekrar yapılır. Bu sayede
# burada "uygun=False" görünen ama gerçekte likit olan bir hisse (örn. daha
# küçük ağırlıkla alınacaksa) portföy aşamasında yine değerlendirilebilir
# hale gelmiyor — bilerek MUHAFAZAKAR bir ön filtre: portföy inşası
# aşamasında zaten "uygun=True" olanlar arasından seçim yapılacağından, bu
# ön-elemenin gereğinden sıkı olması (gerçek ağırlık daha düşük çıkacak
# olsa bile) sistemin likidite riskini ABARTIP daha fazla adayı elemesine
# yol açar — ki bu, "az ama likit" tarafında hata yapmak, "fazla ama
# likidite riskli" tarafında hata yapmaktan daha güvenlidir.
_REFERANS_OZSERMAYE = 1_000_000.0
_MAKS_POZISYON = 10
_LIKIDITE_ORANI = 0.01

_GEREKLI_KOLONLAR = ["Close", "MA200", "ATR14", "HACIM_TL_MEDYAN20"]


def _bugun_satiri(df: pd.DataFrame, tarih: pd.Timestamp) -> pd.Series | None:
    """`tarih`e kadarki veriyi kısıtlar, tam o güne ait satırı döner.

    Son satırın index'i tam olarak `tarih` değilse (o gün için veri yoksa)
    None döner — eski bir günün verisiyle "bugünmüş gibi" işlem yapılmasını
    engeller (look-ahead'in tersi bir hata, ama aynı kökten: tarih hizası).
    """
    if df is None or df.empty:
        return None
    gecmis = df.loc[df.index <= tarih]
    if gecmis.empty or gecmis.index[-1] != tarih:
        return None
    return gecmis


def skorla(veriler: dict, evren: list[str], tarih) -> list[dict]:
    """§3 göreli güç skoru + §4 uygunluk filtrelerini uygular.

    veriler: {sembol: DataFrame} — veri.gostergeler() uygulanmış olmalı
             (en az Close/MA200/ATR14/HACIM_TL_MEDYAN20 kolonları gerekir).
    evren: evren.evren_olustur()'dan gelen, o tarihte işlem yapılabilir
           sembol listesi.
    tarih: karar tarihi (pd.Timestamp'e çevrilir). Bu tarihten SONRAKİ hiçbir
           veriye bakılmaz.

    Döner: [{'sembol','skor','mom6','mom12','vol','uygun': bool,
             'red_nedeni'}] — skora göre AZALAN sırada.

    Skoru hesaplanamayan (12 aylık geçmişi olmayan / volatilitesi
    tanımsız-sıfır olan) semboller listeye HİÇ GİRMEZ — sıralanabilir bir
    skoru olmayan bir aday, "uygun=False, skor=NaN" olarak listede tutulsa
    bile anlamlı bir sıralama konumuna sahip olamaz; bu yüzden en baştan
    dışlanır (evren.evren_olustur() zaten benzer bir "yetersiz geçmiş"
    mantığı uyguluyor, burada da aynı disiplin sürdürülür).
    """
    tarih = pd.Timestamp(tarih)
    sonuclar: list[dict] = []

    for sembol in evren or []:
        df = (veriler or {}).get(sembol)
        gecmis = _bugun_satiri(df, tarih)
        if gecmis is None:
            continue
        for kolon in _GEREKLI_KOLONLAR:
            if kolon not in gecmis.columns:
                gecmis = None
                break
        if gecmis is None:
            continue

        close = gecmis["Close"]
        if len(close) < _MOM12_PENCERE:
            continue  # 12 aylık geçmiş yok -> skor tanımsız, tamamen dışla

        # NOT indeksleme: şartname §3'teki "Kapanış[-21]" gösterimi, dizinin
        # SONUNDAN sayılan pozisyonu (pandas/numpy negatif indeks kuralı)
        # birebir ifade eder -> close.iloc[-21]. Ekstra bir "+1" kayması
        # EKLENMEZ (bu, formülü şartnamede yazılandan 1 gün kaydırırdı).
        kapanis_gecikmeli = close.iloc[-_MOM_GECIKME]
        kapanis_6ay = close.iloc[-_MOM6_PENCERE]
        kapanis_12ay = close.iloc[-_MOM12_PENCERE]
        if (pd.isna(kapanis_gecikmeli) or pd.isna(kapanis_6ay) or pd.isna(kapanis_12ay)
                or kapanis_6ay <= 0 or kapanis_12ay <= 0):
            continue

        mom6 = float(kapanis_gecikmeli / kapanis_6ay - 1.0)
        mom12 = float(kapanis_gecikmeli / kapanis_12ay - 1.0)
        ham = 0.5 * mom6 + 0.5 * mom12

        # Yıllık volatilite: son _VOL_PENCERE günün günlük getiri std sapması,
        # sqrt(252) ile yıllıklandırılır (bugüne kadar — look-ahead güvenli).
        gunluk_getiri = close.pct_change().iloc[-_VOL_PENCERE:]
        if len(gunluk_getiri.dropna()) < _VOL_PENCERE // 2:
            continue  # volatilite güvenilir hesaplanamayacak kadar az veri
        vol_yillik = float(gunluk_getiri.std() * np.sqrt(_YIL_ISLEM_GUNU))
        if pd.isna(vol_yillik) or vol_yillik <= 0:
            continue  # sıfır volatilite (donuk/hatalı veri) -> bölme tanımsız

        skor = ham / vol_yillik

        bugun = gecmis.iloc[-1]
        kapanis_bugun = bugun["Close"]
        ma200_bugun = bugun["MA200"]
        atr_bugun = bugun["ATR14"]
        hacim_medyan = bugun["HACIM_TL_MEDYAN20"]

        # §4 uygunluk filtreleri — İLK tetiklenen red nedeni kaydedilir
        # (hepsi zorunlu olduğundan sıra önemli değil, yalnız okunabilirlik
        # için tek/net bir mesaj tercih edildi — pozisyon.py'deki
        # portfoy_kisit_kontrol ile aynı "ilk ihlal kazanır" deseni).
        red_nedeni: str | None = None

        if pd.isna(ma200_bugun) or pd.isna(kapanis_bugun) or kapanis_bugun <= ma200_bugun:
            red_nedeni = "Kapanış MA200'ün altında/eşit (uzun vadeli trend yukarı değil)."
        elif mom6 <= 0:
            red_nedeni = f"mom6 pozitif değil (mom6={mom6:.4f}) — mutlak momentum şartı sağlanmıyor."
        elif pd.isna(atr_bugun) or atr_bugun <= 0 or (atr_bugun / kapanis_bugun) > _ATR_ORAN_TAVANI:
            atr_oran = (atr_bugun / kapanis_bugun) if (not pd.isna(atr_bugun) and kapanis_bugun) else float("nan")
            red_nedeni = f"ATR14/Kapanış çok yüksek ({atr_oran:.4f} > {_ATR_ORAN_TAVANI}) — aşırı oynak."
        else:
            if pd.isna(hacim_medyan) or hacim_medyan <= 0:
                red_nedeni = "20g medyan TL hacim bilgisi eksik/geçersiz — likidite değerlendirilemedi."
            else:
                # Yaklaşık pozisyon değeri: referans özsermaye eşit ağırlıkla
                # (1/MAKS_POZISYON) bölüştürülmüş varsayımıyla (bkz. modül
                # başındaki YORUM KARARI notu).
                deger_ref = (_REFERANS_OZSERMAYE / _MAKS_POZISYON)
                if deger_ref > _LIKIDITE_ORANI * hacim_medyan:
                    red_nedeni = ("Referans pozisyon değeri 20g medyan TL hacmin %1'ini "
                                  "aşıyor — likidite riski (yaklaşık ön-eleme, nihai kontrol "
                                  "v3_portfoy.hedef_portfoy()'da gerçek ağırlıkla yapılır).")

        sonuclar.append({
            "sembol": sembol,
            "skor": float(skor),
            "mom6": mom6,
            "mom12": mom12,
            "vol": vol_yillik,
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

    n_gun = 300
    tarihler = pd.date_range("2023-01-02", periods=n_gun, freq="B")
    tarih_son = tarihler[-1]

    def _df_kur(kapanis: np.ndarray, hacim: float = 5_000_000.0) -> pd.DataFrame:
        openf = kapanis - 0.05
        high = np.maximum(kapanis, openf) + 0.1
        low = np.minimum(kapanis, openf) - 0.1
        return pd.DataFrame({
            "Open": openf, "High": high, "Low": low, "Close": kapanis,
            "Volume": np.full(len(kapanis), hacim),
        }, index=tarihler)

    # --- Senaryo A: GÜÇLÜ, düşük volatiliteli istikrarlı yükseliş -> yüksek
    # skorlu VE tüm §4 şartlarını geçen "temiz" bir aday. ----------------
    rng = np.random.default_rng(3)
    guclu = 50.0 + np.arange(n_gun) * 0.15 + rng.normal(0, 0.2, n_gun)
    df_guclu = veri.gostergeler(_df_kur(guclu))

    # --- Senaryo B: yatay/düşüş -> MA200 altında kalır, mom6<=0 -> elenir.
    rng2 = np.random.default_rng(4)
    zayif = 80.0 - np.arange(n_gun) * 0.05 + rng2.normal(0, 0.3, n_gun)
    zayif = np.maximum(zayif, 5.0)
    df_zayif = veri.gostergeler(_df_kur(zayif))

    # --- Senaryo C: çok yüksek günlük oynaklık (ATR/Kapanış > %8) -> elenir,
    # ama genel eğilim yine de yukarı (MA200 üstü, mom6>0) olsun ki YALNIZ
    # volatilite filtresi izole test edilsin. ----------------------------
    rng3 = np.random.default_rng(5)
    oynak = 50.0 + np.arange(n_gun) * 0.15 + rng3.normal(0, 10.0, n_gun)
    oynak = np.maximum(oynak, 5.0)
    df_oynak = veri.gostergeler(_df_kur(oynak))

    veriler = {"GUCLU": df_guclu, "ZAYIF": df_zayif, "OYNAK": df_oynak}
    evren = list(veriler.keys())

    sonuc = skorla(veriler, evren, tarih_son)
    harita = {s["sembol"]: s for s in sonuc}

    assert set(harita.keys()) == set(evren), f"Beklenmeyen sembol kümesi: {harita.keys()}"
    assert harita["GUCLU"]["uygun"] is True, harita["GUCLU"]
    assert harita["ZAYIF"]["uygun"] is False, harita["ZAYIF"]
    assert harita["OYNAK"]["uygun"] is False, harita["OYNAK"]

    # Skora göre azalan sıralama kontrolü.
    skorlar = [s["skor"] for s in sonuc]
    assert skorlar == sorted(skorlar, reverse=True), "Sıralama azalan değil"

    # GUCLU'nun skoru en yüksek olmalı (düşük vol + pozitif momentum).
    assert sonuc[0]["sembol"] == "GUCLU", sonuc

    # mom6/mom12 formülü, son 1 ayı (21 gün) dışlıyor mu? Elle doğrula.
    close_g = df_guclu["Close"]
    beklenen_mom6 = float(close_g.iloc[-21] / close_g.iloc[-126] - 1.0)
    fark = abs(harita["GUCLU"]["mom6"] - beklenen_mom6)
    assert fark < 1e-9, f"mom6 formülü tutarsız: {fark}"

    # ── Look-ahead kontrolü: tarihten SONRAKİ satırları bozunca sonuç
    # (skor/uygun) değişmemeli. ------------------------------------------
    df_guclu_bozuk = df_guclu.copy()
    gelecek_tarihler = pd.date_range(tarih_son + pd.Timedelta(days=1), periods=10, freq="B")
    ek = pd.DataFrame({c: [0.01] * 10 for c in df_guclu_bozuk.columns}, index=gelecek_tarihler)
    df_guclu_bozuk = pd.concat([df_guclu_bozuk, ek])
    veriler_bozuk = dict(veriler)
    veriler_bozuk["GUCLU"] = df_guclu_bozuk
    sonuc_bozuk = skorla(veriler_bozuk, evren, tarih_son)
    harita_bozuk = {s["sembol"]: s for s in sonuc_bozuk}
    assert abs(harita_bozuk["GUCLU"]["skor"] - harita["GUCLU"]["skor"]) < 1e-9, (
        "Gelecek tarihli veri skoru değiştirdi — look-ahead riski var"
    )

    # Boş evren / boş veri güvenli şekilde boş liste dönmeli.
    assert skorla({}, [], tarih_son) == []
    assert skorla(veriler, [], tarih_son) == []

    print("v3_skor.py kendi kendine kontrol: BAŞARILI")
    for s in sonuc:
        print(f"  {s['sembol']}: skor={s['skor']:.3f} uygun={s['uygun']} "
              f"red_nedeni={s['red_nedeni']}")
