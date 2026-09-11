# -*- coding: utf-8 -*-
"""
hisse_adlari.py — Hisse KODU ↔ ŞİRKET ADI eşlemesi ve aranabilir etiketler.
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR: BIST'te ~600 hisse var ve kodların çoğu akılda kalmıyor ("EREGL"
kimdi, "Ereğli Demir Çelik" hangi koddu?). Bu modül, arayüzdeki serbest metin
kutularını ŞİRKET ADIYLA DA ARANABİLİR bir listeye çevirmeyi mümkün kılar:
kullanıcı "ereğli" veya "demir" yazınca EREGL'i bulabilir.

VERİ KAYNAĞI VE DÜRÜSTLÜK:
  Adlar UYDURULMAZ. Sıralama şudur:
    1. Disk önbelleği (hisse_adlari.json) — daha önce indirilmişse.
    2. veri_katmani.temel_veriler(...)['sirket_adi'] — gerçek kaynaktan,
       istendiğinde toplu ve paralel olarak indirilir, sonra önbelleğe yazılır.
    3. Aşağıdaki KÜÇÜK yerleşik liste — yalnızca en bilinen ve doğruluğundan
       emin olunan birkaç şirket; internet olmadan da arayüz kullanışlı olsun diye.
  Adı bilinmeyen hisse için SADECE KOD gösterilir; tahmini/uydurma ad yazılmaz.
"""
from __future__ import annotations

import json
import os
import unicodedata

KLASOR = os.path.dirname(os.path.abspath(__file__))
ONBELLEK_DOSYASI = os.path.join(KLASOR, "hisse_adlari.json")

# Yalnızca yaygın ve doğruluğundan emin olunan çekirdek liste (yedek amaçlı).
# Tam liste "Şirket adlarını indir" ile gerçek kaynaktan doldurulur.
YERLESIK_ADLAR = {
    "THYAO": "Türk Hava Yolları",
    "ASELS": "Aselsan",
    "EREGL": "Ereğli Demir ve Çelik",
    "BIMAS": "BİM Birleşik Mağazalar",
    "TUPRS": "Tüpraş",
    "GARAN": "Garanti BBVA",
    "AKBNK": "Akbank",
    "ISCTR": "İş Bankası (C)",
    "YKBNK": "Yapı ve Kredi Bankası",
    "VAKBN": "VakıfBank",
    "HALKB": "Halkbank",
    "KCHOL": "Koç Holding",
    "SAHOL": "Sabancı Holding",
    "SISE": "Şişecam",
    "PGSUS": "Pegasus Hava Taşımacılığı",
    "TCELL": "Turkcell",
    "TTKOM": "Türk Telekom",
    "FROTO": "Ford Otosan",
    "TOASO": "Tofaş Oto",
    "ARCLK": "Arçelik",
    "KRDMD": "Kardemir (D)",
    "PETKM": "Petkim",
    "TAVHL": "TAV Havalimanları",
    "ENKAI": "Enka İnşaat",
    "SASA": "Sasa Polyester",
    "HEKTS": "Hektaş",
    "KOZAL": "Koza Altın",
    "KOZAA": "Koza Anadolu Metal",
    "TKFEN": "Tekfen Holding",
    "AEFES": "Anadolu Efes",
    "CCOLA": "Coca-Cola İçecek",
    "MGROS": "Migros Ticaret",
    "SOKM": "Şok Marketler",
    "ULKER": "Ülker Bisküvi",
    "AKSEN": "Aksa Enerji",
    "ENJSA": "Enerjisa Enerji",
    "AGHOL": "AG Anadolu Grubu Holding",
    "DOHOL": "Doğan Holding",
    "ISGYO": "İş Gayrimenkul Yatırım Ortaklığı",
    "EKGYO": "Emlak Konut GYO",
    "OYAKC": "Oyak Çimento",
    "AKCNS": "Akçansa",
    "ASTOR": "Astor Enerji",
    "ODAS": "Odaş Elektrik",
    "ALARK": "Alarko Holding",
    "VESTL": "Vestel",
    "TSKB": "Türkiye Sınai Kalkınma Bankası",
    "GUBRF": "Gübre Fabrikaları",
}


