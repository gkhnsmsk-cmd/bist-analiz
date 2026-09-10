# PUSULA V3 — Göreli Güç Rotasyonu — Walk-Forward Backtest Sonucu

Çalıştırma: 10.09.2026 09:12 UTC · Başlangıç özsermayesi: 1,000,000 TL

---

## SİSTEM ENDEKSİ YENEMEDİ — TAVSIYE_VERME MODU

**STRATEJI_V3.md §9 gereği: 'Endeksi yenemiyorsa sistem bunu büyük harfle yazar ve TAVSIYE_VERME modunda kalır.' Bu sistemin şu anki hâliyle kullanıcıya sinyal ÜRETMEMESİ gerekir — endeks fonu almak, bu sistemi çalıştırmaktan istatistiksel olarak daha iyi bir sonuç vermiştir.**

---

### TEST dönemi (2024-01-01 → bugün) — DOKUNULMAMIŞ, karar bu tabloya göre verilir

| Metrik | V3 (bu sistem) | BIST100 al-ve-tut | V2 (eski, referans) |
|---|---|---|---|
| **CAGR** | **%-2.32** | %27.02 | — |
| **Maksimum düşüş** | **%-94.9** | %-22.8 | %-30.9 |
| İşlem sayısı | 102 | — (tek alım) | — |
| Kazanma oranı | %35.3 | — | — |
| Profit factor | 0.84 | — | 0.99 |
| Rebalans sayısı | 34 | — | — |
| Yıllık turnover | %693 | — | — |

### Geliştirme dönemi (2019-01-01 → 2023-12-31) — yalnız kıyas amaçlı

| Metrik | V3 (bu sistem) | BIST100 al-ve-tut | V2 (eski, referans) |
|---|---|---|---|
| **CAGR** | **%34.49** | %53.22 | %17.00 |
| **Maksimum düşüş** | **%-29.9** | %-31.8 | %-25.9 |
| İşlem sayısı | 209 | — (tek alım) | — |
| Kazanma oranı | %45.5 | — | — |
| Profit factor | 2.32 | — | 1.80 |
| Rebalans sayısı | 63 | — | — |
| Yıllık turnover | %787 | — | — |

---

## Bilinen sınırlar (dürüstlük notu)

- **Hayatta kalma yanlılığı:** Evren bugünkü BIST100 listesinden türetiliyor; geçmişte borsadan çıkmış/endeksten düşmüş hisseler yok. Bu, sonuçları olduğundan **iyi** gösterme eğilimindedir (hem V3 hem al-tut kıyası için geçerli).
- **Tavan/taban tespiti** ±%9.5 günlük getiri vekiliyle yapılıyor, gerçek seans limit verisi değil.
- **Sektör haritası kısmi** — eşlenmemiş hisseler 'Diğer' sayılıyor, bu da sektör yoğunlaşma kısıtını zayıflatıyor.
- **Trailing/zaman/kâr-hedefi stopu YOKTUR** (bilinçli tasarım kararı, bkz. STRATEJI_V3.md §0/§6) — tek koruma felaket stopu (-%25) ve rejim kapısıdır; bu, V2'ye göre TEK İSİM riskini daha geç keser ama piyasa maruziyetini korur.
- Tek bir piyasa rejimi/ülke; sonuçlar başka dönemlere genellenemez.
