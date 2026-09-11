"""V6 walk-forward backtest koşturucusu (GitHub Actions için).

calistir_v3.py / calistir_v4.py örnek alınarak (kopyalanmadan, uyarlanarak)
yazıldı — AYNI hata yakalama, NaN temizleme ve ozet.md biçimi izlenir.

KULLANICI HEDEFİ (pazarlık yok, bkz. v6_backtest._HEDEF_CAGR/_HEDEF_MAKS_DUSUS/
_HEDEF_PF): TEST döneminde (2024-01-01 -> bugün) CAGR >= %55, maksimum düşüş
<= %25, profit factor >= 1.3. Rapor bu ÜÇ eşiği tek tek GEÇTİ/GEÇMEDİ olarak
gösterir — endeks kıyası da (bilgi amaçlı) ayrıca raporlanır ama GATE bu üç
sabit eşiktir, endeksi yenmek DEĞİL.

Çıktılar (v2/sonuclar_v6/ altında):
  - walk_forward.json : tüm metrikler + doğrulama sonucu (makine okur)
  - islemler_test.csv : test dönemi işlem listesi (elle incelemek için)
  - ozet.md           : insan okuyacak özet (GitHub Actions job summary'de görünür)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import traceback
from datetime import datetime, timezone

import v6_backtest as v6bt

SONUC_DIZINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonuclar_v6")


def _temiz(deger):
    if isinstance(deger, float):
        if math.isnan(deger) or math.isinf(deger):
            return None
        return round(deger, 6)
    if isinstance(deger, dict):
        return {k: _temiz(v) for k, v in deger.items()}
    if isinstance(deger, list):
        return [_temiz(v) for v in deger]
    if hasattr(deger, "isoformat"):
        return deger.isoformat()
    return deger


def _yuzde(deger, basamak: int = 2) -> str:
    if deger is None or (isinstance(deger, float) and (math.isnan(deger) or math.isinf(deger))):
        return "—"
    return f"%{deger * 100:.{basamak}f}"


def _sayi(deger, basamak: int = 2) -> str:
    if deger is None or (isinstance(deger, float) and (math.isnan(deger) or math.isinf(deger))):
        return "—"
    return f"{deger:.{basamak}f}"


def _kiyas_tablosu(baslik: str, v6_m: dict, al_tut_m: dict | None) -> str:
    v6_cagr = v6_m.get("cagr")
    v6_dusus = v6_m.get("maksimum_dusus_%")
    al_tut_cagr = (al_tut_m or {}).get("cagr")
    al_tut_dusus = (al_tut_m or {}).get("maksimum_dusus_%")

    satirlar = [
        f"### {baslik}",
        "",
        "| Metrik | V6 (bu sistem) | Kullanıcı hedefi | BIST100 al-ve-tut |",
        "|---|---|---|---|",
        f"| **CAGR** | **{_yuzde(v6_cagr)}** | >=%{v6bt._HEDEF_CAGR * 100:.0f} | {_yuzde(al_tut_cagr)} |",
        f"| **Maksimum düşüş** | **{_yuzde(v6_dusus, 1)}** | <=%{v6bt._HEDEF_MAKS_DUSUS * 100:.0f} | {_yuzde(al_tut_dusus, 1)} |",
        f"| Profit factor | **{_sayi(v6_m.get('profit_factor'))}** | >={v6bt._HEDEF_PF} | — |",
        f"| İşlem sayısı | {v6_m.get('islem_sayisi', 0)} | — | — (tek alım) |",
        f"| Kazanma oranı | {_yuzde(v6_m.get('kazanma_orani'), 1)} | — | — |",
        f"| Endeks üstü CAGR farkı | {_yuzde(v6_m.get('endeks_ustu_fark'))} | — | — |",
        "",
    ]
    return "\n".join(satirlar)


def _ozet_yaz(sonuc: dict, ozsermaye: float) -> str:
    dogrulama = sonuc.get("dogrulama", {})
    gecti = dogrulama.get("gecti", False)

    test_m = sonuc.get("test", {}).get("metrikler", {})
    gelistirme_m = sonuc.get("gelistirme", {}).get("metrikler", {})
    al_tut_test_m = (sonuc.get("al_tut_test") or {}).get("metrikler")
    al_tut_gelistirme_m = (sonuc.get("al_tut_gelistirme") or {}).get("metrikler")

    satirlar = [
        "# PUSULA V6 — Yoğunlaştırılmış (3-5 pozisyon) Walk-Forward Backtest Sonucu",
        "",
        f"Çalıştırma: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')} · "
        f"Başlangıç özsermayesi: {ozsermaye:,.0f} TL",
        "",
        "**Kullanıcı hedefi (pazarlık yok):** TEST döneminde CAGR >= %55, maksimum düşüş <= %25, "
        "profit factor >= 1.3 — üçü BİRDEN sağlanmalı.",
        "",
        "---",
        "",
    ]

    if gecti:
        satirlar += [
            "## KULLANICI HEDEFİ GEÇİLDİ",
            "",
            "Sistem, **dokunulmamış test döneminde** üç eşiği de (CAGR/maksimum düşüş/profit "
            "factor) BİRDEN sağladı.",
            "",
        ]
    else:
        satirlar += [
            "## KULLANICI HEDEFİ GEÇİLEMEDİ",
            "",
            "Aşağıdaki eşiklerden en az biri test döneminde sağlanmadı:",
            "",
        ]
        for madde in dogrulama.get("basarisiz_kriterler", []):
            satirlar.append(f"- {madde}")
        satirlar.append("")

    satirlar += ["---", ""]
    satirlar.append(_kiyas_tablosu(
        "TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir",
        test_m, al_tut_test_m,
    ))
    satirlar.append(_kiyas_tablosu(
        "Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı",
        gelistirme_m, al_tut_gelistirme_m,
    ))

    satirlar += [
        "---",
        "",
        "## Tasarım özeti (V6 = yoğunlaştırılmış / az sayıda yüksek-güven pozisyon)",
        "",
        "- **Evren:** v2/evren.py likidite/fiyat filtresi + v6_skor.py'nin DÖRT sert şartı "
        "(trend hizası EMA20/EMA50/MA200 üstünde, hacim >=2x patlama, 52 hafta zirvesine "
        "%95 yakınlık, pozitif momentum + ATR/Kapanış<=%9).",
        "- **Pozisyon sayısı:** 3-5 (10 değil) — az ama yüksek ağırlık (%20-33 bandı).",
        "- **Çıkış:** ATR-bazlı stop (-%8/-10 bandı), +%15'te yarısı realize + stop başabaşa, "
        "+%25 sonrası trailing sıkılaşır, rejim R3/R4'te TAM çıkış, MA200 altında 3 gün "
        "üst üste kapanışta trend çıkışı.",
        "- **Rejim kapısı:** İKİLİ ve AGRESİF (R1=tam yatırım, R2=yarı, R3/R4=tam nakit; "
        "kademeli yaklaşma YOK) — sermaye korumasını pozisyon azlığı değil rejim kapısı üstlenir.",
        "- **Tarama sıklığı:** GÜNLÜK (haftalık/aylık değil) — güçlü kırılımları kaçırmamak için.",
        "",
        "## Bilinen sınırlar (dürüstlük notu)",
        "",
        "- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor.",
        "- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans limit "
        "verisi değil.",
        "- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor.",
        "- **Yoğunlaşma riski BİLİNÇLİ:** 3-5 pozisyonla tek isim riski V2/V3'e göre çok daha "
        "yüksektir; bu, CAGR hedefine ulaşmak için göze alınan açık bir riziko dengesidir "
        "(rejim kapısı ve ATR-bazlı stop bunu sınırlamaya çalışır, ORTADAN KALDIRMAZ).",
        "- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.",
        "",
    ]
    return "\n".join(satirlar)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="V6 walk-forward backtest (yoğunlaştırılmış)")
    ayristirici.add_argument("--ozsermaye", type=float, default=1_000_000.0)
    argumanlar = ayristirici.parse_args()

    os.makedirs(SONUC_DIZINI, exist_ok=True)

    try:
        sonuc = v6bt.walk_forward(ozsermaye=argumanlar.ozsermaye)
    except Exception:
        traceback.print_exc()
        hata_metni = (
            "# PUSULA V6 — Backtest ÇALIŞMADI\n\n"
            "Backtest bir hata ile durdu; aşağıdaki traceback'e bakın.\n\n"
            "```\n" + traceback.format_exc() + "\n```\n"
        )
        with open(os.path.join(SONUC_DIZINI, "ozet.md"), "w", encoding="utf-8") as dosya:
            dosya.write(hata_metni)
        return 1

    kayit = {
        "calistirma_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "ozsermaye": argumanlar.ozsermaye,
        "dogrulama": _temiz(sonuc.get("dogrulama", {})),
        "test_metrikleri": _temiz(sonuc.get("test", {}).get("metrikler", {})),
        "gelistirme_metrikleri": _temiz(sonuc.get("gelistirme", {}).get("metrikler", {})),
        "al_tut_test_metrikleri": _temiz((sonuc.get("al_tut_test") or {}).get("metrikler", {})),
        "al_tut_gelistirme_metrikleri": _temiz((sonuc.get("al_tut_gelistirme") or {}).get("metrikler", {})),
        "test_ozsermaye_egrisi": _temiz(sonuc.get("test", {}).get("ozsermaye_egrisi", [])),
    }
    with open(os.path.join(SONUC_DIZINI, "walk_forward.json"), "w", encoding="utf-8") as dosya:
        json.dump(kayit, dosya, ensure_ascii=False, indent=1)

    islemler = sonuc.get("test", {}).get("islemler", [])
    if islemler:
        alanlar = sorted({anahtar for islem in islemler for anahtar in islem.keys()})
        yol = os.path.join(SONUC_DIZINI, "islemler_test.csv")
        with open(yol, "w", encoding="utf-8-sig", newline="") as dosya:
            yazici = csv.DictWriter(dosya, fieldnames=alanlar, extrasaction="ignore")
            yazici.writeheader()
            for islem in islemler:
                yazici.writerow({k: _temiz(v) for k, v in islem.items()})

    ozet = _ozet_yaz(sonuc, argumanlar.ozsermaye)
    with open(os.path.join(SONUC_DIZINI, "ozet.md"), "w", encoding="utf-8") as dosya:
        dosya.write(ozet)

    print()
    print(ozet)

    # NEDEN 0 dönüyoruz: kriterler geçmese bile backtest'in KENDİSİ başarılıdır
    # (bkz. calistir_v3.py/calistir_v4.py'deki AYNI gerekçe).
    return 0


if __name__ == "__main__":
    sys.exit(main())
