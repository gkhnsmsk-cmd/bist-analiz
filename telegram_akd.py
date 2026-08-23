# -*- coding: utf-8 -*-
"""
telegram_akd.py — BOPT (@b0pt_bot) Telegram botundan AKD/derinlik verisini
KENDİ Telegram hesabınla (Telegram'ın resmi "Telegram API" / MTProto yolu,
Telethon kütüphanesi üzerinden) otomatik çekip diske kaydeder.
══════════════════════════════════════════════════════════════════════════════
NASIL ÇALIŞIR (özet):
  1) core.telegram.org/api'de belgelenen "Telegram API"yi kullanıyoruz — bu,
     Telegram Masaüstü/Web'in kendisinin de kullandığı, kullanıcı hesabı ile
     yetkilendirilen resmi API'dir (Bot API'den farklı: burada "biz" bot
     DEĞİLİZ, botla konuşan bir kullanıcıyız — tıpkı elle yazdığın gibi).
  2) İlk çalıştırmada senden telefon numaranı ve Telegram'ın gönderdiği kodu
     (bir kere) ister, bir oturum dosyası (telegram_oturumu.session) oluşur.
     Bir daha kod istemez.
  3) Sonraki çalıştırmalarda bu script, izlediğin sembol(ler) için otomatik
     olarak @b0pt_bot'a komut gönderir (örn. "/akd TERA"), botun cevabını
     okur, ayrıştırır ve .veri_cache/akd_{SEMBOL}.json'a zaman damgalı kaydeder.
  4) app.py bu json'ları okuyup analiz panelinde gösterebilir (oku() fonksiyonu).

KURULUM (SENİN YAPMAN GEREKEN — Claude bu adımı senin adına yapamaz):
  1) https://my.telegram.org adresine KENDİ telefon numaranla giriş yap.
  2) "API development tools" → yeni bir uygulama oluştur (isim/açıklama
     önemsiz, herhangi bir şey yaz). Sana bir "api_id" (sayı) ve "api_hash"
     (uzun bir metin) verecek.
  3) Bu klasördeki telegram_ayarlar.ornek.json dosyasını telegram_ayarlar.json
     olarak kopyala, api_id/api_hash/telefon alanlarını doldur.
  4) pip install telethon --break-system-packages  (veya sanal ortamına kur)
  5) Komut satırından: python telegram_akd.py TERA
     İlk seferde Telegram'dan gelen kodu (ve varsa 2FA şifreni) girmen
     istenecek — bu SADECE ilk seferde olur, sonrasında otomatik bağlanır.

DİKKAT — HIZ SINIRI: @b0pt_bot'a çok sık/otomatik mesaj atmak hesabının
geçici olarak sınırlanmasına (flood wait) yol açabilir. Bu yüzden
toplu_guncelle() komutlar arasına bilerek bekleme (varsayılan 3 sn) koyar;
bunu düşürme. Sadece izlediğin/o an baktığın hisseler için çağır — 560
hisseyi birden taramaya ÇALIŞMA.

AYRIŞTIRMA (akd_ayristir): Botun tam cevap formatını henüz görmediğimiz
için şimdilik GENEL bir "Etiket: Değer" ayrıştırıcısı var. Gerçek bir bot
cevabı geldiğinde (örn. TERA için "/akd" cevabı) bu fonksiyonu o formata
göre kesinleştirmek gerekecek — ham metin her durumda "ham" alanında saklanır,
yani ayrıştırma eksik kalsa bile veri kaybolmaz.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import difflib
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

KLASOR = Path(__file__).parent
AYAR_DOSYASI = KLASOR / "telegram_ayarlar.json"
OTURUM_DOSYASI = str(KLASOR / "telegram_oturumu")  # Telethon .session ekler
CACHE_DIR = KLASOR / ".veri_cache"
CACHE_DIR.mkdir(exist_ok=True)

BOT_KULLANICI_ADI = "b0pt_bot"
VARSAYILAN_KOMUT_SABLONU = "/akd {sembol}"
VARSAYILAN_BEKLEME_SN = 3.0
CEVAP_ZAMAN_ASIMI_SN = 15.0


def _tesseract_yolunu_ayarla():
    """Windows'ta pytesseract, Tesseract-OCR programını PATH'te bulamazsa
    'tesseract is not installed' hatası verir — oysa program çoğu zaman
    standart klasöre kurulmuştur. Bilinen kurulum yollarını tarayıp bulursak
    pytesseract'a elle bildiriyoruz (kullanıcı PATH ayarıyla uğraşmasın)."""
    try:
        import pytesseract
    except ImportError:
        return None
    import shutil
    if shutil.which("tesseract"):
        return "PATH"
    adaylar = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        str(Path.home() / "AppData/Local/Programs/Tesseract-OCR/tesseract.exe"),
        str(Path.home() / "AppData/Local/Tesseract-OCR/tesseract.exe"),
    ]
    for yol in adaylar:
        if os.path.exists(yol):
            pytesseract.pytesseract.tesseract_cmd = yol
            return yol
    return None


def _ayarlari_oku() -> dict:
    if not AYAR_DOSYASI.exists():
        raise FileNotFoundError(
            "telegram_ayarlar.json bulunamadı. Önce telegram_ayarlar.ornek.json "
            "dosyasını telegram_ayarlar.json olarak kopyalayıp api_id/api_hash/"
            "telefon bilgilerini doldurman gerekiyor. Ayrıntı: dosyanın en "
            "üstündeki KURULUM notuna bak."
        )
    with open(AYAR_DOSYASI, encoding="utf-8") as f:
        ayar = json.load(f)
    eksik = [k for k in ("api_id", "api_hash", "telefon") if not ayar.get(k)]
    if eksik:
        raise ValueError(f"telegram_ayarlar.json içinde eksik alan(lar): {eksik}")
    return ayar


