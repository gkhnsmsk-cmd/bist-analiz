# -*- coding: utf-8 -*-
"""
v2/v4_backtest.py — Pusula V4 backtest motoru = V3 + MAKRO (petrol şoku) katmanı.

v3_backtest.py örnek alınarak (kopyalanmadan değil, DOĞRUDAN kopyalanıp
üzerine TEK bir katman eklenerek) yazıldı — bilerek. V3'ün üç zorunlu kuralı
(§6, §8, §9) BİREBİR korunur, tek fark: rejim.rejim_hesapla()'nın ürettiği
hedef_oran, makro_katman.makro_hedef_oran() üzerinden Brent petrol şoku
çarpanıyla (bkz. v2/makro_katman.py) çarpımsal olarak kısılır.

V3'TEN FARKI (bilerek, TEK fark): _calistir_ic artık opsiyonel bir
`petrol_df` parametresi alır. None ise (varsayılan) davranış V3 ile
BİREBİR aynıdır (makro katman devre dışı kalır — hiçbir kod yolu değişmez).
Bir Brent DataFrame'i verilirse, her gün rejim.rejim_hesapla() çıktısı
makro_katman.makro_hedef_oran() ile post-process edilir; kademeli yaklaşma
(§7, _KADEMELI_ADIM) bu KISILMIŞ hedefe göre çalışır.

calistir() artık BZ=F (Brent) verisini de veri.fiyat_indir() ile (AYNI tek
ağ-çağrısı noktasından, §11 kuralı korunarak) indirir ve _calistir_ic'e
iletir. walk_forward() calistir()'i olduğu gibi çağırdığı için ayrıca bir
değişikliğe gerek yoktur.

KABUL KRİTERİ (§9) V3 ile AYNI kalır — bu dosya yalnız GİRDİ tarafında
(hedef_oran) bir kısıtlama ekler, kabul mantığını değiştirmez.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_V2_DIR = Path(__file__).resolve().parent
if str(_V2_DIR) not in sys.path:
    sys.path.insert(0, str(_V2_DIR))

import veri
import evren
import rejim
import v3_skor
import v3_portfoy
import makro_katman

# ─────────────────────────────────────────────────────────────────────────
# §8 — Maliyet modeli (V2/V3 ile AYNI değerler, şartname gereği).
# ─────────────────────────────────────────────────────────────────────────
_KOMISYON_ORANI = 0.0015          # tek yön
_KAYMA_NORMAL = 0.0010            # tek yön, 20g medyan TL hacim >= eşik
_KAYMA_DUSUK_LIKIDITE = 0.0025    # tek yön, 20g medyan TL hacim < eşik
_DUSUK_LIKIDITE_ESIGI = 50_000_000.0

# evren.py ile AYNI tavan/taban proxy eşiği (tutarlılık şart).
_TAVAN_TABAN_ESIGI = 0.095

# §6 — rebalans her 20 işlem günü (≈ aylık).
_REBALANS_ARALIGI = 20

# §7 — rejim yükselirken günde en fazla %33 puan kademeli yaklaşma.
_KADEMELI_ADIM = 0.33

# §6 — sapma %5 puandan küçükse dokunulmaz (gereksiz turnover'ı önler).
_AGIRLIK_TOLERANSI = 0.05

_YIL_ISLEM_GUNU = 252
_TURNOVER_ESIGI_YILLIK = 6.00   # §9: yıllık turnover <= %600
_MIN_REBALANS_SAYISI = 24        # §9

# ── DENEY DESTEĞİ (deney_lab.py) — v3_portfoy.py'nin §5 sabitlerinin AYNISI.
_TEMEL_POZISYON_SAYISI = 10
_TEMEL_AGIRLIK_TABANI = 0.05
_TEMEL_AGIRLIK_TAVANI = 0.15
_TEMEL_MAKS_SEKTOR = 3


def _komisyon_kayma_orani(hacim_tl_medyan) -> float:
    """§8: komisyon + kayma (tek yön), likiditeye göre kayma oranı değişir."""
    if hacim_tl_medyan is None or pd.isna(hacim_tl_medyan) or hacim_tl_medyan < _DUSUK_LIKIDITE_ESIGI:
        return _KOMISYON_ORANI + _KAYMA_DUSUK_LIKIDITE
    return _KOMISYON_ORANI + _KAYMA_NORMAL


def _tavan_taban_mi(df: pd.DataFrame, tarih: pd.Timestamp) -> bool:
    """Bugünün kapanış getirisi mutlak %9.5'i geçiyorsa tavan/taban proxy'si."""
    if df is None or tarih not in df.index:
        return True
    loc = df.index.get_loc(tarih)
    if loc == 0:
        return False
    bugun_kapanis = df["Close"].iloc[loc]
    dun_kapanis = df["Close"].iloc[loc - 1]
    if pd.isna(bugun_kapanis) or pd.isna(dun_kapanis) or dun_kapanis == 0:
        return False
    return bool(abs(bugun_kapanis / dun_kapanis - 1.0) >= _TAVAN_TABAN_ESIGI)


def _pozisyon_bul(acik_pozisyonlar: list[dict], sembol: str) -> dict | None:
    for p in acik_pozisyonlar:
        if p["sembol"] == sembol:
            return p
    return None


# ─────────────────────────────────────────────────────────────────────────
# İç simülasyon çekirdeği — V3 ile BİREBİR AYNI, TEK fark: opsiyonel
# `petrol_df` ile makro_katman.makro_hedef_oran() post-process'i (§ üstteki
# modül docstring'inde açıklandı).
# ─────────────────────────────────────────────────────────────────────────
def _calistir_ic(veriler: dict, endeks_df: pd.DataFrame, baslangic: str, bitis: str,
                  ozsermaye: float = 1_000_000.0, ilerleme: bool = True,
                  izleme_tarihleri: set | None = None,
                  rejim_kapisi_aktif: bool = True,
                  rebalans_gun: int | None = None,
                  pozisyon_sayisi: int | None = None,
                  petrol_df: pd.DataFrame | None = None) -> dict:
    """V3 _calistir_ic ile AYNI davranış + opsiyonel MAKRO (petrol) katmanı.

    petrol_df: None ise (varsayılan) V3 ile BİREBİR aynı — makro katman
        hiç devreye girmez. Bir Brent (BZ=F) DataFrame'i verilirse, her gün
        rejim.rejim_hesapla() çıktısı makro_katman.makro_hedef_oran() ile
        post-process edilir (hedef_oran çarpımsal olarak kısılır) — bu,
        rejim.py'nin KENDİSİNİ DEĞİŞTİRMEDEN ek bir kapı kurar.
    """
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    izleme_tarihleri = izleme_tarihleri or set()
    pozisyon_izleme: dict = {}

    rebalans_araligi = _REBALANS_ARALIGI if rebalans_gun is None else max(1, int(rebalans_gun))
    if pozisyon_sayisi is None:
        poz_maks = None
        poz_ilk_n = None
        poz_taban = None
        poz_tavan = None
        poz_sektor = None
        agirlik_toleransi = _AGIRLIK_TOLERANSI
    else:
        poz_maks = max(1, int(pozisyon_sayisi))
        olcek = _TEMEL_POZISYON_SAYISI / poz_maks
        poz_ilk_n = 2 * poz_maks
        poz_taban = _TEMEL_AGIRLIK_TABANI * olcek
        poz_tavan = _TEMEL_AGIRLIK_TAVANI * olcek
        poz_sektor = max(1, math.ceil(_TEMEL_MAKS_SEKTOR / olcek))
        agirlik_toleransi = _AGIRLIK_TOLERANSI * olcek

    takvim = endeks_df.loc[(endeks_df.index >= baslangic_ts) & (endeks_df.index <= bitis_ts)].index
    if len(takvim) == 0:
        return {
            "islemler": [], "ozsermaye_egrisi": [], "pozisyon_izleme": {},
            "metrikler": _metrikleri_hesapla([], [], endeks_df, baslangic_ts, bitis_ts, 0, 0.0),
        }

    cash = float(ozsermaye)
    acik_pozisyonlar: list[dict] = []
    islemler: list[dict] = []
    ozsermaye_egrisi: list[dict] = []
    pending_orders: list[dict] = []
    turnover_toplam_tl = 0.0
    rebalans_sayisi = 0
    efektif_hedef_oran = 0.0
    toplam_gun = len(takvim)
    son_fiyat_satiri: dict[str, pd.Series] = {}

    for idx, T in enumerate(takvim):
        # ── 1) Dünün emirlerini bugünün AÇILIŞINDA gerçekleştir (§8). ──
        for emir in pending_orders:
            sembol = emir["sembol"]
            df = veriler.get(sembol)
            if df is None or T not in df.index:
                continue
            if _tavan_taban_mi(df, T):
                continue
            satir = df.loc[T]
            acilis = satir.get("Open")
            if acilis is None or pd.isna(acilis) or acilis <= 0:
                continue
            oran = _komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))

            if emir["tip"] == "sat_tum":
                poz = _pozisyon_bul(acik_pozisyonlar, sembol)
                if poz is None:
                    continue
                hasilat_brut = poz["adet"] * acilis
                maliyet = hasilat_brut * oran
                hasilat_net = hasilat_brut - maliyet
                cash += hasilat_net
                turnover_toplam_tl += hasilat_brut
                net_pnl = hasilat_net - poz["adet"] * poz["giris_fiyati"] - poz.get("maliyet_giris_tl", 0.0)
                islemler.append({
                    "sembol": sembol, "giris_tarihi": poz["giris_tarihi"], "cikis_tarihi": T,
                    "giris_fiyati": poz["giris_fiyati"], "cikis_fiyati": float(acilis),
                    "adet": poz["adet"], "cikis_nedeni": emir.get("neden", "cikis"),
                    "net_pnl_tl": float(net_pnl),
                    "getiri_%": float(acilis / poz["giris_fiyati"] - 1.0) if poz["giris_fiyati"] else float("nan"),
                    "tutma_gun": (T - poz["giris_tarihi"]).days,
                })
                acik_pozisyonlar.remove(poz)

            elif emir["tip"] == "hedef_ayarla":
                hedef_tl = max(0.0, emir.get("hedef_tl", 0.0))
                poz = _pozisyon_bul(acik_pozisyonlar, sembol)
                mevcut_adet = poz["adet"] if poz else 0.0
                hedef_adet = math.floor(hedef_tl / acilis)
                delta = hedef_adet - mevcut_adet

                if delta > 0:
                    maliyet = delta * acilis * oran
                    gerekli_nakit = delta * acilis + maliyet
                    if gerekli_nakit > cash:
                        delta = math.floor(cash / (acilis * (1.0 + oran)))
                        if delta <= 0:
                            continue
                        maliyet = delta * acilis * oran
                    cash -= (delta * acilis + maliyet)
                    turnover_toplam_tl += delta * acilis
                    if poz is None:
                        acik_pozisyonlar.append({
                            "sembol": sembol, "giris_tarihi": T, "giris_fiyati": float(acilis),
                            "adet": float(delta), "maliyet_giris_tl": float(maliyet),
                            "skor_giriste": emir.get("skor_giris"),
                        })
                    else:
                        yeni_adet = poz["adet"] + delta
                        poz["giris_fiyati"] = (
                            (poz["giris_fiyati"] * poz["adet"] + acilis * delta) / yeni_adet
                        )
                        poz["adet"] = yeni_adet
                        poz["maliyet_giris_tl"] = poz.get("maliyet_giris_tl", 0.0) + maliyet

                elif delta < 0:
                    if poz is None:
                        continue
                    satilacak_adet = min(-delta, poz["adet"])
                    if satilacak_adet <= 0:
                        continue
                    hasilat_brut = satilacak_adet * acilis
                    maliyet = hasilat_brut * oran
                    cash += (hasilat_brut - maliyet)
                    turnover_toplam_tl += hasilat_brut
                    onceki_adet = poz["adet"]
                    oran_pay = (satilacak_adet / onceki_adet) if onceki_adet > 0 else 0.0
                    poz["maliyet_giris_tl"] = poz.get("maliyet_giris_tl", 0.0) * (1.0 - oran_pay)
                    poz["adet"] -= satilacak_adet
                    if poz["adet"] <= 1e-9:
                        acik_pozisyonlar.remove(poz)
        pending_orders = []

        # ── 2) Rejim (§7) — bugünün kapanışına göre, look-ahead güvenli.
        #        V4 FARKI: rejim_kapisi_aktif VE petrol_df verilmişse, rejim
        #        çıktısı makro_katman.makro_hedef_oran() ile post-process
        #        edilir (hedef_oran petrol şokuna göre çarpımsal kısılır). ──
        if rejim_kapisi_aktif:
            rejim_bugun = rejim.rejim_hesapla(endeks_df, veriler, T)
            if petrol_df is not None:
                rejim_bugun = makro_katman.makro_hedef_oran(rejim_bugun, petrol_df, T)
            hedef_ham = rejim_bugun["hedef_oran"]
            if hedef_ham > efektif_hedef_oran:
                efektif_hedef_oran = min(hedef_ham, efektif_hedef_oran + _KADEMELI_ADIM)
            else:
                efektif_hedef_oran = hedef_ham  # düşerken ANINDA (§7)
        else:
            rejim_bugun = {
                "rejim": "R1",
                "hedef_oran": 1.0,
                "genislik": float("nan"),
                "gerekce": "Rejim kapısı deney amaçlı KAPALI — her zaman tam yatırım.",
            }
            efektif_hedef_oran = 1.0

        # ── 3) Günlük mark-to-market (forward-fill, bkz. V3 notu). ──
        fiyatlar_bugun: dict[str, pd.Series] = {}
        for p in acik_pozisyonlar:
            sembol = p["sembol"]
            df = veriler.get(sembol)
            if df is not None and T in df.index:
                satir = df.loc[T]
                fiyatlar_bugun[sembol] = satir
                son_fiyat_satiri[sembol] = satir
            elif sembol in son_fiyat_satiri:
                fiyatlar_bugun[sembol] = son_fiyat_satiri[sembol]
        yatirim_deger = sum(
            float(fiyatlar_bugun[p["sembol"]]["Close"]) * p["adet"]
            for p in acik_pozisyonlar if p["sembol"] in fiyatlar_bugun
        )
        guncel_ozsermaye = cash + yatirim_deger

        if cash < -0.01 * guncel_ozsermaye:
            raise RuntimeError(
                f"[v4_backtest] KALDIRAÇ SIZINTISI: {T.date()} günü nakit "
                f"({cash:,.2f} TL) özsermayenin (%{guncel_ozsermaye:,.2f} TL) "
                f"%1'inden fazla negatif. Emir doldurma/nakit muhasebesinde "
                f"bir hata var — backtest durduruldu (bkz. STRATEJI_V3.md §8)."
            )

        # ── 4) Günlük kontrol — YALNIZ felaket stopu + rejim çıkışı (§6). ──
        bugun_ctx = {"fiyatlar": fiyatlar_bugun, "ozsermaye": guncel_ozsermaye}
        kapatilacaklar = v3_portfoy.gunluk_kontrol(acik_pozisyonlar, bugun_ctx, rejim_bugun)
        zaten_satilacak: set[str] = set()
        for k in kapatilacaklar:
            pending_orders.append({"tip": "sat_tum", "sembol": k["sembol"], "neden": k["neden"]})
            zaten_satilacak.add(k["sembol"])

        # ── 5) Rebalans günü mü (her 20 işlem günü)? ──
        if idx % rebalans_araligi == 0:
            rebalans_sayisi += 1
            evren_guncel = evren.evren_olustur(veriler, T)
            siralama = v3_skor.skorla(veriler, evren_guncel, T)

            mevcut_liste = [
                {"sembol": p["sembol"], "giris_fiyati": p["giris_fiyati"]}
                for p in acik_pozisyonlar if p["sembol"] not in zaten_satilacak
            ]
            sonuc_portfoy = v3_portfoy.hedef_portfoy(
                siralama, veriler, T, guncel_ozsermaye, efektif_hedef_oran, mevcut_liste,
                maks_pozisyon=poz_maks, ilk_n_tampon=poz_ilk_n,
                agirlik_tabani=poz_taban, agirlik_tavani=poz_tavan,
                maks_sektor=poz_sektor,
            )

            for s in sonuc_portfoy["satilacak"]:
                if s["sembol"] in zaten_satilacak:
                    continue
                pending_orders.append({
                    "tip": "sat_tum", "sembol": s["sembol"], "neden": f"rebalans: {s['neden']}",
                })
                zaten_satilacak.add(s["sembol"])

            skor_haritasi = {s["sembol"]: s["skor"] for s in siralama}
            for sembol, hedef_agirlik in sonuc_portfoy["hedef_agirliklar"].items():
                if sembol in zaten_satilacak:
                    continue
                mevcut_poz = _pozisyon_bul(acik_pozisyonlar, sembol)
                mevcut_agirlik = 0.0
                if mevcut_poz is not None and sembol in fiyatlar_bugun and guncel_ozsermaye > 0:
                    mevcut_agirlik = (
                        float(fiyatlar_bugun[sembol]["Close"]) * mevcut_poz["adet"] / guncel_ozsermaye
                    )
                if abs(hedef_agirlik - mevcut_agirlik) < agirlik_toleransi:
                    continue
                pending_orders.append({
                    "tip": "hedef_ayarla", "sembol": sembol,
                    "hedef_tl": hedef_agirlik * guncel_ozsermaye,
                    "skor_giris": skor_haritasi.get(sembol),
                })

        # ── 6) Günlük özsermaye kaydı. ──
        ozsermaye_egrisi.append({
            "tarih": T, "ozsermaye": guncel_ozsermaye,
            "nakit": cash, "pozisyon_deger": yatirim_deger,
        })

        if T in izleme_tarihleri:
            pozisyon_izleme[T] = [dict(p) for p in acik_pozisyonlar]

        if ilerleme and (idx % 100 == 0 or idx == toplam_gun - 1):
            print(f"[v4_backtest] {idx + 1}/{toplam_gun} gün işlendi ({T.date()}) — "
                  f"açık pozisyon: {len(acik_pozisyonlar)}, rejim: {rejim_bugun['rejim']}, "
                  f"özsermaye: {guncel_ozsermaye:,.0f} TL")

    metrikler = _metrikleri_hesapla(
        islemler, ozsermaye_egrisi, endeks_df, baslangic_ts, bitis_ts,
        rebalans_sayisi, turnover_toplam_tl,
    )
    return {"islemler": islemler, "ozsermaye_egrisi": ozsermaye_egrisi,
            "pozisyon_izleme": pozisyon_izleme, "metrikler": metrikler}


def _metrikleri_hesapla(islemler: list[dict], ozsermaye_egrisi: list[dict],
                         endeks_df: pd.DataFrame, baslangic_ts: pd.Timestamp,
                         bitis_ts: pd.Timestamp, rebalans_sayisi: int,
                         turnover_toplam_tl: float) -> dict:
    """V3 ile BİREBİR aynı metrik hesaplama (§9)."""
    n = len(islemler)
    if n == 0:
        kazanma_orani = float("nan")
        pf = float("nan")
        en_kotu = None
    else:
        kazananlar = [t for t in islemler if t["net_pnl_tl"] > 0]
        kaybedenler = [t for t in islemler if t["net_pnl_tl"] <= 0]
        kazanma_orani = len(kazananlar) / n
        toplam_kazanc_tl = sum(t["net_pnl_tl"] for t in kazananlar)
        toplam_kayip_tl = abs(sum(t["net_pnl_tl"] for t in kaybedenler))
        pf = (toplam_kazanc_tl / toplam_kayip_tl) if toplam_kayip_tl > 0 else float("inf")
        en_kotu_islem = min(islemler, key=lambda t: t["net_pnl_tl"])
        en_kotu = {
            "sembol": en_kotu_islem["sembol"], "net_pnl_tl": en_kotu_islem["net_pnl_tl"],
            "cikis_nedeni": en_kotu_islem["cikis_nedeni"],
        }

    ort_ozsermaye = float("nan")
    yil = float("nan")
    if ozsermaye_egrisi:
        seri = pd.Series({e["tarih"]: e["ozsermaye"] for e in ozsermaye_egrisi}).sort_index()
        seri = seri.dropna()
        if seri.empty:
            maks_dusus = float("nan")
            cagr = float("nan")
        else:
            dusus_serisi = (seri / seri.cummax()) - 1.0
            maks_dusus = float(dusus_serisi.min())
            gun_araligi = (seri.index[-1] - seri.index[0]).days
            yil = max(gun_araligi / 365.25, 1e-9)
            cagr = float((seri.iloc[-1] / seri.iloc[0]) ** (1.0 / yil) - 1.0) if seri.iloc[0] > 0 else float("nan")
            ort_ozsermaye = float(seri.mean())
    else:
        maks_dusus = float("nan")
        cagr = float("nan")

    endeks_araligi = endeks_df.loc[(endeks_df.index >= baslangic_ts) & (endeks_df.index <= bitis_ts)]
    if len(endeks_araligi) >= 2 and endeks_araligi["Close"].iloc[0] > 0:
        gun_e = (endeks_araligi.index[-1] - endeks_araligi.index[0]).days
        yil_e = max(gun_e / 365.25, 1e-9)
        endeks_cagr = float(
            (endeks_araligi["Close"].iloc[-1] / endeks_araligi["Close"].iloc[0]) ** (1.0 / yil_e) - 1.0
        )
    else:
        endeks_cagr = float("nan")

    endeks_ustu_fark = (cagr - endeks_cagr) if not (pd.isna(cagr) or pd.isna(endeks_cagr)) else float("nan")

    yillik_turnover = float("nan")
    if not pd.isna(ort_ozsermaye) and ort_ozsermaye > 0 and not pd.isna(yil) and yil > 0:
        yillik_turnover = (turnover_toplam_tl / ort_ozsermaye) / yil

    return {
        "islem_sayisi": n,
        "kazanma_orani": kazanma_orani,
        "profit_factor": pf,
        "maksimum_dusus_%": maks_dusus,
        "cagr": cagr,
        "endeks_cagr": endeks_cagr,
        "endeks_ustu_fark": endeks_ustu_fark,
        "en_kotu_islem": en_kotu,
        "rebalans_sayisi": rebalans_sayisi,
        "yillik_turnover_%": yillik_turnover,
    }


def _kabul_kriterlerini_kontrol(test_metrikleri: dict) -> dict:
    """§9 kabul kriterleri — V3 ile BİREBİR aynı."""
    basarisiz: list[str] = []

    fark = test_metrikleri.get("endeks_ustu_fark", float("nan"))
    if not (isinstance(fark, (int, float)) and not pd.isna(fark) and fark > 0):
        fark_yuzde = fark * 100 if isinstance(fark, (int, float)) and not pd.isna(fark) else float("nan")
        basarisiz.append(f"CAGR endeksi geçemedi (fark: %{fark_yuzde:.2f} puan) — eşik: >0")

    maks_dusus_v4 = test_metrikleri.get("maksimum_dusus_%", float("nan"))
    maks_dusus_endeks = test_metrikleri.get("endeks_maksimum_dusus_%", float("nan"))
    if (isinstance(maks_dusus_v4, (int, float)) and isinstance(maks_dusus_endeks, (int, float))
            and not pd.isna(maks_dusus_v4) and not pd.isna(maks_dusus_endeks)):
        if abs(maks_dusus_v4) > abs(maks_dusus_endeks) + 1e-9:
            basarisiz.append(
                f"Maksimum düşüş endeksten kötü (V4 %{abs(maks_dusus_v4) * 100:.1f} > "
                f"endeks %{abs(maks_dusus_endeks) * 100:.1f})"
            )
    else:
        basarisiz.append("Maksimum düşüş kıyası hesaplanamadı (eksik veri).")

    rebalans_sayisi = test_metrikleri.get("rebalans_sayisi", 0)
    if not (rebalans_sayisi >= _MIN_REBALANS_SAYISI):
        basarisiz.append(f"Rebalans sayısı {rebalans_sayisi} — eşik: >={_MIN_REBALANS_SAYISI}")

    turnover = test_metrikleri.get("yillik_turnover_%", float("nan"))
    if not (isinstance(turnover, (int, float)) and not pd.isna(turnover) and turnover <= _TURNOVER_ESIGI_YILLIK):
        turnover_yuzde = turnover * 100 if isinstance(turnover, (int, float)) and not pd.isna(turnover) else float("nan")
        basarisiz.append(f"Yıllık turnover %{turnover_yuzde:.0f} — eşik: <=%{_TURNOVER_ESIGI_YILLIK * 100:.0f}")

    return {"gecti": len(basarisiz) == 0, "basarisiz_kriterler": basarisiz}


def calistir(baslangic: str, bitis: str, ozsermaye: float = 1_000_000.0,
             rejim_kapisi_aktif: bool = True,
             rebalans_gun: int | None = None,
             pozisyon_sayisi: int | None = None) -> dict:
    """§11 imzası. V3 calistir() ile AYNI, TEK fark: BZ=F (Brent) verisi de
    AYNI toplu veri.fiyat_indir() çağrısıyla indirilip _calistir_ic'e
    makro_katman'ın kullanacağı `petrol_df` olarak iletilir.

    Döner: {'islemler': [...], 'ozsermaye_egrisi': [...], 'metrikler': {...}}
    """
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    indirme_baslangic = (baslangic_ts - pd.Timedelta(days=550)).strftime("%Y-%m-%d")
    bitis_str = bitis_ts.strftime("%Y-%m-%d")

    print(f"[v4_backtest] Veri indiriliyor: {len(evren.TEMEL_SEMBOLLER)} sembol + XU100.IS + "
          f"{makro_katman.PETROL_SEMBOLU} (petrol/MAKRO) ({indirme_baslangic} -> {bitis_str})...")
    yahoo_semboller = [s + ".IS" for s in evren.TEMEL_SEMBOLLER] + ["XU100.IS", makro_katman.PETROL_SEMBOLU]
    ham = veri.fiyat_indir(yahoo_semboller, indirme_baslangic, bitis_str)

    endeks_df = ham.get("XU100.IS")
    if endeks_df is None or endeks_df.empty:
        raise RuntimeError("XU100.IS verisi indirilemedi — rejim hesaplanamaz, backtest çalıştırılamaz.")

    petrol_df = ham.get(makro_katman.PETROL_SEMBOLU)
    if petrol_df is None or petrol_df.empty:
        print(f"[v4_backtest] UYARI: {makro_katman.PETROL_SEMBOLU} verisi indirilemedi — "
              f"MAKRO katman bu koşuda NÖTR (çarpan=1.0) kalacak.")
        petrol_df = None

    veriler: dict[str, pd.DataFrame] = {}
    for sembol in evren.TEMEL_SEMBOLLER:
        df = ham.get(sembol + ".IS")
        if df is None or df.empty or len(df) < 60:
            continue
        veriler[sembol] = veri.gostergeler(df)
    print(f"[v4_backtest] {len(veriler)}/{len(evren.TEMEL_SEMBOLLER)} sembol için veri hazır.")

    return _calistir_ic(
        veriler, endeks_df, baslangic, bitis, ozsermaye,
        rejim_kapisi_aktif=rejim_kapisi_aktif,
        rebalans_gun=rebalans_gun,
        pozisyon_sayisi=pozisyon_sayisi,
        petrol_df=petrol_df,
    )


def al_tut_kiyas(endeks_df: pd.DataFrame, baslangic: str, bitis: str, ozsermaye: float) -> dict:
    """§9: BIST100'ü aynı dönemde al-ve-tut eder — V3 ile BİREBİR aynı."""
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    takvim = endeks_df.loc[(endeks_df.index >= baslangic_ts) & (endeks_df.index <= bitis_ts)].index
    if len(takvim) < 2:
        return {
            "ozsermaye_egrisi": [],
            "metrikler": {"cagr": float("nan"), "maksimum_dusus_%": float("nan"),
                          "giris_tarihi": None, "giris_fiyati": float("nan")},
        }

    giris_tarihi = takvim[0]
    acilis0 = endeks_df.loc[giris_tarihi, "Open"]
    if acilis0 is None or pd.isna(acilis0) or acilis0 <= 0:
        acilis0 = endeks_df.loc[giris_tarihi, "Close"]

    oran = _KOMISYON_ORANI + _KAYMA_NORMAL
    adet = math.floor(float(ozsermaye) / (float(acilis0) * (1.0 + oran)))
    maliyet = adet * acilis0 * oran
    cash = float(ozsermaye) - adet * acilis0 - maliyet

    egri: list[dict] = []
    for T in takvim:
        kapanis = endeks_df.loc[T, "Close"]
        deger = cash + adet * float(kapanis) if not pd.isna(kapanis) else float("nan")
        egri.append({"tarih": T, "ozsermaye": deger})

    seri = pd.Series({e["tarih"]: e["ozsermaye"] for e in egri}).sort_index()
    seri = seri.dropna()

    if seri.empty:
        cagr = float("nan")
        maks_dusus = float("nan")
    else:
        dusus_serisi = (seri / seri.cummax()) - 1.0
        maks_dusus = float(dusus_serisi.min())
        gun_araligi = (seri.index[-1] - seri.index[0]).days
        yil = max(gun_araligi / 365.25, 1e-9)
        cagr = float((seri.iloc[-1] / seri.iloc[0]) ** (1.0 / yil) - 1.0) if seri.iloc[0] > 0 else float("nan")

    return {
        "ozsermaye_egrisi": egri,
        "metrikler": {
            "cagr": cagr,
            "maksimum_dusus_%": maks_dusus,
            "giris_tarihi": giris_tarihi,
            "giris_fiyati": float(acilis0),
        },
    }


