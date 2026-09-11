# -*- coding: utf-8 -*-
"""
v2/v6_portfoy.py — Pusula V6 YOĞUNLAŞTIRILMIŞ pozisyon yönetimi.

Mimari, pozisyon.py (V2) ile AYNI aileden: her pozisyon KENDİ giriş/stop/
trailing durumuyla ayrı ayrı takip edilir (v3_portfoy.py'nin haftalık ağırlık
REBALANSI değil) — çünkü V6'nın amacı "az sayıda, yüksek güvenli pozisyonu
kâr hedefiyle uzatmak", bu da pozisyon-bazlı bir yaşam döngüsü gerektirir.

V2'den (başarısız) FARKLARI (bilerek):
  - Maks EŞZAMANLI pozisyon 6 değil 3-5 (yoğunlaşma).
  - Pozisyon ağırlığı sabit/küçük değil, %20-%33 bandında YÜKSEK.
  - Zaman stopu YOK (V2'nin "ölü para" mantığı burada gereksiz — az sayıda
    yüksek-güven pozisyonun sabırla beklenmesi bilinçli bir tercih).
  - Kâr hedefi VAR (V2'de yoktu): +%15'te pozisyonun YARISI realize edilir
    ve kalan yarının stopu başabaşa (giriş fiyatına) çekilir — "kazananı
    büyüt, güvenceye al" ilkesi. +%25'ten sonra trailing ATR çarpanı
    SIKILAŞTIRILIR (kazancın daha büyük bir kısmı korunur).
  - Rejim çıkışı İKİLİ (V3'ün kademeli R3=%30 hedefinin AKSİNE): R3 VE R4
    ikisi de TAM nakde çeker — "sermaye korumasını rejim kapısı yapsın,
    pozisyon azlığı riski artırmasın" ilkesi (kullanıcı talimatı).

Ağ çağrısı YOK, dosya okuma YOK (sektör haritası hariç — v3_portfoy.py'deki
AYNI hataya-dayanıklı, opsiyonel okuma yöntemi).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_V2_DIR = Path(__file__).resolve().parent
if str(_V2_DIR) not in sys.path:
    sys.path.insert(0, str(_V2_DIR))

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
# Portföy geometrisi — YOĞUNLAŞTIRILMIŞ (3-5 pozisyon, %20-33 ağırlık).
# ─────────────────────────────────────────────────────────────────────────
_MIN_POZISYON = 3
_MAKS_POZISYON = 5
_AGIRLIK_TABANI = 0.20
_AGIRLIK_TAVANI = 0.33

_MAKS_SEKTOR = 2                    # az sayıda pozisyonda tek sektöre 2 tavanı yeterli çeşitlilik
_MAKS_GUNLUK_YENI_POZISYON = 2      # kaliteyi korumak için günde en fazla 2 yeni giriş
_STOP_SONRASI_BEKLEME_GUN = 20      # stop olan hisseye kısa süreli yeniden-giriş yasağı

# ─────────────────────────────────────────────────────────────────────────
# Stop / kâr hedefi / trailing sabitleri.
# ─────────────────────────────────────────────────────────────────────────
_STOP_ATR_KATSAYI = 2.2
_STOP_ORAN_TABANI = 0.08            # ATR-bazlı stop en az -%8
_STOP_ORAN_TAVANI = 0.10            # ATR-bazlı stop en fazla -%10

_KAR_HEDEF_1_ORAN = 0.15            # +%15'te kısmi realize
_KAR_HEDEF_1_SATIS_PAYI = 0.50      # pozisyonun yarısı satılır
_KAR_HEDEF_2_ORAN = 0.25            # +%25'ten sonra trailing sıkılaşır

_TRAILING_AKTIVASYON_ORAN = 0.10    # +%10 kârdan sonra trailing devreye girer
_CHANDELIER_ATR_KATSAYI = 2.5       # normal trailing mesafesi
_CHANDELIER_ATR_KATSAYI_SIKI = 1.8  # +%25 sonrası sıkılaştırılmış trailing

_TREND_KIRILIM_GUN = 3              # bu kadar ardışık gün Kapanış<MA200 -> çık

# Rejim -> hedef yatırım oranı: İKİLİ ve AGRESİF (kullanıcı talimatı).
# R1 (risk açık) tam yatırım; R2 (temkinli) yarı yatırım; R3/R4 TAM nakit —
# konsantre pozisyon sayısının getirdiği riski rejim kapısı dengeler.
_HEDEF_ORANLAR = {"R1": 1.00, "R2": 0.60, "R3": 0.00, "R4": 0.00}


def hedef_oran_hesapla(rejim_adi: str) -> float:
    """V6'nın ikili/agresif rejim eşlemesi (rejim.py'nin ürettiği R1-R4 etiketine göre)."""
    return _HEDEF_ORANLAR.get(rejim_adi, 0.0)


def giris_stop_hesapla(giris_fiyati: float, atr: float) -> dict:
    """ATR-bazlı ilk stopu [-%8, -%10] bandına sıkıştırır.

    YÖNTEM: ATR14 * 2.2 mesafesinin girişe oranı hesaplanır, sonra bu oran
    [%8, %10] bandına kırpılır (clip) — hem ATR'nin hissenin KENDİ
    oynaklığını yansıtmasına izin verir hem de stopun şartnamedeki "-%8/-10
    makul" aralığının dışına taşmasını engeller (çok dar/çok geniş stop).
    """
    if giris_fiyati is None or giris_fiyati <= 0 or atr is None or pd.isna(atr) or atr <= 0:
        return {"stop": giris_fiyati * (1.0 - _STOP_ORAN_TAVANI) if giris_fiyati else 0.0,
                "stop_orani": _STOP_ORAN_TAVANI}
    ham_oran = (_STOP_ATR_KATSAYI * atr) / giris_fiyati
    oran = min(max(ham_oran, _STOP_ORAN_TABANI), _STOP_ORAN_TAVANI)
    return {"stop": float(giris_fiyati * (1.0 - oran)), "stop_orani": float(oran)}


def hedef_agirlik_hesapla(acik_pozisyon_sayisi: int, hedef_oran: float,
                           min_pozisyon: int | None = None,
                           maks_pozisyon: int | None = None,
                           taban: float | None = None,
                           tavan: float | None = None) -> float:
    """Yeni açılacak pozisyon için hedef ağırlığı (toplam özsermayeye oranla) hesaplar.

    MANTIK: portföy henüz az sayıda pozisyon içeriyorsa (örn. ilk 3 giriş),
    her biri TAVANA yakın büyük ağırlık alır (az ama yüksek güven ilkesi).
    Pozisyon sayısı MAKS_POZISYON'a yaklaştıkça ağırlık TABANA doğru iner
    (5. pozisyon %20 civarı). Bölen, `max(acik+1, min_pozisyon)` olduğundan
    ilk birkaç pozisyon asla yapay biçimde tek başına %100'e yakın bir
    ağırlık almaz (min_pozisyon=3 tabanı, en fazla ~%33'e sabitler).
    """
    min_poz = _MIN_POZISYON if min_pozisyon is None else max(1, int(min_pozisyon))
    maks_poz = _MAKS_POZISYON if maks_pozisyon is None else max(min_poz, int(maks_pozisyon))
    taban_g = _AGIRLIK_TABANI if taban is None else float(taban)
    tavan_g = _AGIRLIK_TAVANI if tavan is None else float(tavan)

    hedef_oran_guvenli = 0.0 if (hedef_oran is None or pd.isna(hedef_oran)) else float(hedef_oran)
    if hedef_oran_guvenli <= 0:
        return 0.0

    bolen = max(acik_pozisyon_sayisi + 1, min_poz)
    bolen = min(bolen, maks_poz)  # 5'i aşınca da tabana (yaklaşık) sabitlenir
    ham_agirlik = 1.0 / bolen
    agirlik = min(max(ham_agirlik, taban_g), tavan_g)
    return float(agirlik * hedef_oran_guvenli)


def pozisyon_boyutu(ozsermaye: float, kapanis: float, atr: float,
                     hacim_tl_medyan, mevcut_yatirim: float,
                     hedef_agirlik: float,
                     likidite_orani: float = 0.02) -> dict:
    """Hedef ağırlık + likidite tavanına göre alınacak adedi/stopu hesaplar.

    likidite_orani VARSAYILANI %2 (v3_skor'un %1'lik ön-eleme eşiğinden
    BİLEREK daha gevşek) — YORUM KARARI: konsantre bir portföyde tek
    pozisyon değeri zaten büyük olacağından ön-elemede (v6_skor.py, %1)
    muhafazakâr davranılıp, burada NİHAİ/OTORİTER kontrolde gerçek ağırlıkla
    biraz daha esnek bir tavan (%2) uygulanıyor; aşan durumda pozisyon TAMAMEN
    reddedilmek yerine likiditenin izin verdiği adede KIRPILIR (v3_portfoy.py
    ile aynı "reddetme değil kırpma" felsefesi).
    """
    if ozsermaye is None or ozsermaye <= 0 or kapanis is None or pd.isna(kapanis) or kapanis <= 0:
        return {"adet": 0, "deger": 0.0, "stop": 0.0, "red_nedeni": "Geçersiz özsermaye/kapanış."}

    hedef_tl = max(0.0, hedef_agirlik) * ozsermaye
    if hedef_tl <= 0:
        return {"adet": 0, "deger": 0.0, "stop": 0.0, "red_nedeni": "Hedef ağırlık sıfır (rejim/kapasite)."}

    if hacim_tl_medyan is not None and not pd.isna(hacim_tl_medyan) and hacim_tl_medyan > 0:
        likidite_tavan_tl = likidite_orani * hacim_tl_medyan
        hedef_tl = min(hedef_tl, likidite_tavan_tl)

    adet = int(hedef_tl // kapanis)
    if adet < 1:
        return {"adet": 0, "deger": 0.0, "stop": 0.0, "red_nedeni": "Likidite/ağırlık kısıtı sonrası adet < 1."}

    stop_bilgi = giris_stop_hesapla(kapanis, atr)
    return {"adet": adet, "deger": float(adet * kapanis), "stop": stop_bilgi["stop"],
            "stop_orani": stop_bilgi["stop_orani"], "red_nedeni": None}


def trailing_guncelle(pozisyon: dict, bugun: pd.Series) -> dict:
    """Chandelier trailing stopu YALNIZ yukarı günceller; günlük sayaçları ilerletir.

    Kâr +%10'u geçmeden trailing devreye girmez (guncel_stop, ilk_stop'ta
    sabit kalır). +%25'i geçtikten sonra ATR çarpanı sıkılaşır (2.5 -> 1.8)
    — kazancın daha büyük bölümü korunur, ama pozisyon yine de açık kalıp
    trendin devamından pay alabilir.
    """
    yeni = dict(pozisyon)
    giris_fiyati = pozisyon["giris_fiyati"]
    ilk_stop = pozisyon["ilk_stop"]
    kapanis_bugun = bugun.get("Close")

    en_yuksek_onceki = pozisyon.get("en_yuksek_kapanis", giris_fiyati)
    en_yuksek_yeni = en_yuksek_onceki
    if kapanis_bugun is not None and not pd.isna(kapanis_bugun):
        en_yuksek_yeni = max(en_yuksek_onceki, float(kapanis_bugun))
    yeni["en_yuksek_kapanis"] = en_yuksek_yeni

    guncel_stop_onceki = pozisyon.get("guncel_stop", ilk_stop)
    yeni_stop = max(guncel_stop_onceki, ilk_stop)  # asla aşağı çekilmez

    if giris_fiyati and giris_fiyati > 0:
        getiri_en_yuksek = (en_yuksek_yeni / giris_fiyati) - 1.0
        if getiri_en_yuksek >= _TRAILING_AKTIVASYON_ORAN:
            atr_bugun = bugun.get("ATR14")
            if atr_bugun is not None and not pd.isna(atr_bugun) and atr_bugun > 0:
                katsayi = (_CHANDELIER_ATR_KATSAYI_SIKI if getiri_en_yuksek >= _KAR_HEDEF_2_ORAN
                           else _CHANDELIER_ATR_KATSAYI)
                chandelier_aday = en_yuksek_yeni - katsayi * atr_bugun
                yeni_stop = max(yeni_stop, chandelier_aday)
    yeni["guncel_stop"] = yeni_stop

    yeni["gun_sayisi"] = pozisyon.get("gun_sayisi", 0) + 1

    ma200_bugun = bugun.get("MA200")
    if (kapanis_bugun is not None and not pd.isna(kapanis_bugun)
            and ma200_bugun is not None and not pd.isna(ma200_bugun)
            and kapanis_bugun < ma200_bugun):
        yeni["ust_uste_ma200_alti"] = pozisyon.get("ust_uste_ma200_alti", 0) + 1
    else:
        yeni["ust_uste_ma200_alti"] = 0

    return yeni


def kar_hedefi_kontrol(pozisyon: dict, bugun: pd.Series) -> dict | None:
    """+%15 kâr hedefi: HENÜZ realize edilmediyse, pozisyonun yarısını kapat + stopu başabaşa çek.

    Döner: {'satis_payi': 0.5, 'fiyat': float, 'yeni_stop': float} veya None.
    Bu fonksiyon TAM çıkış DEĞİLDİR — çağıran taraf (v6_backtest.py) yalnız
    `satis_payi` kadarını satar, pozisyon açık kalır, `yeni_stop` uygulanır
    ve pozisyonun 'kar_hedefi_1_alindi' bayrağı True yapılır (bir daha
    tetiklenmesin diye).
    """
    if pozisyon.get("kar_hedefi_1_alindi", False):
        return None
    kapanis = bugun.get("Close")
    giris = pozisyon.get("giris_fiyati")
    if kapanis is None or pd.isna(kapanis) or not giris or giris <= 0:
        return None
    getiri = (kapanis / giris) - 1.0
    if getiri >= _KAR_HEDEF_1_ORAN:
        yeni_stop = max(pozisyon.get("guncel_stop", pozisyon.get("ilk_stop", giris)), giris)
        return {"satis_payi": _KAR_HEDEF_1_SATIS_PAYI, "fiyat": float(kapanis), "yeni_stop": float(yeni_stop)}
    return None


def cikis_kontrol(pozisyon: dict, bugun: pd.Series, rejim: dict) -> dict | None:
    """TAM çıkış hiyerarşisi — ilk tetiklenen kazanır. Kısmi kâr realizasyonu BURADA değil,
    ayrı `kar_hedefi_kontrol()` fonksiyonundadır (bkz. modül başı notu).

    Sıra:
      1) İlk stop      — bugünün Low'u ilk_stop'a değdi mi?
      2) Trailing stop — trailing aktifse (guncel_stop > ilk_stop) VE Low
                         guncel_stop'a değdi mi?
      3) Rejim çıkışı  — R3 VEYA R4 ise TAM çıkış (V6'nın ikili/agresif
                         rejim kapısı; kademeli değil, kullanıcı talimatı).
      4) Trend kırılımı — Kapanış, MA200 altında _TREND_KIRILIM_GUN gün
                         üst üste kapandıysa.

    Döner: {'neden': 'stop'|'trailing'|'rejim'|'trend', 'fiyat': float} veya None.
    """
    low = bugun.get("Low")
    close = bugun.get("Close")
    openf = bugun.get("Open")
    if low is None or close is None or pd.isna(low) or pd.isna(close):
        return None

    ilk_stop = pozisyon["ilk_stop"]

    if low <= ilk_stop:
        fiyat = min(openf, ilk_stop) if (openf is not None and not pd.isna(openf) and openf < ilk_stop) else ilk_stop
        return {"neden": "stop", "fiyat": float(fiyat)}

    guncel_stop = pozisyon.get("guncel_stop", ilk_stop)
    if guncel_stop > ilk_stop and low <= guncel_stop:
        fiyat = min(openf, guncel_stop) if (openf is not None and not pd.isna(openf) and openf < guncel_stop) else guncel_stop
        return {"neden": "trailing", "fiyat": float(fiyat)}

    rejim_adi = (rejim or {}).get("rejim")
    if rejim_adi in ("R3", "R4"):
        return {"neden": "rejim", "fiyat": float(close)}

    if pozisyon.get("ust_uste_ma200_alti", 0) >= _TREND_KIRILIM_GUN:
        return {"neden": "trend", "fiyat": float(close)}

    return None


def portfoy_kisit_kontrol(aday: dict, acik_pozisyonlar: list[dict],
                           bugun_acilan_sayisi: int, son_stop_tarihleri: dict,
                           maks_pozisyon: int | None = None) -> str | None:
    """V6 portföy kısıtları. Uygunsa None, değilse Türkçe red nedeni.

    Kontrol sırası (ilk ihlal edilen döner):
      1) Maks eşzamanlı pozisyon (varsayılan 5)
      2) Günde maks yeni pozisyon (2)
      3) Aynı sektörden maks 2
      4) Zarardaki pozisyona ekleme yok
      5) Stop olan hisseye 20 gün yeniden giriş yok
    """
    acik_pozisyonlar = acik_pozisyonlar or []
    maks_poz = _MAKS_POZISYON if maks_pozisyon is None else max(1, int(maks_pozisyon))

    if len(acik_pozisyonlar) >= maks_poz:
        return f"Maksimum {maks_poz} eşzamanlı pozisyon sınırına ulaşıldı."

    if (bugun_acilan_sayisi or 0) >= _MAKS_GUNLUK_YENI_POZISYON:
        return f"Bugün için maksimum {_MAKS_GUNLUK_YENI_POZISYON} yeni pozisyon sınırına ulaşıldı."

    aday_sektor = _sektor_bul(aday["sembol"])
    ayni_sektor_sayisi = sum(1 for p in acik_pozisyonlar if _sektor_bul(p.get("sembol", "")) == aday_sektor)
    if ayni_sektor_sayisi >= _MAKS_SEKTOR:
        return f"Aynı sektörden ({aday_sektor}) zaten {_MAKS_SEKTOR} pozisyon açık."

    aday_kapanis = aday.get("kapanis")
    for p in acik_pozisyonlar:
        if p.get("sembol") != aday["sembol"]:
            continue
        giris_fiyati = p.get("giris_fiyati")
        if (aday_kapanis is not None and giris_fiyati is not None
                and not pd.isna(aday_kapanis) and aday_kapanis < giris_fiyati):
            return f"{aday['sembol']} zaten zararda açık bir pozisyon — ekleme yapılamaz."

    son_tarih = (son_stop_tarihleri or {}).get(aday["sembol"])
    bugun_tarih = aday.get("tarih")
    if son_tarih is not None and bugun_tarih is not None:
        fark_gun = (pd.Timestamp(bugun_tarih) - pd.Timestamp(son_tarih)).days
        if fark_gun < _STOP_SONRASI_BEKLEME_GUN:
            kalan = _STOP_SONRASI_BEKLEME_GUN - fark_gun
            return (f"{aday['sembol']} {fark_gun} gün önce stop oldu — "
                    f"{_STOP_SONRASI_BEKLEME_GUN} gün yeniden giriş yasağı sürüyor (kalan {kalan} gün).")

    return None


if __name__ == "__main__":
    # Ağ çağrısı / dosya okuma içermeyen kendi kendine kontrol.

    # ── giris_stop_hesapla: bant [%8,%10] içinde kalmalı. ───────────────────
    s1 = giris_stop_hesapla(100.0, atr=1.0)   # 2.2*1/100=%2.2 -> tabana kırpılır (%8)
    assert abs(s1["stop_orani"] - 0.08) < 1e-9, s1
    s2 = giris_stop_hesapla(100.0, atr=6.0)   # 2.2*6/100=%13.2 -> tavana kırpılır (%10)
    assert abs(s2["stop_orani"] - 0.10) < 1e-9, s2
    s3 = giris_stop_hesapla(100.0, atr=4.0)   # 2.2*4/100=%8.8 -> bandın içinde, kırpılmaz
    assert abs(s3["stop_orani"] - 0.088) < 1e-9, s3

    # ── hedef_agirlik_hesapla: az pozisyonda tavana yakın, çok pozisyonda tabana. ──
    a_ilk = hedef_agirlik_hesapla(0, hedef_oran=1.0)   # bölen=max(1,3)=3 -> 1/3 -> tavan 0.33
    assert abs(a_ilk - _AGIRLIK_TAVANI) < 1e-6, a_ilk
    a_4 = hedef_agirlik_hesapla(3, hedef_oran=1.0)     # bölen=max(4,3)=4 -> 0.25
    assert abs(a_4 - 0.25) < 1e-6, a_4
    a_5 = hedef_agirlik_hesapla(4, hedef_oran=1.0)     # bölen=max(5,3)=5 -> taban 0.20
    assert abs(a_5 - _AGIRLIK_TABANI) < 1e-6, a_5
    a_r2 = hedef_agirlik_hesapla(0, hedef_oran=0.60)   # R2: 0.33*0.60
    assert abs(a_r2 - _AGIRLIK_TAVANI * 0.60) < 1e-6, a_r2
    a_r3 = hedef_agirlik_hesapla(0, hedef_oran=0.0)
    assert a_r3 == 0.0, a_r3

    # ── pozisyon_boyutu: likidite tavanı adedi kırpmalı, reddetmemeli. ──────
    boyut_normal = pozisyon_boyutu(ozsermaye=1_000_000.0, kapanis=50.0, atr=2.0,
                                    hacim_tl_medyan=500_000_000.0, mevcut_yatirim=0.0,
                                    hedef_agirlik=0.33)
    assert boyut_normal["adet"] > 0 and boyut_normal["red_nedeni"] is None, boyut_normal
    boyut_dusuk_likidite = pozisyon_boyutu(ozsermaye=1_000_000.0, kapanis=50.0, atr=2.0,
                                            hacim_tl_medyan=1_000_000.0, mevcut_yatirim=0.0,
                                            hedef_agirlik=0.33)
    # likidite tavanı: %2 * 1.000.000 = 20.000 TL -> 20.000/50=400 adet (hedeften daha az)
    assert boyut_dusuk_likidite["deger"] < boyut_normal["deger"], boyut_dusuk_likidite

    # ── trailing_guncelle: ASLA aşağı inmiyor, +%25 sonrası katsayı sıkılaşıyor. ──
    giris_fiyati = 100.0
    ilk_stop = 90.0
    poz = {"sembol": "TEST", "giris_fiyati": giris_fiyati, "ilk_stop": ilk_stop,
           "guncel_stop": ilk_stop, "en_yuksek_kapanis": giris_fiyati,
           "gun_sayisi": 0, "ust_uste_ma200_alti": 0}
    kapanis_yolu = [105, 112, 120, 132, 128, 122, 126, 118]  # 132 sonrası geri çekilme
    stop_gecmisi = [poz["guncel_stop"]]
    for k in kapanis_yolu:
        bugun = pd.Series({"Close": k, "MA200": 80.0, "ATR14": 4.0})
        poz = trailing_guncelle(poz, bugun)
        stop_gecmisi.append(poz["guncel_stop"])
    for i in range(1, len(stop_gecmisi)):
        assert stop_gecmisi[i] >= stop_gecmisi[i - 1] - 1e-9, f"Trailing aşağı indi! {stop_gecmisi}"
    assert poz["guncel_stop"] > ilk_stop, "Trailing hiç devreye girmedi"

    # ── kar_hedefi_kontrol: +%15'te tetiklenmeli, tek seferlik. ─────────────
    poz_kar = {"giris_fiyati": 100.0, "ilk_stop": 90.0, "guncel_stop": 90.0}
    bugun_kar = pd.Series({"Close": 116.0})
    sonuc_kar = kar_hedefi_kontrol(poz_kar, bugun_kar)
    assert sonuc_kar is not None and sonuc_kar["satis_payi"] == _KAR_HEDEF_1_SATIS_PAYI, sonuc_kar
    assert sonuc_kar["yeni_stop"] >= 100.0, sonuc_kar  # başabaşa çekilmiş
    poz_kar["kar_hedefi_1_alindi"] = True
    assert kar_hedefi_kontrol(poz_kar, bugun_kar) is None  # bir daha tetiklenmemeli

    # ── cikis_kontrol: ilk stop, rejim R3/R4 ikili tam çıkış, trend kırılımı. ──
    poz3 = {"sembol": "DUSUS", "giris_fiyati": 100.0, "ilk_stop": 90.0, "guncel_stop": 90.0,
            "en_yuksek_kapanis": 100.0, "gun_sayisi": 3, "ust_uste_ma200_alti": 0}
    bugun_stop = pd.Series({"Open": 91.0, "High": 92.0, "Low": 88.0, "Close": 89.0})
    sonuc_stop = cikis_kontrol(poz3, bugun_stop, {"rejim": "R1"})
    assert sonuc_stop is not None and sonuc_stop["neden"] == "stop", sonuc_stop

    bugun_notr = pd.Series({"Open": 101.0, "High": 102.0, "Low": 100.5, "Close": 101.5})
    sonuc_r3 = cikis_kontrol(poz3, bugun_notr, {"rejim": "R3"})
    assert sonuc_r3 is not None and sonuc_r3["neden"] == "rejim", sonuc_r3  # V6: R3 de TAM çıkış
    sonuc_r4 = cikis_kontrol(poz3, bugun_notr, {"rejim": "R4"})
    assert sonuc_r4 is not None and sonuc_r4["neden"] == "rejim", sonuc_r4

    poz_trend = dict(poz3)
    poz_trend["ust_uste_ma200_alti"] = _TREND_KIRILIM_GUN
    sonuc_trend = cikis_kontrol(poz_trend, bugun_notr, {"rejim": "R1"})
    assert sonuc_trend is not None and sonuc_trend["neden"] == "trend", sonuc_trend

    # ── portfoy_kisit_kontrol testleri. ─────────────────────────────────────
    acik_5 = [{"sembol": f"H{i}", "giris_fiyati": 10.0} for i in range(5)]
    assert portfoy_kisit_kontrol({"sembol": "YENI", "kapanis": 10.0}, acik_5, 0, {}) is not None
    assert portfoy_kisit_kontrol({"sembol": "YENI", "kapanis": 10.0}, [], 2, {}) is not None

    print("v6_portfoy.py kendi kendine kontrol: BAŞARILI")
    print("Stop bandı örnekleri:", s1, s2, s3)
    print("Hedef ağırlık örnekleri (R1):", a_ilk, a_4, a_5)
    print("Trailing stop geçmişi:", stop_gecmisi)
