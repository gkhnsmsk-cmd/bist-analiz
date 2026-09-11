# PUSULA V5 — "Akıl Hocası" (V2 mimarisi + sıkılaştırılmış giriş/geniş stop) — Walk-Forward Sonucu

Çalıştırma: 11.09.2026 12:56 UTC · Başlangıç özsermayesi: 1,000,000 TL

**Kabul ölçütü artık "endeksi her dönem yen" DEĞİL.** Kullanıcının zaman ayıramadığı için ihtiyacı olan şey: pozitif expectancy'li, disiplinli, riski kontrollü bir "akıl hocası". Kriterler: Expectancy>0R, Profit Factor>=1.3, Maks. düşüş<=%25, CAGR>0 (zorunlu) ve Sharpe>0.8 (tercihen, bağlayıcı değil).

---

## AKIL HOCASI KABUL EDİLMEDİ

Aşağıdaki bağlayıcı kriterlerden en az biri sağlanmadı — TAVSIYE_VERME modu önerilir.

**Başarısız kriterler:**

- Expectancy nanR — eşik: >0R (pozitif olmalı)
- Profit factor tanımsız — eşik: >=1.3
- CAGR %0.00 — eşik: >0 (pozitif sermaye artışı zorunlu)

**Bağlayıcı olmayan uyarılar:**

- Sharpe tanımsız — TERCİH edilen eşik: >0.8 (bağlayıcı değil)
- İşlem sayısı 0 — istatistiksel güven düşük olabilir (bağlayıcı değil, bilgilendirme)

---

### TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir

| Metrik | V5 (bu sistem, akıl hocası) | V2 (eski, referans) |
|---|---|---|
| **Expectancy (R)** | **—** | 0.023 |
| **Profit factor** | **—** | 0.99 |
| **CAGR** | **%0.00** | — |
| Endeks CAGR (BIST100) | %26.66 | — |
| **Maksimum düşüş** | **%0.0** | %-30.9 |
| **Sharpe (yıllık)** | **—** | — |
| Kazanma oranı | — | — |
| İşlem sayısı | 0 | — |
| Ortalama tutma (gün) | — | — |

### Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı

| Metrik | V5 (bu sistem, akıl hocası) | V2 (eski, referans) |
|---|---|---|
| **Expectancy (R)** | **—** | 0.340 |
| **Profit factor** | **—** | 1.80 |
| **CAGR** | **%0.00** | %17.00 |
| Endeks CAGR (BIST100) | %53.23 | — |
| **Maksimum düşüş** | **%0.0** | %-25.9 |
| **Sharpe (yıllık)** | **—** | — |
| Kazanma oranı | — | — |
| İşlem sayısı | 0 | — |
| Ortalama tutma (gün) | — | — |

---

## V5'in V2'den farkı (kök neden analizi ve müdahale)

V2'nin test PF'si 0.99 (neredeyse başabaş) çıkmıştı. Kök neden: (a) giriş filtresi 'kirilim VEYA geri_cekilme' + göreli güç>=75 + uzama<=2.0 ile yeterince seçici değildi — kazanan/kaybedeni ayırt etmiyordu; (b) 2.5xATR ilk stop, normal günlük gürültüde bile sık tetiklenip (whipsaw) potansiyel kazananları erken kesiyordu.

V5 müdahalesi: (1) yalnız 'kirilim' kurulumu + göreli güç>=85 + uzama<=1.2 (daha az ama daha kaliteli sinyal), (2) ilk stop 3.5xATR'ye genişletildi (whipsaw azaltma). Diğer her şey (maliyet modeli, portföy kısıtları, trailing/zaman/trend/rejim çıkışları, T+1 açılış gerçekleşmesi) V2 ile BİREBİR aynı.

## Bilinen sınırlar (dürüstlük notu)

- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor.
- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans limit verisi değil.
- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor.
- **Daha az işlem = daha az istatistiksel güven:** sıkılaştırılmış filtre işlem sayısını azaltır; test döneminin işlem sayısı düşükse (<20-30) PF/expectancy tahminleri geniş güven aralığına sahiptir — bu ozet.md'de ayrı bir uyarı olarak işaretlenir (bağlayıcı değildir, ama dikkat gerektirir).
- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.