def walk_forward(ozsermaye: float = 1_000_000.0) -> dict:
    """§9 doğrulama — V3 ile AYNI yapı; calistir() artık MAKRO katmanı
    kendi içinde uyguladığı için burada ek bir değişikliğe gerek yoktur."""
    print("=" * 70)
    print("V4 WALK-FORWARD (V3 + MAKRO petrol şoku) — Geliştirme: 2019-01-01 → 2023-12-31")
    print("=" * 70)
    gelistirme_v4 = calistir("2019-01-01", "2023-12-31", ozsermaye)

    bugun = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    print("=" * 70)
    print(f"V4 WALK-FORWARD — Test dönemi (DOKUNULMAMIŞ): 2024-01-01 → {bugun}")
    print("=" * 70)
    test_v4 = calistir("2024-01-01", bugun, ozsermaye)

    endeks_ham = veri.fiyat_indir(["XU100.IS"], "2018-06-01", bugun)
    endeks_df = endeks_ham.get("XU100.IS")
    if endeks_df is None or endeks_df.empty:
        raise RuntimeError("XU100.IS verisi al-tut kıyası için indirilemedi.")

    gelistirme_al_tut = al_tut_kiyas(endeks_df, "2019-01-01", "2023-12-31", ozsermaye)
    test_al_tut = al_tut_kiyas(endeks_df, "2024-01-01", bugun, ozsermaye)

    test_metrikleri_kiyaslamali = dict(test_v4["metrikler"])
    test_metrikleri_kiyaslamali["endeks_maksimum_dusus_%"] = test_al_tut["metrikler"]["maksimum_dusus_%"]
    dogrulama = _kabul_kriterlerini_kontrol(test_metrikleri_kiyaslamali)

    print("=" * 70)
    if dogrulama["gecti"]:
        print("SONUÇ: §9 kabul kriterleri GEÇTİ — V4 endeksi yendi, tavsiye verebilir.")
    else:
        print("SONUÇ: §9 kabul kriterleri GEÇMEDİ — TAVSIYE_VERME modu gerekir.")
        for madde in dogrulama["basarisiz_kriterler"]:
            print(f"  - {madde}")
    print("=" * 70)

    return {
        "gelistirme": {"v3": gelistirme_v4, "al_tut": gelistirme_al_tut},
        "test": {"v3": test_v4, "al_tut": test_al_tut},
        "dogrulama": dogrulama,
    }


