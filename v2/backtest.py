# -*- coding: utf-8 -*-
"""
v2/backtest.py — Pusula V2 DÜRÜST backtest motoru (§5, §6, §7, §8, §9, §11).

Bu proje için EN KRİTİK dosya. Önceki sürüm (V1) kendini kandırdığı için para
kaybettirdi (bkz. STRATEJI_V2.md §0). Burada uygulanan üç zorunlu kural asla
gevşetilmez:

  1) Sinyal gün T KAPANIŞINDA üretilir; emir gün T+1 AÇILIŞINDA gerçekleşir.
     Hiçbir yerde aynı günün kapanışıyla işlem yapılmaz (look-ahead yasağı).
  2) Her emir §7 maliyet modelinden (komisyon + kayma) geçer; tavan/taban
     günü işlem yapılamaz; gap koruması (T+1 açılışı hesaplanan stopun
     altındaysa pozisyon AÇILMAZ) uygulanır.
  3) Özsermaye eğrisi GÜNLÜK tutulur; pozisyon boyutu her gün GÜNCEL
     (mark-to-market) özsermayeye göre hesaplanır — sabit/başlangıç
     sermayeye göre DEĞİL (aksi halde kayıplar/kazançlar büyüdükçe risk
     yanlış ölçeklenir).

Mimari: bu dosya §11'de tanımlı hazır modülleri (veri/evren/rejim/sinyal/
risk/pozisyon) SAF FONKSİYON olarak kullanır, onların iç mantığını tekrar
YAZMAZ. Backtest'in kendi sorumluluğu yalnız: (a) günlük simülasyon
döngüsünü (emir kuyruğu, dolum, maliyet, özsermaye takibi) yürütmek, ve
(b) §5 madde 5'teki R3 "portföy seviyesinde en zayıfı kapat" mantığını
uygulamak (pozisyon.cikis_kontrol tek bir pozisyonun bilgisiyle çağrıldığı
için bu portföy-seviyesi kararı onun kapsamı dışında, bkz. pozisyon.py'deki
YORUM KARARI notu).
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
import rejim
import sinyal
import risk
import pozisyon

# Repo kökündeki (v2'nin bir üstü) sektor_haritasi.py'yi kullanmayı dene;
# yoksa tüm semboller "Diğer" sayılır (sektör yoğunlaşma kısıtı yine
# çalışır, yalnız daha kaba/az ayrıştırıcı biçimde) — sistem asla çökmez.
try:
    _REPO_KOKU = _V2_DIR.parent
    if str(_REPO_KOKU) not in sys.path:
        sys.path.insert(0, str(_REPO_KOKU))
    from sektor_haritasi import SEKTOR_HARITASI as _SEKTOR_HARITASI
except Exception:
    _SEKTOR_HARITASI = {}

_DIGER_SEKTOR = "Diğer / Sınıflandırılmamış"


def _sektor_bul(sembol: str) -> str:
    return _SEKTOR_HARITASI.get(sembol.strip().upper(), _DIGER_SEKTOR)


# ─────────────────────────────────────────────────────────────────────────
# §7 — Maliyet ve gerçekçilik sabitleri (şartnameyle birebir).
# ─────────────────────────────────────────────────────────────────────────
_KOMISYON_ORANI = 0.0015          # tek yön
_KAYMA_NORMAL = 0.0010            # tek yön, 20g medyan TL hacim >= eşik
_KAYMA_DUSUK_LIKIDITE = 0.0025    # tek yön, 20g medyan TL hacim < eşik
_DUSUK_LIKIDITE_ESIGI = 50_000_000.0

# evren.py ile AYNI tavan/taban proxy eşiği — iki modül arasında tutarsız
# bir eşik kullanmak, evrene giren ama backtest'te "tavan günü" sayılıp
# işlem yapılamayan (ya da tam tersi) çelişkili sonuçlar üretir.
_TAVAN_TABAN_ESIGI = 0.095

# Portföy kısıtları (§6) — pozisyon.py'nin kendi sabitleriyle birebir aynı;
# burada yalnız döngü sınırlarını erken kesmek için (performans) kullanılır,
# NİHAİ karar her zaman pozisyon.portfoy_kisit_kontrol()'dedir.
_MAKS_ESZAMANLI_POZISYON = 6
_MAKS_GUNLUK_YENI_POZISYON = 2

# Rejim yükselirken günde en fazla %25 puan yaklaşma (§2).
_KADEMELI_ADIM = 0.25

# Evren haftalık yeniden hesaplanır (§3.1) — her 5 işlem gününde bir.
_EVREN_YENILEME_ARALIGI = 5

# "Stop olan hisseye 30 gün yeniden giriş yok" (§6) — YORUM KARARI: hem ilk
# stop hem trailing stop, ikisi de bir "stop" tetiklenmesidir (fiyat riski
# gerçekleşti); zaman/trend/rejim çıkışları bu yasağı TETİKLEMEZ, çünkü
# onlar risk yönetimi değil, kalite/uygunluk kararlarıdır.
_STOP_SAYILAN_NEDENLER = ("stop", "trailing")


def _komisyon_kayma_orani(hacim_tl_medyan) -> float:
    """§7: komisyon + kayma (tek yön), likiditeye göre kayma oranı değişir."""
    if hacim_tl_medyan is None or pd.isna(hacim_tl_medyan) or hacim_tl_medyan < _DUSUK_LIKIDITE_ESIGI:
        return _KOMISYON_ORANI + _KAYMA_DUSUK_LIKIDITE
    return _KOMISYON_ORANI + _KAYMA_NORMAL


def _tavan_taban_mi(df: pd.DataFrame, tarih: pd.Timestamp) -> bool:
    """Bugünün kapanış getirisi mutlak %9.5'i geçiyorsa tavan/taban proxy'si.

    evren.py'deki "son 5 günde tavan/taban" kontrolüyle AYNI eşiği ve aynı
    "günlük kapanış getirisinin mutlak değeri" mantığını kullanır, ama burada
    tek bir GÜNÜN kendisi için soruluyor (§7: "tavan/taban günü işlem
    yapılamaz"). Veri yoksa güvenli tarafta kalınır: işlem yapılamaz.
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


def _guncel_r(pozisyon_dict: dict, fiyat: float) -> float:
    """Güncel R multiple: (fiyat - giriş) / (giriş - ilk_stop)."""
    r_birimi = pozisyon_dict["giris_fiyati"] - pozisyon_dict["ilk_stop"]
    if r_birimi <= 0:
        return 0.0
    return (fiyat - pozisyon_dict["giris_fiyati"]) / r_birimi


# ─────────────────────────────────────────────────────────────────────────
# İç simülasyon çekirdeği — veri İNDİRMEDEN, hazır veriyle çalışır.
# Ayrı bir fonksiyon olmasının nedeni: __main__ altındaki look-ahead testi
# ağ çağrısı yapamadığı için sentetik veriyle DOĞRUDAN bu fonksiyonu
# çağırmalı; calistir() ise yalnız indirme+hazırlık katmanını ekler.
# ─────────────────────────────────────────────────────────────────────────
def _calistir_ic(veriler: dict, endeks_df: pd.DataFrame, baslangic: str, bitis: str,
                  ozsermaye: float = 1_000_000.0, ilerleme: bool = True) -> dict:
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)

    takvim = endeks_df.loc[(endeks_df.index >= baslangic_ts) & (endeks_df.index <= bitis_ts)].index
    if len(takvim) == 0:
        return {
            "islemler": [], "ozsermaye_egrisi": [],
            "metrikler": _metrikleri_hesapla([], [], endeks_df, baslangic_ts, bitis_ts),
        }

    cash = float(ozsermaye)
    acik_pozisyonlar: list[dict] = []
    islemler: list[dict] = []
    ozsermaye_egrisi: list[dict] = []
    pending_orders: list[dict] = []
    son_stop_tarihleri: dict[str, pd.Timestamp] = {}
    efektif_hedef_oran = 0.0
    evren_guncel: list[str] = []

    toplam_gun = len(takvim)
    for idx, T in enumerate(takvim):
        # ── 1) Dünün (T-1 kapanışında karara bağlanan) emirlerini bugünün
        #        AÇILIŞINDA gerçekleştir. §7 zorunlu kuralı burada uygulanır. ──
        bugun_acilan_sayisi = 0
        for emir in pending_orders:
            if bugun_acilan_sayisi >= _MAKS_GUNLUK_YENI_POZISYON:
                break
            if len(acik_pozisyonlar) >= _MAKS_ESZAMANLI_POZISYON:
                break
            sembol = emir["sembol"]
            df = veriler.get(sembol)
            if df is None or T not in df.index:
                continue  # veri yok → emir düşer (gerçekleşmez)
            if _tavan_taban_mi(df, T):
                continue  # tavan/taban günü işlem yapılamaz → emir düşer
            satir = df.loc[T]
            acilis = satir.get("Open")
            if acilis is None or pd.isna(acilis):
                continue
            if acilis < emir["teorik_stop"]:
                continue  # GAP KORUMASI: T+1 açılışı stopun altında → AÇILMAZ

            oran = _komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
            adet = emir["adet"]
            maliyet_giris = adet * acilis * oran
            cash -= (adet * acilis + maliyet_giris)

            ilk_stop = float(acilis - 2.5 * emir["atr_T"])
            acik_pozisyonlar.append({
                "sembol": sembol,
                "giris_tarihi": T,
                "giris_fiyati": float(acilis),
                "ilk_stop": ilk_stop,
                "guncel_stop": ilk_stop,
                "en_yuksek_kapanis": float(acilis),
                "gun_sayisi": 0,
                "ust_uste_ema50_alti": 0,
                "sektor": _sektor_bul(sembol),
                "adet": adet,
                "risk_tl_giris": adet * 2.5 * emir["atr_T"],
                "maliyet_giris_tl": maliyet_giris,
                "kurulum": emir["kurulum"],
                "skor_giriste": emir["skor"],
                "rejim_giriste": emir["rejim_giriste"],
            })
            bugun_acilan_sayisi += 1
        pending_orders = []  # kuyruk tümüyle işlendi (gerçekleşti ya da düştü)

        # ── 2) Rejim (§2) — bugünün kapanışına göre, look-ahead güvenli. ──
        rejim_bugun = rejim.rejim_hesapla(endeks_df, veriler, T)

        # Kademeli giriş (§2): yükselirken günde en fazla %25 puan, düşerken
        # anında. Bu, pozisyon boyutlandırmasında "hedef_oran" olarak
        # risk.pozisyon_boyutu'na verilir — motor.py'deki CANLI sistemle
        # AYNI mantık, aksi halde backtest gerçek sistemden daha iyimser
        # (daha hızlı sermaye dağıtan) bir davranışı test etmiş olurdu.
        hedef = rejim_bugun["hedef_oran"]
        if hedef > efektif_hedef_oran:
            efektif_hedef_oran = min(hedef, efektif_hedef_oran + _KADEMELI_ADIM)
        else:
            efektif_hedef_oran = hedef

        # ── 3) Açık pozisyonlar için trailing güncelle + çıkış tespiti. ──
        kapanislar_bugun: dict[str, float] = {}
        for poz in acik_pozisyonlar:
            df = veriler.get(poz["sembol"])
            if df is None or T not in df.index:
                continue
            satir = df.loc[T]
            poz.update(pozisyon.trailing_guncelle(poz, satir))
            kapanislar_bugun[poz["sembol"]] = float(satir["Close"])

        rejim_bayraksiz = dict(rejim_bugun)
        cikacaklar: dict[str, dict] = {}
        for poz in acik_pozisyonlar:
            df = veriler.get(poz["sembol"])
            if df is None or T not in df.index:
                continue
            satir = df.loc[T]
            sonuc = pozisyon.cikis_kontrol(poz, satir, rejim_bayraksiz)
            if sonuc is not None:
                cikacaklar[poz["sembol"]] = sonuc

        # R3: kalan (henüz çıkış tetiklenmemiş) pozisyonlar arasında GÜNCEL
        # R'ye göre en zayıftan başlayarak, toplam yatırım hedef orana
        # (rejimin kendi hedefi — kademeli DEĞİL, çünkü §2 "rejim düşerken
        # anında uygulanır" diyor) inene dek kapat.
        if rejim_bugun["rejim"] == "R3":
            kalanlar = [p for p in acik_pozisyonlar if p["sembol"] not in cikacaklar
                        and p["sembol"] in kapanislar_bugun]
            toplam_deger = sum(kapanislar_bugun[p["sembol"]] * p["adet"] for p in kalanlar)
            toplam_ozsermaye_tahmini = cash + sum(
                kapanislar_bugun.get(p["sembol"], p["giris_fiyati"]) * p["adet"]
                for p in acik_pozisyonlar if p["sembol"] not in cikacaklar
            )
            hedef_tl = rejim_bugun["hedef_oran"] * toplam_ozsermaye_tahmini
            kalanlar_sirali = sorted(
                kalanlar, key=lambda p: _guncel_r(p, kapanislar_bugun[p["sembol"]])
            )
            for p in kalanlar_sirali:
                if toplam_deger <= hedef_tl:
                    break
                rejim_flagli = dict(rejim_bugun)
                rejim_flagli["r3_bu_pozisyonu_kapat"] = True
                df = veriler[p["sembol"]]
                satir = df.loc[T]
                sonuc = pozisyon.cikis_kontrol(p, satir, rejim_flagli)
                if sonuc is not None:
                    cikacaklar[p["sembol"]] = sonuc
                    toplam_deger -= kapanislar_bugun[p["sembol"]] * p["adet"]

        # ── 4) Çıkışları uygula (tavan/taban kilidi varsa ertelenir). ──
        kalan_pozisyonlar = []
        for poz in acik_pozisyonlar:
            sembol = poz["sembol"]
            if sembol not in cikacaklar:
                kalan_pozisyonlar.append(poz)
                continue
            df = veriler[sembol]
            if _tavan_taban_mi(df, T):
                # Kilitli (tavan/taban) — satılamaz, pozisyon açık kalır,
                # çıkış tetiklenmesi bir sonraki uygun güne ertelenir.
                kalan_pozisyonlar.append(poz)
                continue
            cikis = cikacaklar[sembol]
            fiyat = cikis["fiyat"]
            satir = df.loc[T]
            oran = _komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
            maliyet_cikis = poz["adet"] * fiyat * oran
            hasilat = poz["adet"] * fiyat - maliyet_cikis
            cash += hasilat
            toplam_maliyet = poz.get("maliyet_giris_tl", 0.0) + maliyet_cikis
            # DİKKAT: giriş maliyeti burada AYRICA düşülüyor (cash zaten
            # girişte düşülmüştü, ama "net_pnl_tl" tek başına okunduğunda da
            # doğru sonucu vermeli — aksi halde işlem bazlı R/PF istatistikleri
            # giriş maliyetini görmezden gelip gerçek performansı şişirir).
            net_pnl = hasilat - poz["adet"] * poz["giris_fiyati"] - poz.get("maliyet_giris_tl", 0.0)
            risk_tl = poz.get("risk_tl_giris") or 0.0
            sonuc_r = (net_pnl / risk_tl) if risk_tl > 0 else 0.0
            islemler.append({
                "sembol": sembol,
                "giris_tarihi": poz["giris_tarihi"],
                "cikis_tarihi": T,
                "giris_fiyati": poz["giris_fiyati"],
                "cikis_fiyati": float(fiyat),
                "adet": poz["adet"],
                "kurulum": poz.get("kurulum"),
                "rejim_giriste": poz.get("rejim_giriste"),
                "cikis_nedeni": cikis["neden"],
                "gun_sayisi": poz.get("gun_sayisi", 0),
                "net_pnl_tl": float(net_pnl),
                "toplam_maliyet_tl": float(toplam_maliyet),
                "sonuc_R": float(sonuc_r),
            })
            if cikis["neden"] in _STOP_SAYILAN_NEDENLER:
                son_stop_tarihleri[sembol] = T
        acik_pozisyonlar = kalan_pozisyonlar

        # ── 5) Evren — haftalık (§3.1) yeniden hesapla. ──
        if idx % _EVREN_YENILEME_ARALIGI == 0:
            evren_guncel = evren.evren_olustur(veriler, T)

        # ── 6) Sinyal üret, portföy kısıtları + risk boyutlandırmasından
        #        geçir, kabul edilenleri YARININ açılışı için kuyruğa al. ──
        mevcut_yatirim_deger = sum(
            kapanislar_bugun.get(p["sembol"], p["giris_fiyati"]) * p["adet"]
            for p in acik_pozisyonlar
        )
        guncel_ozsermaye = cash + mevcut_yatirim_deger

        if len(acik_pozisyonlar) < _MAKS_ESZAMANLI_POZISYON:
            adaylar = sinyal.giris_adaylari(veriler, evren_guncel, T)
            yeni_kuyruk_sayisi = 0
            for aday in adaylar:
                if yeni_kuyruk_sayisi >= _MAKS_GUNLUK_YENI_POZISYON:
                    break
                if len(acik_pozisyonlar) + yeni_kuyruk_sayisi >= _MAKS_ESZAMANLI_POZISYON:
                    break
                sembol = aday["sembol"]
                df = veriler.get(sembol)
                if df is None or T not in df.index:
                    continue
                satir = df.loc[T]
                aday_full = dict(aday)
                aday_full["tarih"] = T
                red = pozisyon.portfoy_kisit_kontrol(
                    aday_full, acik_pozisyonlar, yeni_kuyruk_sayisi,
                    son_stop_tarihleri, _SEKTOR_HARITASI,
                )
                if red is not None:
                    continue
                boyut = risk.pozisyon_boyutu(
                    ozsermaye=guncel_ozsermaye, kapanis=aday["kapanis"], atr=aday["atr"],
                    hacim_tl_medyan=satir.get("HACIM_TL_MEDYAN20"),
                    mevcut_yatirim=mevcut_yatirim_deger, hedef_oran=efektif_hedef_oran,
                )
                if boyut["red_nedeni"] is not None or boyut["adet"] < 1:
                    continue
                pending_orders.append({
                    "sembol": sembol, "kapanis_T": aday["kapanis"], "atr_T": aday["atr"],
                    "teorik_stop": boyut["stop"], "adet": boyut["adet"],
                    "kurulum": aday["kurulum"], "skor": aday["skor"],
                    "rejim_giriste": rejim_bugun["rejim"],
                })
                mevcut_yatirim_deger += boyut["deger"]
                yeni_kuyruk_sayisi += 1

        # ── 7) Günlük özsermaye kaydı (mark-to-market, bugünün exitleri
        #        sonrası, YARININ girişleri HARİÇ). ──
        mtm = sum(kapanislar_bugun.get(p["sembol"], p["giris_fiyati"]) * p["adet"]
                  for p in acik_pozisyonlar)
        ozsermaye_egrisi.append({"tarih": T, "ozsermaye": cash + mtm})

        if ilerleme and (idx % 100 == 0 or idx == toplam_gun - 1):
            print(f"[backtest] {idx + 1}/{toplam_gun} gün işlendi "
                  f"({T.date()}) — açık pozisyon: {len(acik_pozisyonlar)}, "
                  f"özsermaye: {cash + mtm:,.0f} TL")

    metrikler = _metrikleri_hesapla(islemler, ozsermaye_egrisi, endeks_df, baslangic_ts, bitis_ts)
    return {"islemler": islemler, "ozsermaye_egrisi": ozsermaye_egrisi, "metrikler": metrikler}


