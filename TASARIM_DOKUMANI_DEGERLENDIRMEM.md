# Teknik Tasarım Dokümanı — Değerlendirmem

Doküman: `borsa_akilli_analiz_ve_ml_teknik_tasarim.md`
Değerlendiren: Claude · 15.08.2026
Yöntem: Doküman, mevcut kod tabanı ve gerçek kayıt dosyaları karşılaştırılarak
incelendi. İddialar mümkün olduğunca ölçüldü, varsayımla yetinilmedi.

---

## Özet yargı

Doküman **profesyonel seviyede** ve amatör bir "borsa botu" planından çok daha
olgun. Özellikle şu maddeler ciddi finansal mühendislik bilgisi gösteriyor:
challenger/rollback, walk-forward, veri sızıntısı koruması, NO TRADE kararı,
execution'ın ML'den ayrılması.

Ancak dokümanın **planlama varsayımlarında üç kritik hata** var. Bunlar
düzeltilmezse proje, teknik olarak doğru ama pratikte tamamlanamayan bir
belgeye dönüşür.

---

# BÖLÜM 1 — Doğru ve değerli bulduklarım

## 1.1. §2.1 teşhisi bağımsız olarak doğrulandı ✅

Doküman "yükselen hisse ile yükselebilecek hisse karışıyor" diyor. Ben bunu
dokümandan bağımsız olarak ölçtüm ve **birebir doğru** çıktı:

| Tavsiye anındaki geçmiş getiri | Son 1 ay | Son 3 ay |
|---|---|---|
| Ortalama | +%19,7 | +%36,7 |
| Zaten pozitif olanlar | **%91** | %89 |
| Zaten %50+ yükselmiş | %8 | **%24** |

Kod tarafında sebebi de buldum: `orta_vade()` fonksiyonundaki **8 pozitif
kuralın 8'i de** trend takibi. Ortalamaya dönüş lehine tek pozitif puan yok.
Ayrıca hiçbir yerde **aşırı uzama (overextension) cezası yok** — MA50'nin %2
üstündeki hisseyle %33 üstündeki hisse aynı puanı alıyor.

Sentetik testle kanıtladım:

| | Sağlıklı yükseliş | Parabolik şişmiş |
|---|---|---|
| MA50'den uzaklık | +%8,3 | +%32,6 |
| **Genel puan** | 70,0 | **71,5** ⬆ |
| Risk motoru | "risk yok" | **"risk yok"** |

**Sonuç:** §2.1, §4 ve §48-2 ("güçlü hisse ile iyi giriş aynı şey değildir")
maddeleri yalnızca doğru değil, **ölçülmüş** bir problemi tarif ediyor.

## 1.2. §25 (Tahmin ↔ Karar ayrımı) — dokümanın en değerli fikri

"Hisse yükselebilir" ile "şu anda bu hisseyi almak mantıklı" ayrımı, tüm
dokümanın en önemli cümlesi. Mevcut yazılımın tek bir 0-100 skoru bu iki soruyu
birbirine karıştırıyor. Bu ayrım tek başına uygulanırsa bile sistem belirgin
şekilde iyileşir.

## 1.3. §46 önceliklendirmesi doğru — ve haklılığı kanıtlandı

"Önce execution güvenilirliği, sonra ML" ilkesi kesinlikle doğru. Bu oturumda
tam da bu kategoriden **iki gerçek hata** buldum:

1. Sanal portföyde fiyatı çözülemeyen pozisyonlar **sessizce 0 TL** sayılıyordu
   → portföy %42 zarar etmiş görünüyordu, gerçekte %1,4'tü.
2. 41 işlemin **16'sı** "SAT (BAŞARISIZ)" olarak kalmıştı.

Bu tür bir altyapı üzerine kurulan bir ML modeli, gürültüyü öğrenirdi.
Dokümanın bu uyarısı isabetli.

## 1.4. §34 (sızıntı/overfitting) ve §20-21 (challenger/rollback)

Bu maddeler çoğu hobi projesinde hiç bulunmaz. Özellikle "yeni model kendini
kanıtlamadan üretime alınmaz" ilkesi ve rollback mekanizması doğru.

## 1.5. §40 (NO TRADE) ve §11 (örüntü modülü)

NO TRADE'in geçerli bir karar sayılması olgun bir yaklaşım. §11'deki örüntü
modülü değerlendirmesi de mevcut deneyimle tutarlı (o modül zaten yanıltıcı
bulunduğu için kaldırılmıştı).

