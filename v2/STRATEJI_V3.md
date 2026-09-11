# PUSULA V3 — GÖRELİ GÜÇ ROTASYONU (endeksi yenmeye yönelik mimari)

Sürüm 1.0 · 10.09.2026 · V2'nin yerine geçer, V2 altyapısını (veri/evren/rejim/backtest) yeniden kullanır.

---

## 0. V2 NEDEN YETMEDİ — ölçülmüş kanıt

Walk-forward run #2 (dokunulmamış test dönemi 2024-01 → 2026-09):

| | V2 sonucu | Endeks |
|---|---|---|
| Toplam getiri (32 ay) | **+%1.4** | ~+%95 |
| Maksimum düşüş | **-%30.9** | — |
| Profit factor | 0.99 | — |

Geliştirme döneminde (2019-2023) işlem istatistikleri iyiydi (PF 1.80,
expectancy 0.34R) **ama CAGR yine de %17 vs endeks %53** kaldı.

**Teşhis — yapısal, ayarlanabilir değil:**

```
Getiri ≈ yıllık_işlem × expectancy(R) × işlem_başına_risk
       ≈ 65 × 0.34 × %1  ≈  yıllık %22   ← TAVAN
```

İşlem başına %1 risk + sıkı ATR stop = düşük ortalama piyasa maruziyeti.
BIST gibi yüksek sürüklenmeli (enflasyonlu) bir piyasada **piyasa dışında
geçen zaman, endekse karşı bileşik kayıptır.** V1 stop'suzdu → battı.
V2 stop'luydu → piyasanın dışında kaldı. İkisi de aynı hatanın iki yüzü.

---

## 1. V3'ÜN TEMEL FİKRİ

> Rejim sağlıklıyken **neredeyse tam yatırımda kal**, ama parayı endeksten
> daha hızlı yükselen hisselerde tut. Düşüş kontrolünü tek tek stop'larla
> değil, **rejim kapısıyla** yap.

Trend piyasasında sıkı stop, seni iyi pozisyonlardan silkeleyip atar
(whipsaw). Bunun yerine çıkış kararı **göreli sıralamaya** bağlanır:
hisse liderliği kaybederse çıkarsın, gürültüyle sarsıldığında değil.

**Kıyas ölçütü artık açık:** BIST100'ü al-ve-tut. Sistem bunu yenemiyorsa
var olmasının anlamı yok ve raporda böyle yazar.

---

## 2. EVREN

V2 §3.1 ile aynı (yeniden kullanılır):
20g medyan TL hacim ≥ 20.000.000 · Kapanış ≥ 2.00 TL · ≥250 gün geçmiş ·
son 5 günde tavan/taban yok · yalnız pay senedi.

---

## 3. GÖRELİ GÜÇ SKORU

Her rebalans gününde, evrendeki her hisse için:

```
mom6  = Kapanış[-21] / Kapanış[-126] - 1     # 6 ay, son 1 ay HARİÇ
mom12 = Kapanış[-21] / Kapanış[-252] - 1     # 12 ay, son 1 ay HARİÇ
ham   = 0.5 × mom6 + 0.5 × mom12
skor  = ham / yillik_volatilite               # riske göre düzeltilmiş momentum
```

**Son 1 ay neden dışlanıyor:** kısa vadeli tersine dönüş (short-term
reversal) etkisi momentumu kirletir; akademik standart "12-1" kuralıdır.

**Volatiliteye bölme neden:** aynı momentumu daha az oynaklıkla üreten
hisse daha kalitelidir; ayrıca V1'in "en şişkin hisseyi tepeye koyma"
hatasını da doğal olarak bastırır.

## 4. UYGUNLUK FİLTRELERİ (hepsi zorunlu)

1. `Kapanış > MA200` — kendi uzun vadeli trendi yukarı
2. `mom6 > 0` — mutlak momentum pozitif
3. `ATR14 / Kapanış ≤ 0.08` — aşırı oynak çöp elenir
4. Pozisyon değeri ≤ 20g medyan TL hacmin **%1**'i

---

## 5. PORTFÖY KURULUMU

- **Pozisyon sayısı:** en yüksek skorlu **10** hisse
- **Ağırlık:** ters-volatilite (`1/ATR%`), normalize edilir
  - tek hisse tavanı **%15**, tabanı **%5**
- **Sektör:** aynı sektörden en fazla **3**
- **Nakit:** rejimin izin verdiği orandan artan kısım

Ters-volatilite ağırlıklandırma, eşit ağırlığa göre düşüşü belirgin azaltır
ve tek bir oynak ismin portföyü sürüklemesini engeller.

---

## 6. REBALANS VE ÇIKIŞ

**Rebalans sıklığı:** her **20 işlem günü** (≈ aylık).

Rebalans gününde:
- Portföydeki hisse, skor sıralamasında **ilk 20**'nin dışına düştüyse → SAT
- `Kapanış < MA200` olduysa → SAT
- Boşalan yerler, uygunluk filtrelerini geçen en yüksek skorlulardan doldurulur
- Kalan pozisyonların ağırlıkları hedefe geri çekilir (turnover'ı azaltmak
  için sapma **%5 puandan** küçükse dokunulmaz)

