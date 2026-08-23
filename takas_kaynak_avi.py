# -*- coding: utf-8 -*-
"""
takas_kaynak_avi.py — Takas verisi için ÇALIŞAN bir kaynak bul.
══════════════════════════════════════════════════════════════════════════════
DURUM
─────
• İş Yatırım ucu (mevcut kodun kullandığı) tüm hisselerde "VERİ YOK" döndü.
  Ama NEDEN bilmiyoruz — teşhis hiç çalıştırılmadı. Basit bir başlık/format
  sorunu olabilir; öyleyse en hızlı çözüm budur.
• MKK verisini kurumsal kanallarla paylaşıyor (FTP, entegrasyon, e-posta).
  Hisse bazında günlük takas için açık bir web ucu bulunamadı.
• MKK API Portal ve VAP test edilemedi (sandbox'tan boş dönüyor).

Bu script, ADAY KAYNAKLARI TEK TEK DENER ve hangisinin gerçekten kullanılabilir
veri verdiğini raporlar. Tahminle değil ölçümle karar vermek için.

DENENENLER
──────────
  A) İş Yatırım — 4 farklı istek biçimi (başlık, format, tarih aralığı)
  B) MKK API Portal ve VAP — erişilebilir mi, kayıt mı istiyor
  C) Bilinen alternatif kamuya açık sayfalar

⚠️ SORUMLU KULLANIM: Her istek arasında bekleme vardır, tek sembol denenir.
Amaç bir kaynağın çalışıp çalışmadığını ölçmektir, toplu veri çekmek değil.
Bir kaynak kullanılacaksa önce o sitenin kullanım şartları kontrol edilmelidir.

ÇALIŞTIRMA: TAKAS_KAYNAK_AVI.bat  (~1-2 dakika)
Sonuç: takas_kaynak_avi_sonuc.txt
"""
from __future__ import annotations

import os
import sys
import json
import time
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

KLASOR = os.path.dirname(os.path.abspath(__file__))
SONUC = os.path.join(KLASOR, "takas_kaynak_avi_sonuc.txt")
SEMBOL = "THYAO"
BEKLE = 1.5          # istekler arası saniye — siteyi yormamak için

_C = []
_CALISAN = []


def yaz(m=""):
    print(m)
    _C.append(str(m))


def cizgi(k="─"):
    yaz(k * 76)


UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"}