def _metrikleri_hesapla(islemler: list[dict], ozsermaye_egrisi: list[dict],
                         endeks_df: pd.DataFrame, baslangic_ts: pd.Timestamp,
                         bitis_ts: pd.Timestamp) -> dict:
    """§8/§9'da istenen tüm metrikleri hesaplar."""
    n = len(islemler)
    if n == 0:
        kazanma_orani = float("nan")
        expectancy = float("nan")
        pf = float("nan")
        ort_kazanc_r = float("nan")
        ort_kayip_r = float("nan")
        ort_tutma = float("nan")
        en_kotu = None
    else:
        r_degerleri = [t["sonuc_R"] for t in islemler]
        kazananlar = [r for r in r_degerleri if r > 0]
        kaybedenler = [r for r in r_degerleri if r <= 0]
        kazanma_orani = len(kazananlar) / n
        expectancy = float(np.mean(r_degerleri))
        toplam_kazanc_tl = sum(t["net_pnl_tl"] for t in islemler if t["net_pnl_tl"] > 0)
        toplam_kayip_tl = abs(sum(t["net_pnl_tl"] for t in islemler if t["net_pnl_tl"] <= 0))
        pf = (toplam_kazanc_tl / toplam_kayip_tl) if toplam_kayip_tl > 0 else float("inf")
        ort_kazanc_r = float(np.mean(kazananlar)) if kazananlar else 0.0
        ort_kayip_r = float(np.mean(kaybedenler)) if kaybedenler else 0.0
        ort_tutma = float(np.mean([t["gun_sayisi"] for t in islemler]))
        en_kotu_islem = min(islemler, key=lambda t: t["sonuc_R"])
        en_kotu = {
            "sembol": en_kotu_islem["sembol"], "sonuc_R": en_kotu_islem["sonuc_R"],
            "net_pnl_tl": en_kotu_islem["net_pnl_tl"],
            "cikis_nedeni": en_kotu_islem["cikis_nedeni"],
        }

    if ozsermaye_egrisi:
        seri = pd.Series(
            {e["tarih"]: e["ozsermaye"] for e in ozsermaye_egrisi}
        ).sort_index()
        dusus_serisi = (seri / seri.cummax()) - 1.0
        maks_dusus = float(dusus_serisi.min())
        gun_araligi = (seri.index[-1] - seri.index[0]).days
        yil = max(gun_araligi / 365.25, 1e-9)
        cagr = float((seri.iloc[-1] / seri.iloc[0]) ** (1.0 / yil) - 1.0) if seri.iloc[0] > 0 else float("nan")
        # Ay sonu değerleri üzerinden aylık getiri tablosu. "M" pandas'ın
        # eski sürümlerinde de çalışan, deprecate edilse dahi işlevsel
        # kalan bir frekans kodu — CI ortamında pandas sürümü garanti
        # edilemediği için "ME" yerine bu tercih edildi.
        aylik = seri.resample("M").last()
        aylik_getiri = aylik.pct_change().dropna()
        aylik_getiri_tablosu = {d.strftime("%Y-%m"): float(v) for d, v in aylik_getiri.items()}
    else:
        maks_dusus = float("nan")
        cagr = float("nan")
        aylik_getiri_tablosu = {}

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

    return {
        "islem_sayisi": n,
        "kazanma_orani": kazanma_orani,
        "expectancy_R": expectancy,
        "profit_factor": pf,
        "ort_kazanc_R": ort_kazanc_r,
        "ort_kayip_R": ort_kayip_r,
        "maksimum_dusus_%": maks_dusus,
        "cagr": cagr,
        "endeks_cagr": endeks_cagr,
        "endeks_ustu_fark": endeks_ustu_fark,
        "ortalama_tutma_gun": ort_tutma,
        "en_kotu_islem": en_kotu,
        "aylik_getiri_tablosu": aylik_getiri_tablosu,
    }


