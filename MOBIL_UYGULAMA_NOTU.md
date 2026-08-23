# Mobil Uygulama Dönüşümü — Gelecek İş Notu

**Kaydedilme tarihi:** 18.08.2026
**Durum:** ERTELENDİ — kullanıcı "sonrası için kaydet" dedi. Başlamadan önce onay alınacak.

---

## İstek (kullanıcının kendi ifadesiyle)

> "yazılımı mobil bir app e dönüştürmek istiyorum. arayüzü güncellemek gerekcek. daha akıcı ve hızlı olmalı. şu an yavaş çalışıyor"

Üç ayrı iş var, birbirine karıştırılmamalı:

1. **Mobil app'e dönüşüm** — mimari karar gerektirir
2. **Arayüz güncellemesi** — mobil ekrana uyum (responsive)
3. **Performans** — mevcut yavaşlık, mobilden BAĞIMSIZ bir sorun

---

## 1. Mobil dönüşüm — önce karar verilmeli

Streamlit native mobil uygulama (APK / App Store) üretemez. Bu yüzden bu iş bir
"özellik ekleme" değil, bir **mimari seçim**. Üç gerçekçi yol var:

### Yol A — Responsive Streamlit + PWA
Mevcut uygulamayı telefonda düzgün görünecek hale getirmek, sonra tarayıcıdan
"Ana ekrana ekle" ile app gibi kısayol oluşturmak.

- **İş yükü:** Düşük (birkaç gün)
- **Sonuç:** Simge telefonda durur, tam ekran açılır — ama gerçek native app değil
- **Kısıt:** Bildirim gönderemez, çevrimdışı çalışmaz, App Store'a konamaz
- **Gerekli:** Sağdaki sohbet kolonu mobilde alta inmeli; tablolar dar ekranda
  yeniden düzenlenmeli; radyal göstergeler küçültülmeli

### Yol B — Ayrı native app (FastAPI + React Native/Flutter)
Analiz motorunu bir API'ye çevirip, telefon için ayrı bir istemci yazmak.

- **İş yükü:** Yüksek (haftalar)
- **Sonuç:** Gerçek app, bildirim gönderebilir ("PGSUS satım eşiğine düştü")
- **Kısıt:** Sunucu gerekir (uygulama artık senin PC'nde değil, bir yerde
  sürekli açık durmalı). Aylık maliyet doğar.
- **Not:** Bu, GSEM sitesinden TAMAMEN ayrı bir sunucu/depo olmalı

### Yol C — Hibrit (önerilen sıra)
Önce analiz motorunu (`analiz_motoru.py`, `veri_katmani.py`) Streamlit'ten
bağımsız bir API katmanına ayır. Mevcut Streamlit uygulaması bu API'yi
kullanmaya devam etsin. Mobil istemci sonra, hazır olunca, aynı API'ye bağlanır.

- **Avantajı:** Mobil kararı ertelenebilir ama bu ayrım her durumda faydalı
- **Zaten yarı yapılmış:** `sohbet_ajani.py` bu ayrımı kısmen yapıyor
  (`kaynaklar` sözlüğü sayesinde Streamlit'siz test edilebiliyor)

---

## 2. Performans — ÖNCE BU YAPILMALI

Yavaşlık mobilden bağımsız bir sorun ve mobil app de aynı motoru kullanacağı için
mobile geçmeden çözülmeli. **Ama önce ölçülmeli** — tahminle optimizasyon yapılmayacak.

### Şüpheliler (henüz doğrulanmamış)

| Şüpheli | Neden şüpheli | Nasıl ölçülür |
|---|---|---|
| yfinance ağ istekleri | ~600 hisse indiriliyor, her biri HTTP isteği | İstek sayısı + toplam bekleme süresi loglanmalı |
| Puanlama hesabı | Hisse başına 20+ gösterge, pandas rolling | `cProfile` ile fonksiyon bazında süre |
| Streamlit yeniden çizimi | Her tıklamada script baştan çalışıyor | Rerun sayısı + `st.cache_data` isabet oranı |
| Sohbet paneli | Her rerun'da LLM zinciri kontrol ediliyor olabilir | `sohbet_hazir_mi()` çağrı sayısı |

### Yapılacak ilk adım
`cProfile` ile tam bir sayfa yüklemesinin profilini çıkar, en pahalı 20 fonksiyonu
listele. Optimizasyon kararları BU LİSTEYE göre verilecek.

### Muhtemel kazanç noktaları (profil sonrası doğrulanacak)
- Arka plan taraması düzgün çalışırsa (Görev Zamanlayıcı kurulunca) "canlı tara"
  ihtiyacı büyük ölçüde ortadan kalkar — en büyük tek kazanç bu olabilir
- `_panel_analiz` zaten önbellekli; `_gecmis`/`_temel` önbellek sürelerine bakılmalı
- Tablolar `_html_tablo` ile basılıyor (iyi); kalan `st.dataframe` çağrıları
  daha ağır çalışıyor olabilir

---

## Önerilen sıra (işe başlanınca)

1. **Görev Zamanlayıcı kurulumu tamamlansın** (zaten bekliyor) — taramanın
   arka planda çalışması hissedilen hızı en çok etkileyecek şey
2. **Profil çıkar** — gerçek darboğazı bul
3. **Darboğazı düzelt** — ölçüme dayalı
4. **Mobil yolu seç** (A / B / C) — kullanıcı kararı
5. Seçilen yola göre arayüz çalışması

---

## Bozulmaması gereken kurallar (mobil arayüzde de geçerli)

- **Sayfada tek kaydırma çubuğu** — kullanıcının tekrarlanan, kalıcı isteği.
  İç kaydırmalı kutu YOK.
- `st.container(border=True)` ile açılan HTML div'i BAŞKA bir `st.markdown`
  çağrısında kapatma. Streamlit her bloğu kendi kapsayıcısına sarar; açık-kapalı
  div'ler farklı kutulara düşer ve görsel kırpılma olur. (Bu hata bu projede
  iki kez yapıldı ve düzeltildi.)
- Sohbet paneli mobilde sağda duramaz — alta inmeli veya açılır panel olmalı.
