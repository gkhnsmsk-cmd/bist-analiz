# PC açıkken arka planda otomatik çalıştırma (basit yöntem)

**Bu, önceki mesajlardaki bulut/GitHub kurulumlarından çok daha basit bir
alternatiftir.** GitHub hesabı, depo, internet ayarı gerekmez. Tek şart:
**bilgisayarın o saatte açık olması** (uyku/kapalı değil).

Ne kazanırsınız: uygulamayı hiç açmadan, hatta ekranın kapalıyken bile,
her gün otomatik olarak veri toplanır, tavsiyeler kaydedilir, sanal portföy
izlenir. Görev Zamanlayıcı'yı doğru ayarlarsanız **hiçbir pencere bile
görünmez** — tamamen sessiz çalışır.

---

## Kuracağınız 3 görev — sıklık: GÜNDE TAM 1 KEZ (hafta içi)

| Bat dosyası | Ne yapar | Saat |
|---|---|---|
| `ARKA_PLAN_TARAMA.bat` | Tüm BIST'i tarar, "Öne Çıkan"/"Yükselebilecek" listelerini günceller, tavsiye kaydeder | **18:30** |
| `GUNLUK_SANAL_YATIRIM.bat` | Sanal portföyü izler; **sadece Cuma günleri** alım-satım yapar, diğer günler izler | **18:40** |
| `GUNLUK_TARAMA.bat` | Portföyünüz + izleme listeniz için AL/SAT/TAKAS önerisi üretir | **18:50** |

Üçü de birbirinden bağımsızdır — istediklerinizi kurun. En kritik olan
performans ölçümü için **`ARKA_PLAN_TARAMA.bat`** ve **`GUNLUK_SANAL_YATIRIM.bat`**.

### Neden günde 1 kez (2-3 kez değil)?

Amacınız "uygulamayı eğitmek / iyi öneri veriyor mu görmek" olduğu için
sıklığı buna göre belirledim — daha sık çalıştırmak **yardımcı olmaz,
zarar verir**:

- **Veri zaten günlük.** Fiyat verisi günlük kapanış (OHLCV) çubukları
  şeklinde geliyor. Gün içinde 5 kez çalıştırsanız da veri kaynağı aynı
  günün aynı verisini döndürür — istatistiksel olarak sıfır ek bilgi.
- **Kayıt sistemi zaten mükerrer engelliyor.** `tavsiye_kaydi.py`, aynı
  gün + aynı hisse için ikinci kaydı otomatik atlıyor (kodda doğruladım).
  Yani günde 2 kez çalıştırsanız ikinci çalıştırma pratikte hiçbir şey
  kaydetmeyecek, sadece boşuna ağ isteği yapacak.
- **Ücretsiz veri kaynakları (Yahoo/İş Yatırım) sık istekte sizi geçici
  engelleyebilir.** Gereksiz tekrar çalıştırmalar bu riski artırır — ve
  engellenirseniz asıl önemli olan akşam kaydı da başarısız olabilir.
- **Ölçümü hızlandıran şey çalıştırma SIKLIĞI değil, GEÇEN GÜN SAYISIDIR.**
  Tavsiyelerin "olgunlaşması" (5/10/20 iş günü sonra sonucun ölçülmesi)
  takvim günü ilerlemesine bağlı, saatlik tekrara değil.
- **Saatler kasıtlı olarak 10'ar dakika arayla verildi** (18:30 / 18:40 /
  18:50) — üçü aynı anda aynı veri kaynağına yüklenmesin, sırayla çalışsın
  diye.

**Tek istisna:** Cuma-Pazartesi arası (hafta sonu) boşluk normaldir, borsa
zaten kapalı — bu yüzden aşağıda "Haftalık" tetikleyici ile sadece hafta içi
(Pazartesi-Cuma) çalışacak şekilde kuracağız; hafta sonu boşuna
çalıştırmayacak.

### Ne kadar sürede anlamlı sonuç çıkar?

- **5 iş günü ufku** (en hızlı sinyal): ~1 hafta sonra ilk olgun sonuçlar
- **10 iş günü ufku**: ~2 hafta
- **20 iş günü ufku** (en güvenilir): ~1 ay
- **İstatistiksel olarak anlamlı yargı** (20-30 olgunlaşmış tavsiye):
  **4-6 hafta kesintisiz günlük çalıştırma**

Bu süreler PC'nin ne kadar sık açık olduğuna bağlı — hafta içi her gün en
az bir kez (18:30 civarı) açıksa yukarıdaki takvim geçerli olur.

---

## Kurulum adımları (her görev için tekrarlanır)

Windows arama çubuğuna **"Görev Zamanlayıcısı"** yazıp açın.

### 1. Yeni görev oluştur

Sağ panelden **"Görev Oluştur..."** (Create Task — "Temel Görev Oluştur"
DEĞİL, tam "Görev Oluştur" sihirbazını kullanın; sessiz/arka plan çalışması
için gereken ayarlar sadece bu sihirbazda var).

### 2. "Genel" sekmesi

- **Ad:** `BIST - Arka Plan Tarama` (her görev için farklı ad verin)
- **"Kullanıcı oturum açmış olsun ya da olmasın çalıştır"** seçeneğini işaretleyin
  ⚠️ **Bu adım kritiktir** — bu seçili olmazsa görev sadece siz oturum
  açıkken ve genelde görünür bir pencereyle çalışır. Bu seçiliyken tamamen
  sessiz/görünmez çalışır.
