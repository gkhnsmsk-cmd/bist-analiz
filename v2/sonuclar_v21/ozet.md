# PUSULA v2.1 — Dinamik & Defansif BIST İşlem Algoritması — Walk-Forward Backtest Sonucu

Çalıştırma: 12.09.2026 09:02 UTC · Başlangıç özsermayesi: 1,000,000 TL

---

## AGRESİF REVİZYON (kullanıcı talebi, 2026-09-12): "yüksek risk olsun, yeter ki para kazansın"

Bu koşum artık şartnamenin BİREBİR uygulaması DEĞİL. Birebir uygulama çok düşük piyasa maruziyeti üretti (test döneminde 32 aydan yalnızca 11'inde pozisyon vardı) ve CAGR risksiz faizin altında kaldı. Kullanıcının açık talimatıyla aşağıdaki noktalarda şartname sınırlarının DIŞINA çıkıldı:
- **§2 Rejim**: giriş tamponu/teyidi gevşetildi (kolay gir), çıkış tetiği MA200'ün %5 altına çekildi (zor çık), MA50>MA200 şartı kaldırıldı, Risk-On/Risk-Off hedef hisse oranları %95/%40'a yükseltildi (eskiden %70/%20).
- **§3.B Seçim**: getiri20 aralığı -%10..+%60'a genişletildi, CMF eşiği >-0.05'e, hacim teyidi >=%80'e gevşetildi, MA50>MA200 şartı kaldırıldı.
- **§5/§6 Pozisyon**: işlem riski %1.5->%3.0, tek hisse tavanı %15->%25, sektör tavanı %30->%45, sert stop 2.0->2.5xATR, Hedef1 3.0->4.0xATR, zaman stopu 25->40 gün.
- **§7 Kilidi**: artık yeni alımları ENGELLEMİYOR, yalnız bilgi amaçlı raporlanıyor.

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
| **CAGR** | **%3.13** | %26.87 | %40.00 |
| **Maksimum düşüş** | **%-35.9** | %-22.9 | %0.0 (varsayım) |
| İşlem sayısı (giriş+kısmi+tam çıkış satırları) | 847 | — (tek alım) | — |
| Kazanma oranı | %41.8 | — | — |
| Profit factor | 1.02 | — | — |
| Expectancy (R) | 0.289 | — | — |
| Ortalama tutma (gün) | 18.1 | — | — |
| Aylık getiri, risksiz ALTINDA kalan ay | 20/32 | — | — |
| §7: kilit aktif olsaydı engellenecek hafta sayısı (BİLGİ AMAÇLI — artık fiilen engellemiyor) | 31 | — | — |

### Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı

| Metrik | v2.1 (Dinamik & Defansif) | BIST100 al-ve-tut | Risksiz faiz varsayımı (%40/yıl) |
|---|---|---|---|
| **CAGR** | **%42.43** | %53.23 | %40.00 |
| **Maksimum düşüş** | **%-31.3** | %-31.8 | %0.0 (varsayım) |
| İşlem sayısı (giriş+kısmi+tam çıkış satırları) | 1356 | — (tek alım) | — |
| Kazanma oranı | %57.2 | — | — |
| Profit factor | 1.84 | — | — |
| Expectancy (R) | 0.751 | — | — |
| Ortalama tutma (gün) | 20.2 | — | — |
| Aylık getiri, risksiz ALTINDA kalan ay | 30/58 | — | — |
| §7: kilit aktif olsaydı engellenecek hafta sayısı (BİLGİ AMAÇLI — artık fiilen engellemiyor) | 52 | — | — |

### Test döneminde en kötü tek işlem

- Sembol: SKBNK, Sonuç: -5.91R, Net PnL: -123,449 TL, Çıkış nedeni: sert_stop

---

## Bilinen sınırlar (dürüstlük notu)

- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor; geçmişte borsadan çıkmış/endeksten düşmüş hisseler yok. Sonuçları olduğundan **iyi** gösterme eğilimindedir (hem v2.1 hem al-tut kıyası için geçerli).
- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans limit verisi değil (v2/backtest.py ile AYNI proxy).
- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor.
- **YORUM KARARLARI** (şartnamenin formül vermediği yerlerde, kod içinde 'YORUM KARARI' etiketiyle belgelenmiştir): §6 sert stop/hedef1 formüllerinde ATR14'ün GÜNCEL (dinamik, sabit-giriş-günü değil) değeri kullanıldı; ikinci dilim tetiği 'kapanış > MA20 VE kapanış > ilk dilim gününün Yüksek'i' olarak yorumlandı; 'CMF kalıcı negatif' 5 ardışık gün olarak sayısallaştırıldı; Risk-On/Risk-Off arası sticky (histerezis) bir durum makinesi kuruldu.
- **Risk-Off'ta 'kademeli küçültme'**, portföy seviyesinde bir ZORLA-KAPAMA mekanizması OLARAK uygulanmadı — yalnız YENİ ALIMLAR durduruldu; mevcut pozisyonlar yine §6'daki 5 kurala göre (sert stop/MA50/CMF/iz süren stop/zaman stopu) yönetilmeye devam eder, bu da zamanla nakit oranını organik biçimde yükseltir.
- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.