---

# BÖLÜM 2 — Ciddi itirazlarım

## 🔴 İTİRAZ 1: ML için veri stratejisi hatalı — 3 yıl beklersiniz

Doküman (§13, §14, §31, §45-Faz5) şu akışı kuruyor:

> Kararları logla → sonuçları ölç → bu deneyimden ML modeli eğit

**Bu akış doğru ama zamanlaması gerçekçi değil.** Kendi kayıtlarınızı ölçtüm:

```
Toplam tavsiye kaydı : 546
Farklı GÜN sayısı    : 5
Farklı hisse         : 129
Olgunlaşmış tavsiye  : 0   (10 iş günü ufku için)
```

Kritik nokta: **546 kayıt, 546 bağımsız gözlem DEĞİLDİR.** Aynı gün kaydedilen
129 hisse aynı piyasa gününü paylaşır — hepsi aynı endeks hareketinden,
aynı rejimden etkilenir. İstatistiksel olarak **etkin bağımsız örnek sayınız
gün sayısına yakındır: 5.**

30+ özellikli bir ML modeli için birkaç bin bağımsız gözlem gerekir. Günde
1 gözlem birikirse bu **8-10 yıl** demektir.

### Çözüm: veriyi beklemeyin, GEÇMİŞTEN üretin

Elinizde zaten `backtest_motoru.py` var ve look-ahead bias'a karşı test edilmiş
durumda. Bu motor, ML veri setini **bugün** üretebilir:

```
5 yıl × ~500 hisse × haftalık örnekleme ≈ 130.000 satır
her satır: o TARİHTE bilinebilen özellikler + ileri getiri etiketi
```

Bu, dokümandaki §35 "Feature Store"un ta kendisidir — ama canlı log
beklemeden. Canlı experience log yine tutulmalı; ancak o, modeli **eğitmek**
için değil, modelin canlıda backtest'teki gibi davranıp davranmadığını
**doğrulamak** için kullanılmalı.

> **Not:** Bu değişiklik dokümanın Faz 5'ini Faz 1'e taşır ve projeyi
> yıllardan aylara indirir.

## 🔴 İTİRAZ 2: §8'deki kâr alma politikası, dokümanın geri kalanıyla çelişiyor

Doküman §8'de "%30-40 kârda pozisyonun bir kısmını sat" diyor. Ancak dokümanın
tamamı momentum/trend takibi üzerine kurulu (§2.1, §3.1, §17).

Bu iki şey birbiriyle çelişir:

- Momentum stratejilerinin kârı **birkaç çok büyük kazanandan** gelir. Getiri
  dağılımı aşırı çarpıktır: işlemlerin %70'i küçük zarar/küçük kâr, %5'i devasa
  kâr eder.
- Kazananı +%30'da kesip kaybedeni stop'a kadar taşımak, bu dağılımın **sağ
  kuyruğunu keser**. Geriye sadece kayıplar kalır.
- Bu davranışın literatürdeki adı **disposition effect**'tir ve bireysel
  yatırımcıların en iyi belgelenmiş sistematik hatasıdır.

**Önerim:** Kısmi kâr alma seviyesi sabit yüzdeye (%30) değil, **volatiliteye**
bağlanmalı (ör. 3×ATR). Oynak bir hissede %30 normal bir dalgalanmadır; sakin
bir hissede ise gerçek bir sinyaldir. Sabit yüzde ikisini de yanlış yönetir.

Bu sizin kişisel tercihiniz — ama dokümanın kendi mantığıyla çeliştiğini
söylemek zorundayım. En azından backtest'te "sabit %30 kâr al" ile "trend
bozulana kadar taşı" senaryolarını **karşılaştırıp** kararı veriyle verin.

## 🔴 İTİRAZ 3: Kapsam tek kişi için gerçekçi değil

Doküman 9 faz, 60+ maddelik bir yol haritası çiziyor. Kaba tahminle bu
**2-3 kişi-yılı** iş. Tek kişilik bir yan proje için bu, yarıda bırakılma
riski çok yüksek bir plandır.

Ayrıca bazı maddeler mevcut varlıkları yok sayıyor: `backtest_motoru.py`,
`tavsiye_kaydi.py`, `piyasa_rejimi()`, `risk_alarmlari()` zaten var ve
dokümandaki bazı kutucukları kısmen dolduruyor.

**Önerim:** Aşağıdaki "gerçekçi sıra" bölümüne bakın.

