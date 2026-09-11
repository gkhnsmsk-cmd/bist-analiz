# PUSULA V6 — Yoğunlaştırılmış (3-5 pozisyon) Walk-Forward Backtest Sonucu

Çalıştırma: 11.09.2026 13:51 UTC · Başlangıç özsermayesi: 1,000,000 TL

**Kullanıcı hedefi (pazarlık yok):** TEST döneminde CAGR >= %55, maksimum düşüş <= %25, profit factor >= 1.3 — üçü BİRDEN sağlanmalı.

---

## KULLANICI HEDEFİ GEÇİLEMEDİ

Aşağıdaki eşiklerden en az biri test döneminde sağlanmadı:

- CAGR %19.23 — eşik: >=%55
- Maksimum düşüş %29.0 — eşik: <=%25

---

### TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir

| Metrik | V6 (bu sistem) | Kullanıcı hedefi | BIST100 al-ve-tut |
|---|---|---|---|
| **CAGR** | **%19.23** | >=%55 | %26.62 |
| **Maksimum düşüş** | **%-29.0** | <=%25 | %-22.8 |
| Profit factor | **1.41** | >=1.3 | — |
| İşlem sayısı | 125 | — | — (tek alım) |
| Kazanma oranı | %59.2 | — | — |
| Endeks üstü CAGR farkı | %-7.43 | — | — |

### Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı

| Metrik | V6 (bu sistem) | Kullanıcı hedefi | BIST100 al-ve-tut |
|---|---|---|---|
| **CAGR** | **%29.49** | >=%55 | %53.22 |
| **Maksimum düşüş** | **%-23.9** | <=%25 | %-31.8 |
| Profit factor | **1.73** | >=1.3 | — |
| İşlem sayısı | 233 | — | — (tek alım) |
| Kazanma oranı | %60.5 | — | — |
| Endeks üstü CAGR farkı | %-23.74 | — | — |

---

## Tasarım özeti (V6 = yoğunlaştırılmış / az sayıda yüksek-güven pozisyon)

- **Evren:** v2/evren.py likidite/fiyat filtresi + v6_skor.py'nin DÖRT sert şartı (trend hizası EMA20/EMA50/MA200 üstünde, hacim >=2x patlama, 52 hafta zirvesine %95 yakınlık, pozitif momentum + ATR/Kapanış<=%9).
- **Pozisyon sayısı:** 3-5 (10 değil) — az ama yüksek ağırlık (%20-33 bandı).
- **Çıkış:** ATR-bazlı stop (-%8/-10 bandı), +%15'te yarısı realize + stop başabaşa, +%25 sonrası trailing sıkılaşır, rejim R3/R4'te TAM çıkış, MA200 altında 3 gün üst üste kapanışta trend çıkışı.
- **Rejim kapısı:** İKİLİ ve AGRESİF (R1=tam yatırım, R2=yarı, R3/R4=tam nakit; kademeli yaklaşma YOK) — sermaye korumasını pozisyon azlığı değil rejim kapısı üstlenir.
- **Tarama sıklığı:** GÜNLÜK (haftalık/aylık değil) — güçlü kırılımları kaçırmamak için.

## Bilinen sınırlar (dürüstlük notu)

- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor.
- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans limit verisi değil.
- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor.
- **Yoğunlaşma riski BİLİNÇLİ:** 3-5 pozisyonla tek isim riski V2/V3'e göre çok daha yüksektir; bu, CAGR hedefine ulaşmak için göze alınan açık bir riziko dengesidir (rejim kapısı ve ATR-bazlı stop bunu sınırlamaya çalışır, ORTADAN KALDIRMAZ).
- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.
