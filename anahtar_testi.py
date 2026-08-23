# -*- coding: utf-8 -*-
"""
anahtar_testi.py — Sohbet asistanının API anahtarlarını GERÇEKTEN test eder.
══════════════════════════════════════════════════════════════════════════════
NE YAPAR: .env dosyasındaki her anahtar için sırayla:
  1) Anahtar okunuyor mu, formatı doğru mu?
  2) Sağlayıcıya GERÇEK bir istek atıp cevap alıyor mu?
  3) Hata varsa NEDENİNİ açıkça yazar (geçersiz anahtar / kota / ağ / model).

Çalıştırma: ANAHTAR_TESTI.bat dosyasına çift tıklayın.

GÜVENLİK: Anahtarların kendisi ekrana YAZILMAZ; sadece ilk birkaç karakteri
ve uzunluğu gösterilir.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

import llm_ajanlari as la

FORMAT = {
    "GROQ_API_KEY":     (r"^gsk_[A-Za-z0-9]{40,}$",        "gsk_ ile başlar, ~56 karakter"),
    "NVIDIA_API_KEY":   (r"^nvapi-[A-Za-z0-9_\-]{40,}$",   "nvapi- ile başlar, ~70 karakter"),
    "OPENAI_API_KEY":   (r"^sk-[A-Za-z0-9_\-]{20,}$",      "sk- ile başlar"),
    "ANTHROPIC_API_KEY": (r"^sk-ant-[A-Za-z0-9_\-]{20,}$", "sk-ant- ile başlar"),
    "XAI_API_KEY":      (r"^xai-[A-Za-z0-9_\-]{20,}$",     "xai- ile başlar"),
    "DEEPSEEK_API_KEY": (r"^sk-[A-Za-z0-9_\-]{20,}$",      "sk- ile başlar"),
}


def _cizgi(baslik=""):
    print("\n" + "═" * 68)
    if baslik:
        print(f"  {baslik}")
        print("═" * 68)


def format_kontrolu():
    _cizgi("1) ANAHTAR FORMAT KONTROLÜ (.env dosyası)")
    bulunan = []
    for ad, (kalip, aciklama) in FORMAT.items():
        deger = la._anahtar(ad)
        if not deger:
            print(f"  ⚪ {ad:20s} boş — bu sağlayıcı kullanılmayacak")
            continue
        if any(c in deger for c in ' "\'\t\r\n'):
            print(f"  ❌ {ad:20s} İÇİNDE BOŞLUK/TIRNAK VAR — .env'de tırnak kullanmayın")
            continue
        # Tekrarlanan önek (en sık yapılan hata: gsk_gsk_..., nvapi-nvapi-...)
        onek = deger.split("_")[0] + "_" if "_" in deger[:8] else deger.split("-")[0] + "-"
        if deger.startswith(onek + onek):
            print(f"  ❌ {ad:20s} ÖNEK İKİ KEZ YAZILMIŞ ('{onek}{onek}...')")
            print(f"      → .env'de satır şöyle olmalı: {ad}={onek}xxxxx")
            continue
        if re.match(kalip, deger):
            print(f"  ✅ {ad:20s} {len(deger):3d} karakter, '{deger[:7]}...' — format doğru")
            bulunan.append(ad)
        else:
            print(f"  ❌ {ad:20s} format hatalı ({aciklama})")
    return bulunan


def canli_test():
    _cizgi("2) GERÇEK BAĞLANTI TESTİ (sağlayıcılara istek atılıyor)")
    herhangi_calisti = False

    for ad, key_ad, url, varsayilan_model in la._SOHBET_ZINCIRI:
        key = la._anahtar(key_ad)
        if not key:
            continue

        model = varsayilan_model
        if ad == "NVIDIA":
            print(f"\n  ── {ad} ─ model kataloğu okunuyor...")
            secilen = la._nvidia_model_sec(key)
            if secilen:
                model = secilen
                print(f"     ✅ Katalog okundu, seçilen model: {model}")
            else:
                print(f"     ⚠️  Katalog okunamadı, sabit model denenecek: {model}")
        else:
            print(f"\n  ── {ad} ─ model: {model}")

        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={"model": model,
                      "messages": [{"role": "user",
                                    "content": "Sadece 'TAMAM' yaz, başka hiçbir şey yazma."}],
                      "max_tokens": 10, "temperature": 0},
                timeout=45)
        except requests.exceptions.ConnectTimeout:
            print("     ❌ BAĞLANTI ZAMAN AŞIMI — internet/güvenlik duvarı engelliyor olabilir")
            continue
        except Exception as e:
            print(f"     ❌ AĞ HATASI: {e}")
            continue

        if r.status_code == 200:
            try:
                cevap = r.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                cevap = "(yanıt çözülemedi)"
            print(f"     ✅ ÇALIŞIYOR — model cevabı: {cevap!r}")
            herhangi_calisti = True
        elif r.status_code == 401:
            print("     ❌ ANAHTAR GEÇERSİZ (401) — anahtar yanlış veya iptal edilmiş")
            print(f"        → Yeni anahtar alın ve .env'deki {key_ad} satırına yazın")
        elif r.status_code == 403:
            print("     ❌ ERİŞİM REDDEDİLDİ (403) — anahtar bu modele yetkili değil")
        elif r.status_code == 404:
            print(f"     ❌ MODEL BULUNAMADI (404): {model}")
            print("        → Model adı değişmiş olabilir; NVIDIA için katalog otomatik okunur")
        elif r.status_code == 429:
            print("     ⚠️  KOTA DOLU (429) — anahtar geçerli ama limit aşılmış")
            print("        → Bir süre bekleyin; asistan bu durumda diğer sağlayıcıya geçer")
        else:
            print(f"     ❌ HTTP {r.status_code}: {r.text[:200]}")

    return herhangi_calisti


def uctan_uca():
    _cizgi("3) ASİSTAN UÇTAN UCA TESTİ")
    yanit, saglayici = la.sohbet_tamamla(
        [{"role": "user", "content": "Tek kelimeyle cevap ver: merhaba"}],
        max_tokens=20)
    if yanit:
        print(f"  ✅ Asistan çalışıyor — kullanılan sağlayıcı: {saglayici}")
        print(f"     Cevap: {yanit[:100]!r}")
        return True
    print(f"  ❌ Asistan cevap veremedi: {saglayici}")
    return False


if __name__ == "__main__":
    print("\n╔" + "═" * 66 + "╗")
    print("║" + "  BIST Analiz Platformu — API ANAHTAR TESTİ".ljust(66) + "║")
    print("╚" + "═" * 66 + "╝")

    format_kontrolu()
    calisti = canli_test()
    if calisti:
        uctan_uca()

    _cizgi("SONUÇ")
    if calisti:
        print("  ✅ En az bir sağlayıcı çalışıyor. Sohbet asistanı kullanıma hazır.")
        print("     Uygulamayı BASLAT.bat ile açın.")
    else:
        print("  ❌ Hiçbir sağlayıcı çalışmadı. Yukarıdaki hata mesajlarına bakın.")
        print("     En sık sebepler:")
        print("       • Anahtar yanlış kopyalanmış (önek iki kez yazılmış)")
        print("       • Anahtar iptal edilmiş / süresi dolmuş")
        print("       • İnternet bağlantısı veya güvenlik duvarı engeli")

    print()
    try:
        input("Kapatmak için Enter'a basın...")
    except EOFError:
        pass          # betik otomatik/yönlendirilmiş çalıştırıldığında beklemesin