def akd_ayristir(ham_metin: str) -> dict:
    """Bot cevabındaki 'Etiket: Değer' / 'Etiket : Değer' satırlarını sözlüğe
    çevirir. Format netleşince bu fonksiyon o formata göre sıkılaştırılacak;
    şimdilik hiçbir veri kaybetmeyecek şekilde genel tutuluyor."""
    alanlar = {}
    for satir in ham_metin.splitlines():
        eslesme = re.match(r"\s*([\wÇĞİÖŞÜçğıöşü %.()/-]{2,40}?)\s*[:：]\s*(.+?)\s*$", satir)
        if eslesme:
            etiket = eslesme.group(1).strip()
            deger = eslesme.group(2).strip()
            if etiket and deger:
                alanlar[etiket] = deger
    return {"ham": ham_metin, "alanlar": alanlar}


# ─────────────────────────────────────────────────────────────────────────────
# AKD GÖRSEL AYRIŞTIRICI — tablo resmini SAYISAL veriye çevirir (OCR).
# ─────────────────────────────────────────────────────────────────────────────
# NEDEN BÖYLE: Bot cevabı bir tablo GÖRSELİ olarak geliyor (bkz. modül başı).
# Görselin arka planında yarı saydam "Borsa Platform Türkiye" filigranı var ve
# bu filigran özellikle NET ALIŞ/SATIŞ (lot) sütununu OCR için okunaksız hale
# getiriyor. Bunu iki yolla aştık (gerçek TERA görseliyle sandbox'ta test edildi):
#   1) NET LOT'u OCR'lamaya güvenmek yerine, tablonun kendi üst bilgisinden
#      ("İlk 10: 1.255.202 Lot - %99.40" gibi) toplam lot'u MATEMATİKSEL olarak
#      hesaplıyoruz, sonra her satırın ORAN'ı (%) ile çarpıyoruz. ORAN sütunu
#      filigrandan neredeyse hiç etkilenmiyor, çok güvenilir okunuyor.
#   2) Kurum isimlerini tek bir OCR geçişine güvenmek yerine BİRDEN FAZLA
#      parlaklık eşiğiyle (ensemble) OCR'layıp, aynı ORAN değerine sahip
#      satırlar arasından bilinen kurum listesine EN İYİ eşleşeni seçiyoruz.
#      Hisse senedinin kendi sembolü de genelde bir "aracı kurum" gibi tabloda
#      görünebildiği için (örn. TERA hissesinde "TERA" kurumu), aday listesine
#      HER ZAMAN o an sorgulanan sembol de ekleniyor.
# Kurum ismi eşleşmesi başarısız olursa (güven düşükse) ham OCR metni saklanır,
# ASLA sessizce yanlış bir isme zorlanmaz — sadece o satırın "kurumsal/yabancı
# mı perakende mi" gibi ileri seviye özellikleri hesaplanamaz, ORAN'a dayalı
# ana sinyal kuralları yine de çalışır.
BILINEN_KURUMLAR = [
    "YAPI KREDI", "BANK OF AMERICA", "TEB", "MARBAS", "GEDIK", "HSBC", "PHILLIP",
    "ALNUS", "AKTIF", "IS", "IS YATIRIM", "GARANTI BBVA", "ZIRAAT", "VAKIF",
    "HALK", "AK", "AK YATIRIM", "MIDAS", "INFO", "QNB YATIRIM", "PUSULA YAT.",
    "DENIZ", "DENIZ YATIRIM", "OYAK", "YATIRIM FINANSMAN", "ATA YATIRIM",
    "ICBC", "SEKER", "ANADOLU", "GLOBAL", "INFINITY", "JPMORGAN", "CITIBANK",
    "DEUTSCHE", "UBS", "CREDIT SUISSE", "MERRILL LYNCH", "GOLDMAN SACHS",
    "MORGAN STANLEY", "VERUSA", "EUROBANK", "TACIRLER", "ZIRAAT YATIRIM",
    "ALTERNATIF", "INVEST", "METRO", "BIZIM", "ARAP TURK", "BURGAN",
]

# Rehberdeki "kurumsal_alim_gucu" özelliği için: bu kurumlar YABANCI/kurumsal
# akışı temsil etme eğiliminde (BIST'te bilinen yapıcı/aracı rolü nedeniyle).
YABANCI_KURUMSAL_KURUMLAR = {
    "BANK OF AMERICA", "HSBC", "PHILLIP", "JPMORGAN", "CITIBANK", "DEUTSCHE",
    "UBS", "CREDIT SUISSE", "MERRILL LYNCH", "GOLDMAN SACHS", "MORGAN STANLEY",
    "QNB YATIRIM", "ICBC", "EUROBANK", "BURGAN", "ARAP TURK",
}
# Bu kurumlar genelde geniş şube ağı üzerinden PERAKENDE (küçük yatırımcı)
# akışını temsil eder (rehberin B senaryosundaki gözlem).
PERAKENDE_TEMSILCI_KURUMLAR = {
    "ZIRAAT", "GARANTI BBVA", "VAKIF", "HALK", "AK", "IS", "IS YATIRIM",
    "ZIRAAT YATIRIM",
}


def _kurum_duzelt(ham: str, aday_liste: list) -> tuple:
    """Ham OCR metnini bilinen kurum listesine (fuzzy) eşler.
    Dönüş: (kurum_adi_veya_None, guven_0_1)."""
    ham = (ham or "").strip(" |_").upper()
    if not ham:
        return None, 0.0
    if "DIGER" in ham or "DİĞER" in ham:
        return "DİĞER", 1.0
    # Başlık/özet satırlarını ("İlk 10: ...", "Net Alıcılar" vb.) kurum sanma.
    if "ILK" in ham or ("NET" in ham and ("ALICI" in ham or "SATICI" in ham)):
        return None, 0.0
    eslesme = difflib.get_close_matches(ham, aday_liste, n=1, cutoff=0.6)
    if eslesme:
        skor = difflib.SequenceMatcher(None, ham, eslesme[0]).ratio()
        return eslesme[0], skor
    return ham, 0.0  # ham metin korunur ama güven 0 — "bilinmiyor" say


def _gorsel_on_isle(gray_arr, esik: int):
    mask = (gray_arr > esik).astype("uint8") * 255
    out = Image.fromarray(mask)
    w, h = out.size
    return out.resize((w * 3, h * 3), Image.LANCZOS)