---

# BÖLÜM 3 — Dokümanda EKSİK olanlar

## 3.1. 🇹🇷 BIST'e özgü gerçekler hiç yok (en önemli eksik)

Doküman genel/uluslararası piyasa varsayımlarıyla yazılmış. BIST backtest'lerini
asıl bozan şeyler bunlar:

| Konu | Neden kritik | Sonuç |
|---|---|---|
| **Tavan/taban (%10)** | Tavandaki hisse alınamaz | Backtest "aldım" sanar, gerçekte emir dolmaz |
| **VBTS (volatilite bazlı tedbir)** | Hisse tek fiyat işlemine alınır | Gün içi çıkış imkânsızlaşır |
| **Likidite** | 560 hissenin çoğu sığ | Kâğıt üstündeki getiri gerçekte alınamaz |
| **Bedelsiz/temettü düzeltmesi** | Yanlış düzeltme sahte %50 düşüş üretir | Sahte "çöküş" sinyalleri |
| **Açığa satış kısıtları** | Dönem dönem yasaklanır | Short varsayan mantık geçersiz |
| **Halka arz etkisi** | İlk günler aşırı oynak | Momentum taraması bunlarla dolar |

Özellikle **tavan kuralı** momentum stratejisi için öldürücüdür: sisteminiz en
güçlü momentumlu hisseyi seçer, o hisse ertesi gün tavan yapar ve **siz
alamazsınız**. Backtest ise almış gibi hesaplar. Bu, en iyimser hata türüdür.

## 3.2. "Vazgeçme kriteri" yok

Doküman sistemin nasıl geliştirileceğini anlatıyor ama **ne zaman
durdurulacağını** söylemiyor. Önceden yazılmalı:

> "N adet olgunlaşmış tavsiyeden sonra endeks üstü getiri istatistiksel olarak
> sıfırdan ayırt edilemiyorsa, motor bu haliyle terk edilir."

Bu madde olmadan proje, sonuç vermese bile yıllarca kaynak yutabilir.

## 3.3. Çoklu test (p-hacking) kontrolü yok

§34 overfitting'i sayıyor ama şunu atlıyor: onlarca aday kural test edilecek.
20 kural denerseniz, hiçbiri gerçekte işe yaramasa bile **biri %5 anlamlılıkla
"çalışıyor" çıkar.** En azından:

- Test edilecek hipotezler **önceden** yazılmalı (pre-registration)
- Test sayısı raporlanmalı
- Deflated Sharpe ratio veya Bonferroni benzeri düzeltme kullanılmalı

## 3.4. Rejim etiketleri geçmişe bakarak atanma riski

§18 rejim bazlı model öneriyor — doğru. Ancak "BULL/BEAR" etiketi genellikle
**sonradan bakılarak** atanır. Rejim tespiti mutlaka **nedensel** olmalı:
o gün, sadece o güne kadarki veriyle hesaplanabilmeli. (Mevcut
`piyasa_rejimi()` bu açıdan kontrol edilmeli.)

## 3.5. Güven aralıkları yok

§7 ve §39 nokta tahminlerinden söz ediyor ("win rate %68"). Sizin örneklem
büyüklüğünüzde bu sayıların güven aralığı çok geniş olacak. **Her metrik
aralıkla raporlanmalı**, yoksa gürültüyü sinyal sanma riski yüksek.

## 3.6. Model karmaşıklığı üst sınırı yok

§12 ve §45-Faz6 ML modelleri sıralıyor (classification, regression,
regime-aware, calibration). Veri kısıtınız düşünülürse başlangıç modeli
**lojistik regresyon** olmalı, XGBoost değil. Kural: her özellik için
**ekonomik gerekçe** yazılmalı; gerekçesi olmayan özellik veri setine
girmemeli.

---

# BÖLÜM 4 — Gerçekçi uygulama sırası (benim önerim)

Dokümanın 9 fazı yerine, **etki/emek oranına göre** sıralanmış hâli:

### Adım 0 — Bu hafta (yarım gün) 🔥
- [ ] **Overextension (aşırı uzama) skoru** — MA50/MA20'den uzaklığa göre kademeli ceza
- [ ] **Early Entry skoru** — trend skorundan AYRI ikinci bir sütun
- [ ] Risk motoruna **"şişkinlik" alarmı** ekle

*Neden önce bu: Ölçülmüş tek somut hatayı doğrudan düzeltiyor ve mevcut
backtest ile hemen doğrulanabiliyor.*