def dene(ad, url, headers=None, aciklama=""):
    """Bir adresi dener ve NE DÖNDÜĞÜNÜ ayrıntılı raporlar."""
    yaz("\n" + "─" * 76)
    yaz(f"  {ad}")
    if aciklama:
        yaz(f"  {aciklama}")
    yaz(f"  {url[:120]}")
    time.sleep(BEKLE)
    try:
        r = requests.get(url, headers=headers or UA, timeout=25)
    except Exception as e:
        yaz(f"  ✗ İSTEK BAŞARISIZ: {type(e).__name__}: {str(e)[:80]}")
        return None
    tip = r.headers.get("Content-Type", "?")
    yaz(f"  HTTP {r.status_code} · {tip[:40]} · {len(r.text):,} karakter")

    if r.status_code != 200:
        yaz(f"  ✗ Sunucu {r.status_code} döndü.")
        return None

    metin = r.text.strip()
    if not metin:
        yaz("  ✗ Cevap BOŞ.")
        return None

    # JSON mu?
    veri = None
    try:
        veri = r.json()
    except Exception:
        # HTML olabilir — giriş sayfası mı, veri sayfası mı?
        dusuk = metin.lower()
        if "login" in dusuk or "giriş" in dusuk or "oturum" in dusuk:
            yaz("  ⚠ HTML döndü ve GİRİŞ/oturum kelimeleri içeriyor → kayıt gerekiyor olabilir.")
        elif "<html" in dusuk:
            yaz("  ⚠ HTML sayfa döndü (JSON değil). İçerik JavaScript ile yükleniyor olabilir.")
            yaz(f"    İlk 200 karakter: {metin[:200]}")
        else:
            yaz(f"  ⚠ Bilinmeyen format. İlk 200: {metin[:200]}")
        return None

    yaz("  ✓ Geçerli JSON döndü.")
    satirlar = None
    if isinstance(veri, dict):
        yaz(f"  Anahtarlar: {list(veri.keys())[:8]}")
        satirlar = veri.get("value")
        if satirlar is None:
            for k, v in veri.items():
                if isinstance(v, list) and v:
                    satirlar, ad_k = v, k
                    yaz(f"  ('value' yok; '{ad_k}' listesi kullanıldı)")
                    break
    elif isinstance(veri, list):
        satirlar = veri

    if not satirlar:
        yaz("  ✗ JSON geldi ama VERİ SATIRI YOK (boş liste).")
        yaz(f"    Tamamı: {json.dumps(veri, ensure_ascii=False)[:250]}")
        return None

    yaz(f"  ✓ {len(satirlar)} satır veri.")
    if isinstance(satirlar[0], dict):
        kolonlar = list(satirlar[0].keys())
        yaz(f"  Kolonlar ({len(kolonlar)}):")
        for i in range(0, min(len(kolonlar), 24), 3):
            yaz("    " + "  ".join(f"{k:24s}" for k in kolonlar[i:i + 3]))
        yab = [k for k in kolonlar if "YABANCI" in k.upper()]
        ipucu = [k for k in kolonlar
                 if any(x in k.upper() for x in ("TAKAS", "SAKLAMA", "FOREIGN", "ORAN"))]
        if yab:
            yaz(f"\n  ✅ 'YABANCI' KOLONU BULUNDU: {yab}")
            ornek = satirlar[-1]
            for k in yab:
                yaz(f"     Son değer — {k}: {ornek.get(k)}")
            _CALISAN.append((ad, url, yab))
            return satirlar
        if ipucu:
            yaz(f"\n  ⚠ 'YABANCI' yok ama benzer kolonlar var: {ipucu}")
            _CALISAN.append((ad, url, ipucu))
            return satirlar
        yaz("\n  ✗ Takas ile ilgili kolon yok — bu uç fiyat verisi veriyor olabilir.")
    return satirlar