def _oran_satirlarini_cikar(gray_arr, aday_kurumlar: list, esikler=(100, 120, 150, 180, 200)):
    """Her eşik değeri için OCR çalıştırıp, aynı (bölüm, ORAN) çiftine sahip
    satırları gruplayıp en güvenilir kurum eşleşmesini seçer.
    Dönüş: (alicilar_listesi, saticilar_listesi, tum_ham_metin) — her liste
    ORAN'a göre azalan sırada [(oran, kurum, guven, ham_metin), ...]."""
    from pytesseract import Output, image_to_data, image_to_string

    # ═══ YÖNTEM (deneyerek bulundu — gerçek TERA görselinde 22/22 doğru) ═══
    # Kurum İSİMLERİNİ tablonun tamamıyla birlikte OCR'lamak ÇALIŞMIYOR: filigran
    # + rakamlar isim sütununa karışıp "HALK"ı "mala", "MIDAS"ı "DANS" gibi
    # okutuyordu. Bunun yerine üç aşamalı, KONUM tabanlı bir yöntem kullanıyoruz:
    #   1) Sağdaki ORAN (%) sütununu OCR'layıp her satırın Y KOORDİNATINI buluyoruz
    #      (yüzdeler filigrandan neredeyse hiç etkilenmiyor).
    #   2) "Alıcılar"/"Satıcılar" başlıklarının Y'sini bulup, her satırın hangi
    #      tabloya ait olduğunu KONUMDAN kesin olarak belirliyoruz (tahmin yok).
    #   3) Her satırın SADECE isim hücresini (solda ~%36'lık şerit) tek tek
    #      kırpıp, birden çok ölçek/psm/eşik ile OCR'layıp bilinen kurum
    #      listesine en iyi eşleşeni seçiyoruz. Kritik ayrıntı: HAM (eşiklenmemiş)
    #      hücre görüntüsü en iyi sonucu veriyor — eşikleme filigranla birlikte
    #      harflerin bir kısmını da siliyor.
    yukseklik, genislik = gray_arr.shape

    # ── 1) Satır Y konumları: sağdaki yüzde sütunu ──
    sag = gray_arr[:, int(genislik * 0.70):]
    ham_yuzdeler = []
    for esik in (120, 150, 180):
        mask = (sag > esik).astype("uint8") * 255
        o = Image.fromarray(mask)
        o = o.resize((o.width * 4, o.height * 4), Image.LANCZOS)
        d = image_to_data(o, lang="eng", config="--psm 6", output_type=Output.DICT)
        for i in range(len(d["text"])):
            t = (d["text"][i] or "").strip()
            if "%" not in t:
                continue
            m = re.search(r"([\d]{1,3}[.,]\d{1,2})", t)
            if not m:
                continue
            y = (d["top"][i] + d["height"][i] / 2) / 4
            ham_yuzdeler.append({"y": y, "oran": float(m.group(1).replace(",", "."))})

    ham_yuzdeler.sort(key=lambda r: r["y"])
    satirlar = []
    for r in ham_yuzdeler:
        if satirlar and abs(r["y"] - satirlar[-1]["y"]) < 12:
            continue  # aynı satırın farklı eşikteki tekrarı
        satirlar.append(r)

    # ── 2) Bölüm başlıklarının Y konumu ──
    basliklar = {}
    for esik in (120, 150, 180):
        mask = (gray_arr > esik).astype("uint8") * 255
        o = Image.fromarray(mask)
        o = o.resize((o.width * 2, o.height * 2), Image.LANCZOS)
        d = image_to_data(o, lang="eng", config="--psm 6", output_type=Output.DICT)
        for i in range(len(d["text"])):
            t = (d["text"][i] or "").strip().lower()
            y = (d["top"][i] + d["height"][i] / 2) / 2
            if ("alicilar" in t or "alıcılar" in t) and "alici" not in basliklar:
                basliklar["alici"] = y
            elif ("saticilar" in t or "satıcılar" in t) and "satici" not in basliklar:
                basliklar["satici"] = y

    alici_y = basliklar.get("alici", 0)
    satici_y = basliklar.get("satici", yukseklik)

    # ── 3) Her satırın isim hücresini ayrı ayrı OCR'la ──
    alicilar_ham, saticilar_ham = [], []
    for satir in satirlar:
        y = satir["y"]
        # Başlık satırlarının kendi yüzdesi ("İlk 10: ... %99.40") veri değildir.
        if abs(y - alici_y) < 20 or abs(y - satici_y) < 20:
            continue
        if y < alici_y:
            continue  # tablodan önceki bir şey
        kurum, guven, ham = _isim_hucresi_oku(gray_arr, y, aday_kurumlar)
        kayit = (satir["oran"], kurum, guven, ham)
        if y < satici_y:
            alicilar_ham.append(kayit)
        else:
            saticilar_ham.append(kayit)

    alicilar_ham.sort(key=lambda s: s[0], reverse=True)
    saticilar_ham.sort(key=lambda s: s[0], reverse=True)

    # Başlıklardaki toplam lot bilgisi için tam-sayfa metin de lazım.
    tam_metin = image_to_string(_gorsel_on_isle(gray_arr, 150), lang="eng", config="--psm 6")
    return alicilar_ham, saticilar_ham, tam_metin


