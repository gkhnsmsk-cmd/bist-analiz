# -*- coding: utf-8 -*-
"""
takas_teshis.py — Takas verisi NEDEN gelmiyor? Ham cevabı inceler.
══════════════════════════════════════════════════════════════════════════════
DURUM: takas_testi.py tüm hisselerde "VERİ YOK" döndürdü. Yani
veri_katmani.yabanci_orani_gecmisi() boş seri veriyor.

Bu fonksiyon hatayı SESSİZCE yutuyor (try/except → boş seri). Bu yüzden
"Hisse Araştır" sekmesinde de takas verisi aslında hiç kullanılmıyor ama
kullanıcı bunu göremiyor — sadece "geçmiş veri alınamadı" yazıyor.

Bu script sessizliği kaldırır ve şunları gösterir:
  1) HTTP isteği gidiyor mu, kaç kodla dönüyor?
  2) Cevap gerçekten JSON mu, yoksa HTML/hata sayfası mı?
  3) JSON'da hangi kolonlar var? "YABANCI" içeren kolon kaldı mı?
  4) Kolon adı değiştiyse yenisi ne?

ÇALIŞTIRMA:  TAKAS_TESHIS.bat
Sonuç: takas_teshis_sonuc.txt
"""
from __future__ import annotations

import os
import sys
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

KLASOR = os.path.dirname(os.path.abspath(__file__))
SONUC = os.path.join(KLASOR, "takas_teshis_sonuc.txt")
_C = []


def yaz(m=""):
    print(m)
    _C.append(str(m))


UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

SEMBOL = "THYAO"


def dene(ad, url, headers=None):
    """Bir URL'yi dener ve cevabı ayrıntılı raporlar."""
    yaz("\n" + "─" * 74)
    yaz(f"  DENEME: {ad}")
    yaz("─" * 74)
    yaz(f"  URL: {url[:150]}")
    try:
        r = requests.get(url, headers=headers or UA, timeout=20)
    except Exception as e:
        yaz(f"  ✗ İSTEK BAŞARISIZ: {type(e).__name__}: {e}")
        return None
    yaz(f"  HTTP durum kodu : {r.status_code}")
    yaz(f"  İçerik tipi     : {r.headers.get('Content-Type', '?')}")
    yaz(f"  Cevap uzunluğu  : {len(r.text):,} karakter")

    if r.status_code != 200:
        yaz(f"  ✗ Sunucu {r.status_code} döndü. İlk 300 karakter:")
        yaz("    " + r.text[:300].replace("\n", "\n    "))
        return None

    # JSON mu?
    try:
        j = r.json()
    except Exception as e:
        yaz(f"  ✗ CEVAP JSON DEĞİL ({e}). İlk 400 karakter:")
        yaz("    " + r.text[:400].replace("\n", "\n    "))
        return None

    yaz(f"  ✓ Cevap geçerli JSON.")
    if isinstance(j, dict):
        yaz(f"  Üst düzey anahtarlar: {list(j.keys())[:10]}")
        satirlar = j.get("value")
        if satirlar is None:
            for k in j:
                if isinstance(j[k], list) and j[k]:
                    satirlar = j[k]
                    yaz(f"  ('value' yok; '{k}' anahtarı liste içeriyor)")
                    break
    elif isinstance(j, list):
        satirlar = j
    else:
        satirlar = None

    if not satirlar:
        yaz("  ✗ Veri satırı YOK (boş liste döndü).")
        yaz("    Cevabın tamamı (ilk 400 kr): " + json.dumps(j, ensure_ascii=False)[:400])
        return None

    yaz(f"  ✓ {len(satirlar)} satır veri geldi.")
    kolonlar = list(satirlar[0].keys()) if isinstance(satirlar[0], dict) else []
    yaz(f"\n  KOLONLAR ({len(kolonlar)} adet):")
    for i in range(0, len(kolonlar), 3):
        yaz("    " + "  ".join(f"{k:26s}" for k in kolonlar[i:i + 3]))

    # YABANCI arayan mantik — veri_katmani ile AYNI
    yab = [k for k in kolonlar if "YABANCI" in k.upper()]
    yaz(f"\n  'YABANCI' içeren kolon: {yab if yab else '✗ YOK — fonksiyonun aradığı kolon KAYIP'}")

    # Benzer olabilecek kolonlar
    ipuclari = [k for k in kolonlar
                if any(x in k.upper() for x in ("TAKAS", "ORAN", "FOREIGN", "SAKLAMA", "YAB"))]
    if ipuclari and not yab:
        yaz(f"  Alternatif olabilecek kolonlar: {ipuclari}")

    yaz("\n  İLK SATIR (örnek değerler):")
    for k, v in list(satirlar[0].items())[:14]:
        yaz(f"    {k:28s} = {v}")
    return satirlar