- **"Gizli"** kutucuğunu da işaretleyin (ekstra sessizlik için)
- Windows şifrenizi sorabilir — bilgisayar şifrenizi girin (görevin
  oturum açmadan çalışabilmesi için gereklidir)

### 3. "Tetikleyiciler" sekmesi

- **Yeni...** → **Görevi başlat: Zamanlanmış**
- **"Günlük" DEĞİL, "Haftalık" seçin** — bu sayede hafta sonu boşuna
  çalışmaz (borsa zaten kapalı, çalıştırmanın hiçbir faydası yok, sadece
  gereksiz bir kayıt/log satırı üretir)
- **Yinelensin:** her `1` hafta
- Gün kutucuklarından yalnızca **Pazartesi, Salı, Çarşamba, Perşembe,
  Cuma**'yı işaretleyin (Cumartesi/Pazar boş kalsın)
- **Saat:** ilgili script için yukarıdaki tablodaki saati girin
  (`ARKA_PLAN_TARAMA.bat` → `18:30`, `GUNLUK_SANAL_YATIRIM.bat` → `18:40`,
  `GUNLUK_TARAMA.bat` → `18:50`)
- Alttaki **Gelişmiş ayarlar** kısmında **"Etkin"** işaretli olsun

### 4. "Eylemler" sekmesi

- **Yeni...**
- **Program/komut dosyası:** ilgili `.bat` dosyasının **tam yolunu** yazın,
  örneğin:
  ```
  C:\Users\gkhns\YandexDisk\Yandex genel\lispler\YAZILIMLAR\Borsa yazılımı1\ARKA_PLAN_TARAMA.bat
  ```
- **Başlangıç konumu (isteğe bağlı):** aynı klasörün yolunu yazın:
  ```
  C:\Users\gkhns\YandexDisk\Yandex genel\lispler\YAZILIMLAR\Borsa yazılımı1
  ```

### 5. "Koşullar" sekmesi

- **"Bilgisayar yalnızca AC gücündeyken görevi başlat"** kutusunun işaretini
  **kaldırın** (dizüstü kullanıyorsanız — yoksa şarj takılı değilse
  çalışmaz)
- **"Görevi çalıştırmak için bilgisayarı uyandır"** kutusunu **işaretleyin**
  — PC uyku modundaysa bile bu sayede o saatte kendini uyandırıp görevi
  çalıştırır, sonra isterseniz tekrar uykuya döner

  > Not: bu seçenek bilgisayar **tamamen kapalıyken** (kapatılmışsa) işe
  > yaramaz — sadece uyku/bekleme modundan uyandırır. Kapalıyken çalışması
  > için bilgisayarın fiziksel olarak açık olması gerekir; bu tamamen
  > normal ve sizin de istediğiniz senaryo.

### 6. "Ayarlar" sekmesi

- **"Görev başarısız olursa yeniden başlatmayı dene"** işaretleyin, 3 kez,
  5 dakika arayla — geçici bir internet kesintisinde bir sonraki denemede
  kurtarır
- **"Görev zaten çalışıyorsa yeni örneği başlatma"** seçili kalsın (üst
  üste binmeyi engeller)

### 7. Kaydet

**Tamam** deyin, Windows şifrenizi tekrar isteyebilir.

---

## Diğer iki görevi de aynı şekilde kurun

Aynı adımları `GUNLUK_SANAL_YATIRIM.bat` (saat `18:40`) ve `GUNLUK_TARAMA.bat`
(saat `18:50`) için tekrarlayın — her ikisinde de tetikleyici **Haftalık,
Pazartesi-Cuma** olacak.

---

## Test etme

Kurduktan sonra görev listesinde göreve sağ tıklayıp **"Çalıştır"** deyin.
Hiçbir pencere açılmamalı (Gizli işaretlediyseniz). Birkaç saniye/dakika
sonra klasörde şu log dosyalarının güncellendiğini kontrol edin:

- `arka_plan_tarama_log.txt`
- `sanal_yatirim_log.txt`
- `gunluk_log.txt`

Loglarda hata görürseniz bana log içeriğini gönderin, birlikte bakarız.

---

## Bu yöntemin sınırı (dürüst uyarı)

Bu, önceki mesajdaki bulut çözümünden **daha kolay ama daha kısıtlı**:

- PC **kapalıyken** (fiziksel olarak kapatılmış/fişten çekilmiş) hiçbir
  şey çalışmaz — sadece uyku modundan uyanabilir, "yoktan var olamaz."
- Siz seyahatteyken/PC'niz kapalıyken veri toplanmaz, o günler boşluk
  kalır. Bu, performans ölçümünü biraz yavaşlatır ama **imkansız kılmaz** —
  sadece PC'yi ne kadar sık açık tutarsanız o kadar hızlı veri birikir.

Eğer ileride "PC hiç açık olmasa da kesintisiz çalışsın" isterseniz, önceki
mesajdaki GitHub Actions kurulumu (`BULUT_KURULUM.md`) o boşluğu tam olarak
kapatıyor — ama şu an için bu basit yöntemle başlamak tamamen makul bir
tercih.
