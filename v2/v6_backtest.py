# -*- coding: utf-8 -*-
"""
v2/v6_backtest.py — Pusula V6 YOĞUNLAŞTIRILMIŞ DÜRÜST backtest motoru.

v3_backtest.py (V3) ÖRNEK ALINARAK (kopyalanmadan, portföy kuralına göre
UYARLANARAK) yazıldı. Üç zorunlu kural (V2/V3'teki gibi) ASLA gevşetilmez:

  1) Sinyal gün T KAPANIŞINDA üretilir; YENİ pozisyon emirleri gün T+1
     AÇILIŞINDA gerçekleşir. Çıkışlar (stop/trailing/rejim/trend/kâr
     hedefi kısmi realizasyonu) o günün KENDİ verisiyle (Low/Close) AYNI
     GÜN uygulanır — bu, pozisyon.py (V2) ile AYNI yorum kararıdır: çıkış
     kuralları riski o gün SINIRLAMAK içindir, ertesi güne ERTELENEMEZ.
  2) Her emir §7/§8 maliyet modelinden (komisyon + kayma) geçer; tavan/
     taban günü YENİ pozisyon açılamaz; gap koruması uygulanır.
  3) Özsermaye eğrisi GÜNLÜK tutulur; pozisyon boyutu GÜNCEL (mark-to-
     market) özsermayeye göre hesaplanır.

V3'ten (başarısız / seyreltilmiş) MİMARİ FARKI: V3 AYLIK ağırlık-rebalansı
yapıyordu (10 pozisyon, %5-15 bant). V6 GÜNLÜK tarama yapar (güçlü kırılımı
kaçırmamak için), ama yalnız v6_skor.py'nin SERT dört şartını birden geçen
az sayıda aday varsa pozisyon açar — dolayısıyla "günlük tarama" turnover'ı
ARTIRMAZ, yalnız FIRSATI erken yakalar (sinyal seyrek, tarama sık).

Rejim kapısı V6'da İKİLİ ve AGRESİF uygulanır (v6_portfoy.hedef_oran_hesapla):
R1 tam yatırım, R2 yarı yatırım, R3/R4 TAM nakit — kademeli yaklaşma YOKTUR
(ne yukarı ne aşağı), çünkü kullanıcı talimatı net: "rejim kapısını AGRESİF
ayarla ... sermaye korumasını rejim kapısı yapsın".
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
import v6_skor
import v6_portfoy

# ─────────────────────────────────────────────────────────────────────────
# §7/§8 maliyet modeli — V2/V3 ile BİREBİR aynı sabitler (tutarlılık şart).
# ─────────────────────────────────────────────────────────────────────────
_KOMISYON_ORANI = 0.0015
_KAYMA_NORMAL = 0.0010
_KAYMA_DUSUK_LIKIDITE = 0.0025
_DUSUK_LIKIDITE_ESIGI = 50_000_000.0
_TAVAN_TABAN_ESIGI = 0.095

_MAKS_POZISYON = v6_portfoy._MAKS_POZISYON
_MIN_POZISYON = v6_portfoy._MIN_POZISYON
_MAKS_GUNLUK_YENI_POZISYON = v6_portfoy._MAKS_GUNLUK_YENI_POZISYON
_STOP_SAYILAN_NEDENLER = ("stop", "trailing")


def _komisyon_kayma_orani(hacim_tl_medyan) -> float:
    if hacim_tl_medyan is None or pd.isna(hacim_tl_medyan) or hacim_tl_medyan < _DUSUK_LIKIDITE_ESIGI:
        return _KOMISYON_ORANI + _KAYMA_DUSUK_LIKIDITE
    return _KOMISYON_ORANI + _KAYMA_NORMAL


def _tavan_taban_mi(df: pd.DataFrame, tarih: pd.Timestamp) -> bool:
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


# ─────────────────────────────────────────────────────────────────────────
# İç simülasyon çekirdeği — veri İNDİRMEDEN, hazır veriyle çalışır (bkz.
# backtest.py / v3_backtest.py'deki AYNI ayrım gerekçesi: __main__ altındaki
# look-ahead testi ağ çağrısı yapamaz, doğrudan bu fonksiyonu çağırır).
# ─────────────────────────────────────────────────────────────────────────
def _calistir_ic(veriler: dict, endeks_df: pd.DataFrame, baslangic: str, bitis: str,
                  ozsermaye: float = 1_000_000.0, ilerleme: bool = True,
                  izleme_tarihleri: set | None = None) -> dict:
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    izleme_tarihleri = izleme_tarihleri or set()
    pozisyon_izleme: dict = {}

    takvim = endeks_df.loc[(endeks_df.index >= baslangic_ts) & (endeks_df.index <= bitis_ts)].index
    if len(takvim) == 0:
        return {
            "islemler": [], "ozsermaye_egrisi": [], "pozisyon_izleme": {},
            "metrikler": _metrikleri_hesapla([], [], endeks_df, baslangic_ts, bitis_ts),
        }

    cash = float(ozsermaye)
    acik_pozisyonlar: list[dict] = []
    islemler: list[dict] = []
    ozsermaye_egrisi: list[dict] = []
    pending_orders: list[dict] = []
    son_stop_tarihleri: dict[str, pd.Timestamp] = {}
    son_fiyat_satiri: dict[str, pd.Series] = {}

    toplam_gun = len(takvim)
    for idx, T in enumerate(takvim):
        # ── 1) Dünün emirlerini bugünün AÇILIŞINDA gerçekleştir (yalnız
        #        YENİ pozisyonlar T+1'e ertelenir; çıkışlar aşağıda AYNI
        #        gün işlenir). ──────────────────────────────────────────
        bugun_acilan_sayisi = 0
        for emir in pending_orders:
            if bugun_acilan_sayisi >= _MAKS_GUNLUK_YENI_POZISYON:
                break
            if len(acik_pozisyonlar) >= _MAKS_POZISYON:
                break
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
            if acilis < emir["teorik_stop"]:
                continue  # GAP KORUMASI: T+1 açılışı (T'nin kapanışına göre
                          # hesaplanan) teorik stopun altında -> açılmaz

            oran = _komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
            adet = emir["adet"]
            maliyet_giris = adet * acilis * oran
            gerekli_nakit = adet * acilis + maliyet_giris
            if gerekli_nakit > cash:
                adet = math.floor(cash / (acilis * (1.0 + oran)))
                if adet < 1:
                    continue
                maliyet_giris = adet * acilis * oran
            cash -= (adet * acilis + maliyet_giris)

            # GERÇEK stop, T+1'in GERÇEK açılış fiyatına göre (T'nin ATR'si
            # kullanılarak) YENİDEN hesaplanır — emir["teorik_stop"] yalnız
            # yukarıdaki gap-koruması eşiği içindi (T'nin kapanışına göre).
            # Böylece stop mesafesi, gap sonrası da niyet edilen [-%8,-%10]
            # bandını GERÇEK giriş fiyatına göre korur (v2/backtest.py'nin
            # `ilk_stop = acilis - 2.5*atr_T` deseniyle AYNI mantık).
            stop_bilgi_gercek = v6_portfoy.giris_stop_hesapla(float(acilis), emir["atr_giris"])
            ilk_stop_gercek = stop_bilgi_gercek["stop"]

            acik_pozisyonlar.append({
                "sembol": sembol,
                "giris_tarihi": T,
                "giris_fiyati": float(acilis),
                "ilk_stop": ilk_stop_gercek,
                "guncel_stop": ilk_stop_gercek,
                "en_yuksek_kapanis": float(acilis),
                "gun_sayisi": 0,
                "ust_uste_ma200_alti": 0,
                "sektor": v6_portfoy._sektor_bul(sembol),
                "adet": adet,
                "maliyet_giris_tl": maliyet_giris,
                "kar_hedefi_1_alindi": False,
                "skor_giriste": emir["skor"],
                "rejim_giriste": emir["rejim_giriste"],
            })
            bugun_acilan_sayisi += 1
        pending_orders = []

        # ── 2) Rejim — İKİLİ/AGRESİF eşleme (kademeli yaklaşma YOK). ───────
        rejim_bugun = rejim.rejim_hesapla(endeks_df, veriler, T)
        efektif_hedef_oran = v6_portfoy.hedef_oran_hesapla(rejim_bugun["rejim"])
        rejim_ile_hedef = dict(rejim_bugun)
        rejim_ile_hedef["hedef_oran"] = efektif_hedef_oran

        # ── 3) Açık pozisyonlar: trailing güncelle, sonra TAM çıkış /
        #        kısmi kâr realizasyonu kontrolü (AYNI gün). ────────────────
        kapanislar_bugun: dict[str, float] = {}
        kalan_pozisyonlar: list[dict] = []
        for poz in acik_pozisyonlar:
            sembol = poz["sembol"]
            df = veriler.get(sembol)
            if df is None or T not in df.index:
                # Veri eksikse (yfinance boşluğu/tatil vb.) pozisyona o gün
                # DOKUNULMAZ, ama mark-to-market'te değeri SIFIRLANMASIN diye
                # (bkz. v3_backtest.py'deki AYNI KRİTİK MUHASEBE DÜZELTMESİ
                # notu) son bilinen kapanışla forward-fill edilir.
                son_bilinen = son_fiyat_satiri.get(sembol)
                if son_bilinen is not None:
                    kapanislar_bugun[sembol] = float(son_bilinen["Close"])
                kalan_pozisyonlar.append(poz)
                continue
            satir = df.loc[T]
            son_fiyat_satiri[sembol] = satir
            kapanislar_bugun[sembol] = float(satir["Close"])
            poz = v6_portfoy.trailing_guncelle(poz, satir)

            if _tavan_taban_mi(df, T):
                # Kilitli gün — ne tam çıkış ne kısmi realizasyon yapılabilir.
                kalan_pozisyonlar.append(poz)
                continue

            tam_cikis = v6_portfoy.cikis_kontrol(poz, satir, rejim_ile_hedef)
            if tam_cikis is not None:
                fiyat = tam_cikis["fiyat"]
                oran = _komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
                maliyet_cikis = poz["adet"] * fiyat * oran
                hasilat = poz["adet"] * fiyat - maliyet_cikis
                cash += hasilat
                toplam_maliyet = poz.get("maliyet_giris_tl", 0.0) + maliyet_cikis
                net_pnl = hasilat - poz["adet"] * poz["giris_fiyati"] - poz.get("maliyet_giris_tl", 0.0)
                islemler.append({
                    "sembol": sembol, "giris_tarihi": poz["giris_tarihi"], "cikis_tarihi": T,
                    "giris_fiyati": poz["giris_fiyati"], "cikis_fiyati": float(fiyat),
                    "adet": poz["adet"], "cikis_nedeni": tam_cikis["neden"],
                    "gun_sayisi": poz.get("gun_sayisi", 0),
                    "net_pnl_tl": float(net_pnl), "toplam_maliyet_tl": float(toplam_maliyet),
                    "rejim_giriste": poz.get("rejim_giriste"), "kismi_mi": False,
                })
                if tam_cikis["neden"] in _STOP_SAYILAN_NEDENLER:
                    son_stop_tarihleri[sembol] = T
                continue  # pozisyon tamamen kapandı, kalan_pozisyonlar'a EKLENMEZ

            kismi = v6_portfoy.kar_hedefi_kontrol(poz, satir)
            if kismi is not None:
                satilacak_adet = int(poz["adet"] * kismi["satis_payi"])
                if satilacak_adet >= 1:
                    fiyat = kismi["fiyat"]
                    oran = _komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
                    maliyet_cikis = satilacak_adet * fiyat * oran
                    hasilat = satilacak_adet * fiyat - maliyet_cikis
                    cash += hasilat
                    onceki_adet = poz["adet"]
                    oran_pay = satilacak_adet / onceki_adet if onceki_adet > 0 else 0.0
                    maliyet_giris_pay = poz.get("maliyet_giris_tl", 0.0) * oran_pay
                    net_pnl = hasilat - satilacak_adet * poz["giris_fiyati"] - maliyet_giris_pay
                    islemler.append({
                        "sembol": sembol, "giris_tarihi": poz["giris_tarihi"], "cikis_tarihi": T,
                        "giris_fiyati": poz["giris_fiyati"], "cikis_fiyati": float(fiyat),
                        "adet": satilacak_adet, "cikis_nedeni": "kar_hedefi_kismi",
                        "gun_sayisi": poz.get("gun_sayisi", 0),
                        "net_pnl_tl": float(net_pnl), "toplam_maliyet_tl": float(maliyet_cikis + maliyet_giris_pay),
                        "rejim_giriste": poz.get("rejim_giriste"), "kismi_mi": True,
                    })
                    poz["adet"] = onceki_adet - satilacak_adet
                    poz["maliyet_giris_tl"] = poz.get("maliyet_giris_tl", 0.0) - maliyet_giris_pay
                    poz["kar_hedefi_1_alindi"] = True
                    poz["guncel_stop"] = max(poz.get("guncel_stop", poz["ilk_stop"]), kismi["yeni_stop"])
                else:
                    poz["kar_hedefi_1_alindi"] = True  # çok küçük pozisyon, bölünemez ama bayrak yine set

            kalan_pozisyonlar.append(poz)
        acik_pozisyonlar = kalan_pozisyonlar

        # ── 4) Evren + sinyal — GÜNLÜK tarama. ──────────────────────────────
        mevcut_yatirim_deger = sum(
            kapanislar_bugun.get(p["sembol"], p["giris_fiyati"]) * p["adet"] for p in acik_pozisyonlar
        )
        guncel_ozsermaye = cash + mevcut_yatirim_deger

        if guncel_ozsermaye < -0.01 * max(ozsermaye, 1.0):
            raise RuntimeError(
                f"[v6_backtest] MUHASEBE HATASI: {T.date()} günü özsermaye ({guncel_ozsermaye:,.2f} TL) "
                f"aşırı negatif — emir doldurma/nakit hesabında bir hata var."
            )

        if efektif_hedef_oran > 0 and len(acik_pozisyonlar) < _MAKS_POZISYON:
            evren_guncel = evren.evren_olustur(veriler, T)
            siralama = v6_skor.skorla(veriler, evren_guncel, T)
            acik_semboller = {p["sembol"] for p in acik_pozisyonlar}
            yeni_kuyruk_sayisi = 0
            for aday in siralama:
                if yeni_kuyruk_sayisi >= _MAKS_GUNLUK_YENI_POZISYON:
                    break
                if len(acik_pozisyonlar) + yeni_kuyruk_sayisi >= _MAKS_POZISYON:
                    break
                if not aday.get("uygun", False):
                    continue
                sembol = aday["sembol"]
                if sembol in acik_semboller:
                    continue
                df = veriler.get(sembol)
                if df is None or T not in df.index:
                    continue
                satir = df.loc[T]
                kapanis_bugun = satir.get("Close")
                atr_bugun = satir.get("ATR14")

                aday_kisit = {"sembol": sembol, "kapanis": kapanis_bugun, "tarih": T}
                red = v6_portfoy.portfoy_kisit_kontrol(
                    aday_kisit, acik_pozisyonlar, yeni_kuyruk_sayisi, son_stop_tarihleri,
                )
                if red is not None:
                    continue

                hedef_agirlik = v6_portfoy.hedef_agirlik_hesapla(
                    len(acik_pozisyonlar) + yeni_kuyruk_sayisi, efektif_hedef_oran,
                )
                boyut = v6_portfoy.pozisyon_boyutu(
                    ozsermaye=guncel_ozsermaye, kapanis=kapanis_bugun, atr=atr_bugun,
                    hacim_tl_medyan=satir.get("HACIM_TL_MEDYAN20"),
                    mevcut_yatirim=mevcut_yatirim_deger, hedef_agirlik=hedef_agirlik,
                )
                if boyut["red_nedeni"] is not None or boyut["adet"] < 1:
                    continue

                pending_orders.append({
                    "sembol": sembol, "adet": boyut["adet"], "teorik_stop": boyut["stop"],
                    "atr_giris": atr_bugun,
                    "skor": aday["skor"], "rejim_giriste": rejim_bugun["rejim"],
                })
                mevcut_yatirim_deger += boyut["deger"]
                yeni_kuyruk_sayisi += 1

        # ── 5) Günlük özsermaye kaydı (mark-to-market, bugünün çıkışları
        #        sonrası, YARININ girişleri HARİÇ). ───────────────────────
        mtm = sum(kapanislar_bugun.get(p["sembol"], p["giris_fiyati"]) * p["adet"] for p in acik_pozisyonlar)
        ozsermaye_egrisi.append({"tarih": T, "ozsermaye": cash + mtm})

        if T in izleme_tarihleri:
            pozisyon_izleme[T] = [dict(p) for p in acik_pozisyonlar]

        if ilerleme and (idx % 100 == 0 or idx == toplam_gun - 1):
            print(f"[v6_backtest] {idx + 1}/{toplam_gun} gün işlendi ({T.date()}) — "
                  f"açık pozisyon: {len(acik_pozisyonlar)}, rejim: {rejim_bugun['rejim']}, "
                  f"özsermaye: {cash + mtm:,.0f} TL")

    metrikler = _metrikleri_hesapla(islemler, ozsermaye_egrisi, endeks_df, baslangic_ts, bitis_ts)
    return {"islemler": islemler, "ozsermaye_egrisi": ozsermaye_egrisi,
            "pozisyon_izleme": pozisyon_izleme, "metrikler": metrikler}


def _metrikleri_hesapla(islemler: list[dict], ozsermaye_egrisi: list[dict],
                         endeks_df: pd.DataFrame, baslangic_ts: pd.Timestamp,
                         bitis_ts: pd.Timestamp) -> dict:
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
        en_kotu = {"sembol": en_kotu_islem["sembol"], "net_pnl_tl": en_kotu_islem["net_pnl_tl"],
                   "cikis_nedeni": en_kotu_islem["cikis_nedeni"]}

    if ozsermaye_egrisi:
        seri = pd.Series({e["tarih"]: e["ozsermaye"] for e in ozsermaye_egrisi}).sort_index()
        seri = seri.dropna()  # bkz. v2/backtest.py'deki AYNI kritik dropna notu
        if seri.empty:
            maks_dusus = float("nan")
            cagr = float("nan")
        else:
            dusus_serisi = (seri / seri.cummax()) - 1.0
            maks_dusus = float(dusus_serisi.min())
            gun_araligi = (seri.index[-1] - seri.index[0]).days
            yil = max(gun_araligi / 365.25, 1e-9)
            cagr = float((seri.iloc[-1] / seri.iloc[0]) ** (1.0 / yil) - 1.0) if seri.iloc[0] > 0 else float("nan")
    else:
        maks_dusus = float("nan")
        cagr = float("nan")

    endeks_araligi = endeks_df.loc[(endeks_df.index >= baslangic_ts) & (endeks_df.index <= bitis_ts)]
    if len(endeks_araligi) >= 2 and endeks_araligi["Close"].iloc[0] > 0:
        gun_e = (endeks_araligi.index[-1] - endeks_araligi.index[0]).days
        yil_e = max(gun_e / 365.25, 1e-9)
        endeks_cagr = float((endeks_araligi["Close"].iloc[-1] / endeks_araligi["Close"].iloc[0]) ** (1.0 / yil_e) - 1.0)
    else:
        endeks_cagr = float("nan")

    endeks_ustu_fark = (cagr - endeks_cagr) if not (pd.isna(cagr) or pd.isna(endeks_cagr)) else float("nan")

    return {
        "islem_sayisi": n, "kazanma_orani": kazanma_orani, "profit_factor": pf,
        "maksimum_dusus_%": maks_dusus, "cagr": cagr, "endeks_cagr": endeks_cagr,
        "endeks_ustu_fark": endeks_ustu_fark, "en_kotu_islem": en_kotu,
    }


# Kullanıcının SABİT hedefi (pazarlık yok): CAGR >= %55, maksimum düşüş
# <= %25, profit factor >= 1.3 — TEST dönemi (2024-01-01 -> bugün) üzerinde.
_HEDEF_CAGR = 0.55
_HEDEF_MAKS_DUSUS = 0.25
_HEDEF_PF = 1.3


def _kabul_kriterlerini_kontrol(test_metrikleri: dict) -> dict:
    basarisiz: list[str] = []

    cagr = test_metrikleri.get("cagr", float("nan"))
    if not (isinstance(cagr, (int, float)) and not pd.isna(cagr) and cagr >= _HEDEF_CAGR):
        cagr_yuzde = cagr * 100 if isinstance(cagr, (int, float)) and not pd.isna(cagr) else float("nan")
        basarisiz.append(f"CAGR %{cagr_yuzde:.2f} — eşik: >=%{_HEDEF_CAGR * 100:.0f}")

    maks_dusus = test_metrikleri.get("maksimum_dusus_%", float("nan"))
    if not (isinstance(maks_dusus, (int, float)) and not pd.isna(maks_dusus) and abs(maks_dusus) <= _HEDEF_MAKS_DUSUS):
        basarisiz.append(f"Maksimum düşüş %{abs(maks_dusus) * 100:.1f} — eşik: <=%{_HEDEF_MAKS_DUSUS * 100:.0f}")

    pf = test_metrikleri.get("profit_factor", float("nan"))
    if not (isinstance(pf, (int, float)) and not pd.isna(pf) and pf >= _HEDEF_PF):
        pf_metni = f"{pf:.2f}" if isinstance(pf, (int, float)) and not pd.isna(pf) else "—"
        basarisiz.append(f"Profit factor {pf_metni} — eşik: >={_HEDEF_PF}")

    return {"gecti": len(basarisiz) == 0, "basarisiz_kriterler": basarisiz}


def calistir(baslangic: str, bitis: str, ozsermaye: float = 1_000_000.0) -> dict:
    """Veriyi indirir/hazırlar, ardından _calistir_ic ile simüle eder."""
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    indirme_baslangic = (baslangic_ts - pd.Timedelta(days=550)).strftime("%Y-%m-%d")
    bitis_str = bitis_ts.strftime("%Y-%m-%d")

    print(f"[v6_backtest] Veri indiriliyor: {len(evren.TEMEL_SEMBOLLER)} sembol + XU100.IS "
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
        veriler[sembol] = veri.gostergeler(df)
    print(f"[v6_backtest] {len(veriler)}/{len(evren.TEMEL_SEMBOLLER)} sembol için veri hazır.")

    return _calistir_ic(veriler, endeks_df, baslangic, bitis, ozsermaye)


def al_tut_kiyas(endeks_df: pd.DataFrame, baslangic: str, bitis: str, ozsermaye: float) -> dict:
    """BIST100'ü aynı dönemde al-ve-tut eder (TEK alım maliyeti) — v3_backtest.al_tut_kiyas
    ile AYNI mantık (bilinçli olarak; bu bir kıyas ölçütü, V6'ya özgü bir tasarım kararı değil).
    """
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    takvim = endeks_df.loc[(endeks_df.index >= baslangic_ts) & (endeks_df.index <= bitis_ts)].index
    if len(takvim) < 2:
        return {"ozsermaye_egrisi": [],
                "metrikler": {"cagr": float("nan"), "maksimum_dusus_%": float("nan")}}

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

    seri = pd.Series({e["tarih"]: e["ozsermaye"] for e in egri}).sort_index().dropna()
    if seri.empty:
        cagr = float("nan")
        maks_dusus = float("nan")
    else:
        dusus_serisi = (seri / seri.cummax()) - 1.0
        maks_dusus = float(dusus_serisi.min())
        gun_araligi = (seri.index[-1] - seri.index[0]).days
        yil = max(gun_araligi / 365.25, 1e-9)
        cagr = float((seri.iloc[-1] / seri.iloc[0]) ** (1.0 / yil) - 1.0) if seri.iloc[0] > 0 else float("nan")

    return {"ozsermaye_egrisi": egri, "metrikler": {"cagr": cagr, "maksimum_dusus_%": maks_dusus,
                                                     "giris_tarihi": giris_tarihi, "giris_fiyati": float(acilis0)}}


def walk_forward(ozsermaye: float = 1_000_000.0) -> dict:
    """Geliştirme (2019-2023) + TEST (2024-bugün, DOKUNULMAMIŞ) dönemleri.

    `dogrulama`, kullanıcının SABİT hedefine göre (CAGR>=%55, maksimum düşüş
    <=%25, profit factor>=1.3) YALNIZ test dönemi üzerinde hesaplanır.
    """
    print("=" * 70)
    print("V6 WALK-FORWARD — Geliştirme dönemi: 2019-01-01 → 2023-12-31")
    print("=" * 70)
    gelistirme = calistir("2019-01-01", "2023-12-31", ozsermaye)

    bugun = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    print("=" * 70)
    print(f"V6 WALK-FORWARD — Test dönemi (DOKUNULMAMIŞ): 2024-01-01 → {bugun}")
    print("=" * 70)
    test = calistir("2024-01-01", bugun, ozsermaye)

    endeks_ham = veri.fiyat_indir(["XU100.IS"], "2018-06-01", bugun)
    endeks_df = endeks_ham.get("XU100.IS")
    al_tut_gelistirme = al_tut_kiyas(endeks_df, "2019-01-01", "2023-12-31", ozsermaye) if endeks_df is not None else None
    al_tut_test = al_tut_kiyas(endeks_df, "2024-01-01", bugun, ozsermaye) if endeks_df is not None else None

    dogrulama = _kabul_kriterlerini_kontrol(test["metrikler"])

    print("=" * 70)
    if dogrulama["gecti"]:
        print("SONUÇ: kullanıcı hedefi (CAGR>=%55, düşüş<=%25, PF>=1.3) GEÇİLDİ.")
    else:
        print("SONUÇ: kullanıcı hedefi GEÇİLEMEDİ.")
        for madde in dogrulama["basarisiz_kriterler"]:
            print(f"  - {madde}")
    print("=" * 70)

    return {"gelistirme": gelistirme, "test": test, "dogrulama": dogrulama,
            "al_tut_gelistirme": al_tut_gelistirme, "al_tut_test": al_tut_test}


# ═══════════════════════════════════════════════════════════════════════
# Kendi kendine kontrol — AĞ ÇAĞRISI YOK. backtest.py/v3_backtest.py'deki
# AYNI desenle: sentetik veride gelecekte "patlayan" bir hisse eklenip,
# patlamadan ÖNCEKİ tüm günlerin sonuçlarının (özsermaye eğrisi + kesim
# gününde açık pozisyonlar) o patlama YOKMUŞ gibi çıkan sonuçlarla BİREBİR
# aynı olduğu kanıtlanır.
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    n_gun = 560
    tarihler = pd.date_range("2022-01-03", periods=n_gun, freq="B")
    kesim_idx = 460
    kesim_tarih = tarihler[kesim_idx]

    def _rastgele_df(baslangic_fiyat, egim, gurultu, hacim, tohum, hacim_patlamasi_gunu=None):
        r = np.random.default_rng(tohum)
        egilim = baslangic_fiyat + np.arange(n_gun) * egim
        kapanis = egilim + r.normal(0, gurultu, n_gun)
        kapanis = np.maximum(kapanis, 1.0)
        acilis = kapanis - r.normal(0, gurultu * 0.3, n_gun)
        yuksek = np.maximum(acilis, kapanis) + np.abs(r.normal(0.3, 0.15, n_gun))
        dusuk = np.minimum(acilis, kapanis) - np.abs(r.normal(0.3, 0.15, n_gun))
        hacim_serisi = r.integers(int(hacim * 0.8), int(hacim * 1.2), n_gun).astype(float)
        if hacim_patlamasi_gunu is not None:
            hacim_serisi[hacim_patlamasi_gunu:] = hacim * 3.0
        return pd.DataFrame({
            "Open": acilis, "High": yuksek, "Low": dusuk, "Close": kapanis, "Volume": hacim_serisi,
        }, index=tarihler)

    endeks_df = _rastgele_df(5000, 3.0, 20.0, 50_000_000, tohum=1)

    def _evren_kur(gelecek_kapanis_override=None):
        veriler = {}
        for i, tohum in enumerate((11, 12, 13, 14, 15, 16, 17, 18)):
            # Dolgu semboller de KIRILIM koşullarını (trend + hacim patlaması)
            # taşısın ki v6_skor'un sert filtreleri en azından bazı adayları
            # geçebilsin, sistem "hep boş" dönmesin.
            df = _rastgele_df(50.0 + i * 5, 0.25, 0.6, 60_000_000, tohum=tohum, hacim_patlamasi_gunu=200)
            veriler[f"DOLGU{i}"] = veri.gostergeler(df)
        gelecek_df = _rastgele_df(40.0, 0.20, 0.5, 60_000_000, tohum=99, hacim_patlamasi_gunu=200)
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

    print("Senaryo A çalıştırılıyor (patlama YOK)...")
    sonuc_a = _calistir_ic(veriler_a, endeks_df, baslangic_str, bitis_str,
                            ozsermaye=1_000_000.0, ilerleme=False, izleme_tarihleri={kesim_tarih})
    print("Senaryo B çalıştırılıyor (GELECEK kesimden sonra %60+ patlıyor)...")
    sonuc_b = _calistir_ic(veriler_b, endeks_df, baslangic_str, bitis_str,
                            ozsermaye=1_000_000.0, ilerleme=False, izleme_tarihleri={kesim_tarih})

    egri_a = {e["tarih"]: e["ozsermaye"] for e in sonuc_a["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    egri_b = {e["tarih"]: e["ozsermaye"] for e in sonuc_b["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    assert set(egri_a.keys()) == set(egri_b.keys()), "Kesim öncesi tarih kümeleri farklı!"
    for t in egri_a:
        fark = abs(egri_a[t] - egri_b[t])
        assert fark < 1e-6, (
            f"LOOK-AHEAD SIZINTISI: {t.date()} günü özsermayesi senaryolar arasında farklı çıktı "
            f"(A={egri_a[t]:.4f}, B={egri_b[t]:.4f})."
        )

    def _pozisyon_ozet(sonuc):
        durum = sonuc["pozisyon_izleme"].get(kesim_tarih, [])
        return sorted((p["sembol"], p["giris_tarihi"], round(p["giris_fiyati"], 6), round(p["adet"], 4))
                      for p in durum)

    pozisyonlar_a = _pozisyon_ozet(sonuc_a)
    pozisyonlar_b = _pozisyon_ozet(sonuc_b)
    assert pozisyonlar_a == pozisyonlar_b, (
        f"LOOK-AHEAD SIZINTISI: kesim gününde açık pozisyonlar farklı!\nA={pozisyonlar_a}\nB={pozisyonlar_b}"
    )

    gelecek_a = [p for p in pozisyonlar_a if p[0] == "GELECEK"]
    gelecek_b = [p for p in pozisyonlar_b if p[0] == "GELECEK"]
    assert gelecek_a == gelecek_b

    print("v6_backtest.py kendi kendine kontrol (LOOK-AHEAD testi): BAŞARILI")
    print(f"  Kesim tarihi: {kesim_tarih.date()}")
    print(f"  Kesim gününde ortak açık pozisyon sayısı: {len(pozisyonlar_a)}")
    print(f"  Senaryo A toplam işlem: {len(sonuc_a['islemler'])}, "
          f"Senaryo B toplam işlem: {len(sonuc_b['islemler'])}")
    print(f"  Senaryo A metrikleri: {sonuc_a['metrikler']}")