**Rebalans dışı GÜNLÜK kontroller (yalnız iki tanesi):**
1. **Felaket stopu:** girişe göre **-%25** → derhal SAT.
   Bu bir trading stopu değil, tek isim riskine karşı sigortadır
   (V1'de HEDEF -%47 yapmıştı; bu kural onu -%25'te keserdi).
2. **Rejim çıkışı:** rejim R3/R4'e düşerse hedef orana inene kadar
   en düşük skorlu pozisyonlar kapatılır.

**Trailing stop, zaman stopu, kâr hedefi YOKTUR** — hepsi kazananları erken
keser ve V2'nin başarısızlığının doğrudan sebebidir.

---

## 7. REJİM KAPISI (düşüş kontrolünün ANA aracı)

XU100 üzerinden, **her gün** hesaplanır:

| Rejim | Koşul | Hedef yatırım |
|---|---|---|
| **R1** | `XU100 > MA200` ve `MA50 > MA50[-5]` | **%100** |
| **R2** | `XU100 > MA200` ve `MA50 ≤ MA50[-5]` | **%80** |
| **R3** | `XU100 < MA200` | **%30** |
| **R4** | `XU100 < MA200` ve `XU100 < MA200[-10] × 0.97` | **%0** |

Genişlik teyidi: evrenin MA50 üzerindeki oranı < %30 ise bir kademe aşağı.

Yükselirken kademeli (günde en fazla %33 puan), düşerken **anında**.

> V2'ye göre R1/R2 oranları yükseltildi (%100/%60 → %100/%80): amaç boğa
> piyasasında maruziyeti korumak, çünkü asıl kayıp orada yaşanıyordu.

---

## 8. MALİYET MODELİ

V2 §7 ile aynı: komisyon %0.15 + kayma %0.10 (düşük likiditede %0.25),
tek yön. Sinyal T kapanışında, emir **T+1 açılışında**. Tavan/taban günü
işlem yok. Aylık rebalans sayesinde turnover V2'nin çok altında olacaktır.

---

## 9. KABUL KRİTERLERİ (§8'in yerine geçer — kullanıcı kararı: "endeksi yenmek zorunlu")

Dokunulmamış test döneminde (2024-01 → bugün), maliyet dahil:

| Metrik | Eşik |
|---|---|
| **CAGR** | **> endeks CAGR** (zorunlu) |
| Maksimum düşüş | **≤ endeksin maksimum düşüşü** |
| Rebalans sayısı | ≥ 24 |
| Yıllık turnover | ≤ 600% (maliyet kontrolü) |

**Rapor artık üç sütun gösterir:** V3 · BIST100 al-ve-tut · V2 (eski).
Endeksi yenemiyorsa sistem bunu büyük harfle yazar ve TAVSIYE_VERME
modunda kalır. Kullanıcıya "endeks fonu al ve bu sistemi kullanma" demek,
kaybettiren bir sistemi çalıştırmaktan iyidir.

---

## 10. NE DEĞİŞMİYOR

- Tek dosya HTML SPA, PC + mobil (V2 arayüzü uyarlanır)
- "Liste değil emir" ilkesi — ama artık emirler aylık rebalansta gelir
- Dürüstlük katmanı: her işlem loglanır, canlı skor kartı, otomatik fren
- Bilinen sınırlar aynen geçerli (hayatta kalma yanlılığı en önemlisi)

---

## 11. MODÜL PLANI

Yeniden kullanılan (değişmeden): `veri.py`, `evren.py`, `backtest.py` iskeleti
Güncellenen: `rejim.py` (§7 oranları)
Yeni: `v3_skor.py` (§3-4), `v3_portfoy.py` (§5-6), `v3_backtest.py` (§9 raporu)

Ana fonksiyon imzaları:

```python
# v3_skor.py
def skorla(veriler: dict, evren: list[str], tarih) -> list[dict]
    """[{'sembol','skor','mom6','mom12','vol','uygun': bool, 'red_nedeni'}] — skora göre azalan."""

# v3_portfoy.py
def hedef_portfoy(siralama: list[dict], veriler: dict, tarih,
                  ozsermaye: float, hedef_oran: float,
                  mevcut: list[dict]) -> dict
    """{'alinacak': [...], 'satilacak': [...], 'hedef_agirliklar': {...}}"""
def gunluk_kontrol(pozisyonlar: list[dict], bugun: dict, rejim: dict) -> list[dict]
    """Yalnız felaket stopu (-%25) ve rejim çıkışı."""

# v3_backtest.py
def calistir(baslangic, bitis, ozsermaye=1_000_000) -> dict
def al_tut_kiyas(endeks_df, baslangic, bitis, ozsermaye) -> dict
    """BIST100 al-ve-tut kıyas serisi — aynı maliyet modeliyle (tek alım)."""
def walk_forward(ozsermaye=1_000_000) -> dict
```
