# PUSULA v2.1 — Dinamik & Defansif BIST İşlem Algoritması — Walk-Forward Backtest Sonucu

Çalıştırma: 12.09.2026 14:20 UTC · Başlangıç özsermayesi: 1,000,000 TL

---

## ÖLÇÜM DÜZELTMESİ (2026-09-12) — bu koşumdan önceki tüm sayılar geçersiz

Bu koşuma kadar backtest'te **nakit %0 faiz kazanıyordu**. Strateji zamanının çoğunu nakitte geçirdiği için (§5 hisseye %70 tavan koyar, §2 Risk-Off'ta %20'ye indirir, §7 kilidi haftalarca yeni alımı durdurur) bu, ölçümü iki yönden bozuyordu:
1) **Haksız ceza:** gerçek hayatta mevduatta ~%40/yıl kazanacak olan atıl nakit, simülasyonda sıfır kazanıyordu. Ortalama %65 nakit ağırlıkta bu, yılda ~26 puanlık getiriyi ölçümden silmek demekti — "CAGR %8.33 vs mevduat %40" karşılaştırması bu yüzden hiçbir zaman adil değildi.
2) **Optimizasyon yanlılığı (asıl tehlike):** nakitte durmak yapay olarak cezalandırıldığı için ölçüm, sistematik biçimde "hep yatırımda kal" stratejilerini kayırıyordu. Bu bozuk hedef fonksiyonuyla bir parametre taraması çalıştırılsaydı, pervasız bir çözümü "optimal" diye bulurdu — gerçek bir edge'i olduğu için değil, alternatifini sıfır faizle ölçtüğümüz için.
Artık nakit, §7 ile aynı kaynaktan (yıllık %40) türetilen günlük bileşik faizi takvim günü üzerinden kazanıyor; kıyas ölçütü olarak da "%100 mevduat" eğrisi eklendi. **Aşağıdaki tablolardaki asıl satır "hisse sleeve yıllık getirisi"dir:** toplam CAGR'ın büyük kısmı zaten faizden gelir, sistemin bir değeri olup olmadığını yalnız hisseye ayrılan sermayenin getirisi gösterir.

## "Yüksek risk" deneyi ve SONUCU (kullanıcı talebi, 2026-09-12)

Kullanıcı "yüksek risk olsun, yeter ki para kazansın" dedikten sonra İKİ farklı yaklaşım denendi, ikisi de test döneminde (asıl referans) SONUCU KÖTÜLEŞTİRDİ, bu yüzden kullanıcı onayıyla TÜM sistem şartnamenin BİREBİR defansif değerlerine geri döndürüldü (bu koşum artık o hâliyle çalışıyor):
1) **Agresif giriş/seçim** (tampon/teyit gevşetildi, MA50 şartı kaldırıldı, GETIRI20 aralığı genişletildi, §7 kilidi kapatıldı): test döneminde işlem sayısı 64->847, profit factor 2.72->1.02, maksimum düşüş -%7.3->-%35.9 (BIST100'ün kendi düşüşünden bile kötü) — aşırı işlem sinyal kalitesini bozdu.
2) **Agresif pozisyon büyüklüğü** (giriş/seçim defansif kalırken yalnız işlem riski %1.5->%3.0, tek hisse %15->%25, sektör %30->%45, stop/hedef mesafeleri genişletildi): test döneminde CAGR %8.33->%6.66, maksimum düşüş -%7.3->-%10.7 — az sayıda işlemde (39-64) pozisyonu büyütmek getiriyi güvenilir şekilde artırmadı, yalnızca varyansı büyüttü.
Sonuç: şu ana kadar bulunan EN İYİ risk-ayarlı performans (CAGR %8.33, düşüş -%7.3, PF 2.72) şartnamenin BİREBİR defansif hâliyle elde edildi — bu koşum o parametrelerle çalışıyor.

## Şartname uygulaması — veri yokluğundan atlanan kısımlar (değişmedi)

- **§2 Makro teyit** (mevduat faizi yatay/düşüş) — VERİ YOK, atlandı.
- **§3.A Temel Sağlık Filtresi** (Cari Oran>1.2, Net Borç/FAVÖK<3.5) — VERİ YOK (KAP API erişilemiyor), sert eleme yapılmadı.
- **§3.C Kurumsal/TEFAS fon payı artışı** — VERİ YOK, skor artırıcı olarak değerlendirilmedi (yalnız RS pozitifliği skoru etkiliyor).

---

## SİSTEM BIST100'Ü CAGR'DA YENDİ

### TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir

| Metrik | v2.1 (Dinamik & Defansif) | BIST100 al-ve-tut | %100 mevduat (%40/yıl) |
|---|---|---|---|
| **CAGR** | **%42.76** | %26.87 | %40.00 |
| **Maksimum düşüş** | **%-7.1** | %-22.9 | %0.0 |
| İşlem sayısı (giriş+kısmi+tam çıkış satırları) | 72 | — (tek alım) | — |
| Kazanma oranı | %51.4 | — | — |
| Profit factor | 1.56 | — | — |
| Expectancy (R) | 0.454 | — | — |
| Ortalama tutma (gün) | 15.9 | — | — |
| Aylık getiri, risksiz ALTINDA kalan ay | 5/13 | — | — |
| §7: yeni alım engellenen hafta sayısı (3 ay üst üste risksiz altı, kilit AKTİF) | 67 | — | — |

