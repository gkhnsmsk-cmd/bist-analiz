"""V3 walk-forward backtest koşturucusu (GitHub Actions için).

calistir_backtest.py (V2) örnek alınarak (kopyalanmadan, uyarlanarak)
yazıldı — AYNI hata yakalama, NaN temizleme ve ozet.md biçimi izlenir.

NEDEN AYRI DOSYA: v3_backtest.py saf bir kütüphane olarak kalsın; dosya
yazma, CLI argümanı ve rapor biçimlendirme gibi yan etkiler burada toplansın.

Çıktılar (v2/sonuclar_v3/ altında):
  - walk_forward.json : tüm metrikler + doğrulama sonucu (makine okur)
  - islemler_test.csv : test dönemi işlem listesi (elle incelemek için)
  - ozet.md           : insan okuyacak özet — V3 / BIST100 al-tut / V2 (eski)
                         ÜÇ SÜTUNLU kıyas ZORUNLU (STRATEJI_V3.md §9).
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

import v3_backtest as v3bt

SONUC_DIZINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonuclar_v3")
# V2'nin eski sonuçları (varsa) — yalnız RAPORDA "üçüncü sütun" olarak
# gösterilir, hiçbir hesaplamaya girmez. Dosya yoksa/okunamazsa sessizce
# atlanır (V3'ün çalışmasını bir V2 kalıntısına bağımlı kılmamak için).
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
    """V2'nin en son walk_forward.json'ını (varsa) en iyi çaba ile okur."""
    try:
        if not os.path.exists(_V2_SONUC_YOLU):
            return None
        with open(_V2_SONUC_YOLU, "r", encoding="utf-8") as dosya:
            return json.load(dosya)
    except Exception:
        return None


def _kiyas_tablosu(baslik: str, v3_m: dict, al_tut_m: dict, v2_m: dict | None) -> str:
    """V3 / BIST100 al-tut / V2 (eski) ÜÇ sütunlu kıyas tablosu (§9)."""
    v3_cagr = v3_m.get("cagr")
    endeks_cagr = al_tut_m.get("cagr")
    v3_dusus = v3_m.get("maksimum_dusus_%")
    endeks_dusus = al_tut_m.get("maksimum_dusus_%")

    v2_cagr = v2_m.get("cagr") if v2_m else None
    v2_dusus = v2_m.get("maksimum_dusus_%") if v2_m else None
    v2_pf = v2_m.get("profit_factor") if v2_m else None

    satirlar = [
        f"### {baslik}",
        "",
        "| Metrik | V3 (bu sistem) | BIST100 al-ve-tut | V2 (eski, referans) |",
        "|---|---|---|---|",
        f"| **CAGR** | **{_yuzde(v3_cagr)}** | {_yuzde(endeks_cagr)} | {_yuzde(v2_cagr) if v2_m else '—'} |",
        f"| **Maksimum düşüş** | **{_yuzde(v3_dusus, 1)}** | {_yuzde(endeks_dusus, 1)} | "
        f"{_yuzde(v2_dusus, 1) if v2_m else '—'} |",
        f"| İşlem sayısı | {v3_m.get('islem_sayisi', 0)} | — (tek alım) | {'—' if not v2_m else '—'} |",
        f"| Kazanma oranı | {_yuzde(v3_m.get('kazanma_orani'), 1)} | — | — |",
        f"| Profit factor | {_sayi(v3_m.get('profit_factor'))} | — | {_sayi(v2_pf) if v2_m else '—'} |",
        f"| Rebalans sayısı | {v3_m.get('rebalans_sayisi', 0)} | — | — |",
        f"| Yıllık turnover | {_yuzde(v3_m.get('yillik_turnover_%'), 0)} | — | — |",
        "",
    ]
    return "\n".join(satirlar)


def _ozet_yaz(sonuc: dict, v2_eski: dict | None, ozsermaye: float) -> str:
    """§9 kabul kriterleri dahil, insan okuyacak özet raporu üretir."""
    dogrulama = sonuc.get("dogrulama", {})
    gecti = dogrulama.get("gecti", False)

    test_v3_m = sonuc.get("test", {}).get("v3", {}).get("metrikler", {})
    test_al_tut_m = sonuc.get("test", {}).get("al_tut", {}).get("metrikler", {})
    gelistirme_v3_m = sonuc.get("gelistirme", {}).get("v3", {}).get("metrikler", {})
    gelistirme_al_tut_m = sonuc.get("gelistirme", {}).get("al_tut", {}).get("metrikler", {})

    v2_test_m = (v2_eski or {}).get("test_metrikleri")
    v2_gelistirme_m = (v2_eski or {}).get("gelistirme_metrikleri")

    endeksi_yendi_mi = (
        isinstance(test_v3_m.get("endeks_ustu_fark"), (int, float))
        and not math.isnan(test_v3_m.get("endeks_ustu_fark"))
        and test_v3_m.get("endeks_ustu_fark") > 0
    )

    satirlar = [
        "# PUSULA V3 — Göreli Güç Rotasyonu — Walk-Forward Backtest Sonucu",
        "",
        f"Çalıştırma: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')} · "
        f"Başlangıç özsermayesi: {ozsermaye:,.0f} TL",
        "",
        "---",
        "",
    ]

    if not endeksi_yendi_mi:
        satirlar += [
            "## SİSTEM ENDEKSİ YENEMEDİ — TAVSIYE_VERME MODU",
            "",
            "**STRATEJI_V3.md §9 gereği: 'Endeksi yenemiyorsa sistem bunu büyük harfle "
            "yazar ve TAVSIYE_VERME modunda kalır.' Bu sistemin şu anki hâliyle kullanıcıya "
            "sinyal ÜRETMEMESİ gerekir — endeks fonu almak, bu sistemi çalıştırmaktan "
            "istatistiksel olarak daha iyi bir sonuç vermiştir.**",
            "",
        ]
    elif gecti:
        satirlar += [
            "## KABUL KRİTERLERİ GEÇİLDİ",
            "",
            "Sistem şartname §9'daki tüm eşikleri **dokunulmamış test döneminde** geçti "
            "(endeksi hem CAGR hem maksimum düşüşte yendi). Tavsiye üretmeye uygundur.",
            "",
        ]
    else:
        satirlar += [
            "## ENDEKSİ CAGR'DA YENDİ AMA DİĞER KRİTERLER EKSİK",
            "",
            "CAGR endeksin üzerinde, ama §9'daki diğer eşiklerden (maksimum düşüş/rebalans "
            "sayısı/turnover) en az biri sağlanmadı. TAVSIYE_VERME modu önerilir.",
            "",
            "**Başarısız kriterler:**",
            "",
        ]
        for madde in dogrulama.get("basarisiz_kriterler", []):
            satirlar.append(f"- {madde}")
        satirlar.append("")

    satirlar += ["---", ""]
    satirlar.append(_kiyas_tablosu(
        "TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir",
        test_v3_m, test_al_tut_m, v2_test_m,
    ))
    satirlar.append(_kiyas_tablosu(
        "Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı",
        gelistirme_v3_m, gelistirme_al_tut_m, v2_gelistirme_m,
    ))

    if v2_eski is None:
        satirlar += [
            "> Not: V2'nin eski sonuçları (`v2/sonuclar/walk_forward.json`) bulunamadı; "
            "üçüncü sütun bu yüzden boş. V2'yi önce çalıştırırsanız (calistir_backtest.py) "
            "kıyas tabloları otomatik dolar.",
            "",
        ]

    satirlar += [
        "---",
        "",
        "## Bilinen sınırlar (dürüstlük notu)",
        "",
        "- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor; "
        "geçmişte borsadan çıkmış/endeksten düşmüş hisseler yok. Bu, sonuçları olduğundan "
        "**iyi** gösterme eğilimindedir (hem V3 hem al-tut kıyası için geçerli).",
        "- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans "
        "limit verisi değil.",
        "- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor, bu da sektör "
        "yoğunlaşma kısıtını zayıflatıyor.",
        "- **Trailing/zaman/kâr-hedefi stopu YOKTUR** (bilinçli tasarım kararı, bkz. "
        "STRATEJI_V3.md §0/§6) — tek koruma felaket stopu (-%25) ve rejim kapısıdır; bu, "
        "V2'ye göre TEK İSİM riskini daha geç keser ama piyasa maruziyetini korur.",
        "- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.",
        "",
    ]
    return "\n".join(satirlar)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="V3 walk-forward backtest")
    ayristirici.add_argument("--ozsermaye", type=float, default=1_000_000.0)
    argumanlar = ayristirici.parse_args()

    os.makedirs(SONUC_DIZINI, exist_ok=True)

    try:
        sonuc = v3bt.walk_forward(ozsermaye=argumanlar.ozsermaye)
    except Exception:
        # NEDEN: Actions çıktısında ham traceback görünsün ama iş akışı da
        # kırmızıya dönsün — sessiz başarısızlık en tehlikeli sonuçtur.
        traceback.print_exc()
        hata_metni = (
            "# PUSULA V3 — Backtest ÇALIŞMADI\n\n"
            "Backtest bir hata ile durdu; aşağıdaki traceback'e bakın.\n\n"
            "```\n" + traceback.format_exc() + "\n```\n"
        )
        with open(os.path.join(SONUC_DIZINI, "ozet.md"), "w", encoding="utf-8") as dosya:
            dosya.write(hata_metni)
        return 1

    v2_eski = _v2_eski_sonuc_oku()

    # 1) Tam sonuç (özsermaye eğrileri dahil — al-tut kıyası için de gerekli,
    #    V2'den farklı olarak burada iki eğri de saklanıyor).
    kayit = {
        "calistirma_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "ozsermaye": argumanlar.ozsermaye,
        "dogrulama": _temiz(sonuc.get("dogrulama", {})),
        "test_v3_metrikleri": _temiz(sonuc.get("test", {}).get("v3", {}).get("metrikler", {})),
        "test_al_tut_metrikleri": _temiz(sonuc.get("test", {}).get("al_tut", {}).get("metrikler", {})),
        "gelistirme_v3_metrikleri": _temiz(sonuc.get("gelistirme", {}).get("v3", {}).get("metrikler", {})),
        "gelistirme_al_tut_metrikleri": _temiz(sonuc.get("gelistirme", {}).get("al_tut", {}).get("metrikler", {})),
        "test_v3_ozsermaye_egrisi": _temiz(sonuc.get("test", {}).get("v3", {}).get("ozsermaye_egrisi", [])),
        "test_al_tut_ozsermaye_egrisi": _temiz(sonuc.get("test", {}).get("al_tut", {}).get("ozsermaye_egrisi", [])),
        "v2_eski_bulundu_mu": v2_eski is not None,
    }
    with open(os.path.join(SONUC_DIZINI, "walk_forward.json"), "w", encoding="utf-8") as dosya:
        json.dump(kayit, dosya, ensure_ascii=False, indent=1)

    # 2) Test dönemi işlemleri — elle inceleme için CSV.
    islemler = sonuc.get("test", {}).get("v3", {}).get("islemler", [])
    if islemler:
        alanlar = sorted({anahtar for islem in islemler for anahtar in islem.keys()})
        yol = os.path.join(SONUC_DIZINI, "islemler_test.csv")
        with open(yol, "w", encoding="utf-8-sig", newline="") as dosya:
            yazici = csv.DictWriter(dosya, fieldnames=alanlar, extrasaction="ignore")
            yazici.writeheader()
            for islem in islemler:
                yazici.writerow({k: _temiz(v) for k, v in islem.items()})

    # 3) İnsan özeti — ÜÇ sütunlu kıyas (V3 / BIST100 al-tut / V2 eski).
    ozet = _ozet_yaz(sonuc, v2_eski, argumanlar.ozsermaye)
    with open(os.path.join(SONUC_DIZINI, "ozet.md"), "w", encoding="utf-8") as dosya:
        dosya.write(ozet)

    print()
    print(ozet)

    # NEDEN 0 dönüyoruz: kriterler geçmese bile backtest'in KENDİSİ başarılıdır.
    # "Strateji endeksi yenemedi" bir hata değil, geçerli ve değerli (ve tam
    # da §9'un amaçladığı) bir sonuçtur — TAVSIYE_VERME modu bunun için var.
    return 0


if __name__ == "__main__":
    sys.exit(main())
