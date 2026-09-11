# SONUÇ: TEST döneminde al-tut'u HEM CAGR'da HEM maksimum düşüşte geçen varyant HİÇBİRİ.

**Geliştirme (2019-01-01 → 2023-12-31)**: al-tut'u HEM CAGR'da HEM maksimum düşüşte geçen varyant **HİÇBİRİ** yok.

**Test — DOKUNULMAMIŞ (2024-01-01 → 2026-09-10)**: al-tut'u HEM CAGR'da HEM maksimum düşüşte geçen varyant **HİÇBİRİ** yok.

> Bu manşet ve iki cümle ELLE yazılmadı; `_kazananlar()` fonksiyonu her
> koşuda AL_TUT satırıyla karşılaştırma yaparak otomatik üretir.

---

## Deney sorusu

V2 (stop'lu swing) ve V3 (momentum rotasyonu) mimarilerinin ikisi de BIST100'ü
al-tut etmekten daha kötü sonuç verdi. Sınanan hipotez: değer kaynağı HANGİ
HİSSEYİ seçtiğin değil, PİYASADA OLUP OLMAMA ZAMANLAMAN olabilir.

- Başlangıç özsermayesi: 1,000,000 TL
- Maliyet (TÜM varyantlarda aynı): komisyon %0.15 + kayma %0.10 = %0.25 tek yön. Endeks işlemlerine de uygulandı (endeksi izleyen bir ETF varsayımı).
- Sinyal gün T KAPANIŞINDA üretilir, emir gün T+1 AÇILIŞINDA gerçekleşir.

## Varyantlar

- **AL_TUT** (endeks): XU100 al ve tut (referans)
- **REJIM_MA200** (endeks): Kapanış > MA200 -> yatırımda, altı -> %100 nakit
- **REJIM_MA200_TAMPON** (endeks): MA200 %+3 üstünde gir, %-3 altında çık
- **REJIM_MA50_200** (endeks): MA50 > MA200 -> yatırımda (golden/death cross)
- **ROTASYON_REJIMSIZ** (rotasyon): V3 momentum rotasyonu, rejim kapısı KAPALI
- **ROTASYON_SEYREK** (rotasyon): V3 rotasyonu, rebalans 60 gün (20 yerine)
- **ROTASYON_20POZ** (rotasyon): V3 rotasyonu, 20 pozisyon (10 yerine)

## Geliştirme dönemi: 2019-01-01 → 2023-12-31

| Varyant | CAGR | Maks düşüş | Sharpe (yıllık) | İşlem sayısı | Piyasada kalma % |
|---|---:|---:|---:|---:|---:|
| AL_TUT (referans) | %53.22 | %-31.81 | 1.66 | 1 | %100.0 |
| REJIM_MA200 | %35.93 | %-23.36 | 1.30 | 39 | %84.7 |
| REJIM_MA200_TAMPON | %35.36 | %-26.94 | 1.28 | 13 | %84.1 |
| REJIM_MA50_200 | %35.22 | %-31.81 | 1.25 | 7 | %83.1 |
| ROTASYON_REJIMSIZ | %63.82 | %-34.12 | 1.77 | 153 | %92.8 |
| ROTASYON_SEYREK | %22.64 | %-27.88 | 1.00 | 116 | %46.0 |
| ROTASYON_20POZ | %35.24 | %-29.58 | 1.45 | 327 | %61.7 |

## Test dönemi (DOKUNULMAMIŞ): 2024-01-01 → 2026-09-10

| Varyant | CAGR | Maks düşüş | Sharpe (yıllık) | İşlem sayısı | Piyasada kalma % |
|---|---:|---:|---:|---:|---:|
| AL_TUT (referans) | %27.02 | %-22.83 | 1.14 | 1 | %99.9 |
| REJIM_MA200 | %12.61 | %-35.05 | 0.69 | 21 | %79.6 |
| REJIM_MA200_TAMPON | %13.83 | %-33.95 | 0.72 | 7 | %81.9 |
| REJIM_MA50_200 | %13.07 | %-32.96 | 0.70 | 5 | %76.3 |
| ROTASYON_REJIMSIZ | %11.75 | %-41.52 | 0.57 | 81 | %97.4 |
| ROTASYON_SEYREK | %3.95 | %-36.94 | 0.30 | 64 | %42.5 |
| ROTASYON_20POZ | %8.42 | %-31.68 | 0.55 | 166 | %54.4 |

## Metrik notları (dürüstlük şartı)

- **Maks düşüş**: günlük mark-to-market özsermaye eğrisi üzerinden; negatif
  sayı, mutlak değeri KÜÇÜK olan daha iyidir.
- **Sharpe (yıllık)**: günlük getirilerin ortalaması / standart sapması ×
  √252, **risksiz faiz = 0** varsayımıyla. Türkiye'de mevduat/
  repo faizi sıfırdan çok uzak olduğu için bu Sharpe MUTLAK bir kalite ölçüsü
  DEĞİLDİR; yalnız varyantları birbirine göre sıralamak için kullanılmalıdır.
- **İşlem sayısı**: endeks varyantlarında GERÇEKLEŞEN EMİR sayısı (giriş ve
  çıkış ayrı sayılır); rotasyon varyantlarında V3 motorunun kendi tanımı olan
  KAPANAN POZİSYON sayısı. İki aile arasında doğrudan kıyaslanamaz.
- **Piyasada kalma %**: ortalama yatırım oranı = mean(pozisyon değeri /
  özsermaye). Endeks varyantlarında gün başına 0 veya 1 olduğu için
  "yatırımda geçirilen gün yüzdesi"ne eşittir; rotasyon varyantlarında
  kısmi maruziyet mümkün olduğundan ORTALAMA MARUZİYET anlamına gelir.
- Tüm dönemler **nominal TL** üzerinden hesaplanmıştır; enflasyon
  düzeltmesi YAPILMAMIŞTIR. Al-tut referansı da aynı ölçekte olduğu için
  KIYAS geçerlidir, ama mutlak CAGR rakamları reel getiri değildir.

_Üretim: `v2/deney_lab.py` — 2026-09-10 14:59_