def _isim_hucresi_oku(gray_arr, y: float, aday_kurumlar: list, satir_yuksekligi: int = 26):
    """Tek bir satırın SADECE kurum-adı hücresini kırpıp birden çok yöntemle
    OCR'lar ve bilinen kurum listesine en iyi eşleşeni döndürür.
    Dönüş: (kurum, guven, en_iyi_ham_metin)."""
    from pytesseract import image_to_string

    yukseklik, genislik = gray_arr.shape
    y0, y1 = max(0, int(y - satir_yuksekligi)), min(yukseklik, int(y + satir_yuksekligi))
    x1 = int(genislik * 0.36)  # isim sütunu, sayıların soluna kadar
    if y1 <= y0:
        return None, 0.0, ""

    adaylar = []
    ham_hucre = Image.fromarray(gray_arr[y0:y1, 0:x1])
    # HAM görüntü (eşiklenmemiş) — deneylerde en yüksek isabeti bu verdi.
    for olcek in (3, 5):
        buyutulmus = ham_hucre.resize((ham_hucre.width * olcek, ham_hucre.height * olcek),
                                       Image.LANCZOS)
        for psm in (7, 8):  # 7: tek satır, 8: tek kelime — ikisi farklı satırlarda kazanıyor
            try:
                t = image_to_string(buyutulmus, lang="eng", config=f"--psm {psm}")
            except Exception:
                continue
            t = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z .]", " ", t)).strip()
            if t:
                adaylar.append(t)
    # Eşiklenmiş varyantlar — bazı satırlarda ham okunamazsa yedek.
    alt = gray_arr[y0:y1, 0:x1]
    for esik in (130, 170, 190):
        mask = (alt > esik).astype("uint8") * 255
        o = Image.fromarray(mask)
        o = o.resize((o.width * 5, o.height * 5), Image.LANCZOS)
        try:
            t = image_to_string(o, lang="eng", config="--psm 7")
        except Exception:
            continue
        t = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z .]", " ", t)).strip()
        if t:
            adaylar.append(t)

    en_iyi_kurum, en_iyi_skor, en_iyi_ham = None, 0.0, (adaylar[0] if adaylar else "")
    for aday in adaylar:
        kurum, skor = _kurum_duzelt(aday, aday_kurumlar)
        if kurum == "DİĞER":
            return "DİĞER", 1.0, aday
        if kurum and skor > en_iyi_skor:
            en_iyi_kurum, en_iyi_skor, en_iyi_ham = kurum, skor, aday
    return en_iyi_kurum, en_iyi_skor, en_iyi_ham


def _basliktan_toplam_lot(ham_metin: str, anahtar_kelime: str):
    """'... ilk 10: 1.255.202 Lot - 99.40%' satırından (ilk10_lot, ilk10_yuzde,
    hesaplanan_toplam_lot) çıkarır. Bulunamazsa None döner."""
    for satir in ham_metin.splitlines():
        if anahtar_kelime.lower() not in satir.lower():
            continue
        m = re.search(r"([\d][\d.,]*\d)\s*Lot\s*-\s*([\d]{1,3}[.,]\d{1,2})\s*%", satir, re.IGNORECASE)
        if m:
            ilk10_lot = float(m.group(1).replace(".", "").replace(",", "."))
            ilk10_yuzde = float(m.group(2).replace(",", "."))
            if ilk10_yuzde > 0:
                toplam = ilk10_lot / (ilk10_yuzde / 100)
                return ilk10_lot, ilk10_yuzde, toplam
    return None


def akd_gorsel_ayristir(gorsel_yolu: str, sembol: str = None) -> dict:
    """AKD tablo görselini sayısal veriye çevirir.

    Dönüş: {"net_alicilar": {"toplam_lot": float|None, "kurumlar": [
                {"kurum": str, "oran": float, "net_lot_tahmini": float|None,
                 "guven": float, "kurumsal_mi": bool|None}, ...]},
            "net_saticilar": {...aynı yapı...},
            "guven": "yuksek"/"orta"/"dusuk", "guven_notu": str}
    """
    try:
        from PIL import Image as _Img  # noqa: F401 (üstte de import edilir, garanti)
    except ImportError as e:
        raise ImportError("Pillow kurulu değil. Kur: pip install pillow --break-system-packages") from e
    try:
        import pytesseract  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "pytesseract kurulu değil. Kur: pip install pytesseract --break-system-packages "
            "— AYRICA Tesseract-OCR programının Windows'a kurulu olması gerekir "
            "(https://github.com/UB-Mannheim/tesseract/wiki)."
        ) from e

    _tesseract_yolunu_ayarla()  # Windows'ta tesseract.exe'yi PATH dışında da bul

    img = Image.open(gorsel_yolu).convert("RGB")
    arr = np.array(img)
    gray = arr.max(axis=2)  # kırmızı/yeşil/beyaz metni eşit yakalamak için luminance değil max-kanal

    aday_kurumlar = list(BILINEN_KURUMLAR)
    if sembol:
        aday_kurumlar = [sembol.upper()] + aday_kurumlar

    alicilar_ham, saticilar_ham, ham_metin = _oran_satirlarini_cikar(gray, aday_kurumlar)
    alici_basligi = _basliktan_toplam_lot(ham_metin, "Alicilar") or _basliktan_toplam_lot(ham_metin, "Alıcılar")
    satici_basligi = _basliktan_toplam_lot(ham_metin, "Saticilar") or _basliktan_toplam_lot(ham_metin, "Satıcılar")

    alicilar = [{"kurum": k, "oran": o, "guven": round(g, 2), "ham": h}
                for o, k, g, h in alicilar_ham]
    saticilar = [{"kurum": k, "oran": o, "guven": round(g, 2), "ham": h}
                 for o, k, g, h in saticilar_ham]

    def _lot_ekle(liste, basligi):
        toplam = basligi[2] if basligi else None
        for satir in liste:
            satir["net_lot_tahmini"] = round(satir["oran"] / 100 * toplam) if toplam else None
            k = satir["kurum"]
            if k in YABANCI_KURUMSAL_KURUMLAR:
                satir["kurumsal_mi"] = True
            elif k in PERAKENDE_TEMSILCI_KURUMLAR:
                satir["kurumsal_mi"] = False
            else:
                satir["kurumsal_mi"] = None
        return toplam

    alici_toplam = _lot_ekle(alicilar, alici_basligi)
    satici_toplam = _lot_ekle(saticilar, satici_basligi)

    # Güven değerlendirmesi: satır sayısı + ortalama kurum-eşleşme güveni +
    # başlıkların bulunup bulunmadığı üzerinden basit bir özet.
    tum_satirlar = alicilar + saticilar
    ort_guven = (sum(s["guven"] for s in tum_satirlar) / len(tum_satirlar)) if tum_satirlar else 0.0
    if not tum_satirlar or not alici_basligi or not satici_basligi:
        guven_seviyesi, guven_notu = "dusuk", "Başlık/toplam bilgisi veya satırlar tam okunamadı."
    elif ort_guven >= 0.8 and len(alicilar) >= 5 and len(saticilar) >= 5:
        guven_seviyesi, guven_notu = "yuksek", "Çoğu satır güvenle okundu."
    else:
        guven_seviyesi, guven_notu = "orta", "Bazı kurum isimleri düşük güvenle eşleşti — ham OCR metni saklandı."

    return {
        "net_alicilar": {"toplam_lot": alici_toplam, "kurumlar": alicilar},
        "net_saticilar": {"toplam_lot": satici_toplam, "kurumlar": saticilar},
        "guven": guven_seviyesi,
        "guven_notu": guven_notu,
    }