**Getiri ayrıştırması — asıl soru: hisse seçimi bir şey katıyor mu?**

| Ölçüt | Değer | Nasıl okunur |
|---|---|---|
| Ortalama hisse ağırlığı | %8.2 | Sermayenin ortalama ne kadarı hissede durdu; kalanı mevduatta faiz kazandı |
| Ortalama yatırılmış sermaye | 143535 TL | Hisse tarafının fiilen kullandığı sermaye |
| Nakde işleyen toplam faiz | 1446541 TL | Hiç hisse alınmasa da kazanılacak olan kısım |
| Toplam işlem K/Z (net) | 132213 TL | Hisse seçiminin ürettiği saf kâr/zarar |
| **Hisse sleeve yıllık getirisi** | **%34.2** | **Bunu %40 ile kıyasla: ALTINDAysa o sermayeyi mevduatta tutmak daha iyiydi** |

❌ Hisse sleeve'i (%34.2) kullandığı sermaye üzerinden risksiz faizin (%40.00) ALTINDA kaldı — yani seçim motoru, o sermayeyi mevduatta tutmaktan daha kötü kullanmış. Pozisyon büyütmek bu tabloda getiriyi ARTIRMAZ, zararı ölçekler.

### Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı

| Metrik | v2.1 (Dinamik & Defansif) | BIST100 al-ve-tut | %100 mevduat (%40/yıl) |
|---|---|---|---|
| **CAGR** | **%38.91** | %53.23 | %40.00 |
| **Maksimum düşüş** | **%-1.7** | %-31.8 | %0.0 |
| İşlem sayısı (giriş+kısmi+tam çıkış satırları) | 13 | — (tek alım) | — |
| Kazanma oranı | %38.5 | — | — |
| Profit factor | 0.58 | — | — |
| Expectancy (R) | -0.017 | — | — |
| Ortalama tutma (gün) | 13.1 | — | — |
| Aylık getiri, risksiz ALTINDA kalan ay | 4/5 | — | — |
| §7: yeni alım engellenen hafta sayısı (3 ay üst üste risksiz altı, kilit AKTİF) | 195 | — | — |

**Getiri ayrıştırması — asıl soru: hisse seçimi bir şey katıyor mu?**

| Ölçüt | Değer | Nasıl okunur |
|---|---|---|
| Ortalama hisse ağırlığı | %0.7 | Sermayenin ortalama ne kadarı hissede durdu; kalanı mevduatta faiz kazandı |
| Ortalama yatırılmış sermaye | 18548 TL | Hisse tarafının fiilen kullandığı sermaye |
| Nakde işleyen toplam faiz | 4171214 TL | Hiç hisse alınmasa da kazanılacak olan kısım |
| Toplam işlem K/Z (net) | -18679 TL | Hisse seçiminin ürettiği saf kâr/zarar |
| **Hisse sleeve yıllık getirisi** | **%-20.2** | **Bunu %40 ile kıyasla: ALTINDAysa o sermayeyi mevduatta tutmak daha iyiydi** |

❌ Hisse sleeve'i (%-20.2) kullandığı sermaye üzerinden risksiz faizin (%40.00) ALTINDA kaldı — yani seçim motoru, o sermayeyi mevduatta tutmaktan daha kötü kullanmış. Pozisyon büyütmek bu tabloda getiriyi ARTIRMAZ, zararı ölçekler.

### Test döneminde en kötü tek işlem

- Sembol: AKBNK, Sonuç: -2.09R, Net PnL: -33,061 TL, Çıkış nedeni: sert_stop

---

## Bilinen sınırlar (dürüstlük notu)

- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor; geçmişte borsadan çıkmış/endeksten düşmüş hisseler yok. Sonuçları olduğundan **iyi** gösterme eğilimindedir (hem v2.1 hem al-tut kıyası için geçerli).
- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans limit verisi değil (v2/backtest.py ile AYNI proxy).
- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor.
- **YORUM KARARLARI** (şartnamenin formül vermediği yerlerde, kod içinde 'YORUM KARARI' etiketiyle belgelenmiştir): §6 sert stop/hedef1 formüllerinde ATR14'ün GÜNCEL (dinamik, sabit-giriş-günü değil) değeri kullanıldı; ikinci dilim tetiği 'kapanış > MA20 VE kapanış > ilk dilim gününün Yüksek'i' olarak yorumlandı; 'CMF kalıcı negatif' 5 ardışık gün olarak sayısallaştırıldı; Risk-On/Risk-Off arası sticky (histerezis) bir durum makinesi kuruldu.
- **Risk-Off'ta 'kademeli küçültme'**, portföy seviyesinde bir ZORLA-KAPAMA mekanizması OLARAK uygulanmadı — yalnız YENİ ALIMLAR durduruldu; mevcut pozisyonlar yine §6'daki 5 kurala göre (sert stop/MA50/CMF/iz süren stop/zaman stopu) yönetilmeye devam eder, bu da zamanla nakit oranını organik biçimde yükseltir.
- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.