def _oku_onbellek() -> dict:
    if not os.path.exists(ONBELLEK_DOSYASI):
        return {}
    try:
        with open(ONBELLEK_DOSYASI, encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, dict) else {}
    except Exception:
        return {}


def _yaz_onbellek(adlar: dict):
    try:
        with open(ONBELLEK_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(adlar, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        pass


def adlari_getir() -> dict:
    """Bilinen tüm kod→ad eşlemesi (önbellek + yerleşik liste)."""
    adlar = dict(YERLESIK_ADLAR)
    adlar.update(_oku_onbellek())     # önbellek daha günceldir, üzerine yazar
    return adlar


def adlari_indir(semboller: list, toplu_temel_getirici, ilerleme=None) -> dict:
    """Şirket adlarını GERÇEK kaynaktan indirip önbelleğe yazar.

    toplu_temel_getirici: semboller -> {sembol: {"sirket_adi": ...}} döndüren
    fonksiyon (örn. veri_katmani.toplu_temel_veriler).
    """
    try:
        temel_harita = toplu_temel_getirici(semboller, ilerleme=ilerleme)
    except TypeError:
        temel_harita = toplu_temel_getirici(semboller)
    except Exception:
        return adlari_getir()

    onbellek = _oku_onbellek()
    eklenen = 0
    for sembol, temel in (temel_harita or {}).items():
        if not isinstance(temel, dict):
            continue
        ad = temel.get("sirket_adi")
        if ad and isinstance(ad, str) and ad.strip():
            temiz = " ".join(ad.split())
            if onbellek.get(sembol) != temiz:
                onbellek[sembol] = temiz
                eklenen += 1
    if eklenen:
        _yaz_onbellek(onbellek)
    return adlari_getir()


def etiket(sembol: str, adlar: dict = None) -> str:
    """Görüntüleme etiketi: 'EREGL — Ereğli Demir ve Çelik' (ad yoksa sadece kod)."""
    adlar = adlar if adlar is not None else adlari_getir()
    ad = adlar.get(sembol)
    return f"{sembol} — {ad}" if ad else sembol


def etiketten_sembol(etiket_metni: str) -> str:
    """'EREGL — Ereğli Demir ve Çelik' -> 'EREGL'"""
    if not etiket_metni:
        return ""
    return etiket_metni.split("—")[0].strip().upper().replace(".IS", "")


def _sadelestir(metin: str) -> str:
    """Türkçe karakterleri ve büyük/küçük farkını yok sayan arama anahtarı.

    'ereğli' ile 'EREGLI' aynı sonucu vermeli; kullanıcı Türkçe klavye
    kullanmıyor olabilir ya da şapkalı harf yazmayabilir.
    """
    if not metin:
        return ""
    esle = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iisSgGuUoOcC")
    metin = metin.translate(esle)
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    return metin.lower().strip()


def ara(sorgu: str, semboller: list, adlar: dict = None, ust_sinir: int = 25) -> list:
    """Koda VEYA şirket adına göre arama. Dönüş: eşleşen sembol listesi.

    Sıralama: önce kodu tam eşleşen, sonra kodu ile başlayan, sonra ad içinde geçen.
    """
    adlar = adlar if adlar is not None else adlari_getir()
    s = _sadelestir(sorgu)
    if not s:
        return list(semboller)[:ust_sinir]

    tam, baslayan, icinde = [], [], []
    for sembol in semboller:
        ks = _sadelestir(sembol)
        ad_s = _sadelestir(adlar.get(sembol, ""))
        if ks == s:
            tam.append(sembol)
        elif ks.startswith(s):
            baslayan.append(sembol)
        elif s in ks or (ad_s and s in ad_s):
            icinde.append(sembol)
    return (tam + baslayan + icinde)[:ust_sinir]
