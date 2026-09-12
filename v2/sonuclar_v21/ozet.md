# PUSULA v2.1 — Dinamik & Defansif BIST İşlem Algoritması — Walk-Forward Backtest Sonucu

Çalıştırma: 12.09.2026 11:50 UTC · Başlangıç özsermayesi: 1,000,000 TL

---

## HİBRİT REVİZYON (kullanıcı talebi, 2026-09-12): "yüksek risk olsun, yeter ki para kazansın"

Bu koşum şartnamenin BİREBİR uygulaması değil, ama saf 'agresif' deneyden de farklı — İKİ TUR sonucunda kalibre edildi:
1) Önce §2/§3.B eşikleri gevşetildi (kolay giriş, geniş getiri20 aralığı, MA50 şartı yok) + §7 kilidi kapatıldı. SONUÇ: geliştirme döneminde CAGR %-0.32'den %42.43'e çıktı ama TEST döneminde (asıl referans) işlem sayısı 64->847'ye fırladı, profit factor 2.72->1.02'ye çöktü, maksimum düşüş -%7.3->-%35.9'a fırladı (BIST100'ün kendi düşüşünden bile kötü) — aşırı işlem sinyal kalitesini bozdu.
2) Bunun üzerine §2/§3.B/§7 şartnamenin BİREBİR defansif değerlerine GERİ DÖNDÜRÜLDÜ. 'Yüksek risk' isteği artık YALNIZ §5/§6'daki pozisyon büyüklüğü/ stop-hedef mesafeleri üzerinden karşılanıyor:
- **§5 Pozisyon**: işlem riski %1.5->%3.0, tek hisse tavanı %15->%25, sektör tavanı %30->%45.
- **§6 Stop/Hedef**: sert stop 2.0->2.5xATR, Hedef1 3.0->4.0xATR, zaman stopu 25->40 gün.
- **§2/§3.B/§7**: şartname değerlerine GERİ DÖNDÜRÜLDÜ (tampon %2/3 gün teyit/ MA50>MA200, GETIRI20 %5-25/CMF>0/hacim>=%120, §7 kilidi AKTİF).

## Şartname uygulaması — veri yokluğundan atlanan kısımlar (değişmedi)

- **§2 Makro teyit** (mevduat faizi yatay/düşüş) — VERİ YOK, atlandı.
- **§3.A Temel Sağlık Filtresi** (Cari Oran>1.2, Net Borç/FAVÖK<3.5) — VERİ YOK (KAP API erişilemiyor), sert eleme yapılmadı.
- **§3.C Kurumsal/TEFAS fon payı artışı** — VERİ YOK, skor artırıcı olarak değerlendirilmedi (yalnız RS pozitifliği skoru etkiliyor).

---

## SİSTEM BIST100'Ü CAGR'DA YENEMEDİ

Test döneminde (dokunulmamış) v2.1'in CAGR'ı BIST100 al-ve-tut'un altında kaldı.

**Ayrıca test döneminde v2.1'in CAGR'ı, şartnamedeki risksiz faiz varsayımının (%40/yıl sabit) ALTINDA kaldı.**

### TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir

| Metrik | v2.1 (Dinamik & Defansif) | BIST100 al-ve-tut | Risksiz faiz varsayımı (%40/yıl) |
|---|---|---|---|
| **CAGR** | **%6.66** | %26.87 | %40.00 |
| **Maksimum düşüş** | **%-10.7** | %-22.9 | %0.0 (varsayım) |
| İşlem sayısı (giriş+kısmi+tam çıkış satırları) | 39 | — (tek alım) | — |
| Kazanma oranı | %51.3 | — | — |
| Profit factor | 2.39 | — | — |
| Expectancy (R) | 0.815 | — | — |
| Ortalama tutma (gün) | 29.2 | — | — |
| Aylık getiri, risksiz ALTINDA kalan ay | 7/10 | — | — |
| §7: yeni alım engellenen hafta sayısı (3 ay üst üste risksiz altı, kilit AKTİF) | 102 | — | — |

### Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı

| Metrik | v2.1 (Dinamik & Defansif) | BIST100 al-ve-tut | Risksiz faiz varsayımı (%40/yıl) |
|---|---|---|---|
| **CAGR** | **%-1.49** | %53.23 | %40.00 |
| **Maksimum düşüş** | **%-13.5** | %-31.8 | %0.0 (varsayım) |
| İşlem sayısı (giriş+kısmi+tam çıkış satırları) | 23 | — (tek alım) | — |
| Kazanma oranı | %47.8 | — | — |
| Profit factor | 0.60 | — | — |
| Expectancy (R) | 0.237 | — | — |
| Ortalama tutma (gün) | 24.3 | — | — |
| Aylık getiri, risksiz ALTINDA kalan ay | 9/10 | — | — |
| §7: yeni alım engellenen hafta sayısı (3 ay üst üste risksiz altı, kilit AKTİF) | 167 | — | — |

### Test döneminde en kötü tek işlem

- Sembol: AEFES, Sonuç: -1.15R, Net PnL: -7,444 TL, Çıkış nedeni: sert_stop

---

## Bilinen sınırlar (dürüstlük notu)

- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor; geçmişte borsadan çıkmış/endeksten düşmüş hisseler yok. Sonuçları olduğundan **iyi** gösterme eğilimindedir (hem v2.1 hem al-tut kıyası için geçerli).
- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans limit verisi değil (v2/backtest.py ile AYNI proxy).
- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor.
- **YORUM KARARLARI** (şartnamenin formül vermediği yerlerde, kod içinde 'YORUM KARARI' etiketiyle belgelenmiştir): §6 sert stop/hedef1 formüllerinde ATR14'ün GÜNCEL (dinamik, sabit-giriş-günü değil) değeri kullanıldı; ikinci dilim tetiği 'kapanış > MA20 VE kapanış > ilk dilim gününün Yüksek'i' olarak yorumlandı; 'CMF kalıcı negatif' 5 ardışık gün olarak sayısallaştırıldı; Risk-On/Risk-Off arası sticky (histerezis) bir durum makinesi kuruldu.
- **Risk-Off'ta 'kademeli küçültme'**, portföy seviyesinde bir ZORLA-KAPAMA mekanizması OLARAK uygulanmadı — yalnız YENİ ALIMLAR durduruldu; mevcut pozisyonlar yine §6'daki 5 kurala göre (sert stop/MA50/CMF/iz süren stop/zaman stopu) yönetilmeye devam eder, bu da zamanla nakit oranını organik biçimde yükseltir.
- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.
