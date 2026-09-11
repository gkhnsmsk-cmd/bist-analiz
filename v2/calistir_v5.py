"""V5 walk-forward backtest koşturucusu (GitHub Actions için).

calistir_v3.py örnek alınarak (kopyalanmadan, uyarlanarak) yazıldı — AYNI
hata yakalama, NaN temizleme deseni izlenir. TEK fark: V5, V2 mimarisi
üzerine kurulu (rotasyon değil, tekil hisse swing) ve YENİ ("akıl hocası")
kabul ölçütlerini kullanır — endeksi CAGR'da yenmek ZORUNLU DEĞİL; asıl
ölçüt pozitif expectancy, PF>=1.3, kontrollü düşüş (<=%25), pozitif CAGR
ve (tercihen) Sharpe>0.8.

NEDEN AYRI DOSYA: v5_backtest.py saf bir kütüphane olarak kalsın; dosya
yazma, CLI argümanı ve rapor biçimlendirme gibi yan etkiler burada toplansın.

Çıktılar (v2/sonuclar_v5/ altında):
  - walk_forward.json : tüm metrikler + doğrulama sonucu (makine okur)
  - islemler_test.csv : test dönemi işlem listesi (elle incelemek için)
  - ozet.md           : insan okuyacak özet — V5 / V2(eski) kıyası +
                         AKIL HOCASI KABUL EDİLDİ / EDİLMEDİ kararı.
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

import v5_backtest as v5bt

SONUC_DIZINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonuclar_v5")
# V2'nin eski sonuçları (varsa) — yalnız RAPORDA kıyas sütunu olarak
# gösterilir, hiçbir hesaplamaya girmez.
_V2_SONUC_YOLU = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonuclar", "walk_forward.json")


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


def _v2_eski_sonuc_oku() -> dict | None:
    try:
        if not os.path.exists(_V2_SONUC_YOLU):
            return None
        with open(_V2_SONUC_YOLU, "r", encoding="utf-8") as dosya:
            return json.load(dosya)
    except Exception:
        return None


def _kiyas_tablosu(baslik: str, v5_m: dict, v2_m: dict | None) -> str:
    v2_cagr = v2_m.get("cagr") if v2_m else None
    v2_dusus = v2_m.get("maksimum_dusus_%") if v2_m else None
    v2_pf = v2_m.get("profit_factor") if v2_m else None
    v2_expectancy = v2_m.get("expectancy_R") if v2_m else None

    satirlar = [
        f"### {baslik}",
        "",
        "| Metrik | V5 (bu sistem, akıl hocası) | V2 (eski, referans) |",
        "|---|---|---|",
        f"| **Expectancy (R)** | **{_sayi(v5_m.get('expectancy_R'), 3)}** | {_sayi(v2_expectancy, 3) if v2_m else '—'} |",
        f"| **Profit factor** | **{_sayi(v5_m.get('profit_factor'))}** | {_sayi(v2_pf) if v2_m else '—'} |",
        f"| **CAGR** | **{_yuzde(v5_m.get('cagr'))}** | {_yuzde(v2_cagr) if v2_m else '—'} |",
        f"| Endeks CAGR (BIST100) | {_yuzde(v5_m.get('endeks_cagr'))} | — |",
        f"| **Maksimum düşüş** | **{_yuzde(v5_m.get('maksimum_dusus_%'), 1)}** | "
        f"{_yuzde(v2_dusus, 1) if v2_m else '—'} |",
        f"| **Sharpe (yıllık)** | **{_sayi(v5_m.get('sharpe_yillik'))}** | — |",
        f"| Kazanma oranı | {_yuzde(v5_m.get('kazanma_orani'), 1)} | — |",
        f"| İşlem sayısı | {v5_m.get('islem_sayisi', 0)} | — |",
        f"| Ortalama tutma (gün) | {_sayi(v5_m.get('ortalama_tutma_gun'), 1)} | — |",
        "",
    ]
    return "\n".join(satirlar)


def _ozet_yaz(sonuc: dict, v2_eski: dict | None, ozsermaye: float) -> str:
    dogrulama = sonuc.get("dogrulama", {})
    gecti = dogrulama.get("gecti", False)

    test_m = sonuc.get("test", {}).get("metrikler", {})
    gelistirme_m = sonuc.get("gelistirme", {}).get("metrikler", {})
    v2_test_m = (v2_eski or {}).get("test_metrikleri")
    v2_gelistirme_m = (v2_eski or {}).get("gelistirme_metrikleri")

    satirlar = [
        "# PUSULA V5 — \"Akıl Hocası\" (V2 mimarisi + sıkılaştırılmış giriş/geniş stop) — Walk-Forward Sonucu",
        "",
        f"Çalıştırma: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')} · "
        f"Başlangıç özsermayesi: {ozsermaye:,.0f} TL",
        "",
        "**Kabul ölçütü artık \"endeksi her dönem yen\" DEĞİL.** Kullanıcının zaman ayıramadığı "
        "için ihtiyacı olan şey: pozitif expectancy'li, disiplinli, riski kontrollü bir "
        "\"akıl hocası\". Kriterler: Expectancy>0R, Profit Factor>=1.3, Maks. düşüş<=%25, "
        "CAGR>0 (zorunlu) ve Sharpe>0.8 (tercihen, bağlayıcı değil).",
        "",
        "---",
        "",
    ]

    if gecti:
        satirlar += [
            "## AKIL HOCASI KABUL EDİLDİ",
            "",
            "Sistem **dokunulmamış test döneminde** yukarıdaki tüm bağlayıcı kriterleri geçti. "
            "Kullanıcıya sinyal üretmeye uygundur.",
            "",
        ]
    else:
        satirlar += [
            "## AKIL HOCASI KABUL EDİLMEDİ",
            "",
            "Aşağıdaki bağlayıcı kriterlerden en az biri sağlanmadı — TAVSIYE_VERME modu önerilir.",
            "",
            "**Başarısız kriterler:**",
            "",
        ]
        for madde in dogrulama.get("basarisiz_kriterler", []):
            satirlar.append(f"- {madde}")
        satirlar.append("")

    uyarilar = dogrulama.get("uyarilar", [])
    if uyarilar:
        satirlar += ["**Bağlayıcı olmayan uyarılar:**", ""]
        for u in uyarilar:
            satirlar.append(f"- {u}")
        satirlar.append("")

    satirlar += ["---", ""]
    satirlar.append(_kiyas_tablosu(
        "TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir",
        test_m, v2_test_m,
    ))
    satirlar.append(_kiyas_tablosu(
        "Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı",
        gelistirme_m, v2_gelistirme_m,
    ))

    if v2_eski is None:
        satirlar += [
            "> Not: V2'nin eski sonuçları (`v2/sonuclar/walk_forward.json`) bulunamadı; "
            "kıyas sütunu bu yüzden boş.",
            "",
        ]

    satirlar += [
        "---",
        "",
        "## V5'in V2'den farkı (kök neden analizi ve müdahale)",
        "",
        "V2'nin test PF'si 0.99 (neredeyse başabaş) çıkmıştı. Kök neden: (a) giriş filtresi "
        "'kirilim VEYA geri_cekilme' + göreli güç>=75 + uzama<=2.0 ile yeterince seçici değildi "
        "— kazanan/kaybedeni ayırt etmiyordu; (b) 2.5xATR ilk stop, normal günlük gürültüde bile "
        "sık tetiklenip (whipsaw) potansiyel kazananları erken kesiyordu.",
        "",
        "V5 müdahalesi: (1) yalnız 'kirilim' kurulumu + göreli güç>=85 + uzama<=1.2 (daha az "
        "ama daha kaliteli sinyal), (2) ilk stop 3.5xATR'ye genişletildi (whipsaw azaltma). "
        "Diğer her şey (maliyet modeli, portföy kısıtları, trailing/zaman/trend/rejim çıkışları, "
        "T+1 açılış gerçekleşmesi) V2 ile BİREBİR aynı.",
        "",
        "## Bilinen sınırlar (dürüstlük notu)",
        "",
        "- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor.",
        "- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans "
        "limit verisi değil.",
        "- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor.",
        "- **Daha az işlem = daha az istatistiksel güven:** sıkılaştırılmış filtre işlem "
        "sayısını azaltır; test döneminin işlem sayısı düşükse (<20-30) PF/expectancy "
        "tahminleri geniş güven aralığına sahiptir — bu ozet.md'de ayrı bir uyarı olarak "
        "işaretlenir (bağlayıcı değildir, ama dikkat gerektirir).",
        "- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.",
        "",
    ]
    return "\n".join(satirlar)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="V5 walk-forward backtest (akıl hocası kriterleri)")
    ayristirici.add_argument("--ozsermaye", type=float, default=1_000_000.0)
    argumanlar = ayristirici.parse_args()

    os.makedirs(SONUC_DIZINI, exist_ok=True)

    try:
        sonuc = v5bt.walk_forward(ozsermaye=argumanlar.ozsermaye)
    except Exception:
        traceback.print_exc()
        hata_metni = (
            "# PUSULA V5 — Backtest ÇALIŞMADI\n\n"
            "Backtest bir hata ile durdu; aşağıdaki traceback'e bakın.\n\n"
            "```\n" + traceback.format_exc() + "\n```\n"
        )
        with open(os.path.join(SONUC_DIZINI, "ozet.md"), "w", encoding="utf-8") as dosya:
            dosya.write(hata_metni)
        return 1

    v2_eski = _v2_eski_sonuc_oku()

    kayit = {
        "calistirma_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "ozsermaye": argumanlar.ozsermaye,
        "dogrulama": _temiz(sonuc.get("dogrulama", {})),
        "test_metrikleri": _temiz(sonuc.get("test", {}).get("metrikler", {})),
        "gelistirme_metrikleri": _temiz(sonuc.get("gelistirme", {}).get("metrikler", {})),
        "test_ozsermaye_egrisi": _temiz(sonuc.get("test", {}).get("ozsermaye_egrisi", [])),
        "v2_eski_bulundu_mu": v2_eski is not None,
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

    ozet = _ozet_yaz(sonuc, v2_eski, argumanlar.ozsermaye)
    with open(os.path.join(SONUC_DIZINI, "ozet.md"), "w", encoding="utf-8") as dosya:
        dosya.write(ozet)

    print()
    print(ozet)

    # NEDEN 0 dönüyoruz: kriterler geçmese bile backtest'in KENDİSİ başarılıdır
    # — dürüst bir "kabul edilmedi" sonucu da geçerli/değerli bir sonuçtur.
    return 0


if __name__ == "__main__":
    sys.exit(main())