# ─────────────────────────────────────────────────────────────────────────────
# KURAL TABANLI SİNYAL MOTORU — kullanıcının 3 kuralı + rehberin A/B senaryosu
# ─────────────────────────────────────────────────────────────────────────────
VARSAYILAN_SINYAL_ESIKLERI = {
    "diger_alici_yuksek": 20.0,      # alıcı tarafında DİĞER bu %'nin üstündeyse
    "diger_satici_yuksek": 20.0,     # satıcı tarafında DİĞER bu %'nin üstündeyse
    "tek_kurum_konsantrasyon": 40.0, # tek (DİĞER olmayan) kurum bu %'nin üstünü topladıysa
    "spread_esik": 15.0,             # ilk5 alıcı-satıcı farkı bu kadar aşarsa
}


def akd_sinyal_uret(ayristirilmis: dict, esikler: dict = None) -> dict:
    """Kullanıcının tarif ettiği 3 kural + rehberdeki 'mal toplanması/dağıtımı'
    senaryosunu uygular. Kurum İSMİ hatalı okunsa bile bu kurallar bozulmaz —
    hepsi sadece ORAN (%) değerlerine bakar (OCR'da en güvenilir sütun).

    Kurallar:
      1) Alıcı tarafında DİĞER (dağınık küçük yatırımcı) oranı yüksekse →
         düşüş sinyali (genelde tepe/FOMO işareti).
      2) Satıcı tarafında DİĞER oranı yüksekse → yükseliş sinyali (genelde
         kapitülasyon/dip işareti).
      3) Tek bir (DİĞER olmayan) kurum alımın büyük bölümünü tek başına
         topladıysa → yükseliş sinyali (kurumsal/güçlü elde birikim).
    """
    esikler = {**VARSAYILAN_SINYAL_ESIKLERI, **(esikler or {})}
    alicilar = ayristirilmis.get("net_alicilar", {}).get("kurumlar", [])
    saticilar = ayristirilmis.get("net_saticilar", {}).get("kurumlar", [])

    diger_alici = next((s["oran"] for s in alicilar if s["kurum"] == "DİĞER"), 0.0)
    diger_satici = next((s["oran"] for s in saticilar if s["kurum"] == "DİĞER"), 0.0)
    isimli_alicilar = [s for s in alicilar if s["kurum"] != "DİĞER"]
    en_buyuk_alici = max(isimli_alicilar, key=lambda s: s["oran"], default=None)

    ilk5_alici_yuzde = round(sum(s["oran"] for s in alicilar[:5]), 2)
    ilk5_satici_yuzde = round(sum(s["oran"] for s in saticilar[:5]), 2)
    akd_spread = round(ilk5_alici_yuzde - ilk5_satici_yuzde, 2)

    sebepler = []
    puan = 0

    if diger_alici >= esikler["diger_alici_yuksek"]:
        puan -= 25
        sebepler.append(
            f"Alıcı tarafında DİĞER (dağınık küçük yatırımcı) oranı yüksek "
            f"(%{diger_alici:.1f}) — genelde tepe/FOMO işareti, düşüş riski taşır.")

    if diger_satici >= esikler["diger_satici_yuksek"]:
        puan += 25
        sebepler.append(
            f"Satıcı tarafında DİĞER (dağınık küçük yatırımcı) oranı yüksek "
            f"(%{diger_satici:.1f}) — genelde kapitülasyon/dip işareti, yükseliş potansiyeli taşır.")

    if en_buyuk_alici and en_buyuk_alici["oran"] >= esikler["tek_kurum_konsantrasyon"]:
        etiket = en_buyuk_alici["kurum"] if en_buyuk_alici["guven"] >= 0.6 else "bilinmeyen bir kurum"
        puan += 25
        sebepler.append(
            f"Tek bir kurum ({etiket}) alımın %{en_buyuk_alici['oran']:.1f}'ini tek başına "
            f"yapmış — güçlü/kurumsal birikim işareti, yükseliş potansiyeli taşır.")

    if akd_spread > esikler["spread_esik"]:
        puan += 15
        sebepler.append(
            f"İlk 5 alıcının payı ilk 5 satıcının payından belirgin yüksek "
            f"(spread %{akd_spread:+.1f}) — 'mal toplanması' (accumulation) sinyali.")
    elif akd_spread < -esikler["spread_esik"]:
        puan -= 15
        sebepler.append(
            f"İlk 5 satıcının payı ilk 5 alıcının payından belirgin yüksek "
            f"(spread %{akd_spread:+.1f}) — 'mal dağıtımı' (distribution) sinyali.")

    puan = max(-100, min(100, puan))
    if puan >= 30:
        karar = "🟢 YÜKSELİŞ SİNYALİ"
    elif puan <= -30:
        karar = "🔴 DÜŞÜŞ SİNYALİ"
    else:
        karar = "⚪ NÖTR"

    if not sebepler:
        sebepler.append("Belirgin bir konsantrasyon/dağınıklık paterni tespit edilmedi.")

    return {
        "karar": karar,
        "puan": puan,
        "sebepler": sebepler,
        "diger_alici_yuzde": diger_alici,
        "diger_satici_yuzde": diger_satici,
        "en_buyuk_alici": en_buyuk_alici,
        "ilk5_alici_yuzde": ilk5_alici_yuzde,
        "ilk5_satici_yuzde": ilk5_satici_yuzde,
        "akd_spread": akd_spread,
    }