### Adım 1 — Bu ay 🔥
- [ ] **Backtest'ten feature store üret** (5 yıl × 500 hisse × haftalık)
- [ ] Backtest'e **komisyon + slippage + tavan/taban filtresi** ekle
- [ ] **Benchmark metrikleri**: excess return, max drawdown, Sharpe, profit factor

*Neden: ML veri setini yıllarca beklemeden bugün üretir; ayrıca mevcut
backtest'in iyimserliğini giderir.*

### Adım 2 — Sonraki ay
- [ ] **İki aşamalı çıkış motoru** (WARNING → EXIT) — §6
- [ ] Volatiliteye bağlı kısmi kâr alma (sabit %30 değil)
- [ ] Karar snapshot'ları (§13) — ama **doğrulama** amaçlı, eğitim değil

### Adım 3 — Ancak bundan sonra
- [ ] Basit ML: lojistik regresyon, ≤10 özellik, walk-forward
- [ ] Challenger/registry/rollback
- [ ] Hata kategorileri ve kümeleme

### Sonraya bırakılacaklar (şimdilik gereksiz)
- Broker API, kill switch, order reconciliation (§28, §42) — gerçek para
  aşaması çok uzakta; şimdi yazılırsa kullanılmadan eskiyecek.
- Sektör/makro faktörler — veri kalitesi maliyeti yüksek, katkısı belirsiz.

---

# BÖLÜM 5 — Kısa notlar (madde madde)

| § | Not |
|---|---|
| §3.1 | Faktör listesi çok uzun. 30 faktör × sınırlı veri = ezberleme. Önce 8-10 faktörle başlayın. |
| §5 | Satış motorunun ayrı olması doğru. `risk_alarmlari()` bunun temelini zaten atmış — sıfırdan yazmayın, genişletin. |
| §7 | Kademeli güven skoru iyi fikir. Ancak eşikler (90/80/70/60) uydurma; backtest'ten çıkarılmalı. Doküman bunu zaten söylüyor ✅ |
| §9 | Model portföy soruları doğru. `sanal_yatirimci.py` bunların bir kısmını yapıyor. |
| §10 | Benchmark zorunluluğu **en yüksek öncelikli eksik**. Şu an sistem "kâr etti mi" diyor, "endeksi yendi mi" demiyor. |
| §16 | Hata kategorileri listesi çok iyi. `OVEREXTENDED_ENTRY` sizin ana probleminiz — ilk ölçülecek kategori bu olmalı. |
| §17 | Özellik önem tablosundaki değerler (strong/weak) **örnek** olmalı, hedef değil. Şu an gerçek değerleri bilmiyoruz. |
| §22 | Kontrollü self-learning akışı doğru. "Human approval" adımını uzun süre koruyun. |
| §26 | Pozisyon büyüklüğü volatiliteye bağlanmalı — bu, sabit ağırlıktan çok daha etkili ve uygulaması kolay. Erken adıma alınabilir. |
| §29 | Paper trading aşaması zaten var ama **ölçüm katmanı bozuktu** (bu oturumda düzeltildi). Önce ölçümün doğruluğunu doğrulayın. |
| §37 | İşlem maliyeti gerçekçiliği kritik. Mevcut backtest komisyonu **hiç** hesaba katmıyor (kodda doğruladım). |
| §43 | Günlük rapor iyi fikir; günlük otomasyon kurulumu (`GOREV_ZAMANLAYICI_KURULUM.md`) buna hazır. |
| §48 | 20 ilkenin tamamı sağlam. Özellikle 2, 3, 17 ve 20 doğru. |

---

# Sonuç

Doküman **fikir olarak sağlam, plan olarak fazla iddialı, veri stratejisi
olarak hatalı.**

Üç cümlelik özet:

1. Teşhis doğru — ve ben bunu bağımsız olarak veriyle doğruladım.
2. ML'i canlı loglardan öğrenmeyi beklemeyin; backtest'ten veri seti üretin,
   yıllar yerine haftalar kazanın.
3. Önce ölçüm (benchmark, maliyet, tavan/taban) doğru olsun; ölçüm bozukken
   yapılan her iyileştirme kendini kanıtlayamaz.

**En değerli tek adım:** Overextension + Early Entry skorlarını ayırmak.
Yarım günlük iş, ölçülmüş bir hatayı düzeltiyor ve dokümanın §2.1/§4/§25
maddelerinin tamamını aynı anda hayata geçiriyor.
