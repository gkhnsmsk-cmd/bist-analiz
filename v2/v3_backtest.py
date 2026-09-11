# -*- coding: utf-8 -*-
"""
v2/v3_backtest.py — Pusula V3 DÜRÜST backtest motoru (§6, §8, §9).

backtest.py (V2) örnek alınarak (kopyalanmadan, uyarlanarak) yazıldı. Üç
zorunlu kural V2'deki gibi asla gevşetilmez:

  1) Sinyal gün T KAPANIŞINDA üretilir; emir gün T+1 AÇILIŞINDA gerçekleşir.
  2) Her emir §8 maliyet modelinden (komisyon + kayma) geçer; tavan/taban
     günü işlem yapılamaz.
  3) Özsermaye eğrisi GÜNLÜK tutulur; pozisyon boyutu GÜNCEL (mark-to-market)
     özsermayeye göre hesaplanır.

V2'den FARKI (bilerek): V3'te sinyal/rebalans AYLIK'tır (her 20 işlem günü),
günlük olarak yalnız İKİ kontrol çalışır (felaket stopu + rejim çıkışı,
v3_portfoy.gunluk_kontrol üzerinden) — trailing/zaman/kâr-hedefi YOKTUR.
Bu, STRATEJI_V3.md §0'da teşhis edilen V2 hatasının (piyasa dışında geçen
zamanın bileşik kaybı) doğrudan çözümüdür.

KABUL KRİTERİ (§9) V2'den TAMAMEN FARKLI: artık "endeksi yenmek zorunlu".
Bu yüzden `al_tut_kiyas()` fonksiyonu bu dosyada BİRİNCİ SINIF bir
vatandaştır — raporun var olma sebebi bu kıyastır.
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

# ─────────────────────────────────────────────────────────────────────────
# §8 — Maliyet modeli (V2 §7 ile AYNI değerler, şartname gereği).
# ─────────────────────────────────────────────────────────────────────────
_KOMISYON_ORANI = 0.0015          # tek yön
_KAYMA_NORMAL = 0.0010            # tek yön, 20g medyan TL hacim >= eşik
_KAYMA_DUSUK_LIKIDITE = 0.0025    # tek yön, 20g medyan TL hacim < eşik
_DUSUK_LIKIDITE_ESIGI = 50_000_000.0

# evren.py ile AYNI tavan/taban proxy eşiği (tutarlılık şart).
_TAVAN_TABAN_ESIGI = 0.095

# §6 — rebalans her 20 işlem günü (≈ aylık).
_REBALANS_ARALIGI = 20

# §7 — rejim yükselirken günde en fazla %33 puan kademeli yaklaşma (V3
# güncellemesi; V2'de %25'ti). Düşerken anında (rejim.rejim_hesapla zaten
# o günün NİHAİ hedefini döner, kademeleme yalnız YÜKSELİRKEN uygulanır).
_KADEMELI_ADIM = 0.33

# §6 — sapma %5 puandan küçükse dokunulmaz (gereksiz turnover'ı önler).
_AGIRLIK_TOLERANSI = 0.05

_YIL_ISLEM_GUNU = 252
_TURNOVER_ESIGI_YILLIK = 6.00   # §9: yıllık turnover <= %600
_MIN_REBALANS_SAYISI = 24        # §9

# ── DENEY DESTEĞİ (deney_lab.py) — v3_portfoy.py'nin §5 sabitlerinin AYNISI.
# `pozisyon_sayisi` parametresi verilmediğinde bunların HİÇBİRİ kullanılmaz
# (v3_portfoy kendi sabitlerini kullanır), yani mevcut V3 davranışı birebir
# korunur. Verildiğinde ise portföy geometrisi pozisyon sayısıyla ORANTILI
# olarak ölçeklenir: N=10 için hesaplanan değerler §5 sabitleriyle AYNIDIR
# (tampon 20, band %5-%15, sektör 3, tolerans %5) — yani ölçekleme mevcut
# tasarımın genelleştirilmesidir, farklı bir tasarım değil.
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
    """Bugünün kapanış getirisi mutlak %9.5'i geçiyorsa tavan/taban proxy'si.

    evren.py ile AYNI eşik/mantık (§8: "Tavan/taban günü işlem yok").
    """
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
# İç simülasyon çekirdeği — veri İNDİRMEDEN, hazır veriyle çalışır (bkz.
# backtest.py'deki AYNI ayrım gerekçesi: __main__ altındaki look-ahead
# testi ağ çağrısı yapamaz, doğrudan bu fonksiyonu sentetik veriyle çağırır).
# ─────────────────────────────────────────────────────────────────────────
def _calistir_ic(veriler: dict, endeks_df: pd.DataFrame, baslangic: str, bitis: str,
                  ozsermaye: float = 1_000_000.0, ilerleme: bool = True,
                  izleme_tarihleri: set | None = None,
                  rejim_kapisi_aktif: bool = True,
                  rebalans_gun: int | None = None,
                  pozisyon_sayisi: int | None = None) -> dict:
    """izleme_tarihleri: YALNIZ self-test için — verilen tarihlerde açık
    pozisyonların anlık (o günkü) kopyasını `pozisyon_izleme` içine alır.
    Üretimde (calistir()/walk_forward()) KULLANILMAZ (None -> sıfır ek
    maliyet); amaç, HÂLÂ AÇIK olan (hiç kapanmamış) pozisyonların da
    look-ahead testine dahil edilebilmesidir — `islemler` listesi yalnız
    KAPANAN işlemleri kaydeder, aylık rebalans + trend-takibi tarzı bir
    sistemde birçok pozisyon backtest boyunca hiç kapanmayabilir.

    DENEY PARAMETRELERİ (deney_lab.py için; VARSAYILANLARI mevcut V3
    davranışını BİREBİR korur — bu üçü dokunulmadığında tek bir satır kod
    yolu bile değişmez):
      rejim_kapisi_aktif=True : False ise rejim.rejim_hesapla() sonucu
          KULLANILMAZ; her gün R1/%100 varsayılır (rejim kaynaklı R3/R4
          çıkışları da devre dışı kalır). Felaket stopu ve hisse bazlı
          "Kapanış < MA200 -> sat" kuralı AYNEN çalışmaya devam eder.
      rebalans_gun=None       : None ise §6'daki 20 işlem günü.
      pozisyon_sayisi=None    : None ise v3_portfoy'un §5 sabitleri (10
          pozisyon). Bir sayı verilirse tampon/ağırlık bandı/sektör tavanı/
          ağırlık toleransı bu sayıyla ORANTILI ölçeklenir.
    """
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    izleme_tarihleri = izleme_tarihleri or set()
    pozisyon_izleme: dict = {}

    # ── Deney parametrelerinin çözümlenmesi (varsayılanlar = mevcut V3). ──
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
        # ÖNEMLİ: tolerans da ölçeklenmeli. Aksi halde N=20'de hedef ağırlık
        # (~%2.5) sabit %5'lik toleransın ALTINDA kalır ve motor HİÇBİR alım
        # emri üretmez — deney sessizce "hep nakitte" bir sonuç verirdi.
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
    # KRİTİK MUHASEBE DÜZELTMESİ: `takvim` XU100.IS endeksinin tarih index'inden
    # türetiliyor; ama TEK TEK hisselerin DataFrame'i (ayrı ayrı indirilen/
    # önbelleklenen) o GÜN İÇİN bir satıra sahip olmayabilir (tatil öncesi
    # yarım seans, o hisseye özel veri gecikmesi/eksikliği, yfinance toplu
    # indirmenin "sessizce bazı sembolleri atlaması" — bkz. veri.py
    # _TOPLU_BOYUT notu). Bu satır önceden mark-to-market toplamından
    # SESSİZCE düşürülüyordu (bkz. aşağıdaki eski kod), bu da elde tutulan
    # bir pozisyonu o GÜN İÇİN "değeri 0'mış gibi" saymak anlamına geliyordu
    # — ertesi gün veri geri gelince özsermaye birebir eski seviyesine
    # sıçrıyor. Bu, sahte (gerçek olmayan) tek-günlük çöküş+tam-toparlanma
    # döngüleri üretip maksimum düşüş metriğini anlamsızlaştırıyordu (bkz.
    # 2024-04-09 ve 2026-09-07 örnekleri). Düzeltme: veri eksik olan bir gün
    # için pozisyon SON BİLİNEN kapanış fiyatıyla değerlenir (forward-fill),
    # asla sıfırlanmaz.
    son_fiyat_satiri: dict[str, pd.Series] = {}

    for idx, T in enumerate(takvim):
        # ── 1) Dünün (T-1 kapanışında karara bağlanan) emirlerini bugünün
        #        AÇILIŞINDA gerçekleştir. §8 zorunlu kuralı burada uygulanır. ──
        for emir in pending_orders:
            sembol = emir["sembol"]
            df = veriler.get(sembol)
            if df is None or T not in df.index:
                continue  # veri yok → emir düşer (gerçekleşmez)
            if _tavan_taban_mi(df, T):
                # Tavan/taban günü işlem yapılamaz → emir bugün düşer. Not:
                # bir sonraki günde koşul (felaket stop/rejim/rebalans
                # sapması) hâlâ geçerliyse, aşağıdaki adımlar (2-5) bu
                # koşulu O GÜN İÇİN YENİDEN üretip kuyruğa alacaktır —
                # ayrı bir "ertelenmiş emir" defteri tutmaya gerek yok,
                # günlük kontrol zaten idempotent biçimde her gün çalışıyor.
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
                        # Nakit yetersizse (yuvarlama/eşzamanlı emirler
                        # nedeniyle) mümkün olan en büyük tam paya küçült —
                        # sessizce başarısız olmak yerine kısmi gerçekleşme.
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
                        # Mevcut pozisyona EKLEME: giriş fiyatı ağırlıklı
                        # ortalamaya güncellenir (felaket stopu -%25 GİRİŞ
                        # fiyatına göre tanımlı olduğundan bu güncelleme
                        # doğrudan risk hesabını etkiler — es geçilemez).
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
                    # Kısmi azaltmanın maliyet payını orantılı düş (kalan
                    # pozisyonun ortalama maliyet tabanını bozmamak için) —
                    # oran, adet güncellenmeden ÖNCEki (eski) adede göre
                    # hesaplanmalı, aksi halde pay yanlış çıkar.
                    onceki_adet = poz["adet"]
                    oran_pay = (satilacak_adet / onceki_adet) if onceki_adet > 0 else 0.0
                    poz["maliyet_giris_tl"] = poz.get("maliyet_giris_tl", 0.0) * (1.0 - oran_pay)
                    poz["adet"] -= satilacak_adet
                    if poz["adet"] <= 1e-9:
                        acik_pozisyonlar.remove(poz)
        pending_orders = []

        # ── 2) Rejim (§7) — bugünün kapanışına göre, look-ahead güvenli. ──
        if rejim_kapisi_aktif:
            rejim_bugun = rejim.rejim_hesapla(endeks_df, veriler, T)
            hedef_ham = rejim_bugun["hedef_oran"]
            if hedef_ham > efektif_hedef_oran:
                efektif_hedef_oran = min(hedef_ham, efektif_hedef_oran + _KADEMELI_ADIM)
            else:
                efektif_hedef_oran = hedef_ham  # düşerken ANINDA (§7)
        else:
            # DENEY: rejim kapısı KAPALI. rejim.rejim_hesapla() hiç çağrılmaz
            # (hem hız hem de "rejimin hiçbir kanaldan sızmaması" için); her
            # gün R1/%100 varsayılır, kademeleme de anlamsızlaştığı için
            # doğrudan tam yatırım hedefi verilir. v3_portfoy.gunluk_kontrol
            # bu sözlükte R1 gördüğü için R3/R4 çıkış dallarına HİÇ girmez —
            # yani rejim kaynaklı satış da tamamen devre dışıdır.
            rejim_bugun = {
                "rejim": "R1",
                "hedef_oran": 1.0,
                "genislik": float("nan"),
                "gerekce": "Rejim kapısı deney amaçlı KAPALI — her zaman tam yatırım.",
            }
            efektif_hedef_oran = 1.0

        # ── 3) Günlük mark-to-market. ──
        # ÖNEMLİ: bir hissenin bugünkü satırı eksikse pozisyon mark-to-market
        # toplamından DÜŞÜRÜLMEZ (bu, değerini sessizce 0 saymakla eşdeğerdi
        # ve sahte tek-günlük çöküş+toparlanma döngüleri üretiyordu — bkz.
        # yukarıdaki KRİTİK MUHASEBE DÜZELTMESİ notu). Bunun yerine son
        # bilinen kapanışla (forward-fill) değerlenir; hiç fiyat geçmişi
        # yoksa (teorik olarak olmamalı, pozisyon zaten bir açılış fiyatıyla
        # kurulmuş olmalı) yine de dışarıda bırakılır.
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

        # ── GÜVENLİK KONTROLÜ: nakit özsermayenin %1'inden fazla negatife
        #    düşerse (kaldıraç sızıntısı / emir doldurma hatası) backtest
        #    SESSİZCE yanlış sonuç üretmek yerine ÇÖKER. ──
        if cash < -0.01 * guncel_ozsermaye:
            raise RuntimeError(
                f"[v3_backtest] KALDIRAÇ SIZINTISI: {T.date()} günü nakit "
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
                # ÖNEMLİ: bugün felaket stopu/rejim çıkışıyla (ya da MA200
                # kaybı/top-20 dışı kalma nedeniyle rebalansın kendisiyle)
                # satılmasına karar verilen bir sembol, v3_portfoy açısından
                # "şu an elde değilmiş" gibi göründüğünden yeniden en iyi
                # adaylardan biri olarak seçilebilir (hedef_agirliklar'da
                # yer alabilir) — bu kontrol, AYNI GÜN satılıp hemen geri
                # alınmasını (gereksiz çift maliyet + felaket stopunun
                # sigorta amacını boşa çıkarması) engeller. Bir sonraki
                # rebalansta (20 gün sonra) hâlâ iyi bir adaysa normal
                # şekilde yeniden değerlendirilir.
                if sembol in zaten_satilacak:
                    continue
                mevcut_poz = _pozisyon_bul(acik_pozisyonlar, sembol)
                mevcut_agirlik = 0.0
                if mevcut_poz is not None and sembol in fiyatlar_bugun and guncel_ozsermaye > 0:
                    mevcut_agirlik = (
                        float(fiyatlar_bugun[sembol]["Close"]) * mevcut_poz["adet"] / guncel_ozsermaye
                    )
                # §6: sapma %5 puandan küçükse dokunulmaz (turnover azaltma).
                if abs(hedef_agirlik - mevcut_agirlik) < agirlik_toleransi:
                    continue
                pending_orders.append({
                    "tip": "hedef_ayarla", "sembol": sembol,
                    "hedef_tl": hedef_agirlik * guncel_ozsermaye,
                    "skor_giris": skor_haritasi.get(sembol),
                })

        # ── 6) Günlük özsermaye kaydı (mark-to-market, bugünün exitleri
        #        sonrası, YARININ emirleri HARİÇ). `nakit`/`pozisyon_deger`
        #        teşhis amaçlı ayrıca tutulur (bkz. cash < 0 / mark-to-market
        #        anomalilerini ileride erken yakalamak için). ──
        ozsermaye_egrisi.append({
            "tarih": T, "ozsermaye": guncel_ozsermaye,
            "nakit": cash, "pozisyon_deger": yatirim_deger,
        })

        if T in izleme_tarihleri:
            pozisyon_izleme[T] = [dict(p) for p in acik_pozisyonlar]

        if ilerleme and (idx % 100 == 0 or idx == toplam_gun - 1):
            print(f"[v3_backtest] {idx + 1}/{toplam_gun} gün işlendi ({T.date()}) — "
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
    """§9'da istenen metrikleri hesaplar (V2'nin R-multiple bazlı istatistikleri
    YOKTUR — V3'te ATR-stop tabanlı bir risk birimi tanımlı değil, felaket
    stopu sabit bir yüzde; bunun yerine TL/% bazlı basit istatistikler
    kullanılır).
    """
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
        # KRİTİK (bkz. v2/backtest.py'deki AYNI düzeltme): son günün barı
        # eksik olabileceğinden mark-to-market özsermaye NaN çıkabilir. Tek
        # bir NaN, serinin SON değeri olduğunda CAGR'ı sessizce nan yapar —
        # CAGR hesaplamadan ÖNCE dropna() ZORUNLU.
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
    """§9 kabul kriterlerini (TEST dönemi metrikleri üzerinde) kontrol eder.

    "Endeksi yenmek zorunlu" kuralı burada: CAGR üstünlüğü VE maksimum düşüş
    üstünlüğü ikisi de aranıyor (§9 tablosu).
    """
    basarisiz: list[str] = []

    fark = test_metrikleri.get("endeks_ustu_fark", float("nan"))
    if not (isinstance(fark, (int, float)) and not pd.isna(fark) and fark > 0):
        fark_yuzde = fark * 100 if isinstance(fark, (int, float)) and not pd.isna(fark) else float("nan")
        basarisiz.append(f"CAGR endeksi geçemedi (fark: %{fark_yuzde:.2f} puan) — eşik: >0")

    maks_dusus_v3 = test_metrikleri.get("maksimum_dusus_%", float("nan"))
    maks_dusus_endeks = test_metrikleri.get("endeks_maksimum_dusus_%", float("nan"))
    if (isinstance(maks_dusus_v3, (int, float)) and isinstance(maks_dusus_endeks, (int, float))
            and not pd.isna(maks_dusus_v3) and not pd.isna(maks_dusus_endeks)):
        if abs(maks_dusus_v3) > abs(maks_dusus_endeks) + 1e-9:
            basarisiz.append(
                f"Maksimum düşüş endeksten kötü (V3 %{abs(maks_dusus_v3) * 100:.1f} > "
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
    """§11 imzası. Veriyi indirir/hazırlar, ardından _calistir_ic ile simüle eder.

    Son üç parametre YALNIZ deney_lab.py içindir; varsayılanları (True/None/
    None) mevcut V3 davranışını BİREBİR korur — calistir_v3.py ve
    walk_forward() bunları hiç vermez, dolayısıyla etkilenmez. Ayrıntı için
    bkz. _calistir_ic docstring'i.

    Döner: {'islemler': [...], 'ozsermaye_egrisi': [...], 'metrikler': {...}}
    """
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    # MA200 + 252 günlük momentum penceresi + 21 günlük gecikme için en az
    # ~275 işlem günü (~ 1 takvim yılı + pay) geçmiş gerekir; V2'nin 500
    # günlük tamponu burada da güvenli bir marj sağlıyor (252 hafta sonu +
    # tatil boşluklarıyla birlikte ~500 takvim günü ~340 işlem günü eder).
    indirme_baslangic = (baslangic_ts - pd.Timedelta(days=550)).strftime("%Y-%m-%d")
    bitis_str = bitis_ts.strftime("%Y-%m-%d")

    print(f"[v3_backtest] Veri indiriliyor: {len(evren.TEMEL_SEMBOLLER)} sembol + XU100.IS "
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
    print(f"[v3_backtest] {len(veriler)}/{len(evren.TEMEL_SEMBOLLER)} sembol için veri hazır.")

    return _calistir_ic(
        veriler, endeks_df, baslangic, bitis, ozsermaye,
        rejim_kapisi_aktif=rejim_kapisi_aktif,
        rebalans_gun=rebalans_gun,
        pozisyon_sayisi=pozisyon_sayisi,
    )


def al_tut_kiyas(endeks_df: pd.DataFrame, baslangic: str, bitis: str, ozsermaye: float) -> dict:
    """§9: BIST100'ü aynı dönemde al-ve-tut eder (TEK alım maliyeti).

    Sistem kıyasın kendisidir: V3 bunu yenemiyorsa var olmasının anlamı
    yoktur (bkz. STRATEJI_V3.md §1, §9). Look-ahead riski taşımaz — bu,
    veriye bakıp karar veren bir SİNYAL değil, dönemin en başında verilmiş
    statik bir tahsis kararıdır; yine de gerçekçilik için ilk günün
    AÇILIŞ fiyatından, normal likidite maliyet oranıyla (endeks çok likit
    kabul edilir) giriş yapılır ve bir daha HİÇ işlem yapılmaz.

    Döner: {'ozsermaye_egrisi': [...], 'metrikler': {'cagr','maksimum_dusus_%',
            'giris_tarihi','giris_fiyati'}}
    """
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
        acilis0 = endeks_df.loc[giris_tarihi, "Close"]  # açılış yoksa kapanışla gir (nadir veri boşluğu)

    oran = _KOMISYON_ORANI + _KAYMA_NORMAL  # endeks çok likit -> normal kayma
    adet = math.floor(float(ozsermaye) / (float(acilis0) * (1.0 + oran)))
    maliyet = adet * acilis0 * oran
    cash = float(ozsermaye) - adet * acilis0 - maliyet

    egri: list[dict] = []
    for T in takvim:
        kapanis = endeks_df.loc[T, "Close"]
        deger = cash + adet * float(kapanis) if not pd.isna(kapanis) else float("nan")
        egri.append({"tarih": T, "ozsermaye": deger})

    seri = pd.Series({e["tarih"]: e["ozsermaye"] for e in egri}).sort_index()
    seri = seri.dropna()  # bkz. calistir()'deki AYNI kritik dropna notu

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
    """§9 doğrulama: 2019-2023 geliştirme + 2024-bugün DOKUNULMAMIŞ test.

    Her iki dönem için V3 SONUCU ile AYNI dönemin al-tut kıyası birlikte
    üretilir. `dogrulama` YALNIZ test dönemi üzerinde hesaplanır ve hem
    CAGR hem maksimum düşüş üstünlüğünü zorunlu kılar (§9: "endeksi yenmek
    zorunlu").

    Döner: {'gelistirme': {'v3':..., 'al_tut':...}, 'test': {'v3':..., 'al_tut':...},
            'dogrulama': {'gecti': bool, 'basarisiz_kriterler': [...]}}
    """
    print("=" * 70)
    print("V3 WALK-FORWARD — Geliştirme dönemi: 2019-01-01 → 2023-12-31")
    print("=" * 70)
    gelistirme_v3 = calistir("2019-01-01", "2023-12-31", ozsermaye)

    bugun = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    print("=" * 70)
    print(f"V3 WALK-FORWARD — Test dönemi (DOKUNULMAMIŞ): 2024-01-01 → {bugun}")
    print("=" * 70)
    test_v3 = calistir("2024-01-01", bugun, ozsermaye)

    # al_tut_kiyas için endeks verisini calistir()'in indirdiği önbellekten
    # tekrar çekiyoruz (küçük ek maliyet, ama modülerlik/temizlik için
    # calistir()'in iç veri sözlüğünü dışarı sızdırmamak tercih edildi).
    endeks_ham = veri.fiyat_indir(["XU100.IS"], "2018-06-01", bugun)
    endeks_df = endeks_ham.get("XU100.IS")
    if endeks_df is None or endeks_df.empty:
        raise RuntimeError("XU100.IS verisi al-tut kıyası için indirilemedi.")

    gelistirme_al_tut = al_tut_kiyas(endeks_df, "2019-01-01", "2023-12-31", ozsermaye)
    test_al_tut = al_tut_kiyas(endeks_df, "2024-01-01", bugun, ozsermaye)

    # Kabul kriterleri: endeks maksimum düşüşü test_v3 metriklerine eklenip
    # (yalnız kontrol için, kalıcı olarak sözlüğe yazılmadan) kontrol edilir.
    test_metrikleri_kiyaslamali = dict(test_v3["metrikler"])
    test_metrikleri_kiyaslamali["endeks_maksimum_dusus_%"] = test_al_tut["metrikler"]["maksimum_dusus_%"]
    dogrulama = _kabul_kriterlerini_kontrol(test_metrikleri_kiyaslamali)

    print("=" * 70)
    if dogrulama["gecti"]:
        print("SONUÇ: §9 kabul kriterleri GEÇTİ — V3 endeksi yendi, tavsiye verebilir.")
    else:
        print("SONUÇ: §9 kabul kriterleri GEÇMEDİ — TAVSIYE_VERME modu gerekir.")
        for madde in dogrulama["basarisiz_kriterler"]:
            print(f"  - {madde}")
    print("=" * 70)

    return {
        "gelistirme": {"v3": gelistirme_v3, "al_tut": gelistirme_al_tut},
        "test": {"v3": test_v3, "al_tut": test_al_tut},
        "dogrulama": dogrulama,
    }


# ═══════════════════════════════════════════════════════════════════════
# Kendi kendine kontrol — AĞ ÇAĞRISI YOK. backtest.py'deki (V2) AYNI desenle
# (uyarlanarak, kopyalanmadan): sentetik veriyle gelecekte "patlayan" bir
# hisse eklenip, patlamadan ÖNCEKİ tüm günlerin sonuçlarının (özsermaye
# eğrisi + kesim öncesi açılan pozisyonlar) o patlama YOKMUŞ gibi çıkan
# sonuçlarla BİREBİR aynı olduğu kanıtlanır — TÜM PİPELİNE (evren+rejim+
# v3_skor+v3_portfoy+maliyet+emir kuyruğu) uçtan uca test edilir.
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    n_gun = 560
    tarihler = pd.date_range("2022-01-03", periods=n_gun, freq="B")
    kesim_idx = 460  # bu günden SONRASI iki senaryoda farklılaşacak
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

    # XU100 endeksi: iki senaryoda da AYNI (yalnız GELECEK hissesinin verisi
    # değişecek) — istikrarlı bir yükseliş, ki R1 rejimi tetiklensin ve
    # rebalans/portföy mantığı gerçekten çalıştırılsın.
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

    print("Senaryo A çalıştırılıyor (patlama YOK)...")
    sonuc_a = _calistir_ic(veriler_a, endeks_df, baslangic_str, bitis_str,
                            ozsermaye=1_000_000.0, ilerleme=False,
                            izleme_tarihleri={kesim_tarih})
    print("Senaryo B çalıştırılıyor (GELECEK kesimden sonra %60+ patlıyor)...")
    sonuc_b = _calistir_ic(veriler_b, endeks_df, baslangic_str, bitis_str,
                            ozsermaye=1_000_000.0, ilerleme=False,
                            izleme_tarihleri={kesim_tarih})

    # ── Kontrol 1: kesim tarihine KADAR özsermaye eğrisi birebir aynı. ────
    egri_a = {e["tarih"]: e["ozsermaye"] for e in sonuc_a["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    egri_b = {e["tarih"]: e["ozsermaye"] for e in sonuc_b["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    assert set(egri_a.keys()) == set(egri_b.keys()), "Kesim öncesi tarih kümeleri farklı!"
    for t in egri_a:
        fark = abs(egri_a[t] - egri_b[t])
        assert fark < 1e-6, (
            f"LOOK-AHEAD SIZINTISI: {t.date()} günü özsermayesi senaryolar arasında "
            f"farklı çıktı (A={egri_a[t]:.4f}, B={egri_b[t]:.4f})."
        )

    # ── Kontrol 2: TAM OLARAK kesim gününde açık olan pozisyonların durumu
    #    (sembol, giriş tarihi, giriş fiyatı, adet) birebir aynı olmalı.
    #    NOT: `islemler` listesi yalnız KAPANAN işlemleri kaydeder; V3'te
    #    aylık rebalans + trend-takibi nedeniyle birçok pozisyon (özellikle
    #    GELECEK gibi hâlâ trendde olanlar) backtest boyunca hiç kapanmaz —
    #    bu yüzden kapanmamış pozisyonları da kapsayan `pozisyon_izleme`
    #    anlık görüntüsü kullanılıyor (bkz. _calistir_ic'teki izleme_tarihleri
    #    parametresi). Bu, Kontrol 1'in (özsermaye eğrisi) tamamlayıcısıdır:
    #    eğri toplamda aynı çıksa bile, TEORİK olarak farklı pozisyon
    #    karışımlarının aynı toplam değere denk gelmesi ihtimaline karşı
    #    pozisyon bazında da doğrulama yapılıyor. ──────────────────────────
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

    # ── Kontrol 3: GELECEK'e kesime KADAR verilen ağırlık/adet iki
    #    senaryoda da birebir aynı olmalı (asıl "gelecekte patlayacağını
    #    önceden görüp önceden büyük pozisyon açma" hatasının doğrudan testi). ──
    gelecek_a = [p for p in pozisyonlar_a if p[0] == "GELECEK"]
    gelecek_b = [p for p in pozisyonlar_b if p[0] == "GELECEK"]
    assert gelecek_a == gelecek_b
    assert len(gelecek_a) == 1, "Test dizaynı hatalı: GELECEK'te kesim gününde pozisyon bekleniyordu"

    # ── al_tut_kiyas kendi kendine kontrol: dropna sonrası CAGR NaN
    #    olmamalı, giriş TEK seferlik olmalı (adet, ilk günden sonra hiç
    #    değişmemeli -> ozsermaye_egrisi Close ile doğrusal orantılı). ────
    kiyas = al_tut_kiyas(endeks_df, baslangic_str, bitis_str, ozsermaye=1_000_000.0)
    assert not pd.isna(kiyas["metrikler"]["cagr"]), "al_tut_kiyas CAGR NaN çıktı"
    kiyas_seri = pd.Series({e["tarih"]: e["ozsermaye"] for e in kiyas["ozsermaye_egrisi"]}).dropna()
    endeks_araligi = endeks_df.loc[kiyas_seri.index, "Close"]
    oran_serisi = (kiyas_seri - kiyas_seri.iloc[0]) / (endeks_araligi - endeks_araligi.iloc[0]).replace(0, np.nan)
    oran_gecerli = oran_serisi.dropna()
    if len(oran_gecerli) > 5:
        assert oran_gecerli.std() < 1.0, "al_tut_kiyas eğrisi endeksle orantılı büyümüyor (yeniden alım şüphesi)"

    print("v3_backtest.py kendi kendine kontrol (LOOK-AHEAD testi): BAŞARILI")
    print(f"  Kesim tarihi: {kesim_tarih.date()}")
    print(f"  Kesim gününde ortak açık pozisyon sayısı: {len(pozisyonlar_a)}")
    print(f"  Senaryo A toplam işlem: {len(sonuc_a['islemler'])}, "
          f"Senaryo B toplam işlem: {len(sonuc_b['islemler'])}")
    print(f"  Senaryo A metrikleri: {sonuc_a['metrikler']}")
    print(f"  al_tut_kiyas metrikleri: {kiyas['metrikler']}")