def akd_haberler_uret(bugun: dict, dun: dict = None) -> list:
    """'Bu hafta BofA bu kağıdı %10 sattı' tarzı okunabilir haber cümleleri
    üretir: bugünün sinyal gerekçeleri + (varsa dünle/önceki kayıtla
    karşılaştırmalı) kurum bazlı belirgin değişiklikler."""
    sinyal = akd_sinyal_uret(bugun)
    haberler = [f"{sinyal['karar']} (puan {sinyal['puan']:+d})"] + list(sinyal["sebepler"])

    if dun:
        def _kurum_sozlugu(veri, taraf):
            return {s["kurum"]: s["oran"] for s in veri.get(taraf, {}).get("kurumlar", [])
                    if s.get("guven", 0) >= 0.6}

        for taraf, etiket in (("net_alicilar", "alım"), ("net_saticilar", "satım")):
            bugun_d = _kurum_sozlugu(bugun, taraf)
            dun_d = _kurum_sozlugu(dun, taraf)
            for kurum, oran in bugun_d.items():
                onceki = dun_d.get(kurum)
                if onceki is not None and abs(oran - onceki) >= 10:
                    yon = "artırdı" if oran > onceki else "azalttı"
                    haberler.append(
                        f"📰 {kurum}, {etiket} payını %{onceki:.1f}'den %{oran:.1f}'e {yon}.")

    return haberler


def _fiyat_cikar(ham_metin: str):
    """Bot caption'ından ('... 185.30 TL | 🟢+0.16%') kapanış fiyatını çıkarır."""
    m = re.search(r"([\d]{1,4}[.,]\d{1,4})\s*TL", ham_metin or "")
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def akd_ozellik_cikar(ayristirilmis: dict, kapanis_fiyati: float = None,
                       ort_hacim_10gun: float = None) -> dict:
    """AKD_Model_Egitim_Rehberi.md'deki özellik tablosunu üretir (ML modelinin
    girdi değişkenleri). Maliyet_Fiyat_Farki şu an için hesaplanmıyor (OCR bu
    sütunu güvenilir vermiyor) — None döner, model bu özelliği eksik alır."""
    sinyal = akd_sinyal_uret(ayristirilmis)
    alicilar = ayristirilmis.get("net_alicilar", {}).get("kurumlar", [])
    saticilar = ayristirilmis.get("net_saticilar", {}).get("kurumlar", [])

    kurumsal_alim = sum(s.get("net_lot_tahmini") or 0 for s in alicilar if s.get("kurumsal_mi") is True)
    kurumsal_satim = sum(s.get("net_lot_tahmini") or 0 for s in saticilar if s.get("kurumsal_mi") is True)
    toplam_akd_lot = (ayristirilmis.get("net_alicilar", {}).get("toplam_lot") or 0)

    akd_hacim_rasyosu = None
    if ort_hacim_10gun and ort_hacim_10gun > 0:
        akd_hacim_rasyosu = round(toplam_akd_lot / ort_hacim_10gun, 4)

    return {
        "ilk5_alici_yuzde": sinyal["ilk5_alici_yuzde"],
        "ilk5_satici_yuzde": sinyal["ilk5_satici_yuzde"],
        "akd_spread": sinyal["akd_spread"],
        "diger_alici_yuzde": sinyal["diger_alici_yuzde"],
        "diger_satici_yuzde": sinyal["diger_satici_yuzde"],
        "en_buyuk_alici_yuzde": (sinyal["en_buyuk_alici"] or {}).get("oran"),
        "kurumsal_alim_gucu": kurumsal_alim - kurumsal_satim,
        "maliyet_fiyat_farki": None,  # bkz. docstring — OCR ile şu an hesaplanamıyor
        "akd_hacim_rasyosu": akd_hacim_rasyosu,
        "kural_puani": sinyal["puan"],  # kural-tabanlı motorun kendi puanı, model'e ek sinyal olarak da verilebilir
    }


def _kaydet(sembol: str, ayristirilmis: dict):
    dosya = CACHE_DIR / f"akd_{sembol.upper()}.json"
    icerik = {
        "sembol": sembol.upper(),
        "zaman": dt.datetime.now().isoformat(),
        "kaynak": f"Telegram @{BOT_KULLANICI_ADI}",
        **ayristirilmis,
    }
    with open(dosya, "w", encoding="utf-8") as f:
        json.dump(icerik, f, ensure_ascii=False, indent=2)
    return dosya


def oku(sembol: str, tazelik_dakika: float = 30.0) -> dict | None:
    """app.py'nin çağırması için: diskteki en son AKD verisini okur.
    Belirtilenden eskiyse None döner (arayüz 'bayat, yeniden çek' diyebilsin)."""
    dosya = CACHE_DIR / f"akd_{sembol.upper()}.json"
    if not dosya.exists():
        return None
    try:
        with open(dosya, encoding="utf-8") as f:
            icerik = json.load(f)
        zaman = dt.datetime.fromisoformat(icerik["zaman"])
        yas_dk = (dt.datetime.now() - zaman).total_seconds() / 60
        icerik["taze_mi"] = yas_dk <= tazelik_dakika
        return icerik
    except Exception:
        return None


