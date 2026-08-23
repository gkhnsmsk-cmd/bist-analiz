# Uygulamayı internete koymak (Streamlit Community Cloud)

**Amaç:** BIST Analiz Platformu'nu web'de yayınlamak — bilgisayar kapalıyken
bile telefon/tablet/başka bir bilgisayardan açılabilsin.

## ⚠️ GSEM sitesiyle karışmaz — önemli izolasyon garantileri

Bu kurulum, GSEM Mühendislik web sitenizle **hiçbir ortak nokta paylaşmaz**:

| | GSEM sitesi | Bu uygulama |
|---|---|---|
| Barındırma servisi | (kendi hosting'iniz) | Streamlit Community Cloud — farklı platform |
| GitHub deposu | GSEM'in kendi deposu | **Yepyeni, ayrı** bir depo (aşağıda kurulacak) |
| Dosyalar | Kendi klasörü | `Borsa yazılımı1` klasörü — hiç dokunulmuyor |
| Alan adı/URL | GSEM'in adresi | `xxx.streamlit.app` — tamamen farklı adres |

Yani bu kurulumda GSEM'in deposuna, hosting hesabına veya dosyalarına
**kesinlikle dokunmuyoruz.** Sıfırdan, bağımsız, izole bir "kutu" açıyoruz.
Biri bozulsa diğerini etkilemez.

---

## Ön koşul

Önceki adımda (`BULUT_KURULUM.md`) anlatılan GitHub deposu zaten varsa onu
kullanabiliriz. Yoksa aşağıdaki 1. adımda kurarız — **GSEM'inkinden farklı,
yeni bir depo** olacak (örn. `bist-analiz`).

## Adımlar

### 1. GitHub deposu (BULUT_KURULUM.md'deki 1-2. adımlarla aynı)

Zaten yaptıysanız atlayın. Yapmadıysanız `BULUT_KURULUM.md` dosyasındaki
1. ve 2. adımları uygulayın: private bir depo açıp GitHub Desktop ile bu
klasörü (`Borsa yazılımı1`) oraya yükleyin.

### 2. Streamlit Community Cloud hesabı

1. [share.streamlit.io](https://share.streamlit.io) adresine gidin
2. **Sign in with GitHub** — GitHub hesabınızla giriş yapın (yeni şifre
   oluşturmanıza gerek yok)
3. İlk girişte deponuza erişim izni ister — onaylayın

### 3. Uygulamayı yayınlama

1. Sağ üstten **Create app** (veya **New app**)
2. **"Deploy a public app from GitHub"** seçin (private depo da desteklenir)
3. Ayarlar:
   - **Repository:** kurduğunuz depo (örn. `kullanici-adiniz/bist-analiz`)
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL:** istediğiniz bir alt ad (örn. `bist-analiz` → `bist-analiz.streamlit.app`)
4. **Advanced settings** (isteğe bağlı ama önerilir):
   - **Python version:** `3.12`
5. **Deploy!**

İlk kurulum (`requirements.txt`'teki tüm paketler + `packages.txt`'teki
`tesseract-ocr`) 3-8 dakika sürebilir. Bittiğinde uygulama otomatik açılır.

### 4. Gizli anahtarları ekleme (opsiyonel — LLM ajanları için)

`.env` dosyası güvenlik gereği GitHub'a hiç yüklenmedi; bulut bu yüzden onu
göremez. LLM konsensüs ajanlarını (Groq/OpenAI/vb.) bulutta da kullanmak
isterseniz:

1. Streamlit Cloud'da uygulamanız → **⚙️ Settings → Secrets**
2. Şu formatta yapıştırın (sadece kullandıklarınızı yazın):
   ```toml
   GROQ_API_KEY = "..."
   OPENAI_API_KEY = "..."
   ```
3. **Save** — uygulama otomatik yeniden başlar

Hiçbir anahtar girmezseniz uygulama yine sorunsuz çalışır; sadece o ajanlar
"kapalı" görünür (mevcut yerel davranışla aynı).

### 5. Telegram/AKD hakkında dürüst not

Telegram oturum dosyası (`telegram_oturumu.session`) ve ayarları
(`telegram_ayarlar.json`) güvenlik gereği depoya yüklenmiyor — bu yüzden
**AKD verisi çekme özelliği bulut sürümünde çalışmaz.** Bu bilinçli bir
tercih: o dosyaları buluta koymak, Telegram hesabınızın erişimini üçüncü bir
sunucuya (Streamlit'e) vermek anlamına gelirdi. AKD özelliğini kullanmak
isterseniz bilgisayarınızdaki yerel kurulumu (`BASLAT.bat`) kullanmaya devam
edin — bulut sürümü diğer her şeyde (tarama, analiz, sanal portföy,
backtest) tam çalışır.

---

## GitHub Actions ile birlikte kullanmak

`BULUT_KURULUM.md`'deki günlük otomasyonu da kurduysanız akış şöyle olur:

```
Her gün 19:00 → GitHub Actions tarar, tavsiye_gecmisi.json'ı günceller, depoya yazar
                          ↓
        Streamlit Cloud, depodaki güncel dosyayı bir sonraki açılışta okur
                          ↓
              Siz veya herkes xxx.streamlit.app'i açtığında güncel veriyi görür
```

İkisi birbirini tamamlar: Actions veri toplar, Streamlit Cloud onu sunar.
Hiçbir manuel adım gerekmez.

---

## Bilinen sınırlamalar (dürüst uyarılar)

- **Uygulama "uykuya dalabilir."** Streamlit Community Cloud, birkaç gün
  ziyaret edilmeyen ücretsiz uygulamaları duraklatır. Bir sonraki açılışta
  ~30 saniye "uyanma" süresi olur — veri kaybolmaz, sadece gecikir.
- **Dosya yazma kalıcı değildir.** Uygulama yeniden başladığında (deploy
  güncellemesi, uyku sonrası uyanma vb.) yerel diskteki değişiklikler
  GitHub'a otomatik geri yazılmaz — sadece GitHub Actions adımı (varsa)
  bunu yapar. Yani sanal portföy işlemlerini KALICI kaydetmek için Actions
  kurulumu (`BULUT_KURULUM.md`) şarttır.
- **AKD/Telegram bulutta çalışmaz** (yukarıda açıklandı).
- **Ücretsiz kaynak sınırlıdır** (1 GB bellek civarı). ~600 hisseli tam BIST
  taraması yerelde de birkaç dakika sürüyor; bulutta biraz daha yavaş
  olabilir ama çalışır — bu zaten `arka_plan_tarama.py` ile Actions
  üzerinden, kullanıcıyı bekletmeden yapılıyor.