def _kabul_kriterlerini_kontrol(metrikler: dict) -> dict:
    """§8 kabul kriterlerini (TEST dönemi metrikleri üzerinde) kontrol eder."""
    basarisiz: list[str] = []

    expectancy = metrikler.get("expectancy_R", float("nan"))
    if not (isinstance(expectancy, (int, float)) and expectancy > 0.15):
        basarisiz.append(f"Expectancy {expectancy:.3f}R — eşik: >0.15R")

    pf = metrikler.get("profit_factor", float("nan"))
    if not (isinstance(pf, (int, float)) and pf >= 1.4):
        basarisiz.append(f"Profit factor {pf:.2f} — eşik: >=1.4")

    maks_dusus = metrikler.get("maksimum_dusus_%", float("nan"))
    if not (isinstance(maks_dusus, (int, float)) and abs(maks_dusus) <= 0.20):
        basarisiz.append(f"Maksimum düşüş %{abs(maks_dusus) * 100:.1f} — eşik: <=%20")

    fark = metrikler.get("endeks_ustu_fark", float("nan"))
    if not (isinstance(fark, (int, float)) and fark > 0):
        fark_yuzde = fark * 100 if isinstance(fark, (int, float)) and not pd.isna(fark) else float("nan")
        basarisiz.append(f"Endeks üstü CAGR farkı %{fark_yuzde:.2f} puan — eşik: >0")

    n = metrikler.get("islem_sayisi", 0)
    if not (n >= 100):
        basarisiz.append(f"İşlem sayısı {n} — eşik: >=100")

    return {"gecti": len(basarisiz) == 0, "basarisiz_kriterler": basarisiz}