async def _akd_getir_async(sembol: str, komut_sablonu: str = VARSAYILAN_KOMUT_SABLONU,
                            buton_anahtari: str = "akd"):
    try:
        from telethon import TelegramClient
    except ImportError as e:
        raise ImportError(
            "telethon kurulu değil. Kur: pip install telethon --break-system-packages"
        ) from e

    ayar = _ayarlari_oku()
    client = TelegramClient(OTURUM_DOSYASI, int(ayar["api_id"]), ayar["api_hash"])
    await client.start(phone=ayar["telefon"])  # ilk seferde kod/2FA sorar

    try:
        bot = await client.get_entity(BOT_KULLANICI_ADI)
        komut = komut_sablonu.format(sembol=sembol.upper())
        gonderilen = await client.send_message(bot, komut)

        # Botun cevabını bekle: gönderdiğimiz mesajdan SONRAKİ ilk mesajı yakala.
        cevap_mesaji = None
        for _ in range(int(CEVAP_ZAMAN_ASIMI_SN / 0.5)):
            await asyncio.sleep(0.5)
            son_mesajlar = await client.get_messages(bot, limit=5)
            for m in son_mesajlar:
                if m.id > gonderilen.id and (m.text or m.buttons):
                    cevap_mesaji = m
                    break
            if cevap_mesaji:
                break

        if not cevap_mesaji:
            raise TimeoutError(
                f"{sembol}: bot {CEVAP_ZAMAN_ASIMI_SN:.0f} sn içinde cevap vermedi."
            )

        buton_etiketleri = [b.text for satir in (cevap_mesaji.buttons or []) for b in satir]
        cevap_metni = cevap_mesaji.text or ""

        # ASIL VERİ genelde bir GÖRSEL (AKD tablosu resmi) olarak, caption'ın
        # (üstteki kısa fiyat satırı) EKİ olarak geliyor — bot komutu bu resmi
        # doğrudan ilk cevapta gönderiyor, ayrı bir buton tıklaması gerekmiyor.
        gorsel_dosya = None
        if cevap_mesaji.media:
            gorsel_dosya = str(CACHE_DIR / f"akd_{sembol.upper()}.jpg")
            await client.download_media(cevap_mesaji, gorsel_dosya)

        ayristirilmis = akd_ayristir(cevap_metni)
        ayristirilmis["butonlar"] = buton_etiketleri
        ayristirilmis["kapanis_fiyati"] = _fiyat_cikar(cevap_metni)
        if gorsel_dosya:
            ayristirilmis["gorsel_dosya"] = gorsel_dosya
            # Görseli otomatik sayısal veriye çevirmeyi dene — OCR kurulu
            # değilse (pytesseract/Tesseract eksikse) sessizce atla, en
            # azından görsel ve ham metin her zaman kaydedilmiş olsun.
            try:
                tablo = akd_gorsel_ayristir(gorsel_dosya, sembol=sembol)
                ayristirilmis["tablo"] = tablo
                ayristirilmis["sinyal"] = akd_sinyal_uret(tablo)
            except ImportError as e:
                ayristirilmis["tablo_hatasi"] = f"OCR kurulu değil: {e}"
            except Exception as e:
                ayristirilmis["tablo_hatasi"] = f"Tablo ayrıştırılamadı: {e}"
        dosya = _kaydet(sembol, ayristirilmis)
        return dosya, ayristirilmis
    finally:
        await client.disconnect()


def akd_getir(sembol: str, komut_sablonu: str = VARSAYILAN_KOMUT_SABLONU):
    """Senkron sarmalayıcı — app.py veya komut satırından doğrudan çağrılabilir."""
    return asyncio.run(_akd_getir_async(sembol, komut_sablonu))


# ─────────────────────────────────────────────────────────────────────────────
# TAKAS ANALİZİ (Haftalık / Aylık / 6 Aylık / Yıllık vb.) — /takas komutu
# ─────────────────────────────────────────────────────────────────────────────
# BULGU (Chrome üzerinden botla elle konuşarak doğrulandı): /akd komutu SADECE
# anlık/günlük veri veriyor. Haftalık/3 aylık/6 aylık gibi TARİHSEL veri için
# bot AYRI bir komut kullanıyor: "/takas SEMBOL" → bot "periyot seçin" diyip
# şu butonları sunuyor: Günlük, 3 Günlük, Haftalık, Aylık, 6 Aylık, Yıllık,
# Manuel Tarih Seçiniz. Seçilen periyoda göre "... veri hazırlanıyor..." yazıp
# birkaç saniye sonra sonucu (muhtemelen görsel) gönderiyor.
# NOT: İlk testte (gece yarısından hemen sonra) TÜM periyotlar (Günlük dahil)
# "Lütfen 12:00'den sonra tekrar kontrol edin" hatası verdi — bu bizim koddan
# değil, botun takas verisini muhtemelen öğleden sonra (Takasbank'ın günlük
# veriyi yayınlama saatine bağlı) hazırlamasından kaynaklanıyor. Öğleden sonra
# tekrar denenmeli.
TAKAS_PERIYOTLARI = ["Günlük", "3 Günlük", "Haftalık", "Aylık", "6 Aylık", "Yıllık"]


