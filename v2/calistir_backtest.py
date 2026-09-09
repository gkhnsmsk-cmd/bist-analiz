"""V2 walk-forward backtest koşturucusu (GitHub Actions için).

NEDEN AYRI DOSYA: backtest.py saf bir kütüphane olarak kalsın; dosya yazma,
CLI argümanı ve rapor biçimlendirme gibi yan etkiler burada toplansın.

Çıktılar (v2/sonuclar/ altında):
  - walk_forward.json : tüm metrikler + doğrulama sonucu (makine okur)
  - islemler_test.csv : test dönemi işlem listesi (elle incelemek için)
  - ozet.md           : insan okuyacak özet (Actions sayfasında da gösterilir)
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

import backtest as bt

SONUC_DIZINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonuclar")


def _temiz(deger):
    """JSON, NaN/Infinity kabul etmez — bunları None'a çevirir."""
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


def _metrik_tablosu(baslik: str, m: dict) -> str:
    """Bir dönemin metriklerini markdown tablosu olarak biçimler."""
    # NOT: backtest._metrikleri_hesapla()'da 'en_kotu_islem' bir SÖZLÜK
    # ({'sembol','sonuc_R','net_pnl_tl','cikis_nedeni'}) veya None döner —
    # tek bir sayı DEĞİLDİR. _sayi() doğrudan bir dict'i ":.Nf" ile
    # biçimlendirmeye çalışırsa TypeError fırlatır; bu yüzden burada önce
    # dict'ten 'sonuc_R' çıkarılıyor.
    en_kotu = m.get('en_kotu_islem')
    if en_kotu:
        en_kotu_metni = (f"{_sayi(en_kotu.get('sonuc_R'))}R "
                          f"({en_kotu.get('sembol', '—')}, {en_kotu.get('cikis_nedeni', '—')})")
    else:
        en_kotu_metni = "—"
    return "\n".join([
        f"### {baslik}",
        "",
        "| Metrik | Değer |",
        "|---|---|",
        f"| İşlem sayısı | {m.get('islem_sayisi', 0)} |",
        f"| Kazanma oranı | {_yuzde(m.get('kazanma_orani'), 1)} |",
        f"| **Expectancy** | **{_sayi(m.get('expectancy_R'), 3)}R** |",
        f"| **Profit factor** | **{_sayi(m.get('profit_factor'))}** |",
        f"| Ort. kazanç / kayıp | {_sayi(m.get('ort_kazanc_R'))}R / {_sayi(m.get('ort_kayip_R'))}R |",
        f"| **Maksimum düşüş** | **{_yuzde(m.get('maksimum_dusus_%'), 1)}** |",
        f"| CAGR | {_yuzde(m.get('cagr'))} |",
        f"| Endeks CAGR | {_yuzde(m.get('endeks_cagr'))} |",
        f"| **Endeks üstü fark** | **{_yuzde(m.get('endeks_ustu_fark'))}** |",
        f"| Ort. tutma süresi | {_sayi(m.get('ortalama_tutma_gun'), 1)} gün |",
        f"| En kötü tek işlem | {en_kotu_metni} |",
        "",
    ])