def main():
    yaz("═" * 76)
    yaz("  TAKAS VERİSİ — KAYNAK AVI")
    yaz(f"  {dt.datetime.now():%d.%m.%Y %H:%M}   Test hissesi: {SEMBOL}")
    yaz("═" * 76)
    yaz("  Amaç: hangi kaynağın GERÇEKTEN kullanılabilir takas verisi")
    yaz("  verdiğini ölçmek. Tahmin değil, ölçüm.")

    bit = dt.date.today()
    bas = bit - dt.timedelta(days=120)

    # ── A) İŞ YATIRIM — mevcut kodun kaynağı, 4 varyant ──────────────────────
    yaz("\n" + "═" * 76)
    yaz("  A) İŞ YATIRIM — mevcut kodun kullandığı kaynak")
    yaz("═" * 76)
    yaz("  Bu kaynak eskiden çalışıyordu, şimdi boş dönüyor. Sorun basit bir")
    yaz("  istek biçimi meselesi olabilir — 4 varyant deneniyor.")

    tabani = ("https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/"
              f"Data.aspx/HisseTekil?hisse={SEMBOL}"
              f"&startdate={bas:%d-%m-%Y}&enddate={bit:%d-%m-%Y}")

    dene("A1 · Mevcut kod (sonunda .json)", tabani + ".json",
         aciklama="veri_katmani.yabanci_orani_gecmisi bunu kullanıyor")
    dene("A2 · '.json' EKSİZ", tabani,
         aciklama="Sondaki .json bazı sürümlerde URL'yi bozuyor olabilir")

    h3 = dict(UA)
    h3.update({"Referer": "https://www.isyatirim.com.tr/tr-tr/analiz/hisse/Sayfalar/default.aspx",
               "Accept": "application/json, text/javascript, */*; q=0.01",
               "X-Requested-With": "XMLHttpRequest"})
    dene("A3 · Referer + XHR başlıkları", tabani + ".json", h3,
         aciklama="Site doğrudan istekleri reddediyor olabilir")

    kisa = ("https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/"
            f"Data.aspx/HisseTekil?hisse={SEMBOL}"
            f"&startdate={(bit - dt.timedelta(days=20)):%d-%m-%Y}&enddate={bit:%d-%m-%Y}.json")
    dene("A4 · Kısa tarih aralığı (20 gün)", kisa, h3,
         aciklama="Uzun aralık zaman aşımına düşüyor olabilir")

    # ── B) MKK ve VAP ────────────────────────────────────────────────────────
    yaz("\n" + "═" * 76)
    yaz("  B) MKK / VAP — kurumsal platformlar")
    yaz("═" * 76)
    yaz("  MKK verisini kurumsal kanallarla paylaşıyor (FTP, entegrasyon,")
    yaz("  e-posta). Aşağıdakiler erişilebilir mi, kayıt mı istiyor — ölçülüyor.")

    dene("B1 · MKK API Portal", "https://apiportal.mkk.com.tr/",
         aciklama="Kayıt/anahtar gerekiyorsa giriş sayfası döner")
    dene("B2 · VAP (Veri Analiz Platformu)", "https://www.vap.org.tr/",
         aciklama="MKK'nın veri analiz platformu")

    # ── C) Alternatif kamuya açık kaynaklar ──────────────────────────────────
    yaz("\n" + "═" * 76)
    yaz("  C) ALTERNATİF KAYNAKLAR")
    yaz("═" * 76)
    dene("C1 · Halk Yatırım analiz",
         "https://analizim.halkyatirim.com.tr/Analysis/ForeignExchangeRates",
         aciklama="Yabancı takas oranları sayfası — erişilebilir mi?")

    # ── SONUÇ ────────────────────────────────────────────────────────────────
    yaz("\n" + "═" * 76)
    yaz("  SONUÇ")
    yaz("═" * 76)
    if _CALISAN:
        yaz(f"  ✅ {len(_CALISAN)} kaynak kullanılabilir veri döndürdü:")
        for ad, url, kolonlar in _CALISAN:
            yaz(f"     • {ad}")
            yaz(f"       kolon: {kolonlar}")
        yaz("\n  → Bu bilgiyle veri_katmani.yabanci_orani_gecmisi düzeltilebilir.")
        yaz("    Sonra takas verisi taramaya eklenip ÖNGÖRÜ GÜCÜ ölçülür")
        yaz("    (aynı disiplinle: korelasyon, desil, walk-forward, anlamlılık).")
    else:
        yaz("  ❌ Hiçbir kaynak kullanılabilir takas verisi vermedi.")
        yaz("\n  Bu durumda gerçekçi seçenekler:")
        yaz("    1) Aracı kurumunuzun verdiği veri ekranı (Matriks/Foreks/İdeal)")
        yaz("       — çoğu kurum müşterisine ücretsiz veriyor. Ekrandan bakılır,")
        yaz("       yazılıma otomatik akmaz ama elle kontrol için yeterlidir.")
        yaz("    2) Matriks API (gerçek API'si olan tek uygun seçenek) +")
        yaz("       Borsa İstanbul veri lisansı.")
        yaz("    3) MKK ile doğrudan iletişim: veri dağıtım sözleşmesi şartları.")
        yaz("       (212) 334 57 00 · mkk.com.tr/iletisim-formu")
        yaz("\n  NOT: Takas verisi olmadan da motorun birikim/dağıtım vekili")
        yaz("  (CMF) ölçüldü ve BIST'te anlamlı çıktı — sanal portföy artık")
        yaz("  onu kullanıyor. Yani takas yokluğu yolu tamamen kapatmıyor.")
    yaz("═" * 76)


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            with open(SONUC, "w", encoding="utf-8") as f:
                f.write("\n".join(_C))
            print(f"\n  Sonuç: {os.path.basename(SONUC)}")
        except Exception as e:
            print(f"\n  UYARI: dosyaya yazılamadı: {e}")