async def _takas_getir_async(sembol: str, periyot: str = "Haftalık"):
    try:
        from telethon import TelegramClient
    except ImportError as e:
        raise ImportError(
            "telethon kurulu değil. Kur: pip install telethon --break-system-packages"
        ) from e
    if periyot not in TAKAS_PERIYOTLARI:
        raise ValueError(f"Geçersiz periyot: {periyot!r}. Geçerli seçenekler: {TAKAS_PERIYOTLARI}")

    ayar = _ayarlari_oku()
    client = TelegramClient(OTURUM_DOSYASI, int(ayar["api_id"]), ayar["api_hash"])
    await client.start(phone=ayar["telefon"])

    try:
        bot = await client.get_entity(BOT_KULLANICI_ADI)
        gonderilen = await client.send_message(bot, f"/takas {sembol.upper()}")

        # 1) Periyot seçim menüsünü (butonlu mesaj) bekle.
        menu_mesaji = None
        for _ in range(int(CEVAP_ZAMAN_ASIMI_SN / 0.5)):
            await asyncio.sleep(0.5)
            son = await client.get_messages(bot, limit=5)
            for m in son:
                if m.id > gonderilen.id and m.buttons:
                    menu_mesaji = m
                    break
            if menu_mesaji:
                break
        if not menu_mesaji:
            raise TimeoutError(f"{sembol}: periyot menüsü {CEVAP_ZAMAN_ASIMI_SN:.0f} sn içinde gelmedi.")

        hedef = None
        for i, satir in enumerate(menu_mesaji.buttons):
            for j, b in enumerate(satir):
                if periyot.lower() in b.text.lower():
                    hedef = (i, j)
                    break
            if hedef:
                break
        if not hedef:
            mevcut = [b.text for satir in menu_mesaji.buttons for b in satir]
            raise ValueError(f"'{periyot}' butonu bulunamadı. Mevcut butonlar: {mevcut}")

        onceki_id = menu_mesaji.id
        await menu_mesaji.click(hedef[0], hedef[1])

        # 2) Bot genelde önce "... veri hazırlanıyor..." yazar, sonra asıl
        # sonucu (metin veya görsel) ayrı bir mesaj/edit olarak gönderir. Uzunca
        # bekleyip (30 sn'ye kadar) her 1 sn'de bir kontrol ediyoruz.
        sonuc_mesaji = None
        for _ in range(30):
            await asyncio.sleep(1.0)
            son = await client.get_messages(bot, limit=5)
            adaylar = [m for m in son if m.id > onceki_id and (m.text or m.media)]
            if adaylar:
                en_yeni = adaylar[0]
                # "hazırlanıyor" gibi ARA mesajları atla, asıl sonucu bekle.
                if en_yeni.text and "hazırlan" in en_yeni.text.lower():
                    continue
                sonuc_mesaji = en_yeni
                break

        if not sonuc_mesaji:
            raise TimeoutError(f"{sembol} ({periyot}): sonuç 30 sn içinde gelmedi.")

        cevap_metni = sonuc_mesaji.text or ""
        gorsel_dosya = None
        if sonuc_mesaji.media:
            periyot_dosya_adi = periyot.lower().replace(" ", "_")
            gorsel_dosya = str(CACHE_DIR / f"takas_{sembol.upper()}_{periyot_dosya_adi}.jpg")
            await client.download_media(sonuc_mesaji, gorsel_dosya)

        basarisiz = "sorun oluştu" in cevap_metni.lower() or "❌" in cevap_metni

        sonuc = {
            "sembol": sembol.upper(),
            "periyot": periyot,
            "zaman": dt.datetime.now().isoformat(),
            "kaynak": f"Telegram @{BOT_KULLANICI_ADI}",
            "ham": cevap_metni,
            "basarili": not basarisiz,
        }
        if gorsel_dosya:
            sonuc["gorsel_dosya"] = gorsel_dosya

        periyot_dosya_adi = periyot.lower().replace(" ", "_")
        dosya = CACHE_DIR / f"takas_{sembol.upper()}_{periyot_dosya_adi}.json"
        with open(dosya, "w", encoding="utf-8") as f:
            json.dump(sonuc, f, ensure_ascii=False, indent=2)
        return dosya, sonuc
    finally:
        await client.disconnect()


def takas_getir(sembol: str, periyot: str = "Haftalık"):
    """Senkron sarmalayıcı. periyot: 'Günlük','3 Günlük','Haftalık','Aylık',
    '6 Aylık','Yıllık' — TAKAS_PERIYOTLARI listesine bakınız.
    3 AYLIK için: bot menüsünde yok, botun 'Manuel Tarih Seçiniz' seçeneği
    var ama bu script henüz onu otomatikleştirmiyor (elle tarih girişi
    gerektiriyor) — şimdilik en yakın hazır seçenek 'Aylık' veya '6 Aylık'."""
    return asyncio.run(_takas_getir_async(sembol, periyot))


def takas_oku(sembol: str, periyot: str = "Haftalık", tazelik_dakika: float = 720.0) -> dict | None:
    """app.py'nin çağırması için: diskteki en son takas verisini okur."""
    periyot_dosya_adi = periyot.lower().replace(" ", "_")
    dosya = CACHE_DIR / f"takas_{sembol.upper()}_{periyot_dosya_adi}.json"
    if not dosya.exists():
        return None
    try:
        with open(dosya, encoding="utf-8") as f:
            icerik = json.load(f)
        zaman = dt.datetime.fromisoformat(icerik["zaman"])
        yas_dk = (dt.datetime.now() - zaman).total_seconds() / 60
        icerik["taze_mi"] = yas_dk <= tazelik_dakika
        return icerik
    except Exception:
        return None


def toplu_guncelle(semboller: list[str], bekleme_sn: float = VARSAYILAN_BEKLEME_SN,
                    komut_sablonu: str = VARSAYILAN_KOMUT_SABLONU, ilerleme=None):
    """Birden çok sembol için sırayla çeker, aralarda bekler (flood-wait riskini
    azaltmak için). SADECE o an izlenen/taranan az sayıda hisse için kullan —
    bunu tüm BIST'e (~560 hisse) otomatik uygulamaya ÇALIŞMA."""
    sonuclar = {}
    async def _calistir():
        for i, s in enumerate(semboller):
            try:
                dosya, veri = await _akd_getir_async(s, komut_sablonu)
                sonuclar[s] = veri
            except Exception as e:
                sonuclar[s] = {"hata": str(e)}
            if ilerleme:
                ilerleme(i + 1, len(semboller), s)
            if i < len(semboller) - 1:
                await asyncio.sleep(bekleme_sn)
    asyncio.run(_calistir())
    return sonuclar


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python telegram_akd.py SEMBOL [SEMBOL2 ...]")
        print("Örnek:    python telegram_akd.py TERA")
        sys.exit(1)

    semboller_arg = [s.upper() for s in sys.argv[1:]]
    for sembol in semboller_arg:
        print(f"\n--- {sembol} için @{BOT_KULLANICI_ADI}'a soruluyor... ---")
        try:
            dosya, veri = akd_getir(sembol)
            print(f"Kaydedildi: {dosya}")
            if veri.get("gorsel_dosya"):
                print(f"AKD görseli indirildi: {veri['gorsel_dosya']}")
            if veri.get("sinyal"):
                s = veri["sinyal"]
                print(f"\n{s['karar']}  (puan {s['puan']:+d})")
                for sebep in s["sebepler"]:
                    print(f"  • {sebep}")
            elif veri.get("tablo_hatasi"):
                print(f"UYARI — sayısal tablo çıkarılamadı: {veri['tablo_hatasi']}")
            if veri.get("butonlar"):
                print(f"Bulunan butonlar: {veri['butonlar']}")
            print(f"Ham metin: {veri['ham']!r}")
            print("Ayrıştırılan alanlar:")
            for k, v in veri["alanlar"].items():
                print(f"  {k}: {v}")
            if not veri["alanlar"]:
                print("  (Hiçbir 'Etiket: Değer' satırı bulunamadı — ham metni "
                      "kontrol et, format farklı olabilir. Ham metin dosyaya "
                      "kaydedildi.)")
        except Exception as e:
            print(f"HATA: {e}")
