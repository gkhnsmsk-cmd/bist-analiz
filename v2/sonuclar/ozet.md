# PUSULA V2 — Walk-Forward Backtest Sonucu

Çalıştırma: 10.09.2026 06:20 UTC · Başlangıç özsermayesi: 1,000,000 TL

---

## ❌ KABUL KRİTERLERİ GEÇİLEMEDİ

Şartname §8 gereği sistem **TAVSIYE_VERME** modunda kalmalıdır.
Kullanıcıya sinyal gösterilmez; nedeni ana ekranda yazılır.

**Başarısız kriterler:**

- Expectancy 0.023R — eşik: >0.15R
- Profit factor 0.99 — eşik: >=1.4
- Maksimum düşüş %30.9 — eşik: <=%20
- Endeks üstü CAGR farkı %nan puan — eşik: >0

---

### TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir

| Metrik | Değer |
|---|---|
| İşlem sayısı | 249 |
| Kazanma oranı | %32.9 |
| **Expectancy** | **0.023R** |
| **Profit factor** | **0.99** |
| Ort. kazanç / kayıp | 1.26R / -0.58R |
| **Maksimum düşüş** | **%-30.9** |
| CAGR | — |
| Endeks CAGR | %27.06 |
| **Endeks üstü fark** | **—** |
| Ort. tutma süresi | 11.9 gün |
| En kötü tek işlem | -3.10R (QUAGR, stop) |

### Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı

| Metrik | Değer |
|---|---|
| İşlem sayısı | 326 |
| Kazanma oranı | %39.6 |
| **Expectancy** | **0.340R** |
| **Profit factor** | **1.80** |
| Ort. kazanç / kayıp | 1.75R / -0.58R |
| **Maksimum düşüş** | **%-25.9** |
| CAGR | %17.00 |
| Endeks CAGR | %53.23 |
| **Endeks üstü fark** | **%-36.23** |
| Ort. tutma süresi | 15.0 gün |
| En kötü tek işlem | -3.02R (ECILC, stop) |

---

## Bilinen sınırlar (dürüstlük notu)

- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor;
  geçmişte borsadan çıkmış/endeksten düşmüş hisseler yok. Bu, sonuçları
  olduğundan **iyi** gösterme eğilimindedir.
- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek
  seans limit verisi değil.
- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor, bu da
  sektör yoğunlaşma kısıtını zayıflatıyor.
- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.
