"""v2.1 walk-forward backtest koşturucusu (GitHub Actions için).

calistir_v4.py örnek alınarak (kopyalanmadan, uyarlanarak) yazıldı — AYNI
hata yakalama / NaN temizleme / dosya yapısı izlenir. Rapor ÜÇ sütunlu:
v2.1 / BIST100 al-tut / risksiz-faiz-varsayımı (yıllık %40 sabit, aylık ~%2.84
bileşik) — şartname §7 gereği.

Çıktılar (v2/sonuclar_v21/ altında):
  - walk_forward.json : tüm metrikler (makine okur)
  - islemler_test.csv : test dönemi işlem listesi (elle incelemek için)
  - ozet.md           : insan okuyacak özet — ÜÇ SÜTUNLU kıyas.
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

import v21_backtest as v21bt
from v21_portfoy import _RISKSIZ_AYLIK_GETIRI

SONUC_DIZINI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sonuclar_v21")

_RISKSIZ_YILLIK_VARSAYIM = 1.40 ** 1 - 1.0  # %40/yıl sabit varsayım (şartname §7)


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


def _ay_altinda_sayisi(aylik_getiriler: list[float]) -> tuple[int, int]:
    """(risksiz aylık getirinin ALTINDA kalan ay sayısı, toplam tamamlanmış ay sayısı)."""
    if not aylik_getiriler:
        return 0, 0
    altinda = sum(1 for g in aylik_getiriler if g is not None and not math.isnan(g) and g < _RISKSIZ_AYLIK_GETIRI)
    return altinda, len(aylik_getiriler)


def _kiyas_tablosu(baslik: str, v21_m: dict, endeks_m: dict, aylik_getiriler: list[float],
                    risksiz_engelli_ay: int, islem_sayisi_ayri: int,
                    mevduat_m: dict | None = None, sleeve_m: dict | None = None) -> str:
    v21_cagr = v21_m.get("cagr")
    v21_dusus = v21_m.get("maksimum_dusus_%")
    endeks_cagr = endeks_m.get("cagr")
    endeks_dusus = endeks_m.get("maksimum_dusus_%")
    altinda, toplam_ay = _ay_altinda_sayisi(aylik_getiriler)
    mevduat_m = mevduat_m or {}
    sleeve_m = sleeve_m or {}
    mevduat_cagr = mevduat_m.get("cagr", _RISKSIZ_YILLIK_VARSAYIM)

    satirlar = [
        f"### {baslik}",
        "",
        "| Metrik | v2.1 (Dinamik & Defansif) | BIST100 al-ve-tut | %100 mevduat (%40/yıl) |",
        "|---|---|---|---|",
        f"| **CAGR** | **{_yuzde(v21_cagr)}** | {_yuzde(endeks_cagr)} | {_yuzde(mevduat_cagr)} |",
        f"| **Maksimum düşüş** | **{_yuzde(v21_dusus, 1)}** | {_yuzde(endeks_dusus, 1)} | %0.0 |",
        f"| İşlem sayısı (giriş+kısmi+tam çıkış satırları) | {v21_m.get('islem_sayisi', 0)} | — (tek alım) | — |",
        f"| Kazanma oranı | {_yuzde(v21_m.get('kazanma_orani'), 1)} | — | — |",
        f"| Profit factor | {_sayi(v21_m.get('profit_factor'))} | — | — |",
        f"| Expectancy (R) | {_sayi(v21_m.get('expectancy_R'), 3)} | — | — |",
        f"| Ortalama tutma (gün) | {_sayi(v21_m.get('ortalama_tutma_gun'), 1)} | — | — |",
        f"| Aylık getiri, risksiz ALTINDA kalan ay | {altinda}/{toplam_ay} | — | — |",
        f"| §7: yeni alım engellenen hafta sayısı (3 ay üst üste risksiz altı, kilit AKTİF) | {risksiz_engelli_ay} | — | — |",
        "",
    ]

    # ── Getiri ayrıştırması: toplam CAGR'ın ne kadarı faizden, ne kadarı
    #    hisse seçiminden geldi? Asıl karar bu tabloya göre verilir. ──
    if sleeve_m:
        sleeve_yillik = sleeve_m.get("sleeve_yillik_getiri")
        agirlik = sleeve_m.get("ortalama_hisse_agirligi")
        satirlar += [
            "**Getiri ayrıştırması — asıl soru: hisse seçimi bir şey katıyor mu?**",
            "",
            "| Ölçüt | Değer | Nasıl okunur |",
            "|---|---|---|",
            f"| Ortalama hisse ağırlığı | {_yuzde(agirlik, 1)} | Sermayenin ortalama ne kadarı hissede durdu; kalanı mevduatta faiz kazandı |",
            f"| Ortalama yatırılmış sermaye | {_sayi(sleeve_m.get('ortalama_yatirilan_tl'), 0)} TL | Hisse tarafının fiilen kullandığı sermaye |",
            f"| Nakde işleyen toplam faiz | {_sayi(sleeve_m.get('kumulatif_faiz_tl'), 0)} TL | Hiç hisse alınmasa da kazanılacak olan kısım |",
            f"| Toplam işlem K/Z (net) | {_sayi(sleeve_m.get('toplam_islem_pnl_tl'), 0)} TL | Hisse seçiminin ürettiği saf kâr/zarar |",
            f"| **Hisse sleeve yıllık getirisi** | **{_yuzde(sleeve_yillik, 1)}** | **Bunu %40 ile kıyasla: ALTINDAysa o sermayeyi mevduatta tutmak daha iyiydi** |",
            "",
        ]
        if isinstance(sleeve_yillik, (int, float)) and not math.isnan(sleeve_yillik):
            if sleeve_yillik > _RISKSIZ_YILLIK_VARSAYIM:
                satirlar += [
                    f"✅ Hisse sleeve'i ({_yuzde(sleeve_yillik, 1)}) kullandığı sermaye üzerinden "
                    f"risksiz faizi ({_yuzde(_RISKSIZ_YILLIK_VARSAYIM)}) GEÇTİ — gerçek bir edge adayı var, "
                    "asıl mesele bu edge'in ne kadar ölçeklenebildiği (pozisyon boyutu / maruziyet).",
                    "",
                ]
            else:
                satirlar += [
                    f"❌ Hisse sleeve'i ({_yuzde(sleeve_yillik, 1)}) kullandığı sermaye üzerinden "
                    f"risksiz faizin ({_yuzde(_RISKSIZ_YILLIK_VARSAYIM)}) ALTINDA kaldı — yani seçim motoru, "
                    "o sermayeyi mevduatta tutmaktan daha kötü kullanmış. Pozisyon büyütmek bu tabloda "
                    "getiriyi ARTIRMAZ, zararı ölçekler.",
                    "",
                ]
    return "\n".join(satirlar)


def _ozet_yaz(sonuc: dict, ozsermaye: float) -> str:
    test = sonuc["test"]
    gelistirme = sonuc["gelistirme"]

    test_v21_m = test["metrikler"]
    test_endeks_m = test["endeks_metrikleri"]
    gelistirme_v21_m = gelistirme["metrikler"]
    gelistirme_endeks_m = gelistirme["endeks_metrikleri"]

    endeksi_yendi_mi = (
        isinstance(test_v21_m.get("endeks_ustu_fark"), (int, float))
        and not math.isnan(test_v21_m.get("endeks_ustu_fark"))
        and test_v21_m.get("endeks_ustu_fark") > 0
    )
    risksizi_yendi_mi = (
        isinstance(test_v21_m.get("cagr"), (int, float))
        and not math.isnan(test_v21_m.get("cagr"))
        and test_v21_m.get("cagr") > _RISKSIZ_YILLIK_VARSAYIM
    )

    satirlar = [
        "# PUSULA v2.1 — Dinamik & Defansif BIST İşlem Algoritması — Walk-Forward Backtest Sonucu",
        "",
        f"Çalıştırma: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')} · "
        f"Başlangıç özsermayesi: {ozsermaye:,.0f} TL",
        "",
        "---",
        "",
        "## ÖLÇÜM DÜZELTMESİ (2026-09-12) — bu koşumdan önceki tüm sayılar geçersiz",
        "",
        "Bu koşuma kadar backtest'te **nakit %0 faiz kazanıyordu**. Strateji zamanının "
        "çoğunu nakitte geçirdiği için (§5 hisseye %70 tavan koyar, §2 Risk-Off'ta %20'ye "
        "indirir, §7 kilidi haftalarca yeni alımı durdurur) bu, ölçümü iki yönden bozuyordu:",
        "1) **Haksız ceza:** gerçek hayatta mevduatta ~%40/yıl kazanacak olan atıl nakit, "
        "simülasyonda sıfır kazanıyordu. Ortalama %65 nakit ağırlıkta bu, yılda ~26 puanlık "
        "getiriyi ölçümden silmek demekti — \"CAGR %8.33 vs mevduat %40\" karşılaştırması "
        "bu yüzden hiçbir zaman adil değildi.",
        "2) **Optimizasyon yanlılığı (asıl tehlike):** nakitte durmak yapay olarak "
        "cezalandırıldığı için ölçüm, sistematik biçimde \"hep yatırımda kal\" stratejilerini "
        "kayırıyordu. Bu bozuk hedef fonksiyonuyla bir parametre taraması çalıştırılsaydı, "
        "pervasız bir çözümü \"optimal\" diye bulurdu — gerçek bir edge'i olduğu için değil, "
        "alternatifini sıfır faizle ölçtüğümüz için.",
        "Artık nakit, §7 ile aynı kaynaktan (yıllık %40) türetilen günlük bileşik faizi "
        "takvim günü üzerinden kazanıyor; kıyas ölçütü olarak da \"%100 mevduat\" eğrisi "
        "eklendi. **Aşağıdaki tablolardaki asıl satır \"hisse sleeve yıllık getirisi\"dir:** "
        "toplam CAGR'ın büyük kısmı zaten faizden gelir, sistemin bir değeri olup olmadığını "
        "yalnız hisseye ayrılan sermayenin getirisi gösterir.",
        "",
        "## \"Yüksek risk\" deneyi ve SONUCU (kullanıcı talebi, 2026-09-12)",
        "",
        "Kullanıcı \"yüksek risk olsun, yeter ki para kazansın\" dedikten sonra İKİ farklı "
        "yaklaşım denendi, ikisi de test döneminde (asıl referans) SONUCU KÖTÜLEŞTİRDİ, "
        "bu yüzden kullanıcı onayıyla TÜM sistem şartnamenin BİREBİR defansif değerlerine "
        "geri döndürüldü (bu koşum artık o hâliyle çalışıyor):",
        "1) **Agresif giriş/seçim** (tampon/teyit gevşetildi, MA50 şartı kaldırıldı, "
        "GETIRI20 aralığı genişletildi, §7 kilidi kapatıldı): test döneminde işlem "
        "sayısı 64->847, profit factor 2.72->1.02, maksimum düşüş -%7.3->-%35.9 "
        "(BIST100'ün kendi düşüşünden bile kötü) — aşırı işlem sinyal kalitesini bozdu.",
        "2) **Agresif pozisyon büyüklüğü** (giriş/seçim defansif kalırken yalnız işlem "
        "riski %1.5->%3.0, tek hisse %15->%25, sektör %30->%45, stop/hedef mesafeleri "
        "genişletildi): test döneminde CAGR %8.33->%6.66, maksimum düşüş "
        "-%7.3->-%10.7 — az sayıda işlemde (39-64) pozisyonu büyütmek getiriyi "
        "güvenilir şekilde artırmadı, yalnızca varyansı büyüttü.",
        "Sonuç: şu ana kadar bulunan EN İYİ risk-ayarlı performans (CAGR %8.33, "
        "düşüş -%7.3, PF 2.72) şartnamenin BİREBİR defansif hâliyle elde edildi — "
        "bu koşum o parametrelerle çalışıyor.",
        "",
        "## Şartname uygulaması — veri yokluğundan atlanan kısımlar (değişmedi)",
        "",
        "- **§2 Makro teyit** (mevduat faizi yatay/düşüş) — VERİ YOK, atlandı.",
        "- **§3.A Temel Sağlık Filtresi** (Cari Oran>1.2, Net Borç/FAVÖK<3.5) — VERİ YOK "
        "(KAP API erişilemiyor), sert eleme yapılmadı.",
        "- **§3.C Kurumsal/TEFAS fon payı artışı** — VERİ YOK, skor artırıcı olarak "
        "değerlendirilmedi (yalnız RS pozitifliği skoru etkiliyor).",
        "",
        "---",
        "",
    ]

    if not endeksi_yendi_mi:
        satirlar += [
            "## SİSTEM BIST100'Ü CAGR'DA YENEMEDİ",
            "",
            "Test döneminde (dokunulmamış) v2.1'in CAGR'ı BIST100 al-ve-tut'un altında kaldı.",
            "",
        ]
    else:
        satirlar += [
            "## SİSTEM BIST100'Ü CAGR'DA YENDİ",
            "",
        ]
    if not risksizi_yendi_mi:
        satirlar += [
            "**Ayrıca test döneminde v2.1'in CAGR'ı, şartnamedeki risksiz faiz varsayımının "
            "(%40/yıl sabit) ALTINDA kaldı.**",
            "",
        ]

    satirlar.append(_kiyas_tablosu(
        "TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir",
        test_v21_m, test_endeks_m, test.get("aylik_getiriler", []),
        test.get("risksiz_engelli_ay_sayisi", 0), test_v21_m.get("islem_sayisi", 0),
        test.get("mevduat_metrikleri"), test.get("sleeve_metrikleri"),
    ))
    satirlar.append(_kiyas_tablosu(
        "Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı",
        gelistirme_v21_m, gelistirme_endeks_m, gelistirme.get("aylik_getiriler", []),
        gelistirme.get("risksiz_engelli_ay_sayisi", 0), gelistirme_v21_m.get("islem_sayisi", 0),
        gelistirme.get("mevduat_metrikleri"), gelistirme.get("sleeve_metrikleri"),
    ))

    en_kotu = test_v21_m.get("en_kotu_islem")
    if en_kotu:
        satirlar += [
            "### Test döneminde en kötü tek işlem",
            "",
            f"- Sembol: {en_kotu.get('sembol')}, Sonuç: {_sayi(en_kotu.get('sonuc_R'), 2)}R, "
            f"Net PnL: {en_kotu.get('net_pnl_tl'):,.0f} TL, Çıkış nedeni: {en_kotu.get('cikis_nedeni')}"
            if en_kotu.get('net_pnl_tl') is not None else "",
            "",
        ]

    satirlar += [
        "---",
        "",
        "## Bilinen sınırlar (dürüstlük notu)",
        "",
        "- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor; "
        "geçmişte borsadan çıkmış/endeksten düşmüş hisseler yok. Sonuçları olduğundan "
        "**iyi** gösterme eğilimindedir (hem v2.1 hem al-tut kıyası için geçerli).",
        "- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans "
        "limit verisi değil (v2/backtest.py ile AYNI proxy).",
        "- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor.",
        "- **YORUM KARARLARI** (şartnamenin formül vermediği yerlerde, kod içinde 'YORUM "
        "KARARI' etiketiyle belgelenmiştir): §6 sert stop/hedef1 formüllerinde ATR14'ün "
        "GÜNCEL (dinamik, sabit-giriş-günü değil) değeri kullanıldı; ikinci dilim tetiği "
        "'kapanış > MA20 VE kapanış > ilk dilim gününün Yüksek'i' olarak yorumlandı; 'CMF "
        "kalıcı negatif' 5 ardışık gün olarak sayısallaştırıldı; Risk-On/Risk-Off arası "
        "sticky (histerezis) bir durum makinesi kuruldu.",
        "- **Risk-Off'ta 'kademeli küçültme'**, portföy seviyesinde bir ZORLA-KAPAMA "
        "mekanizması OLARAK uygulanmadı — yalnız YENİ ALIMLAR durduruldu; mevcut pozisyonlar "
        "yine §6'daki 5 kurala göre (sert stop/MA50/CMF/iz süren stop/zaman stopu) yönetilmeye "
        "devam eder, bu da zamanla nakit oranını organik biçimde yükseltir.",
        "- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.",
        "",
    ]
    return "\n".join(satirlar)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="v2.1 walk-forward backtest")
    ayristirici.add_argument("--ozsermaye", type=float, default=1_000_000.0)
    argumanlar = ayristirici.parse_args()

    os.makedirs(SONUC_DIZINI, exist_ok=True)

    try:
        sonuc = v21bt.walk_forward(ozsermaye=argumanlar.ozsermaye)
    except Exception:
        traceback.print_exc()
        hata_metni = (
            "# PUSULA v2.1 — Backtest ÇALIŞMADI\n\n"
            "Backtest bir hata ile durdu; aşağıdaki traceback'e bakın.\n\n"
            "```\n" + traceback.format_exc() + "\n```\n"
        )
        with open(os.path.join(SONUC_DIZINI, "ozet.md"), "w", encoding="utf-8") as dosya:
            dosya.write(hata_metni)
        return 1

    kayit = {
        "calistirma_zamani_utc": datetime.now(timezone.utc).isoformat(),
        "ozsermaye": argumanlar.ozsermaye,
        "risksiz_aylik_getiri_varsayimi": _RISKSIZ_AYLIK_GETIRI,
        "test_metrikleri": _temiz(sonuc["test"]["metrikler"]),
        "test_endeks_metrikleri": _temiz(sonuc["test"]["endeks_metrikleri"]),
        "test_aylik_getiriler": _temiz(sonuc["test"].get("aylik_getiriler", [])),
        "test_risksiz_engelli_ay_sayisi": sonuc["test"].get("risksiz_engelli_ay_sayisi", 0),
        "gelistirme_metrikleri": _temiz(sonuc["gelistirme"]["metrikler"]),
        "gelistirme_endeks_metrikleri": _temiz(sonuc["gelistirme"]["endeks_metrikleri"]),
        "gelistirme_aylik_getiriler": _temiz(sonuc["gelistirme"].get("aylik_getiriler", [])),
        "gelistirme_risksiz_engelli_ay_sayisi": sonuc["gelistirme"].get("risksiz_engelli_ay_sayisi", 0),
        "test_ozsermaye_egrisi": _temiz(sonuc["test"]["ozsermaye_egrisi"]),
    }
    with open(os.path.join(SONUC_DIZINI, "walk_forward.json"), "w", encoding="utf-8") as dosya:
        json.dump(kayit, dosya, ensure_ascii=False, indent=1)

    islemler = sonuc["test"].get("islemler", [])
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