def _ozet_yaz(sonuc: dict, ozsermaye: float) -> str:
    """§8 kabul kriterleri dahil, insan okuyacak özet raporu üretir."""
    dogrulama = sonuc.get("dogrulama", {})
    gecti = dogrulama.get("gecti", False)

    satirlar = [
        "# PUSULA V2 — Walk-Forward Backtest Sonucu",
        "",
        f"Çalıştırma: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')} · "
        f"Başlangıç özsermayesi: {ozsermaye:,.0f} TL",
        "",
        "---",
        "",
    ]

    if gecti:
        satirlar += [
            "## ✅ KABUL KRİTERLERİ GEÇİLDİ",
            "",
            "Sistem şartname §8'deki tüm eşikleri **dokunulmamış test döneminde** geçti.",
            "Tavsiye üretmeye uygundur.",
            "",
        ]
    else:
        satirlar += [
            "## ❌ KABUL KRİTERLERİ GEÇİLEMEDİ",
            "",
            "Şartname §8 gereği sistem **TAVSIYE_VERME** modunda kalmalıdır.",
            "Kullanıcıya sinyal gösterilmez; nedeni ana ekranda yazılır.",
            "",
            "**Başarısız kriterler:**",
            "",
        ]
        for madde in dogrulama.get("basarisiz_kriterler", []):
            satirlar.append(f"- {madde}")
        satirlar.append("")

    satirlar += ["---", ""]
    satirlar.append(_metrik_tablosu(
        "TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir",
        sonuc.get("test", {}).get("metrikler", {}),
    ))
    satirlar.append(_metrik_tablosu(
        "Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı",
        sonuc.get("gelistirme", {}).get("metrikler", {}),
    ))

    satirlar += [
        "---",
        "",
        "## Bilinen sınırlar (dürüstlük notu)",
        "",
        "- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor;",
        "  geçmişte borsadan çıkmış/endeksten düşmüş hisseler yok. Bu, sonuçları",
        "  olduğundan **iyi** gösterme eğilimindedir.",
        "- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek",
        "  seans limit verisi değil.",
        "- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor, bu da",
        "  sektör yoğunlaşma kısıtını zayıflatıyor.",
        "- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.",
        "",
    ]
    return "\n".join(satirlar)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="V2 walk-forward backtest")
    ayristirici.add_argument("--ozsermaye", type=float, default=1_000_000.0)
    argumanlar = ayristirici.parse_args()

    os.makedirs(SONUC_DIZINI, exist_ok=True)

    try:
        sonuc = bt.walk_forward(ozsermaye=argumanlar.ozsermaye)
    except Exception:
        # NEDEN: Actions çıktısında ham traceback görünsün ama iş akışı da
        # kırmızıya dönsün — sessiz başarısızlık en tehlikeli sonuçtur.
        traceback.print_exc()
        hata_metni = (
            "# PUSULA V2 — Backtest ÇALIŞMADI\n\n"
            "Backtest bir hata ile durdu; aşağıdaki traceback'e bakın.\n\n"
            "```\n" + traceback.format_exc() + "\n```\n"
        )
        with open(os.path.join(SONUC_DIZINI, "ozet.md"), "w", encoding="utf-8") as dosya:
            dosya.write(hata_metni)
        return 1

    # 1) Tam sonuç (özsermaye eğrisi hariç — çok büyük, ayrı tutulur)
    kayit = {
        "calistirma_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "ozsermaye": argumanlar.ozsermaye,
        "dogrulama": _temiz(sonuc.get("dogrulama", {})),
        "test_metrikleri": _temiz(sonuc.get("test", {}).get("metrikler", {})),
        "gelistirme_metrikleri": _temiz(sonuc.get("gelistirme", {}).get("metrikler", {})),
        "test_ozsermaye_egrisi": _temiz(sonuc.get("test", {}).get("ozsermaye_egrisi", [])),
    }
    with open(os.path.join(SONUC_DIZINI, "walk_forward.json"), "w", encoding="utf-8") as dosya:
        json.dump(kayit, dosya, ensure_ascii=False, indent=1)

    # 2) Test dönemi işlemleri — elle inceleme için CSV
    islemler = sonuc.get("test", {}).get("islemler", [])
    if islemler:
        alanlar = sorted({anahtar for islem in islemler for anahtar in islem.keys()})
        yol = os.path.join(SONUC_DIZINI, "islemler_test.csv")
        with open(yol, "w", encoding="utf-8-sig", newline="") as dosya:
            yazici = csv.DictWriter(dosya, fieldnames=alanlar, extrasaction="ignore")
            yazici.writeheader()
            for islem in islemler:
                yazici.writerow({k: _temiz(v) for k, v in islem.items()})

    # 3) İnsan özeti
    ozet = _ozet_yaz(sonuc, argumanlar.ozsermaye)
    with open(os.path.join(SONUC_DIZINI, "ozet.md"), "w", encoding="utf-8") as dosya:
        dosya.write(ozet)

    print()
    print(ozet)

    # NEDEN 0 dönüyoruz: kriterler geçmese bile backtest'in KENDİSİ başarılıdır.
    # "Strateji yetersiz" bir hata değil, geçerli ve değerli bir sonuçtur.
    return 0


if __name__ == "__main__":
    sys.exit(main())
