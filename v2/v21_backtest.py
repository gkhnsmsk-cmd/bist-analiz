# -*- coding: utf-8 -*-
"""
v2/v21_backtest.py — Dinamik & Defansif BIST Algoritması v2.1 walk-forward
backtest motoru.

v2/backtest.py, v2/veri.py, v2/evren.py DEĞİŞTİRİLMEDİ — bu dosya onları
SAF ("yeniden kullan") biçimde import edip kullanır:
  - veri.fiyat_indir / veri.gostergeler  : OHLCV indirme + temel göstergeler
  - evren.TEMEL_SEMBOLLER / evren.evren_olustur : aday evren + likidite filtresi
  - backtest._komisyon_kayma_orani / backtest._tavan_taban_mi /
    backtest._metrikleri_hesapla / backtest._sektor_bul / backtest._SEKTOR_HARITASI
    : §7 (maliyet modeli) V2/V3 ile BİREBİR AYNI kalsın diye doğrudan
    yeniden kullanılıyor (kopyalanmadı — kopyalamak iki modülün zamanla
    tutarsızlaşmasına yol açabilirdi).

DÜRÜST BACKTEST kuralları (v2/backtest.py ile AYNI desen):
  - Sinyaller/tetikler HER ZAMAN yalnız `tarih <= T` verisine bakar
    (evren.py / v21_rejim.py / v21_secim.py zaten bunu kendi içinde uygular).
  - Yeni bir ALIM SİNYALİ (haftalık tarama) T Cuma KAPANIŞINDA oluşur; bu
    sinyalin karşılığı olan LİMİT EMİR ancak T+1'den itibaren "canlı" sayılır
    ve o günden sonraki günlerin Düşük/Açılışına göre doldurulur (gerçek bir
    limit emrin davranışına en yakın, gelecek bilgisi kullanmayan model).
  - Çıkışlar (sert stop / MA50 kırılımı / CMF / iz süren stop / zaman stopu)
    GÜNÜN KENDİ verisiyle (Low/Close) aynı gün tetiklenip aynı gün
    gerçekleşir — bu, önceden borsada bekleyen bir STOP EMRİNİN davranışıdır
    (v2/pozisyon.py::cikis_kontrol ile AYNI yorum kararı), yeni bir
    sinyal/karar DEĞİLDİR, dolayısıyla ileri bilgiye dayanmaz.

Mimari (§11 benzeri ayrım): v21_gosterge/v21_rejim/v21_secim/v21_portfoy SAF
fonksiyonlardır; bu dosyanın sorumluluğu yalnız günlük simülasyon döngüsünü
(emir kuyruğu, dolum, maliyet, özsermaye takibi, §7 rutin/aylık kontrol)
yürütmektir.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_V2_DIR = Path(__file__).resolve().parent
if str(_V2_DIR) not in sys.path:
    sys.path.insert(0, str(_V2_DIR))

import veri
import evren
import backtest as v2bt  # yalnız YENİDEN KULLANIM (maliyet modeli, sektör, metrikler) — v2bt DEĞİŞTİRİLMEZ

import v21_gosterge as vgo
import v21_rejim as vrj
import v21_secim as vse
import v21_portfoy as vpf

# ─────────────────────────────────────────────────────────────────────────
# Sabitler
# ─────────────────────────────────────────────────────────────────────────
_HAFTALIK_TARAMA_GUNU = 4          # Cuma (Python: Pazartesi=0 ... Cuma=4)
_SINYAL_GECERLILIK_GUN = vpf._SINYAL_GECERLILIK_GUN                  # 3 işlem günü
_IKINCI_DILIM_MAKS_BEKLEME_GUN = vpf._IKINCI_DILIM_MAKS_BEKLEME_GUN   # 15 işlem günü
_STOP_ATR_KATSAYI = vpf._STOP_ATR_KATSAYI


def _kapanis_veya_maliyet(veriler: dict, sembol: str, T: pd.Timestamp, yedek: float) -> float:
    df = veriler.get(sembol)
    if df is not None and T in df.index:
        deger = df.loc[T, "Close"]
        if not pd.isna(deger):
            return float(deger)
    return float(yedek)


def _portfoy_degerleri(pozisyonlar: list[dict], veriler: dict, T: pd.Timestamp) -> tuple[float, dict]:
    toplam = 0.0
    sektor_toplam: dict[str, float] = {}
    for p in pozisyonlar:
        fiyat = _kapanis_veya_maliyet(veriler, p["sembol"], T, p["maliyet_ortalama"])
        deger = fiyat * p["adet_toplam"]
        toplam += deger
        sektor_toplam[p["sektor"]] = sektor_toplam.get(p["sektor"], 0.0) + deger
    return toplam, sektor_toplam


def _islem_kaydi(poz: dict, cikis_tarihi, cikis_fiyati: float, adet: float,
                  cikis_nedeni: str, oran_maliyet: float, risk_tl_pay: float) -> dict:
    """Bir kapama (tam ya da kısmi) için işlem kaydı üretir — sonuc_R,
    net_pnl_tl v2bt._metrikleri_hesapla'nın beklediği alan adlarıyla AYNI.
    """
    maliyet_cikis = adet * cikis_fiyati * oran_maliyet
    hasilat = adet * cikis_fiyati - maliyet_cikis
    maliyet_giris_pay = poz.get("maliyet_giris_tl", 0.0) * (adet / poz.get("adet_ilk_toplam", adet))
    net_pnl = hasilat - adet * poz["maliyet_ortalama"] - maliyet_giris_pay
    sonuc_r = (net_pnl / risk_tl_pay) if risk_tl_pay and risk_tl_pay > 0 else 0.0
    return {
        "sembol": poz["sembol"],
        "giris_tarihi": poz["giris_tarihi_ilk"],
        "cikis_tarihi": cikis_tarihi,
        "giris_fiyati": poz["maliyet_ortalama"],
        "cikis_fiyati": float(cikis_fiyati),
        "adet": adet,
        "cikis_nedeni": cikis_nedeni,
        "gun_sayisi": poz.get("gun_sayisi", 0),
        "net_pnl_tl": float(net_pnl),
        "toplam_maliyet_tl": float(maliyet_giris_pay + maliyet_cikis),
        "sonuc_R": float(sonuc_r),
        "hasilat_tl": float(hasilat),
    }


def _calistir_ic(veriler: dict, endeks_df: pd.DataFrame, baslangic: str, bitis: str,
                  ozsermaye: float = 1_000_000.0, ilerleme: bool = True) -> dict:
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)

    takvim = endeks_df.loc[(endeks_df.index >= baslangic_ts) & (endeks_df.index <= bitis_ts)].index
    if len(takvim) == 0:
        return {
            "islemler": [], "ozsermaye_egrisi": [],
            "metrikler": v2bt._metrikleri_hesapla([], [], endeks_df, baslangic_ts, bitis_ts),
            "endeks_metrikleri": _endeks_al_tut_metrikleri(endeks_df, baslangic_ts, bitis_ts),
            "risksiz_engelli_ay_sayisi": 0,
            "aylik_getiriler": [],
        }

    cash = float(ozsermaye)
    acik_pozisyonlar: list[dict] = []
    bekleyen_sinyaller: list[dict] = []
    islemler: list[dict] = []
    ozsermaye_egrisi: list[dict] = []
    evren_guncel: list[str] = []

    mevcut_ay_anahtari = None
    onceki_ay_sonu_deger = None
    ay_sonu_deger_biriken = None
    tamamlanan_aylik_getiriler: list[float] = []
    risksiz_engelli_ay_sayisi = 0
    pozisyon_vardi_bu_ay = False  # BUG FİKSİ notu: bkz. adım 9 açıklaması

    toplam_gun = len(takvim)
    for idx, T in enumerate(takvim):
        # ── 1) Sayaçları güncelle (gun_sayisi, cmf_ardisik_negatif, iz süren
        #        stop) — cikis_kontrol'den ÖNCE (pozisyon.py deseniyle aynı). ──
        for poz in acik_pozisyonlar:
            df = veriler.get(poz["sembol"])
            if df is None or T not in df.index:
                continue
            satir = df.loc[T]
            poz.update(vpf.sayaclari_guncelle(poz, satir))

        # ── 2) İkinci dilim: DÜN tetiklenmişse bugün AÇILIŞTA doldur. Bu adım
        #        çıkış tespitinden ÖNCE çalışır — gerçek piyasada açılış,
        #        günün Düşük/Kapanış'ından KRONOLOJİK olarak önce gelir; bu
        #        yüzden bugünün çıkış kontrolleri (adım 3) maliyet ortalaması/
        #        adet GÜNCELLENMİŞ pozisyonla yapılmalı. ──
        for poz in acik_pozisyonlar:
            if poz.get("ikinci_dilim_durum") != "tetiklendi":
                continue
            if poz.get("ikinci_dilim_tetik_idx") != idx - 1:
                continue
            sembol = poz["sembol"]
            df = veriler.get(sembol)
            if df is None or T not in df.index or v2bt._tavan_taban_mi(df, T):
                poz["ikinci_dilim_durum"] = "iptal"
                continue
            satir = df.loc[T]
            acilis = satir.get("Open")
            if acilis is None or pd.isna(acilis):
                poz["ikinci_dilim_durum"] = "iptal"
                continue
            adet_ikinci = poz.get("ikinci_dilim_hedef_adet", 0.0)
            maliyet_ihtiyaci = adet_ikinci * float(acilis)
            if maliyet_ihtiyaci > 0 and cash < maliyet_ihtiyaci:
                adet_ikinci = float(np.floor(cash / float(acilis))) if float(acilis) > 0 else 0.0
            if adet_ikinci < 1.0:
                poz["ikinci_dilim_durum"] = "iptal"
                continue
            oran = v2bt._komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
            maliyet_giris = adet_ikinci * float(acilis) * oran
            cash -= (adet_ikinci * float(acilis) + maliyet_giris)

            adet_ilk = poz["adet_ilk"]
            yeni_maliyet_ort = (
                (adet_ilk * poz["giris_fiyati_ilk"] + adet_ikinci * float(acilis))
                / (adet_ilk + adet_ikinci)
            )
            poz["adet_ikinci"] = adet_ikinci
            poz["adet_toplam"] = adet_ilk + adet_ikinci
            poz["giris_tarihi_ikinci"] = T
            poz["giris_fiyati_ikinci"] = float(acilis)
            poz["maliyet_ortalama"] = float(yeni_maliyet_ort)
            poz["maliyet_giris_tl"] = poz.get("maliyet_giris_tl", 0.0) + maliyet_giris
            poz["adet_ilk_toplam"] = adet_ilk + adet_ikinci
            poz["ikinci_dilim_durum"] = "dolduruldu"

        # ── 3) Çıkışları tespit et (tam + kısmi/Hedef1), tavan/taban kilidi
        #        varsa ertele, aksi halde bugün uygula. ──
        cikacak_tam: dict[str, dict] = {}
        kismi_satis: dict[str, dict] = {}
        for poz in acik_pozisyonlar:
            df = veriler.get(poz["sembol"])
            if df is None or T not in df.index:
                continue
            satir = df.loc[T]
            tam = vpf.cikis_kontrol(poz, satir)
            if tam is not None:
                cikacak_tam[poz["sembol"]] = tam
                continue
            kismi = vpf.hedef1_kontrol(poz, satir)
            if kismi is not None:
                kismi_satis[poz["sembol"]] = kismi

        kalan_pozisyonlar = []
        for poz in acik_pozisyonlar:
            sembol = poz["sembol"]
            df = veriler.get(sembol)
            kilitli = (df is None) or v2bt._tavan_taban_mi(df, T)

            if sembol in cikacak_tam and not kilitli:
                cikis = cikacak_tam[sembol]
                satir = df.loc[T]
                oran = v2bt._komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
                adet = poz["adet_toplam"]
                risk_tl_pay = poz.get("risk_tl_kalan", 0.0)
                islem = _islem_kaydi(poz, T, cikis["fiyat"], adet, cikis["neden"], oran, risk_tl_pay)
                cash += islem["hasilat_tl"]
                islemler.append(islem)
                continue  # pozisyon tamamen kapandı, kalan listeye eklenmez

            if sembol in kismi_satis and not kilitli:
                kismi = kismi_satis[sembol]
                satir = df.loc[T]
                oran = v2bt._komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
                adet_sat = float(np.floor(poz["adet_toplam"] * kismi["oran"]))
                if adet_sat >= 1.0:
                    risk_tl_pay = poz.get("risk_tl_kalan", 0.0) * kismi["oran"]
                    islem = _islem_kaydi(poz, T, kismi["fiyat"], adet_sat, kismi["neden"], oran, risk_tl_pay)
                    cash += islem["hasilat_tl"]
                    islemler.append(islem)
                    poz["adet_toplam"] -= adet_sat
                    poz["risk_tl_kalan"] = poz.get("risk_tl_kalan", 0.0) - risk_tl_pay
                    poz["hedef1_alindi"] = True
                    # İz süren stopun başlangıç seviyesi: bugünkü Donchian alt
                    # kanal (varsa), yoksa güvenli taraf: mevcut sert stop.
                    donchian_alt = satir.get("DONCHIAN_ALT10")
                    baslangic_stop = poz["maliyet_ortalama"] - _STOP_ATR_KATSAYI * poz.get("atr_giris", 0.0)
                    if donchian_alt is not None and not pd.isna(donchian_alt):
                        poz["guncel_stop"] = max(baslangic_stop, float(donchian_alt))
                    else:
                        poz["guncel_stop"] = baslangic_stop
            kalan_pozisyonlar.append(poz)
        acik_pozisyonlar = kalan_pozisyonlar

        # ── 4) İkinci dilim TETİK tespiti (bugünün kapanışıyla) — yarın açılışta dolar. ──
        for poz in acik_pozisyonlar:
            if poz.get("ikinci_dilim_durum") != "bekliyor":
                continue
            if idx > poz.get("ikinci_dilim_son_idx", -1):
                poz["ikinci_dilim_durum"] = "iptal"
                continue
            df = veriler.get(poz["sembol"])
            if df is None or T not in df.index:
                continue
            satir = df.loc[T]
            if vpf.ikinci_dilim_tetiklendi_mi(satir, poz.get("ilk_dolum_yuksek")):
                poz["ikinci_dilim_durum"] = "tetiklendi"
                poz["ikinci_dilim_tetik_idx"] = idx

        # ── 5) Rejim (§2) — bugünün kapanışına göre, look-ahead güvenli. ──
        rejim_bugun = vrj.rejim_hesapla(endeks_df, T)

        # ── 6) Bekleyen (ilk dilim) sinyallerin dolumu — bugünün Düşük/Açılışı. ──
        kalan_sinyaller = []
        for sinyal in bekleyen_sinyaller:
            if idx < sinyal["olusturma_idx"] + 1:
                kalan_sinyaller.append(sinyal)
                continue
            if idx > sinyal["olusturma_idx"] + _SINYAL_GECERLILIK_GUN:
                continue  # sinyal iptal (3 işlem günü içinde dolmadı)

            sembol = sinyal["sembol"]
            df = veriler.get(sembol)
            if df is None or T not in df.index or v2bt._tavan_taban_mi(df, T):
                kalan_sinyaller.append(sinyal)
                continue
            satir = df.loc[T]
            low = satir.get("Low")
            acilis = satir.get("Open")
            limit = sinyal["limit_seviyesi"]
            if low is None or pd.isna(low) or low > limit:
                kalan_sinyaller.append(sinyal)
                continue

            fiyat_ilk = min(float(acilis), limit) if (acilis is not None and not pd.isna(acilis) and acilis < limit) else limit
            atr_bugun = satir.get("ATR14")
            atr_fill = float(atr_bugun) if (atr_bugun is not None and not pd.isna(atr_bugun)) else sinyal["atr_sinyal"]
            if atr_fill is None or pd.isna(atr_fill) or atr_fill <= 0:
                continue  # ATR hesaplanamıyor, sinyal düşer

            toplam_deger, sektor_deger = _portfoy_degerleri(acik_pozisyonlar, veriler, T)
            guncel_ozsermaye = cash + toplam_deger
            boyut = vpf.pozisyon_boyutu_hesapla(
                ozsermaye=guncel_ozsermaye, fiyat=fiyat_ilk, atr=atr_fill,
                sektor_toplam_deger=sektor_deger.get(sinyal["sektor"], 0.0),
                hisse_toplam_deger=toplam_deger,
                hedef_hisse_orani=rejim_bugun["hedef_hisse_orani"],
            )
            if boyut["red_nedeni"] is not None or boyut["adet_toplam"] < 1:
                continue  # kapasite kalmamış — sinyal düşer (yeniden kuyruğa alınmaz)

            adet_toplam_hedef = boyut["adet_toplam"]
            if adet_toplam_hedef < 2:
                adet_ilk = adet_toplam_hedef
                adet_ikinci_hedef = 0.0
            else:
                adet_ilk = float(np.floor(adet_toplam_hedef / 2.0))
                adet_ikinci_hedef = adet_toplam_hedef - adet_ilk

            maliyet_ihtiyaci = adet_ilk * fiyat_ilk
            if maliyet_ihtiyaci > 0 and cash < maliyet_ihtiyaci:
                adet_ilk = float(np.floor(cash / fiyat_ilk)) if fiyat_ilk > 0 else 0.0
            if adet_ilk < 1.0:
                continue

            oran = v2bt._komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
            maliyet_giris = adet_ilk * fiyat_ilk * oran
            cash -= (adet_ilk * fiyat_ilk + maliyet_giris)

            yeni_poz = {
                "sembol": sembol,
                "sektor": sinyal["sektor"],
                "giris_tarihi_ilk": T,
                "giris_fiyati_ilk": fiyat_ilk,
                "adet_ilk": adet_ilk,
                "giris_tarihi_ikinci": None,
                "giris_fiyati_ikinci": None,
                "adet_ikinci": 0.0,
                "adet_toplam": adet_ilk,
                "adet_ilk_toplam": adet_ilk + adet_ikinci_hedef,
                "maliyet_ortalama": fiyat_ilk,
                "atr_giris": atr_fill,
                "hedef1_alindi": False,
                "guncel_stop": float("nan"),
                "gun_sayisi": 0,
                "cmf_ardisik_negatif": 0,
                "maliyet_giris_tl": maliyet_giris,
                "risk_tl_kalan": boyut["risk_tl"],
                "ilk_dolum_yuksek": float(satir.get("High")) if not pd.isna(satir.get("High")) else fiyat_ilk,
                "ikinci_dilim_durum": ("bekliyor" if adet_ikinci_hedef >= 1 else "yok"),
                "ikinci_dilim_hedef_adet": adet_ikinci_hedef,
                "ikinci_dilim_son_idx": idx + _IKINCI_DILIM_MAKS_BEKLEME_GUN,
                "ikinci_dilim_tetik_idx": None,
                "skor_giriste": sinyal.get("skor"),
            }
            acik_pozisyonlar.append(yeni_poz)
            # sinyal kuyruktan düşer (kalan_sinyaller'e eklenmez)
        bekleyen_sinyaller = kalan_sinyaller

        # ── 7) Haftalık tarama (Cuma kapanışı) — §3 seçim + §7 3-ay risksiz kontrolü. ──
        if T.dayofweek == _HAFTALIK_TARAMA_GUNU:
            evren_guncel = evren.evren_olustur(veriler, T)
            risksiz_engelli = vpf.risksiz_altinda_mi_son_uc_ay(tamamlanan_aylik_getiriler)
            if risksiz_engelli:
                risksiz_engelli_ay_sayisi += 1
            if rejim_bugun["durum"] == "Risk-On" and not risksiz_engelli:
                adaylar = vse.secim_yap(veriler, evren_guncel, T, endeks_df=endeks_df)
                acik_semboller = {p["sembol"] for p in acik_pozisyonlar}
                bekleyen_semboller = {s["sembol"] for s in bekleyen_sinyaller}
                for aday in adaylar:
                    sembol = aday["sembol"]
                    if sembol in acik_semboller or sembol in bekleyen_semboller:
                        continue
                    df = veriler.get(sembol)
                    if df is None or T not in df.index:
                        continue
                    satir = df.loc[T]
                    limit = vpf.limit_seviyesi(satir)
                    if pd.isna(limit) or limit <= 0:
                        continue
                    bekleyen_sinyaller.append({
                        "sembol": sembol,
                        "sektor": v2bt._sektor_bul(sembol),
                        "olusturma_idx": idx,
                        "limit_seviyesi": float(limit),
                        "atr_sinyal": float(aday["atr"]),
                        "skor": aday["skor"],
                    })
                    bekleyen_semboller.add(sembol)

        # ── 8) Günlük özsermaye (mark-to-market) ──
        toplam_deger, _ = _portfoy_degerleri(acik_pozisyonlar, veriler, T)
        guncel_ozsermaye = cash + toplam_deger
        ozsermaye_egrisi.append({"tarih": T, "ozsermaye": guncel_ozsermaye})
        if acik_pozisyonlar:
            pozisyon_vardi_bu_ay = True

        # ── 9) §7 Aylık getiri takibi (yalnız TAMAMLANMIŞ aylar sayılır). ──
        # BUG FİKSİ (YORUM KARARI): tamamen NAKİTTE geçen bir ay (hiç açık
        # pozisyon yokken) §7'nin "3 ay üst üste risksiz altı" sayacına
        # KATILMAZ. Aksi halde kendi kendini besleyen bir kısır döngü
        # oluşuyordu: sistem henüz hiç pozisyon açmadan (örn. başlangıçta
        # Risk-Off olduğu için) geçen aylar da ~%0 getiri ürettiğinden
        # risksiz eşiğin altında sayılıyor, 3 ay sonra "yeni alım dur"
        # kilidi devreye giriyor VE bir daha asla açılamıyor (kilit
        # açıldığında hâlâ pozisyon yoksa getiri yine ~%0 kalır → sonsuza
        # dek kilitli — geliştirme dönemi backtest'inde tam olarak bu
        # yaşandı: 0 işlem, CAGR %0.00). §7'nin amacı "yatırılmış sermaye
        # risksiz faizden kötü performans gösteriyorsa dur" demektir,
        # "sermaye hiç yatırılmadıysa dur" değil — bu yüzden salt-nakit
        # aylar sayaca dahil edilmez (ne kilitler ne serbest bırakır,
        # yalnızca nötrdür/atlanır).
        ay_anahtari = (T.year, T.month)
        if mevcut_ay_anahtari is None:
            mevcut_ay_anahtari = ay_anahtari
            onceki_ay_sonu_deger = guncel_ozsermaye
        elif ay_anahtari != mevcut_ay_anahtari:
            if (pozisyon_vardi_bu_ay and onceki_ay_sonu_deger and onceki_ay_sonu_deger > 0
                    and ay_sonu_deger_biriken is not None):
                tamamlanan_aylik_getiriler.append(ay_sonu_deger_biriken / onceki_ay_sonu_deger - 1.0)
            onceki_ay_sonu_deger = ay_sonu_deger_biriken
            mevcut_ay_anahtari = ay_anahtari
            pozisyon_vardi_bu_ay = bool(acik_pozisyonlar)
        ay_sonu_deger_biriken = guncel_ozsermaye

        if ilerleme and (idx % 100 == 0 or idx == toplam_gun - 1):
            print(f"[v21_backtest] {idx + 1}/{toplam_gun} gün işlendi ({T.date()}) — "
                  f"rejim: {rejim_bugun['durum']}, açık pozisyon: {len(acik_pozisyonlar)}, "
                  f"özsermaye: {guncel_ozsermaye:,.0f} TL")

    metrikler = v2bt._metrikleri_hesapla(islemler, ozsermaye_egrisi, endeks_df, baslangic_ts, bitis_ts)
    return {
        "islemler": islemler,
        "ozsermaye_egrisi": ozsermaye_egrisi,
        "metrikler": metrikler,
        "endeks_metrikleri": _endeks_al_tut_metrikleri(endeks_df, baslangic_ts, bitis_ts),
        "risksiz_engelli_ay_sayisi": risksiz_engelli_ay_sayisi,
        "aylik_getiriler": tamamlanan_aylik_getiriler,
    }


def _endeks_al_tut_metrikleri(endeks_df: pd.DataFrame, baslangic_ts: pd.Timestamp,
                               bitis_ts: pd.Timestamp) -> dict:
    """BIST100 al-ve-tut için CAGR + maksimum düşüş — yalnız RAPOR amaçlı
    (hiçbir karara girmez). v2bt._metrikleri_hesapla zaten 'endeks_cagr'
    üretiyor ama kendi maksimum düşüşünü üretmiyor; burada o boşluk dolduruluyor.
    """
    araligi = endeks_df.loc[(endeks_df.index >= baslangic_ts) & (endeks_df.index <= bitis_ts)]
    if len(araligi) < 2 or araligi["Close"].iloc[0] <= 0:
        return {"cagr": float("nan"), "maksimum_dusus_%": float("nan")}
    kapanis = araligi["Close"]
    gun = (araligi.index[-1] - araligi.index[0]).days
    yil = max(gun / 365.25, 1e-9)
    cagr = float((kapanis.iloc[-1] / kapanis.iloc[0]) ** (1.0 / yil) - 1.0)
    dusus_serisi = (kapanis / kapanis.cummax()) - 1.0
    return {"cagr": cagr, "maksimum_dusus_%": float(dusus_serisi.min())}


def calistir(baslangic: str, bitis: str, ozsermaye: float = 1_000_000.0) -> dict:
    """Veriyi indirir/hazırlar (veri.py + evren.py + v21_gosterge.py), ardından
    _calistir_ic ile simüle eder. Döner: {'islemler','ozsermaye_egrisi','metrikler',...}
    """
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    # MA200 + 3 gün teyidi ve 250 günlük evren geçmişi için tampon.
    indirme_baslangic = (baslangic_ts - pd.Timedelta(days=500)).strftime("%Y-%m-%d")
    bitis_str = bitis_ts.strftime("%Y-%m-%d")

    print(f"[v21_backtest] Veri indiriliyor: {len(evren.TEMEL_SEMBOLLER)} sembol + XU100.IS "
          f"({indirme_baslangic} -> {bitis_str})...")
    yahoo_semboller = [s + ".IS" for s in evren.TEMEL_SEMBOLLER] + ["XU100.IS"]
    ham = veri.fiyat_indir(yahoo_semboller, indirme_baslangic, bitis_str)

    endeks_df = ham.get("XU100.IS")
    if endeks_df is None or endeks_df.empty:
        raise RuntimeError("XU100.IS verisi indirilemedi — rejim hesaplanamaz, backtest çalıştırılamaz.")

    veriler: dict[str, pd.DataFrame] = {}
    for sembol in evren.TEMEL_SEMBOLLER:
        df = ham.get(sembol + ".IS")
        if df is None or df.empty or len(df) < 60:
            continue
        temel = veri.gostergeler(df)
        veriler[sembol] = vgo.ek_gostergeler(temel)
    print(f"[v21_backtest] {len(veriler)}/{len(evren.TEMEL_SEMBOLLER)} sembol için veri hazır.")

    return _calistir_ic(veriler, endeks_df, baslangic, bitis, ozsermaye)


def walk_forward(ozsermaye: float = 1_000_000.0) -> dict:
    """Geliştirme: 2019-01-01 → 2023-12-31. Test (DOKUNULMAMIŞ): 2024-01-01 → bugün."""
    print("=" * 70)
    print("v2.1 WALK-FORWARD — Geliştirme dönemi: 2019-01-01 → 2023-12-31")
    print("=" * 70)
    gelistirme = calistir("2019-01-01", "2023-12-31", ozsermaye)

    bugun = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    print("=" * 70)
    print(f"v2.1 WALK-FORWARD — Test dönemi (DOKUNULMAMIŞ): 2024-01-01 → {bugun}")
    print("=" * 70)
    test = calistir("2024-01-01", bugun, ozsermaye)

    return {"gelistirme": gelistirme, "test": test}


if __name__ == "__main__":
    # Ağ çağrısı YOK — sentetik veriyle LOOK-AHEAD testi (v2/backtest.py'deki
    # desenle AYNI mantık): gelecekte "patlayan" bir hisse, patlamadan ÖNCEKİ
    # günlerin sonuçlarını (özsermaye eğrisi + kesim öncesi girişler)
    # ETKİLEMEMELİ.
    n_gun = 420
    tarihler = pd.date_range("2022-01-03", periods=n_gun, freq="B")
    kesim_idx = 340
    kesim_tarih = tarihler[kesim_idx]

    def _rastgele_df(baslangic_fiyat, egim, gurultu, hacim, tohum):
        r = np.random.default_rng(tohum)
        egilim = baslangic_fiyat + np.arange(n_gun) * egim
        kapanis = egilim + r.normal(0, gurultu, n_gun)
        kapanis = np.maximum(kapanis, 1.0)
        acilis = kapanis - r.normal(0, gurultu * 0.3, n_gun)
        yuksek = np.maximum(acilis, kapanis) + np.abs(r.normal(0.3, 0.15, n_gun))
        dusuk = np.minimum(acilis, kapanis) - np.abs(r.normal(0.3, 0.15, n_gun))
        return pd.DataFrame({
            "Open": acilis, "High": yuksek, "Low": dusuk, "Close": kapanis,
            "Volume": r.integers(int(hacim * 0.8), int(hacim * 1.2), n_gun).astype(float),
        }, index=tarihler)

    endeks_df = _rastgele_df(5000, 3.0, 20.0, 50_000_000, tohum=1)

    def _hazirla(df):
        return vgo.ek_gostergeler(veri.gostergeler(df))

    def _evren_kur(gelecek_override=None):
        veriler = {}
        for i, tohum in enumerate((11, 12, 13, 14, 15, 16, 17, 18)):
            df = _rastgele_df(50.0 + i * 5, 0.06, 0.6, 30_000_000, tohum=tohum)
            veriler[f"DOLGU{i}"] = _hazirla(df)
        gelecek_df = _rastgele_df(40.0, 0.05, 0.5, 40_000_000, tohum=99)
        if gelecek_override is not None:
            gelecek_df = gelecek_df.copy()
            m = gelecek_df.index > kesim_tarih
            gelecek_df.loc[m, "Close"] = gelecek_override
            gelecek_df.loc[m, "Open"] = gelecek_override
            gelecek_df.loc[m, "High"] = gelecek_override * 1.01
            gelecek_df.loc[m, "Low"] = gelecek_override * 0.99
        veriler["GELECEK"] = _hazirla(gelecek_df)
        return veriler

    veriler_a = _evren_kur(None)
    n_sonrasi = int((tarihler > kesim_tarih).sum())
    patlama = 40.0 * (1.6 + np.linspace(0, 0.4, n_sonrasi))
    veriler_b = _evren_kur(patlama)

    print("Senaryo A (patlama YOK) çalıştırılıyor...")
    sonuc_a = _calistir_ic(veriler_a, endeks_df,
                            tarihler[250].strftime("%Y-%m-%d"), tarihler[-1].strftime("%Y-%m-%d"),
                            ozsermaye=1_000_000.0, ilerleme=False)
    print("Senaryo B (GELECEK kesimden sonra patlıyor) çalıştırılıyor...")
    sonuc_b = _calistir_ic(veriler_b, endeks_df,
                            tarihler[250].strftime("%Y-%m-%d"), tarihler[-1].strftime("%Y-%m-%d"),
                            ozsermaye=1_000_000.0, ilerleme=False)

    egri_a = {e["tarih"]: e["ozsermaye"] for e in sonuc_a["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    egri_b = {e["tarih"]: e["ozsermaye"] for e in sonuc_b["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    assert set(egri_a.keys()) == set(egri_b.keys()), "Kesim öncesi tarih kümeleri farklı!"
    for t in egri_a:
        fark = abs(egri_a[t] - egri_b[t])
        assert fark < 1e-6, (
            f"LOOK-AHEAD SIZINTISI: {t.date()} özsermayesi senaryolar arasında farklı "
            f"(A={egri_a[t]:.4f}, B={egri_b[t]:.4f})."
        )

    def _kesim_oncesi_girisler(sonuc):
        return sorted(
            [(t["sembol"], t["giris_tarihi"], round(t["giris_fiyati"], 6))
             for t in sonuc["islemler"] if t["giris_tarihi"] <= kesim_tarih]
        )
    girisler_a = _kesim_oncesi_girisler(sonuc_a)
    girisler_b = _kesim_oncesi_girisler(sonuc_b)
    assert girisler_a == girisler_b, (
        f"LOOK-AHEAD SIZINTISI: kesim öncesi girişler farklı!\nA={girisler_a}\nB={girisler_b}"
    )

    print("v21_backtest.py kendi kendine kontrol (LOOK-AHEAD testi): BAŞARILI")
    print(f"  Kesim öncesi ortak işlem sayısı: {len(girisler_a)}")
    print(f"  Senaryo A toplam işlem: {len(sonuc_a['islemler'])}, Senaryo B toplam işlem: {len(sonuc_b['islemler'])}")
    print(f"  Senaryo A metrikleri: {sonuc_a['metrikler']}")
