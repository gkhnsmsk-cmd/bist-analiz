# Bulutta günlük otomasyon — kurulum (GitHub Actions)

**Amaç:** Bilgisayarın kapalı olsa bile yazılım her iş günü bulutta çalışsın,
tarama yapıp tavsiyeleri kaydetsin. Böylece performansı ölçmek için gereken
kayıtlar kesintisiz birikir.

> **Neden gerekli:** Yazılımın gerçekten işe yarayıp yaramadığı ancak gerçek
> zamanda verilmiş tavsiyelerin sonucuna bakılarak ölçülebilir. 7-13 Ağustos
> arasında bilgisayar kapalı olduğu için hiç kayıt oluşmadı ve ölçüm durdu.

---

## Ne kuruluyor?

Her hafta içi günü, saat **19:00 (TR)** civarında GitHub'ın sunucularında:

1. `arka_plan_tarama.py` → tüm BIST taranır, tavsiyeler `tavsiye_gecmisi.json`'a yazılır
2. `gunluk_sanal_yatirim.py` → sanal portföy izlenir/rebalans edilir
3. Değişen JSON kayıtları depoya geri yazılır

**Ücret:** Yok. GitHub Actions, özel (private) depolarda ayda 2000 dakika
ücretsiz verir; bu iş akışı günde ~5-15 dakika kullanır.

---

## Adım adım kurulum

### 1. GitHub hesabı ve depo

1. [github.com](https://github.com) → hesabın yoksa ücretsiz aç.
2. Sağ üstten **+ → New repository**
3. Ayarlar:
   - **Repository name:** `bist-analiz` (veya istediğin ad)
   - **Visibility: `Private`** ← ⚠️ **Bunu mutlaka seç.** Portföy ve tavsiye kayıtların herkese açık olmasın.
   - "Add a README" kutusunu **işaretleme**
4. **Create repository**

### 2. Klasörü depoya yükle (GitHub Desktop ile)

Bilgisayarında GitHub Desktop kurulu.

1. GitHub Desktop → **File → Add local repository**
2. Klasörü seç: `C:\Users\gkhns\YandexDisk\Yandex genel\lispler\YAZILIMLAR\Borsa yazılımı1`
3. "This directory does not appear to be a Git repository" derse → **create a repository** bağlantısına tıkla → **Create repository**
4. Sol panelde dosya listesi çıkacak. **⚠️ Şunları kontrol et — listede GÖRÜNMEMELİ:**
   - `.env`
   - `telegram_ayarlar.json`
   - `telegram_oturumu.session`

   Bunlar `.gitignore` ile hariç tutuldu. Yine de listede görürsen **bana haber ver, push etme.**
5. Alt sola bir mesaj yaz (örn. "ilk yükleme") → **Commit to main**
6. Üstte **Publish repository** → **Keep this code private** işaretli olsun → **Publish**

### 3. Actions iznini aç

1. GitHub'da deponu aç → **Settings** sekmesi
2. Sol menü → **Actions → General**
3. En altta **Workflow permissions** bölümü:
   - **Read and write permissions** seçeneğini işaretle
   - **Save**

> Bu izin olmadan otomasyon çalışır ama sonuçları depoya **geri yazamaz**.

### 4. İlk çalıştırmayı elle test et

1. Depoda **Actions** sekmesi → sol menüden **Günlük BIST otomasyonu**
2. Sağda **Run workflow** → **Run workflow**
3. 5-15 dakika bekle, sonucu izle.
   - ✅ Yeşil tik: çalıştı. Depoda `tavsiye_gecmisi.json`'ın güncellendiğini göreceksin.
   - ❌ Kırmızı: adım loglarına tıkla, hatayı bana gönder.

Bundan sonra her hafta içi otomatik çalışır; hiçbir şey yapmana gerek yok.

---

## Sonuçları bilgisayarına indirmek

Bulut kendi kopyasına yazar. Uygulamayı açmadan **önce** sonuçları çekmelisin:

1. GitHub Desktop'ı aç
2. Üstte **Pull origin** düğmesine bas
3. Sonra `BASLAT.bat` ile uygulamayı aç

> **Alışkanlık hâline getir:** önce Pull, sonra BASLAT.

### Çakışma olursa

Hem bulut hem sen aynı JSON dosyasını değiştirdiyseniz GitHub Desktop çakışma
(conflict) bildirir. En güvenli çözüm: **buluttaki sürümü kabul et** — orada
kesintisiz ve otomatik biriken kayıt vardır.

---

## Bilinmesi gerekenler (dürüst uyarılar)

- **Veri kaynağı riski:** Yahoo Finance bazen bulut sunucu IP'lerini kısıtlar.
  Böyle bir günde tarama boş dönebilir; iş akışı çökmez, o günü atlar
  (`continue-on-error`). Sık yaşanırsa alternatif kaynağa (İş Yatırım/Mynet)
  öncelik verecek şekilde ayarlayabiliriz.
- **Telegram/AKD bulutta çalışmaz.** Oturum dosyası ve API anahtarı güvenlik
  gereği yüklenmiyor. AKD verisi yalnızca sen uygulamayı açtığında çekilir.
- **Zamanlama kayabilir.** GitHub cron'u yoğunlukta 5-30 dakika gecikebilir.
  Gün sonu verisiyle çalıştığımız için bu sonucu etkilemez.
- **Resmî tatiller filtrelenmiyor.** Tatil günlerinde tarama çalışır ama borsa
  kapalı olduğundan bir önceki günün verisi tekrar kaydedilir; `tavsiye_kaydi`
  mükerrer kayıtları zaten eliyor.
- **Sabır gerekir.** Anlamlı bir performans yargısı için en az **20-30
  olgunlaşmış tavsiye** lazım. Bu, kesintisiz çalışmayla yaklaşık **4-6
  hafta** demektir. Bu süreden önce çıkarılan sonuç yanıltıcı olur.