def calistir(baslangic: str, bitis: str, ozsermaye: float = 1_000_000.0) -> dict:
    """§11 imzası. Veriyi indirir/hazırlar, ardından _calistir_ic ile simüle eder.

    Döner: {'islemler': [...], 'ozsermaye_egrisi': [...], 'metrikler': {...}}
    """
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    # MA200(+10 gün kıyas) ve 250 günlük evren geçmişi şartı için baslangıç
    # tarihinden ÖNCEYE uzanan bir tampon indirilir — aksi halde backtest'in
    # ilk aylarında evren/rejim hep boş/varsayılan (R4) çıkar ve bu durum
    # yanlışlıkla "sistem hiç işlem yapmıyor" gibi yorumlanabilir.
    indirme_baslangic = (baslangic_ts - pd.Timedelta(days=500)).strftime("%Y-%m-%d")
    bitis_str = bitis_ts.strftime("%Y-%m-%d")

    print(f"[backtest] Veri indiriliyor: {len(evren.TEMEL_SEMBOLLER)} sembol + XU100.IS "
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
    print(f"[backtest] {len(veriler)}/{len(evren.TEMEL_SEMBOLLER)} sembol için veri hazır.")

    return _calistir_ic(veriler, endeks_df, baslangic, bitis, ozsermaye)


def walk_forward(ozsermaye: float = 1_000_000.0) -> dict:
    """§8 doğrulama: 2019-2023 geliştirme + 2024-bugün DOKUNULMAMIŞ test.

    Döner: {'gelistirme': {...}, 'test': {...}, 'dogrulama': {'gecti': bool,
    'basarisiz_kriterler': [...]}} — dogrulama YALNIZ test dönemi üzerinde
    hesaplanır (§8: "Kabul kriterleri (test döneminde, maliyet dahil)").
    """
    print("=" * 70)
    print("WALK-FORWARD — Geliştirme dönemi: 2019-01-01 → 2023-12-31")
    print("=" * 70)
    gelistirme = calistir("2019-01-01", "2023-12-31", ozsermaye)

    bugun = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    print("=" * 70)
    print(f"WALK-FORWARD — Test dönemi (DOKUNULMAMIŞ): 2024-01-01 → {bugun}")
    print("=" * 70)
    test = calistir("2024-01-01", bugun, ozsermaye)

    dogrulama = _kabul_kriterlerini_kontrol(test["metrikler"])

    print("=" * 70)
    if dogrulama["gecti"]:
        print("SONUÇ: §8 kabul kriterleri GEÇTİ — sistem tavsiye verebilir.")
    else:
        print("SONUÇ: §8 kabul kriterleri GEÇMEDİ — TAVSIYE_VERME modu gerekir.")
        for madde in dogrulama["basarisiz_kriterler"]:
            print(f"  - {madde}")
    print("=" * 70)

    return {"gelistirme": gelistirme, "test": test, "dogrulama": dogrulama}


# ═══════════════════════════════════════════════════════════════════════
# Kendi kendine kontrol — AĞ ÇAĞRISI YOK. Sentetik veriyle backtest
# döngüsünün LOOK-AHEAD sızıntısı yapmadığını doğrular: gelecekte "patlayan"
# bir hisse eklenir ve patlamadan ÖNCEKİ tüm günlerin sonuçlarının
# (özsermaye eğrisi + işlem listesi), o patlama var olmasaydı çıkacak
# sonuçlarla BİREBİR aynı olduğu kanıtlanır. Aynı desen veri.py / evren.py /
# rejim.py / sinyal.py'nin kendi self-testlerinde de kullanılıyor; burada
# TÜM PİPELİNE (evren+rejim+sinyal+risk+pozisyon+maliyet+emir kuyruğu)
# birlikte, uçtan uca test ediliyor.
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    n_gun = 480
    tarihler = pd.date_range("2022-01-03", periods=n_gun, freq="B")
    kesim_idx = 380  # bu günden SONRASI iki senaryoda farklılaşacak
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
    # değişecek) — böylece gözlenecek herhangi bir fark, saf biçimde o
    # hissenin gelecekteki verisinin geçmişe sızıp sızmadığını gösterir.
    endeks_df = _rastgele_df(5000, 3.0, 20.0, 50_000_000, tohum=1)

    def _evren_kur(gelecek_kapanis_override=None):
        veriler = {}
        # Dolgu sembolleri: evren/göreli güç yüzdeliğinin anlamlı çalışması
        # ve rejim genişliğinin makul çıkması için birkaç sembol daha.
        for i, tohum in enumerate((11, 12, 13, 14, 15, 16)):
            df = _rastgele_df(50.0 + i * 5, 0.05, 0.6, 30_000_000, tohum=tohum)
            veriler[f"DOLGU{i}"] = veri.gostergeler(df)
        gelecek_df = _rastgele_df(40.0, 0.04, 0.5, 40_000_000, tohum=99)
        if gelecek_kapanis_override is not None:
            gelecek_df = gelecek_df.copy()
            gelecek_df.loc[gelecek_df.index > kesim_tarih, "Close"] = gelecek_kapanis_override
            gelecek_df.loc[gelecek_df.index > kesim_tarih, "Open"] = gelecek_kapanis_override
            gelecek_df.loc[gelecek_df.index > kesim_tarih, "High"] = gelecek_kapanis_override * 1.01
            gelecek_df.loc[gelecek_df.index > kesim_tarih, "Low"] = gelecek_kapanis_override * 0.99
        veriler["GELECEK"] = veri.gostergeler(gelecek_df)
        return veriler

    # Senaryo A: GELECEK, kesimden sonra da normal/durgun devam ediyor.
    veriler_a = _evren_kur(gelecek_kapanis_override=None)

    # Senaryo B: GELECEK, kesimden HEMEN SONRA aniden %60 PATLIYOR (tek
    # günde büyük sıçrama, ardından yüksek seviyede tutunuyor). Sistem bunu
    # ÖNCEDEN (kesim tarihine kadar olan kararlarda) GÖRMEMELİ.
    n_sonrasi = (tarihler > kesim_tarih).sum()
    patlama_seviyesi = 40.0 * (1.6 + np.linspace(0, 0.4, n_sonrasi))
    veriler_b = _evren_kur(gelecek_kapanis_override=patlama_seviyesi)

    print("Senaryo A çalıştırılıyor (patlama YOK)...")
    sonuc_a = _calistir_ic(veriler_a, endeks_df,
                            tarihler[250].strftime("%Y-%m-%d"),
                            tarihler[-1].strftime("%Y-%m-%d"),
                            ozsermaye=1_000_000.0, ilerleme=False)
    print("Senaryo B çalıştırılıyor (GELECEK kesimden sonra %60+ patlıyor)...")
    sonuc_b = _calistir_ic(veriler_b, endeks_df,
                            tarihler[250].strftime("%Y-%m-%d"),
                            tarihler[-1].strftime("%Y-%m-%d"),
                            ozsermaye=1_000_000.0, ilerleme=False)

    # ── Kontrol 1: kesim tarihine KADAR olan özsermaye eğrisi birebir aynı
    #    olmalı (bir kuruşluk fark bile look-ahead sızıntısına işaret eder). ──
    egri_a = {e["tarih"]: e["ozsermaye"] for e in sonuc_a["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    egri_b = {e["tarih"]: e["ozsermaye"] for e in sonuc_b["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    assert set(egri_a.keys()) == set(egri_b.keys()), "Kesim öncesi tarih kümeleri farklı!"
    for t in egri_a:
        fark = abs(egri_a[t] - egri_b[t])
        assert fark < 1e-6, (
            f"LOOK-AHEAD SIZINTISI: {t.date()} günü özsermayesi senaryolar arasında "
            f"farklı çıktı (A={egri_a[t]:.4f}, B={egri_b[t]:.4f}). Gelecekteki patlama "
            f"geçmiş kararları etkilemiş."
        )

    # ── Kontrol 2: kesim tarihine kadar GİRİŞİ yapılmış işlemler de birebir
    #    aynı olmalı (giriş tarihi, fiyatı, adedi vb.). ──
    def _kesim_oncesi_girisler(sonuc):
        return sorted(
            [(t["sembol"], t["giris_tarihi"], round(t["giris_fiyati"], 6), t["adet"])
             for t in sonuc["islemler"] if t["giris_tarihi"] <= kesim_tarih]
        )
    girisler_a = _kesim_oncesi_girisler(sonuc_a)
    girisler_b = _kesim_oncesi_girisler(sonuc_b)
    assert girisler_a == girisler_b, (
        "LOOK-AHEAD SIZINTISI: kesim öncesi açılan pozisyonlar senaryolar arasında "
        f"farklı!\nA={girisler_a}\nB={girisler_b}"
    )

    # ── Kontrol 3: sistem GELECEK'e kesim tarihinden ÖNCE, patlamayı önceden
    #    görmüşçesine anormal büyük/erken bir pozisyon açmamış olmalı —
    #    yani "GELECEK" sembolüne kesim öncesi açılan pozisyon sayısı iki
    #    senaryoda da (zaten Kontrol 2 ile) birebir aynı çıkmış olmalı. ──
    gelecek_girisleri_a = [g for g in girisler_a if g[0] == "GELECEK"]
    gelecek_girisleri_b = [g for g in girisler_b if g[0] == "GELECEK"]
    assert gelecek_girisleri_a == gelecek_girisleri_b

    print("backtest.py kendi kendine kontrol (LOOK-AHEAD testi): BAŞARILI")
    print(f"  Kesim tarihi: {kesim_tarih.date()}")
    print(f"  Kesim öncesi ortak işlem sayısı: {len(girisler_a)}")
    print(f"  Senaryo A toplam işlem: {len(sonuc_a['islemler'])}, "
          f"Senaryo B toplam işlem: {len(sonuc_b['islemler'])}")
    print(f"  Senaryo A metrikleri: {sonuc_a['metrikler']}")