# ═══════════════════════════════════════════════════════════════════════
# Kendi kendine kontrol — AĞ ÇAĞRISI YOK. V3'teki AYNI look-ahead testi
# (petrol_df=None ile, yani makro katman devre dışı — bu, V4'ün V3 ile
# BİREBİR aynı davrandığını, makro katman verilmediğinde, kanıtlar) +
# EK bir kontrol: petrol şoku verildiğinde hedef_oran'ın gerçekten kısıldığı.
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    n_gun = 560
    tarihler = pd.date_range("2022-01-03", periods=n_gun, freq="B")
    kesim_idx = 460
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

    def _evren_kur(gelecek_kapanis_override=None):
        veriler = {}
        for i, tohum in enumerate((11, 12, 13, 14, 15, 16, 17, 18)):
            df = _rastgele_df(50.0 + i * 5, 0.06, 0.6, 60_000_000, tohum=tohum)
            veriler[f"DOLGU{i}"] = veri.gostergeler(df)
        gelecek_df = _rastgele_df(40.0, 0.04, 0.5, 60_000_000, tohum=99)
        if gelecek_kapanis_override is not None:
            gelecek_df = gelecek_df.copy()
            gelecek_df.loc[gelecek_df.index > kesim_tarih, "Close"] = gelecek_kapanis_override
            gelecek_df.loc[gelecek_df.index > kesim_tarih, "Open"] = gelecek_kapanis_override
            gelecek_df.loc[gelecek_df.index > kesim_tarih, "High"] = gelecek_kapanis_override * 1.01
            gelecek_df.loc[gelecek_df.index > kesim_tarih, "Low"] = gelecek_kapanis_override * 0.99
        veriler["GELECEK"] = veri.gostergeler(gelecek_df)
        return veriler

    veriler_a = _evren_kur(gelecek_kapanis_override=None)

    n_sonrasi = (tarihler > kesim_tarih).sum()
    patlama_seviyesi = 40.0 * (1.6 + np.linspace(0, 0.4, n_sonrasi))
    veriler_b = _evren_kur(gelecek_kapanis_override=patlama_seviyesi)

    baslangic_str = tarihler[350].strftime("%Y-%m-%d")
    bitis_str = tarihler[-1].strftime("%Y-%m-%d")

    print("Senaryo A çalıştırılıyor (patlama YOK, petrol_df=None -> V3 davranışı)...")
    sonuc_a = _calistir_ic(veriler_a, endeks_df, baslangic_str, bitis_str,
                            ozsermaye=1_000_000.0, ilerleme=False,
                            izleme_tarihleri={kesim_tarih})
    print("Senaryo B çalıştırılıyor (GELECEK kesimden sonra %60+ patlıyor)...")
    sonuc_b = _calistir_ic(veriler_b, endeks_df, baslangic_str, bitis_str,
                            ozsermaye=1_000_000.0, ilerleme=False,
                            izleme_tarihleri={kesim_tarih})

    egri_a = {e["tarih"]: e["ozsermaye"] for e in sonuc_a["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    egri_b = {e["tarih"]: e["ozsermaye"] for e in sonuc_b["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    assert set(egri_a.keys()) == set(egri_b.keys()), "Kesim öncesi tarih kümeleri farklı!"
    for t in egri_a:
        fark = abs(egri_a[t] - egri_b[t])
        assert fark < 1e-6, (
            f"LOOK-AHEAD SIZINTISI: {t.date()} günü özsermayesi senaryolar arasında "
            f"farklı çıktı (A={egri_a[t]:.4f}, B={egri_b[t]:.4f})."
        )

    def _pozisyon_ozet(sonuc):
        durum = sonuc["pozisyon_izleme"].get(kesim_tarih, [])
        return sorted(
            (p["sembol"], p["giris_tarihi"], round(p["giris_fiyati"], 6), round(p["adet"], 4))
            for p in durum
        )
    pozisyonlar_a = _pozisyon_ozet(sonuc_a)
    pozisyonlar_b = _pozisyon_ozet(sonuc_b)
    assert len(pozisyonlar_a) > 0, "Test dizaynı hatalı: kesim gününde hiç açık pozisyon yok"
    assert pozisyonlar_a == pozisyonlar_b, (
        f"LOOK-AHEAD SIZINTISI: kesim gününde açık pozisyonlar farklı!\nA={pozisyonlar_a}\nB={pozisyonlar_b}"
    )

    gelecek_a = [p for p in pozisyonlar_a if p[0] == "GELECEK"]
    gelecek_b = [p for p in pozisyonlar_b if p[0] == "GELECEK"]
    assert gelecek_a == gelecek_b
    assert len(gelecek_a) == 1, "Test dizaynı hatalı: GELECEK'te kesim gününde pozisyon bekleniyordu"

    kiyas = al_tut_kiyas(endeks_df, baslangic_str, bitis_str, ozsermaye=1_000_000.0)
    assert not pd.isna(kiyas["metrikler"]["cagr"]), "al_tut_kiyas CAGR NaN çıktı"
    kiyas_seri = pd.Series({e["tarih"]: e["ozsermaye"] for e in kiyas["ozsermaye_egrisi"]}).dropna()
    endeks_araligi = endeks_df.loc[kiyas_seri.index, "Close"]
    oran_serisi = (kiyas_seri - kiyas_seri.iloc[0]) / (endeks_araligi - endeks_araligi.iloc[0]).replace(0, np.nan)
    oran_gecerli = oran_serisi.dropna()
    if len(oran_gecerli) > 5:
        assert oran_gecerli.std() < 1.0, "al_tut_kiyas eğrisi endeksle orantılı büyümüyor (yeniden alım şüphesi)"

    # ── EK kontrol (V4'e özgü): petrol şoku verildiğinde efektif hedef oran
    #    kısılmalı — yani MAKRO katman gerçekten devrede. Sentetik bir Brent
    #    serisi (kesimden SONRA sert şok) ile Senaryo A'yı tekrar çalıştırıp
    #    özsermaye eğrisinin (rejim R1 varsayıp tam yatırım yapan versiyona
    #    göre) FARKLI çıktığını doğruluyoruz. ──
    def _petrol_df_uret(sok_var_mi: bool):
        baz = [80.0] * n_gun
        if sok_var_mi:
            for i in range(kesim_idx, n_gun):
                baz[i] = 80.0 * (1 + 0.35 * min(1.0, (i - kesim_idx) / 20.0))
        return pd.DataFrame({
            "Open": baz, "High": baz, "Low": baz, "Close": baz,
            "Volume": [1_000_000.0] * n_gun,
        }, index=tarihler)

    petrol_soksuz = _petrol_df_uret(False)
    petrol_soklu = _petrol_df_uret(True)

    sonuc_petrol_soksuz = _calistir_ic(veriler_a, endeks_df, baslangic_str, bitis_str,
                                        ozsermaye=1_000_000.0, ilerleme=False,
                                        petrol_df=petrol_soksuz)
    sonuc_petrol_soklu = _calistir_ic(veriler_a, endeks_df, baslangic_str, bitis_str,
                                       ozsermaye=1_000_000.0, ilerleme=False,
                                       petrol_df=petrol_soklu)
    egri_soksuz_son = sonuc_petrol_soksuz["ozsermaye_egrisi"][-1]["ozsermaye"]
    egri_soklu_son = sonuc_petrol_soklu["ozsermaye_egrisi"][-1]["ozsermaye"]
    assert egri_soksuz_son != egri_soklu_son, (
        "MAKRO katman etkisiz görünüyor: petrol şoklu/şoksuz senaryolar aynı sonucu verdi."
    )

    print("v4_backtest.py kendi kendine kontrol (LOOK-AHEAD + MAKRO katman testi): BAŞARILI")
    print(f"  Kesim tarihi: {kesim_tarih.date()}")
    print(f"  Kesim gününde ortak açık pozisyon sayısı: {len(pozisyonlar_a)}")
    print(f"  Senaryo A toplam işlem: {len(sonuc_a['islemler'])}, "
          f"Senaryo B toplam işlem: {len(sonuc_b['islemler'])}")
    print(f"  Senaryo A metrikleri: {sonuc_a['metrikler']}")
    print(f"  al_tut_kiyas metrikleri: {kiyas['metrikler']}")
    print(f"  Petrol şoksuz son özsermaye: {egri_soksuz_son:,.2f} TL")
    print(f"  Petrol şoklu son özsermaye:  {egri_soklu_son:,.2f} TL")