def main():
    yaz("═" * 74)
    yaz("  TAKAS VERİSİ TEŞHİS")
    yaz(f"  {dt.datetime.now():%d.%m.%Y %H:%M}   Test hissesi: {SEMBOL}")
    yaz("═" * 74)
    yaz("  takas_testi.py tüm hisselerde 'VERİ YOK' döndürdü.")
    yaz("  Bu script sebebini bulmak için ham HTTP cevabını inceler.")

    bit = dt.date.today()
    bas = bit - dt.timedelta(days=365)

    # 1) veri_katmani'nin kullandigi URL — BIREBIR AYNI
    url1 = ("https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/"
            f"Data.aspx/HisseTekil?hisse={SEMBOL}"
            f"&startdate={bas:%d-%m-%Y}&enddate={bit:%d-%m-%Y}.json")
    r1 = dene("veri_katmani'nin kullandığı URL (mevcut kod)", url1)

    # 2) Sonundaki ".json" olmadan — bu ek bazen URL'yi bozar
    url2 = ("https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/"
            f"Data.aspx/HisseTekil?hisse={SEMBOL}"
            f"&startdate={bas:%d-%m-%Y}&enddate={bit:%d-%m-%Y}")
    r2 = dene("Aynı URL, sonundaki '.json' KALDIRILMIŞ", url2)

    # 3) Referer basligiyla — bazi siteler dogrudan istegi reddeder
    h3 = dict(UA)
    h3["Referer"] = "https://www.isyatirim.com.tr/"
    h3["Accept"] = "application/json, text/javascript, */*; q=0.01"
    h3["X-Requested-With"] = "XMLHttpRequest"
    r3 = dene("Referer + XMLHttpRequest başlıklarıyla", url1, h3)

    # 4) Daha kisa tarih araligi
    url4 = ("https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/"
            f"Data.aspx/HisseTekil?hisse={SEMBOL}"
            f"&startdate={(bit - dt.timedelta(days=30)):%d-%m-%Y}&enddate={bit:%d-%m-%Y}.json")
    r4 = dene("Sadece son 30 gün (kısa aralık)", url4)

    yaz("\n" + "═" * 74)
    yaz("  ÖZET VE YORUM")
    yaz("═" * 74)
    calisan = [ad for ad, r in [("mevcut kod", r1), ("'.json' kaldırılmış", r2),
                                ("Referer'lı", r3), ("kısa aralık", r4)] if r]
    if not calisan:
        yaz("  ❌ HİÇBİR DENEME VERİ GETİREMEDİ.")
        yaz("     Muhtemel sebepler:")
        yaz("       • İş Yatırım bu ucu kapattı veya adresi değişti")
        yaz("       • Site bot isteklerini engelliyor (Cloudflare vb.)")
        yaz("       • Ağ/güvenlik duvarı engeli")
        yaz("     → Takas için ALTERNATİF KAYNAK gerekiyor.")
    else:
        yaz(f"  ✓ Veri getiren deneme(ler): {', '.join(calisan)}")
        yaz("     Eğer 'mevcut kod' listede YOKSA, veri_katmani.py'deki istek")
        yaz("     düzeltilebilir demektir — çalışan denemenin biçimi kullanılmalı.")
    yaz("═" * 74)


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            with open(SONUC, "w", encoding="utf-8") as f:
                f.write("\n".join(_C))
            print(f"\n  Sonuç kaydedildi: {os.path.basename(SONUC)}")
        except Exception as e:
            print(f"\n  UYARI: dosyaya yazılamadı: {e}")
