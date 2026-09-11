# PUSULA v2.1 — Dinamik & Defansif BIST İşlem Algoritması — Walk-Forward Backtest Sonucu

Çalıştırma: 11.09.2026 23:11 UTC · Başlangıç özsermayesi: 1,000,000 TL

---

## Şartname uygulaması — atlanan/veri-yok kısımlar

- **§2 Makro teyit** (mevduat faizi yatay/düşüş) — VERİ YOK, atlandı; yalnız teknik koşullarla (MA200 %2 tamponu + MA50>MA200) karar verildi.
- **§3.A Temel Sağlık Filtresi** (Cari Oran>1.2, Net Borç/FAVÖK<3.5) — VERİ YOK (KAP API erişilemiyor), sert eleme yapılmadı.
- **§3.C Kurumsal/TEFAS fon payı artışı** — VERİ YOK, skor artırıcı olarak değerlendirilmedi (yalnız RS pozitifliği skoru etkiliyor).

---

## SİSTEM BIST100'Ü CAGR'DA YENEMEDİ

Test döneminde (dokunulmamış) v2.1'in CAGR'ı BIST100 al-ve-tut'un altında kaldı.

**Ayrıca test döneminde v2.1'in CAGR'ı, şartnamedeki risksiz faiz varsayımının (%40/yıl sabit) ALTINDA kaldı.**

### TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir

| Metrik | v2.1 (Dinamik & Defansif) | BIST100 al-ve-tut | Risksiz faiz varsayımı (%40/yıl) |
|---|---|---|---|
| **CAGR** | **%8.34** | %26.66 | %40.00 |
| **Maksimum düşüş** | **%-7.3** | %-22.9 | %0.0 (varsayım) |
| İşlem sayısı (giriş+kısmi+tam çıkış satırları) | 64 | — (tek alım) | — |
| Kazanma oranı | %56.2 | — | — |
| Profit factor | 2.72 | — | — |
| Expectancy (R) | 0.590 | — | — |
| Ortalama tutma (gün) | 17.1 | — | — |
| Aylık getiri, risksiz ALTINDA kalan ay | 28/32 | — | — |
| §7: yeni alım engellenen ay sayısı (3 ay üst üste risksiz altı) | 92 | — | — |

### Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı

| Metrik | v2.1 (Dinamik & Defansif) | BIST100 al-ve-tut | Risksiz faiz varsayımı (%40/yıl) |
|---|---|---|---|
| **CAGR** | **%0.00** | %53.23 | %40.00 |
| **Maksimum düşüş** | **%0.0** | %-31.8 | %0.0 (varsayım) |
| İşlem sayısı (giriş+kısmi+tam çıkış satırları) | 0 | — (tek alım) | — |
| Kazanma oranı | — | — | — |
| Profit factor | — | — | — |
| Expectancy (R) | — | — | — |
| Ortalama tutma (gün) | — | — | — |
| Aylık getiri, risksiz ALTINDA kalan ay | 59/59 | — | — |
| §7: yeni alım engellenen ay sayısı (3 ay üst üste risksiz altı) | 233 | — | — |

### Test döneminde en kötü tek işlem

- Sembol: GWIND, Sonuç: -1.25R, Net PnL: -8,419 TL, Çıkış nedeni: sert_stop

---

## Bilinen sınırlar (dürüstlük notu)

- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor; geçmişte borsadan çıkmış/endeksten düşmüş hisseler yok. Sonuçları olduğundan **iyi** gösterme eğilimindedir (hem v2.1 hem al-tut kıyası için geçerli).
- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans limit verisi değil (v2/backtest.py ile AYNI proxy).
- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor.
- **YORUM KARARLARI** (şartnamenin formül vermediği yerlerde, kod içinde 'YORUM KARARI' etiketiyle belgelenmiştir): §6 sert stop/hedef1 formüllerinde ATR14'ün GÜNCEL (dinamik, sabit-giriş-günü değil) değeri kullanıldı; ikinci dilim tetiği 'kapanış > MA20 VE kapanış > ilk dilim gününün Yüksek'i' olarak yorumlandı; 'CMF kalıcı negatif' 5 ardışık gün olarak sayısallaştırıldı; Risk-On/Risk-Off arası sticky (histerezis) bir durum makinesi kuruldu.
- **Risk-Off'ta 'kademeli küçültme'**, portföy seviyesinde bir ZORLA-KAPAMA mekanizması OLARAK uygulanmadı — yalnız YENİ ALIMLAR durduruldu; mevcut pozisyonlar yine §6'daki 5 kurala göre (sert stop/MA50/CMF/iz süren stop/zaman stopu) yönetilmeye devam eder, bu da zamanla nakit oranını organik biçimde yükseltir.
- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.
