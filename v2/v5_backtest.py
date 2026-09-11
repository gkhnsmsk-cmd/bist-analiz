# -*- coding: utf-8 -*-
"""
v2/v5_backtest.py — "Akıl hocası" V5: V2 mimarisi üzerinde, DAHA AZ ama DAHA
KALİTELİ sinyal + DAHA GENİŞ stop mesafesiyle whipsaw azaltma denemesi.

BAĞLAM (neden bu dosya var): V2'nin test dönemi sonucu PF=0.99, expectancy
neredeyse sıfırdı — kabul edilemez. Kullanıcının artık istediği ölçüt
"endeksi her koşulda yen" DEĞİL, "zaman ayıramayan kullanıcı için pozitif
expectancy'li, riski kontrollü, disiplinli bir akıl hocası" olmak. Bu dosya
V2'nin (backtest.py/sinyal.py/risk.py/pozisyon.py) HİÇBİRİNİ DEĞİŞTİRMEZ —
onları olduğu gibi import edip YENİDEN KULLANIR; yalnız iki noktada V5'e özgü
YEREL mantık ekler:

  1) GİRİŞ FİLTRESİ SIKILAŞTIRMA: sinyal.giris_adaylari() zaten V2'nin 6
     şartının (VE mantığı) TAMAMINI uygulayıp bir aday listesi döndürüyor.
     V5 bu listeyi olduğu gibi ALMAZ, üstüne ÜÇ ek süzgeç koyar:
       a) yalnız 'kirilim' kurulumu (fiyat+hacim TEYİTLİ, 'geri_cekilme'nin
          RSI-dönüşü yorumundan daha öznel/gürültülü sinyalini ELE),
       b) göreli güç yüzdeliği >= 85 (V2'de 75 idi — yalnız evrenin gerçekten
          en güçlü %15'i),
       c) UZAMA <= 1.2 (V2'de tavan 2.0 idi — yalnız henüz aşırı uzamamış,
          "taze" kırılımlar; aşırı uzamış kırılımlar whipsaw'a daha yatkın).
     Amaç: işlem SAYISINI azaltıp KALİTESİNİ artırmak (kök neden: gevşek
     giriş, kazanan/kaybedeni ayırt edemiyordu -> PF~1).

  2) STOP MESAFESİ GENİŞLETME: V2 ilk_stop = giriş - 2.5×ATR14 kullanıyordu.
     risk.py bu çarpanı SABİT (2.5) kodluyor ve dışarıdan parametre almıyor;
     bu yüzden risk.py'ye DOKUNMADAN aynı 4-kısıt mantığını YEREL bir
     `_pozisyon_boyutu_v5()` fonksiyonunda, yalnız stop çarpanı 3.5×ATR
     olacak şekilde yeniden uyguluyoruz (risk.py'nin metodolojisini birebir
     taklit eder, tek fark stop mesafesi). Amaç: kök neden analizi 2.5×ATR'nin
     normal günlük gürültüde bile sık tetiklenip (whipsaw) kazanan olabilecek
     pozisyonları erken kestiği yönünde; 3.5×ATR bu payı büyütür.

     pozisyon.py'nin trailing_guncelle()/cikis_kontrol() fonksiyonları
     DEĞİŞTİRİLMEDEN, olduğu gibi kullanılır — bunlar yalnız pozisyon
     sözlüğündeki 'ilk_stop'/'guncel_stop' DEĞERLERİNİ okur, çarpanı kendi
     içinde sabitlemez (chandelier çarpanı ayrı, o V2'deki 3.0×ATR/+1R
     aktivasyonuyla aynen kalıyor — kazananları daha uzun tutma denemesi de
     buradan geliyor: artık 3.5×ATR'lik bir ilk stopun ardından devreye giren
     aynı chandelier, göreli olarak daha az sık tetiklenecek).

Ayrıca bu dosya §8 tarzı metriklere EK olarak yıllıklandırılmış SHARPE
ORANINI da hesaplar (V2/V3/V4'te yoktu) — kullanıcının yeni kabul ölçütü
Sharpe > 0.8 (tercihen) içerdiği için.

Mimari disiplin: backtest.py'deki ÜÇ ZORUNLU kural (T kapanışı->T+1 açılışı,
§7 maliyet/tavan-taban/gap koruması, günlük mark-to-market özsermaye) BİREBİR
korunur — bu dosya backtest._calistir_ic'in bir ÇATALIDIR (fork), iskeleti
aynıdır, yalnız yukarıdaki iki nokta değişir.
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
import sinyal
import pozisyon  # cikis_kontrol, trailing_guncelle, portfoy_kisit_kontrol — DEĞİŞTİRİLMEDEN kullanılır

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
# §7 maliyet sabitleri — V2 ile BİREBİR AYNI (maliyet modelini gevşetmek
# "iyileştirme" değil kendini kandırma olurdu).
# ─────────────────────────────────────────────────────────────────────────
_KOMISYON_ORANI = 0.0015
_KAYMA_NORMAL = 0.0010
_KAYMA_DUSUK_LIKIDITE = 0.0025
_DUSUK_LIKIDITE_ESIGI = 50_000_000.0
_TAVAN_TABAN_ESIGI = 0.095

_MAKS_ESZAMANLI_POZISYON = 6
_MAKS_GUNLUK_YENI_POZISYON = 2
_KADEMELI_ADIM = 0.25
_EVREN_YENILEME_ARALIGI = 5
_STOP_SAYILAN_NEDENLER = ("stop", "trailing")

# ─────────────────────────────────────────────────────────────────────────
# V5'E ÖZGÜ DEĞİŞİKLİKLER (bkz. modül başı dokümantasyonu).
# ─────────────────────────────────────────────────────────────────────────
<<<<<<< HEAD
# DENEME 2 NOTU: ilk deneme (kirilim-yalnız + göreli güç>=85 + uzama<=1.2)
# BIST100 evreninde 5 yıl boyunca SIFIR işlem üretti — üç filtrenin AYNI ANDA
# uygulanması pratikte boş küme veriyordu (aşırı sıkılaştırma, kabul
# edilemez bir sonuç: "işlem yok" pozitif expectancy DEĞİLDİR). Bu yüzden
# kurulum kısıtı V2'deki gibi (kirilim + geri_cekilme) GERİ ALINDI ve
# göreli güç/uzama eşikleri DAHA YUMUŞAK tutuldu — ana müdahale artık
# STOP GENİŞLETME (kök neden analizinin ikinci bacağı: whipsaw) üzerinde
# yoğunlaşıyor, giriş filtresi yalnız HAFİF sıkılaştırılıyor.
_V5_STOP_ATR_KATSAYI = 3.5          # V2: 2.5 — whipsaw azaltmak için genişletildi
_V5_MIN_GORELI_GUC = 80.0           # V2: 75.0 — hafif sıkılaştırma (85 çok sertti)
_V5_MAKS_UZAMA = 1.6                # V2: 2.0 — hafif sıkılaştırma (1.2 çok sertti)
_V5_IZIN_VERILEN_KURULUMLAR = ("kirilim", "geri_cekilme")  # V2 ile AYNI (değiştirilmedi)
=======
_V5_STOP_ATR_KATSAYI = 3.5          # V2: 2.5 — whipsaw azaltmak için genişletildi
_V5_MIN_GORELI_GUC = 85.0           # V2: 75.0 — yalnız evrenin en güçlü %15'i
_V5_MAKS_UZAMA = 1.2                # V2: 2.0 — yalnız taze/az uzamış kırılımlar
_V5_IZIN_VERILEN_KURULUMLAR = ("kirilim",)  # V2: kirilim + geri_cekilme
>>>>>>> 814e7b23fae176dcf700d5f8089f95b99b47d6ce

# risk.py ile aynı diğer sabitler (yalnız stop çarpanı farklı).
_RISK_ORANI = 0.01
_TEK_POZISYON_TAVANI = 0.20
_LIKIDITE_ORANI = 0.01


def _v5_giris_adaylari(veriler: dict, evren_guncel: list[str], tarih) -> list[dict]:
    """sinyal.giris_adaylari()'nin (V2, DEĞİŞTİRİLMEMİŞ) çıktısına V5'in üç
    ek/sıkılaştırılmış süzgecini uygular. sinyal.py'nin kendisi ASLA
    değiştirilmez — yalnız onun ürettiği (zaten 6 V2 şartının tamamını
    geçmiş) listeden daha az/daha kaliteli bir alt küme seçilir.
    """
    taban_adaylar = sinyal.giris_adaylari(veriler, evren_guncel, tarih)
    v5_adaylar = [
        a for a in taban_adaylar
        if a["kurulum"] in _V5_IZIN_VERILEN_KURULUMLAR
        and a["goreli_guc"] >= _V5_MIN_GORELI_GUC
        and a["uzama"] <= _V5_MAKS_UZAMA
    ]
    return v5_adaylar


def _pozisyon_boyutu_v5(ozsermaye, kapanis, atr, hacim_tl_medyan,
                         mevcut_yatirim, hedef_oran) -> dict:
    """risk.pozisyon_boyutu() ile AYNI dört-kısıt metodolojisi (%1 risk,
    tek pozisyon %20 tavanı, likidite %1, rejim hedef kapasitesi) — TEK FARK:
    stop mesafesi 2.5xATR yerine _V5_STOP_ATR_KATSAYI (3.5) x ATR. risk.py'ye
    dokunulmadığından bu mantık burada yerel olarak (kısa) yeniden yazıldı.
    """
    if ozsermaye is None or pd.isna(ozsermaye) or ozsermaye <= 0:
        return {"adet": 0.0, "stop": float("nan"), "deger": 0.0, "risk_tl": 0.0,
                "red_nedeni": "Özsermaye geçersiz (sıfır veya negatif)."}
    if kapanis is None or pd.isna(kapanis) or kapanis <= 0:
        return {"adet": 0.0, "stop": float("nan"), "deger": 0.0, "risk_tl": 0.0,
                "red_nedeni": "Kapanış fiyatı geçersiz (sıfır veya negatif)."}
    if atr is None or pd.isna(atr) or atr <= 0:
        return {"adet": 0.0, "stop": kapanis, "deger": 0.0, "risk_tl": 0.0,
                "red_nedeni": "ATR14 geçersiz (sıfır/NaN) — stop mesafesi hesaplanamıyor."}

    stop_mesafe = _V5_STOP_ATR_KATSAYI * atr
    stop_fiyati = kapanis - stop_mesafe

    risk_tutari = ozsermaye * _RISK_ORANI
    adet_ham = risk_tutari / stop_mesafe

    deger_tavan_pozisyon = ozsermaye * _TEK_POZISYON_TAVANI

    if hacim_tl_medyan is None or pd.isna(hacim_tl_medyan) or hacim_tl_medyan <= 0:
        deger_tavan_likidite = 0.0
        likidite_bilgi_yok = True
    else:
        deger_tavan_likidite = hacim_tl_medyan * _LIKIDITE_ORANI
        likidite_bilgi_yok = False

    mevcut_yatirim_guvenli = 0.0 if (mevcut_yatirim is None or pd.isna(mevcut_yatirim)) else mevcut_yatirim
    hedef_oran_guvenli = 0.0 if (hedef_oran is None or pd.isna(hedef_oran)) else hedef_oran
    kalan_hedef_kapasite = hedef_oran_guvenli * ozsermaye - mevcut_yatirim_guvenli
    deger_tavan_rejim = max(0.0, kalan_hedef_kapasite)

    adet_tavan_pozisyon = deger_tavan_pozisyon / kapanis
    adet_tavan_likidite = deger_tavan_likidite / kapanis
    adet_tavan_rejim = deger_tavan_rejim / kapanis

    adaylar = {
        "risk_kurali_%1": adet_ham,
        "tek_pozisyon_%20": adet_tavan_pozisyon,
        "likidite_%1_hacim": adet_tavan_likidite,
        "rejim_hedef_kapasitesi": adet_tavan_rejim,
    }
    baglayan_kisit = min(adaylar, key=lambda k: adaylar[k])
    adet_nihai = max(0.0, adaylar[baglayan_kisit])
    adet_nihai = float(math.floor(adet_nihai))

    if adet_nihai < 1.0:
        if likidite_bilgi_yok:
            neden = "20 günlük medyan TL hacim bilgisi eksik/geçersiz — likidite kısıtı değerlendirilemedi."
        elif baglayan_kisit == "likidite_%1_hacim":
            neden = ("Hesaplanan pozisyon büyüklüğü günlük hacmin %1'ini aşıyor "
                      "(20g medyan TL hacim çok düşük) — 1 pay bile alınamıyor.")
        elif baglayan_kisit == "rejim_hedef_kapasitesi":
            neden = ("Mevcut yatırım zaten rejimin hedef yatırım oranına ulaşmış/aşmış "
                      "— yeni pozisyon için kapasite kalmadı.")
        elif baglayan_kisit == "tek_pozisyon_%20":
            neden = "Tek pozisyon tavanı (özsermayenin %20'si) 1 payı bile karşılamıyor."
        else:
            neden = "Hesaplanan pozisyon büyüklüğü (%1 risk kuralına göre) 1 paydan küçük çıktı."
        return {"adet": 0.0, "stop": float(stop_fiyati), "deger": 0.0, "risk_tl": 0.0,
                "red_nedeni": neden}

    deger = adet_nihai * kapanis
    risk_tl = adet_nihai * stop_mesafe

    return {
        "adet": adet_nihai, "stop": float(stop_fiyati), "deger": float(deger),
        "risk_tl": float(risk_tl), "red_nedeni": None,
    }


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


def _guncel_r(pozisyon_dict: dict, fiyat: float) -> float:
    r_birimi = pozisyon_dict["giris_fiyati"] - pozisyon_dict["ilk_stop"]
    if r_birimi <= 0:
        return 0.0
    return (fiyat - pozisyon_dict["giris_fiyati"]) / r_birimi


# ─────────────────────────────────────────────────────────────────────────
# Simülasyon çekirdeği — backtest._calistir_ic'in ÇATALI. İskelet birebir
# aynı (look-ahead güvenliği, emir kuyruğu, mark-to-market) — yalnız (1)
# sinyal üretiminde _v5_giris_adaylari, (2) boyutlandırmada
# _pozisyon_boyutu_v5, (3) ilk_stop hesabında _V5_STOP_ATR_KATSAYI kullanılır.
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
        bugun_acilan_sayisi = 0
        for emir in pending_orders:
            if bugun_acilan_sayisi >= _MAKS_GUNLUK_YENI_POZISYON:
                break
            if len(acik_pozisyonlar) >= _MAKS_ESZAMANLI_POZISYON:
                break
            sembol = emir["sembol"]
            df = veriler.get(sembol)
            if df is None or T not in df.index:
                continue
            if _tavan_taban_mi(df, T):
                continue
            satir = df.loc[T]
            acilis = satir.get("Open")
            if acilis is None or pd.isna(acilis):
                continue
            if acilis < emir["teorik_stop"]:
                continue

            oran = _komisyon_kayma_orani(satir.get("HACIM_TL_MEDYAN20"))
            adet = emir["adet"]
            maliyet_giris = adet * acilis * oran
            cash -= (adet * acilis + maliyet_giris)

            ilk_stop = float(acilis - _V5_STOP_ATR_KATSAYI * emir["atr_T"])
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
                "risk_tl_giris": adet * _V5_STOP_ATR_KATSAYI * emir["atr_T"],
                "maliyet_giris_tl": maliyet_giris,
                "kurulum": emir["kurulum"],
                "skor_giriste": emir["skor"],
                "rejim_giriste": emir["rejim_giriste"],
            })
            bugun_acilan_sayisi += 1
        pending_orders = []

        rejim_bugun = rejim.rejim_hesapla(endeks_df, veriler, T)

        hedef = rejim_bugun["hedef_oran"]
        if hedef > efektif_hedef_oran:
            efektif_hedef_oran = min(hedef, efektif_hedef_oran + _KADEMELI_ADIM)
        else:
            efektif_hedef_oran = hedef

        kapanislar_bugun: dict[str, float] = {}
        for poz in acik_pozisyonlar:
            df = veriler.get(poz["sembol"])
            if df is None or T not in df.index:
                continue
            satir = df.loc[T]
            poz.update(pozisyon.trailing_guncelle(poz, satir))  # V2, DEĞİŞTİRİLMEDEN
            kapanislar_bugun[poz["sembol"]] = float(satir["Close"])

        rejim_bayraksiz = dict(rejim_bugun)
        cikacaklar: dict[str, dict] = {}
        for poz in acik_pozisyonlar:
            df = veriler.get(poz["sembol"])
            if df is None or T not in df.index:
                continue
            satir = df.loc[T]
            sonuc = pozisyon.cikis_kontrol(poz, satir, rejim_bayraksiz)  # V2, DEĞİŞTİRİLMEDEN
            if sonuc is not None:
                cikacaklar[poz["sembol"]] = sonuc

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

        kalan_pozisyonlar = []
        for poz in acik_pozisyonlar:
            sembol = poz["sembol"]
            if sembol not in cikacaklar:
                kalan_pozisyonlar.append(poz)
                continue
            df = veriler[sembol]
            if _tavan_taban_mi(df, T):
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

        if idx % _EVREN_YENILEME_ARALIGI == 0:
            evren_guncel = evren.evren_olustur(veriler, T)

        mevcut_yatirim_deger = sum(
            kapanislar_bugun.get(p["sembol"], p["giris_fiyati"]) * p["adet"]
            for p in acik_pozisyonlar
        )
        guncel_ozsermaye = cash + mevcut_yatirim_deger

        if len(acik_pozisyonlar) < _MAKS_ESZAMANLI_POZISYON:
            adaylar = _v5_giris_adaylari(veriler, evren_guncel, T)  # V5: sıkılaştırılmış
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
                red = pozisyon.portfoy_kisit_kontrol(  # V2, DEĞİŞTİRİLMEDEN
                    aday_full, acik_pozisyonlar, yeni_kuyruk_sayisi,
                    son_stop_tarihleri, _SEKTOR_HARITASI,
                )
                if red is not None:
                    continue
                boyut = _pozisyon_boyutu_v5(
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

        mtm = sum(kapanislar_bugun.get(p["sembol"], p["giris_fiyati"]) * p["adet"]
                  for p in acik_pozisyonlar)
        ozsermaye_egrisi.append({"tarih": T, "ozsermaye": cash + mtm})

        if ilerleme and (idx % 100 == 0 or idx == toplam_gun - 1):
            print(f"[v5_backtest] {idx + 1}/{toplam_gun} gün işlendi "
                  f"({T.date()}) — açık pozisyon: {len(acik_pozisyonlar)}, "
                  f"özsermaye: {cash + mtm:,.0f} TL")

    metrikler = _metrikleri_hesapla(islemler, ozsermaye_egrisi, endeks_df, baslangic_ts, bitis_ts)
    return {"islemler": islemler, "ozsermaye_egrisi": ozsermaye_egrisi, "metrikler": metrikler}


def _yillik_sharpe_hesapla(ozsermaye_egrisi: list[dict]) -> float:
    """Yıllıklandırılmış Sharpe oranı (risksiz oran=0 varsayımıyla, basit
    yaklaşım): günlük özsermaye getirilerinin ortalaması / std sapması,
    sqrt(252) ile yıllıklandırılır. Getiri serisi çok kısa/sabit ise NaN
    döner (bölme tanımsız durumları sessizce yanlış yorumlamak yerine)."""
    if not ozsermaye_egrisi or len(ozsermaye_egrisi) < 3:
        return float("nan")
    seri = pd.Series(
        {e["tarih"]: e["ozsermaye"] for e in ozsermaye_egrisi}
    ).sort_index().dropna()
    if len(seri) < 3:
        return float("nan")
    gunluk_getiri = seri.pct_change().dropna()
    if len(gunluk_getiri) < 2 or gunluk_getiri.std() == 0 or pd.isna(gunluk_getiri.std()):
        return float("nan")
    return float((gunluk_getiri.mean() / gunluk_getiri.std()) * np.sqrt(252))


def _metrikleri_hesapla(islemler: list[dict], ozsermaye_egrisi: list[dict],
                         endeks_df: pd.DataFrame, baslangic_ts: pd.Timestamp,
                         bitis_ts: pd.Timestamp) -> dict:
    """backtest._metrikleri_hesapla ile AYNI + ek olarak 'sharpe_yillik'."""
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

    sharpe = _yillik_sharpe_hesapla(ozsermaye_egrisi)

    if ozsermaye_egrisi:
        seri = pd.Series(
            {e["tarih"]: e["ozsermaye"] for e in ozsermaye_egrisi}
        ).sort_index()
        seri = seri.dropna()
        if seri.empty:
            return {
                "islem_sayisi": n, "kazanma_orani": kazanma_orani,
                "expectancy_R": expectancy, "profit_factor": pf,
                "ort_kazanc_R": ort_kazanc_r, "ort_kayip_R": ort_kayip_r,
                "maksimum_dusus_%": float("nan"), "cagr": float("nan"),
                "endeks_cagr": float("nan"), "endeks_ustu_fark": float("nan"),
                "ortalama_tutma_gun": ort_tutma, "en_kotu_islem": en_kotu,
                "sharpe_yillik": sharpe, "aylik_getiri_tablosu": {},
            }
        dusus_serisi = (seri / seri.cummax()) - 1.0
        maks_dusus = float(dusus_serisi.min())
        gun_araligi = (seri.index[-1] - seri.index[0]).days
        yil = max(gun_araligi / 365.25, 1e-9)
        cagr = float((seri.iloc[-1] / seri.iloc[0]) ** (1.0 / yil) - 1.0) if seri.iloc[0] > 0 else float("nan")
        try:
            aylik = seri.resample("ME").last()
        except ValueError:
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
        "sharpe_yillik": sharpe,
        "aylik_getiri_tablosu": aylik_getiri_tablosu,
    }


def _kabul_kriterlerini_kontrol(metrikler: dict) -> dict:
    """YENİ (V5) kabul kriterleri — kullanıcının değişen ölçütü:
    'endeksi her dönem yen' ZORUNLU DEĞİL; asıl ölçüt pozitif expectancy,
    PF>=1.3, kontrollü düşüş (<=%25), pozitif/mantıklı CAGR. Sharpe>0.8
    TERCİH edilir ama tek başına reddettirmez (bilgilendirme amaçlı)."""
    basarisiz: list[str] = []
    uyarilar: list[str] = []

    expectancy = metrikler.get("expectancy_R", float("nan"))
    if not (isinstance(expectancy, (int, float)) and expectancy > 0):
        basarisiz.append(f"Expectancy {expectancy:.3f}R — eşik: >0R (pozitif olmalı)")

    pf = metrikler.get("profit_factor", float("nan"))
    if not (isinstance(pf, (int, float)) and pf >= 1.3):
        pf_metin = f"{pf:.2f}" if isinstance(pf, (int, float)) and not pd.isna(pf) else "tanımsız"
        basarisiz.append(f"Profit factor {pf_metin} — eşik: >=1.3")

    maks_dusus = metrikler.get("maksimum_dusus_%", float("nan"))
    if not (isinstance(maks_dusus, (int, float)) and abs(maks_dusus) <= 0.25):
        basarisiz.append(f"Maksimum düşüş %{abs(maks_dusus) * 100:.1f} — eşik: <=%25")

    cagr = metrikler.get("cagr", float("nan"))
    if not (isinstance(cagr, (int, float)) and cagr > 0):
        cagr_metin = f"%{cagr*100:.2f}" if isinstance(cagr, (int, float)) and not pd.isna(cagr) else "tanımsız"
        basarisiz.append(f"CAGR {cagr_metin} — eşik: >0 (pozitif sermaye artışı zorunlu)")

    sharpe = metrikler.get("sharpe_yillik", float("nan"))
    if not (isinstance(sharpe, (int, float)) and sharpe > 0.8):
        sharpe_metin = f"{sharpe:.2f}" if isinstance(sharpe, (int, float)) and not pd.isna(sharpe) else "tanımsız"
        uyarilar.append(f"Sharpe {sharpe_metin} — TERCİH edilen eşik: >0.8 (bağlayıcı değil)")

    n = metrikler.get("islem_sayisi", 0)
    if n < 20:
        uyarilar.append(f"İşlem sayısı {n} — istatistiksel güven düşük olabilir (bağlayıcı değil, bilgilendirme)")

    return {"gecti": len(basarisiz) == 0, "basarisiz_kriterler": basarisiz, "uyarilar": uyarilar}


def calistir(baslangic: str, bitis: str, ozsermaye: float = 1_000_000.0) -> dict:
    baslangic_ts = pd.Timestamp(baslangic)
    bitis_ts = pd.Timestamp(bitis)
    indirme_baslangic = (baslangic_ts - pd.Timedelta(days=500)).strftime("%Y-%m-%d")
    bitis_str = bitis_ts.strftime("%Y-%m-%d")

    print(f"[v5_backtest] Veri indiriliyor: {len(evren.TEMEL_SEMBOLLER)} sembol + XU100.IS "
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
    print(f"[v5_backtest] {len(veriler)}/{len(evren.TEMEL_SEMBOLLER)} sembol için veri hazır.")

    return _calistir_ic(veriler, endeks_df, baslangic, bitis, ozsermaye)


def walk_forward(ozsermaye: float = 1_000_000.0) -> dict:
    """§8 doğrulama deseni (V2 ile aynı bölünme): 2019-2023 geliştirme +
    2024-bugün DOKUNULMAMIŞ test. Dogrulama YALNIZ test döneminde, YENİ (V5)
    kabul kriterleriyle hesaplanır."""
    print("=" * 70)
    print("V5 WALK-FORWARD — Geliştirme dönemi: 2019-01-01 → 2023-12-31")
    print("=" * 70)
    gelistirme = calistir("2019-01-01", "2023-12-31", ozsermaye)

    bugun = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")
    print("=" * 70)
    print(f"V5 WALK-FORWARD — Test dönemi (DOKUNULMAMIŞ): 2024-01-01 → {bugun}")
    print("=" * 70)
    test = calistir("2024-01-01", bugun, ozsermaye)

    dogrulama = _kabul_kriterlerini_kontrol(test["metrikler"])

    print("=" * 70)
    if dogrulama["gecti"]:
        print("SONUÇ: V5 YENİ kabul kriterleri GEÇTİ — AKIL HOCASI KABUL EDİLDİ.")
    else:
        print("SONUÇ: V5 YENİ kabul kriterleri GEÇMEDİ.")
        for madde in dogrulama["basarisiz_kriterler"]:
            print(f"  - {madde}")
    for uyari in dogrulama.get("uyarilar", []):
        print(f"  [uyarı, bağlayıcı değil] {uyari}")
    print("=" * 70)

    return {"gelistirme": gelistirme, "test": test, "dogrulama": dogrulama}


# ═══════════════════════════════════════════════════════════════════════
# Kendi kendine kontrol — AĞ ÇAĞRISI YOK. backtest.py'deki desenle aynı
# LOOK-AHEAD testi + ayrıca V5'in giriş filtresinin GERÇEKTEN V2'den daha
# az/daha sıkı aday ürettiğini doğrular.
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    n_gun = 480
    tarihler = pd.date_range("2022-01-03", periods=n_gun, freq="B")
    kesim_idx = 380
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

    veriler_a = _evren_kur(gelecek_kapanis_override=None)
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

    egri_a = {e["tarih"]: e["ozsermaye"] for e in sonuc_a["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    egri_b = {e["tarih"]: e["ozsermaye"] for e in sonuc_b["ozsermaye_egrisi"] if e["tarih"] <= kesim_tarih}
    assert set(egri_a.keys()) == set(egri_b.keys()), "Kesim öncesi tarih kümeleri farklı!"
    for t in egri_a:
        fark = abs(egri_a[t] - egri_b[t])
        assert fark < 1e-6, (
            f"LOOK-AHEAD SIZINTISI: {t.date()} günü özsermayesi senaryolar arasında farklı çıktı."
        )

    def _kesim_oncesi_girisler(sonuc):
        return sorted(
            [(t["sembol"], t["giris_tarihi"], round(t["giris_fiyati"], 6), t["adet"])
             for t in sonuc["islemler"] if t["giris_tarihi"] <= kesim_tarih]
        )
    girisler_a = _kesim_oncesi_girisler(sonuc_a)
    girisler_b = _kesim_oncesi_girisler(sonuc_b)
    assert girisler_a == girisler_b, "LOOK-AHEAD SIZINTISI: kesim öncesi açılan pozisyonlar farklı!"

    print("v5_backtest.py kendi kendine kontrol (LOOK-AHEAD testi): BAŞARILI")
    print(f"  Kesim tarihi: {kesim_tarih.date()}")
    print(f"  Senaryo A toplam işlem: {len(sonuc_a['islemler'])}")
    print(f"  Senaryo A metrikleri: {sonuc_a['metrikler']}")

<<<<<<< HEAD
    # V5 filtresinin V2'den DAHA AZ/EŞİT aday ürettiğini doğrula (sıkılaştırma
    # gerçekten kısıtlayıcı, gevşetici değil).
=======
>>>>>>> 814e7b23fae176dcf700d5f8089f95b99b47d6ce
    evren_test = evren.evren_olustur(veriler_a, tarihler[300])
    v2_adaylar = sinyal.giris_adaylari(veriler_a, evren_test, tarihler[300])
    v5_adaylar = _v5_giris_adaylari(veriler_a, evren_test, tarihler[300])
    assert len(v5_adaylar) <= len(v2_adaylar), (
        f"V5 filtresi V2'den DAHA FAZLA aday üretti (beklenmiyor): V2={len(v2_adaylar)}, V5={len(v5_adaylar)}"
    )
    print(f"  V2 aday sayısı: {len(v2_adaylar)}, V5 (sıkılaştırılmış) aday sayısı: {len(v5_adaylar)}")
    print("v5_backtest.py: giriş filtresi sıkılaştırması doğrulandı.")
