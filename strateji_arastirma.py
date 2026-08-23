# -*- coding: utf-8 -*-
"""
strateji_arastirma.py — "Ne zaman alınır, ne zaman satılır?" sorusunu
BIST verisiyle TEST eder.
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR
─────────
Sanal portföy 28 Tem – 21 Ağu 2026 arasında %-1,59 yaparken BIST 100 %+5,89
yükseldi; motor endeksin %7,49 gerisinde kaldı. Backtest de gösterdi ki motor
puanının ileri getiriyle korelasyonu +0,012 — yani pratikte yön öngörmüyor.
Sorun uygulamada değil, SEÇİM YÖNTEMİNDE.

Bu script, akademik literatürde en sağlam belgelenmiş yöntemleri BIST verisi
üzerinde tek tek ölçer. Hiçbirini "doğru kabul etmez" — BIST'te işe yaramazsa
bunu açıkça yazar.

TEST EDİLEN YÖNTEMLER VE KAYNAKLARI
───────────────────────────────────
1) 12-1 MOMENTUM  (Jegadeesh & Titman 1993; 30+ yıl doğrulanmış)
   Son 12 ayın getirisi, ANCAK SON AY HARİÇ. Son ay dışlanır çünkü çok kısa
   vadeli getiriler TERSİNE DÖNER (mikroyapı etkisi). Bu, mevcut motorumuzun
   yaptığının tam tersidir: motor RSI/MACD gibi kısa vadeli göstergelerle son
   günlerin hareketini kovalıyor — literatürün "kaçının" dediği şey.

2) MUTLAK MOMENTUM FİLTRESİ  (Antonacci, Dual Momentum)
   Sadece "diğerlerine göre iyi" olan değil, KENDİ BAŞINA da yükselen hisse
   alınır. Ayrıca endeks kendi uzun vadeli ortalamasının altındaysa piyasadan
   çıkılır. Antonacci'nin testinde maksimum düşüşü %60'tan %23'e indirmiş.
   Bizim motorumuzun "her zaman tam yatırımlı" kuralının tam karşıtı.

3) VOLATİLİTEYE GÖRE ÖLÇEKLEME  (Barroso & Santa-Clara 2015)
   Momentum çökmeleri, momentumun kendi oynaklığı yükseldiğinde gelir.
   Oynaklık yüksekken pozisyon küçültülür. Sharpe 0,53 → 0,97.

4) KISA VADELİ TERSİNE DÖNÜŞ  (kontrol testi)
   Son 1 ayın getirisi. Literatür NEGATİF öngörücü olduğunu söyler. Eğer
   BIST'te de negatifse, motorun kısa vadeli gösterge ağırlığı zararlıdır.

⚠️ BIST UYARISI: Momentum ABD'de sağlam ama BIST literatürü KARIŞIK — bazı
çalışmalar BIST100'de ortalamaya dönüş buluyor. Bu yüzden hiçbir sonuç
peşinen kabul edilmez; walk-forward (ilk yarı / ikinci yarı) tutarlılık
kontrolü yapılır. Bir yöntem sadece bir dönemde işe yarıyorsa TESADÜF
sayılır ve öyle raporlanır.

ÇALIŞTIRMA:  STRATEJI_ARASTIRMA.bat   (30-60 dakika sürebilir)
Sonuç: strateji_arastirma_sonuc.txt
"""
from __future__ import annotations

import os
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import veri_katmani as vk
import analiz_motoru as am

KLASOR = os.path.dirname(os.path.abspath(__file__))
SONUC_DOSYASI = os.path.join(KLASOR, "strateji_arastirma_sonuc.txt")
CSV_DOSYASI = os.path.join(KLASOR, "strateji_arastirma_veri.csv")

# ── Ayarlar ──────────────────────────────────────────────────────────────────
YIL = 5.0                    # kaç yıllık geçmiş
KAPSAM = "TUM"
TUR_MALIYETI = 0.50          # komisyon+slipaj, gidiş-dönüş %  (backtest_motoru ile aynı)
MIN_HACIM_MTL = 5.0          # likidite filtresi (milyon TL, 20 günlük ort.)
UST_N = 10                   # portföyde kaç hisse
REBALANS_GUN = 21            # ~1 ay (aylık rebalans — devir maliyetini düşürür)
ILERI = 21                   # sonraki rebalansa kadarki getiri


def _log(mesaj, dosya=None):
    print(mesaj)
    if dosya is not None:
        dosya.write(mesaj + "\n")
        dosya.flush()


# ─────────────────────────────────────────────────────────────────────────────
# ÖZELLİKLER — hepsi SADECE t anına kadarki veriden hesaplanır (sızıntı yok)
# ─────────────────────────────────────────────────────────────────────────────
def ozellikler(kapanis: pd.Series, yuksek=None, dusuk=None, hacim=None,
               i: int = None) -> dict | None:
    """t=i anındaki özellikler. i'den SONRAKİ hiçbir veri kullanılmaz."""
    if i is None:
        i = len(kapanis) - 1
    if i < 260:
        return None
    p = kapanis.iloc[:i + 1]          # ← t'ye kadar (t dahil), sonrası YOK
    son = float(p.iloc[-1])
    if not np.isfinite(son) or son <= 0:
        return None

    def getiri(gun_once_bas, gun_once_bit=0):
        try:
            a = float(p.iloc[-1 - gun_once_bas])
            b = float(p.iloc[-1 - gun_once_bit]) if gun_once_bit else son
            return 100 * (b / a - 1) if a > 0 else None
        except Exception:
            return None

    # 12-1 momentum: t-252 → t-21 (SON AY HARİÇ — kısa vadeli tersine dönüş)
    mom_12_1 = getiri(252, 21)
    # 6-1 momentum
    mom_6_1 = getiri(126, 21)
    # Son 1 ay (literatürde NEGATİF öngörücü — kontrol testi)
    son_1ay = getiri(21, 0)
    # Mutlak momentum: 12 aylık getiri pozitif mi + MA200 üstünde mi
    mom_12 = getiri(252, 0)
    ma200 = float(p.tail(200).mean()) if len(p) >= 200 else np.nan
    ma50 = float(p.tail(50).mean()) if len(p) >= 50 else np.nan
    # Volatilite (yıllık %)
    gunluk = p.pct_change().tail(126)
    vol = float(gunluk.std() * np.sqrt(252) * 100) if len(gunluk) > 30 else np.nan

    hacim_mtl = np.nan
    if hacim is not None:
        try:
            h = hacim.iloc[:i + 1].tail(20)
            k = p.tail(20)
            hacim_mtl = float((k * h).mean()) / 1e6
        except Exception:
            pass

    return {
        "mom_12_1": mom_12_1,
        "mom_6_1": mom_6_1,
        "son_1ay": son_1ay,
        "mom_12": mom_12,
        "ma200_ustunde": 1 if (np.isfinite(ma200) and son > ma200) else 0,
        "ma50_ustunde": 1 if (np.isfinite(ma50) and son > ma50) else 0,
        "volatilite": vol,
        "hacim_mtl": hacim_mtl,
        "fiyat": son,
    }


def veri_topla(veriler: dict, endeks: pd.Series, dosya) -> pd.DataFrame:
    """Her hisse için REBALANS_GUN aralıklarla özellik + ileri getiri tablosu."""
    satirlar = []
    toplam = len(veriler)
    for sira, (sembol, df) in enumerate(veriler.items(), 1):
        if sira % 50 == 0:
            _log(f"    ... {sira}/{toplam} hisse işlendi", dosya)
        try:
            if df is None or len(df) < 300 or "Close" not in df.columns:
                continue
            kapanis = pd.to_numeric(df["Close"], errors="coerce")
            hacim = pd.to_numeric(df.get("Volume"), errors="coerce")
            n = len(kapanis)
            for i in range(260, n - ILERI, REBALANS_GUN):
                o = ozellikler(kapanis, hacim=hacim, i=i)
                if o is None:
                    continue
                ileri_fiyat = float(kapanis.iloc[i + ILERI])
                if not np.isfinite(ileri_fiyat) or ileri_fiyat <= 0:
                    continue
                o["sembol"] = sembol
                o["tarih"] = kapanis.index[i]
                o["ileri_getiri"] = 100 * (ileri_fiyat / o["fiyat"] - 1)
                # Endeksin AYNI dönemdeki getirisi (endeks üstü hesabı için)
                o["endeks_getiri"] = np.nan
                if endeks is not None:
                    try:
                        e = endeks.reindex(kapanis.index).ffill()
                        e0, e1 = float(e.iloc[i]), float(e.iloc[i + ILERI])
                        if np.isfinite(e0) and e0 > 0:
                            o["endeks_getiri"] = 100 * (e1 / e0 - 1)
                    except Exception:
                        pass
                satirlar.append(o)
        except Exception:
            continue
    return pd.DataFrame(satirlar)


# ─────────────────────────────────────────────────────────────────────────────
# ANALİZ
# ─────────────────────────────────────────────────────────────────────────────
def ongoru_gucu(d: pd.DataFrame, dosya):
    _log("\n" + "═" * 74, dosya)
    _log("  1) HANGİ ÖZELLİK GELECEĞİ ÖNGÖRÜYOR? (Spearman korelasyon)", dosya)
    _log("═" * 74, dosya)
    _log("  Korelasyon 0'a yakınsa öngörü YOK demektir. |0,05| üstü zayıf ama", dosya)
    _log("  anlamlı, |0,10| üstü BIST için iyi sayılır.\n", dosya)
    _log(f"  {'Özellik':16s}{'ham getiri':>13s}{'endeks üstü':>14s}{'n':>10s}", dosya)
    _log("  " + "─" * 60, dosya)
    d = d.copy()
    d["endeks_ustu"] = d["ileri_getiri"] - d["endeks_getiri"]
    for a in ["mom_12_1", "mom_6_1", "son_1ay", "mom_12", "volatilite"]:
        if a not in d.columns:
            continue
        x = d[[a, "ileri_getiri", "endeks_ustu"]].dropna()
        if len(x) < 100:
            continue
        r1 = x[a].corr(x["ileri_getiri"], method="spearman")
        r2 = x[a].corr(x["endeks_ustu"], method="spearman")
        _log(f"  {a:16s}{r1:>+12.4f}{r2:>+13.4f}{len(x):>10,}", dosya)
    _log("\n  YORUM: 'son_1ay' NEGATİF çıkarsa, literatürdeki kısa vadeli tersine", dosya)
    _log("  dönüş etkisi BIST'te de var demektir — motorun RSI/MACD gibi kısa", dosya)
    _log("  vadeli göstergelere yaslanması bu durumda ZARARLIDIR.", dosya)


def _strateji_getirileri(d: pd.DataFrame, siralama: str, n=UST_N,
                         filtre=None, ters=False) -> pd.Series:
    """Her rebalans tarihinde en iyi n hisseyi seç, ortalama getirisini al."""
    x = d if filtre is None else d[filtre(d)]
    out = {}
    for t, g in x.groupby("tarih"):
        g = g.dropna(subset=[siralama, "ileri_getiri"])
        if len(g) < n:
            continue
        sec = g.nsmallest(n, siralama) if ters else g.nlargest(n, siralama)
        out[t] = sec["ileri_getiri"].mean()
    return pd.Series(out).sort_index()


def strateji_testi(d: pd.DataFrame, dosya):
    _log("\n" + "═" * 74, dosya)
    _log(f"  2) STRATEJİ TESTİ — her ay en iyi {UST_N} hisseyi al, 1 ay tut", dosya)
    _log("═" * 74, dosya)
    _log(f"  Tur maliyeti %{TUR_MALIYETI:.2f} DÜŞÜLMÜŞTÜR.", dosya)
    _log("  'Endeks üstü' sütunu asıl ölçüttür: negatifse endekse yatırmak daha iyi.\n", dosya)

    likit = lambda x: x["hacim_mtl"].fillna(0) >= MIN_HACIM_MTL
    endeks_ay = d.groupby("tarih")["endeks_getiri"].mean()
    evren_ay = d.groupby("tarih")["ileri_getiri"].mean()

    _log(f"  {'Strateji':40s}{'aylık':>9s}{'endeks üstü':>13s}{'kazanan':>9s}", dosya)
    _log("  " + "─" * 71, dosya)

    def yaz(ad, seri, maliyet=True):
        if seri is None or len(seri) == 0:
            _log(f"  {ad:40s}{'veri yok':>9s}", dosya)
            return None
        ortak = seri.index.intersection(endeks_ay.index)
        s = seri.reindex(ortak)
        e = endeks_ay.reindex(ortak)
        net = s - (TUR_MALIYETI if maliyet else 0.0)
        fark = (net - e).mean()
        _log(f"  {ad:40s}{net.mean():>+8.2f}%{fark:>+12.2f}%{100*(net>0).mean():>8.0f}%", dosya)
        return fark

    yaz("BIST 100 (endeks, al-tut)", endeks_ay, maliyet=False)
    yaz("Tüm hisseler eşit ağırlık (al-tut)", evren_ay, maliyet=False)
    _log("", dosya)

    sonuclar = {}
    sonuclar["12-1 momentum"] = yaz(
        f"12-1 momentum — en iyi {UST_N}", _strateji_getirileri(d, "mom_12_1", filtre=likit))
    sonuclar["6-1 momentum"] = yaz(
        f"6-1 momentum — en iyi {UST_N}", _strateji_getirileri(d, "mom_6_1", filtre=likit))
    sonuclar["son 1 ay (kovalama)"] = yaz(
        f"Son 1 ay getirisi — en iyi {UST_N}", _strateji_getirileri(d, "son_1ay", filtre=likit))
    sonuclar["son 1 ay TERSİ"] = yaz(
        f"Son 1 ayda en ÇOK DÜŞEN {UST_N}", _strateji_getirileri(d, "son_1ay", filtre=likit, ters=True))
    _log("", dosya)

    # Mutlak momentum filtresi (Antonacci)
    mutlak = lambda x: likit(x) & (x["ma200_ustunde"] == 1) & (x["mom_12"].fillna(-1) > 0)
    sonuclar["12-1 + mutlak filtre"] = yaz(
        f"12-1 mom + MUTLAK filtre (MA200 üstü)", _strateji_getirileri(d, "mom_12_1", filtre=mutlak))

    # Düşük volatilite tercihi (momentum çökmesi koruması)
    d2 = d.copy()
    med_vol = d2["volatilite"].median()
    dusuk_vol = lambda x: mutlak(x) & (x["volatilite"].fillna(999) <= med_vol)
    sonuclar["12-1 + mutlak + düşük vol"] = yaz(
        f"12-1 mom + mutlak + DÜŞÜK volatilite", _strateji_getirileri(d, "mom_12_1", filtre=dusuk_vol))
    return sonuclar


def walk_forward(d: pd.DataFrame, dosya):
    _log("\n" + "═" * 74, dosya)
    _log("  3) WALK-FORWARD — sonuç TESADÜF mü, TUTARLI mı?", dosya)
    _log("═" * 74, dosya)
    _log("  Veri ikiye bölünür. Bir yöntem SADECE bir yarıda işe yarıyorsa", dosya)
    _log("  tesadüftür ve KULLANILMAMALIDIR. İki yarıda da pozitifse güvenilir.\n", dosya)

    orta = d["tarih"].quantile(0.5)
    d1, d2 = d[d["tarih"] < orta], d[d["tarih"] >= orta]
    _log(f"  1. yarı: {d['tarih'].min():%d.%m.%Y} → {orta:%d.%m.%Y}", dosya)
    _log(f"  2. yarı: {orta:%d.%m.%Y} → {d['tarih'].max():%d.%m.%Y}\n", dosya)
    _log(f"  {'Strateji':40s}{'1.yarı':>11s}{'2.yarı':>11s}{'karar':>10s}", dosya)
    _log("  " + "─" * 72, dosya)

    likit = lambda x: x["hacim_mtl"].fillna(0) >= MIN_HACIM_MTL
    mutlak = lambda x: likit(x) & (x["ma200_ustunde"] == 1) & (x["mom_12"].fillna(-1) > 0)

    for ad, kolon, flt, ters in [
        ("12-1 momentum", "mom_12_1", likit, False),
        ("6-1 momentum", "mom_6_1", likit, False),
        ("Son 1 ay kovalama", "son_1ay", likit, False),
        ("12-1 + mutlak filtre", "mom_12_1", mutlak, False),
    ]:
        farklar = []
        for yari in (d1, d2):
            s = _strateji_getirileri(yari, kolon, filtre=flt, ters=ters)
            e = yari.groupby("tarih")["endeks_getiri"].mean()
            ortak = s.index.intersection(e.index)
            if len(ortak) == 0:
                farklar.append(np.nan); continue
            farklar.append(((s.reindex(ortak) - TUR_MALIYETI) - e.reindex(ortak)).mean())
        a, b = farklar
        if np.isnan(a) or np.isnan(b):
            karar = "veri yok"
        elif a > 0 and b > 0:
            karar = "✓ TUTARLI"
        elif a > 0 or b > 0:
            karar = "~ karışık"
        else:
            karar = "✗ işe yaramaz"
        _log(f"  {ad:40s}{a:>+10.2f}%{b:>+10.2f}%{karar:>10s}", dosya)


def main():
    with open(SONUC_DOSYASI, "w", encoding="utf-8") as f:
        _log("═" * 74, f)
        _log("  STRATEJİ ARAŞTIRMASI — 'ne zaman al, ne zaman sat?'", f)
        _log(f"  {dt.datetime.now():%d.%m.%Y %H:%M}", f)
        _log("═" * 74, f)
        _log("  Test edilen yöntemler akademik literatürden alınmıştır ama", f)
        _log("  hiçbiri peşinen doğru kabul EDİLMEZ — BIST verisiyle sınanır.", f)
        _log(f"\n  Kapsam: {KAPSAM} · {YIL:.0f} yıl · rebalans {REBALANS_GUN} iş günü", f)
        _log(f"  Portföy: en iyi {UST_N} hisse · maliyet %{TUR_MALIYETI}/tur", f)

        _log("\n  Veri indiriliyor (birkaç dakika sürebilir)...", f)
        semboller = vk.sembol_listesi(KAPSAM)
        veriler = vk.toplu_fiyat(semboller, yil=YIL)
        _log(f"  {len(veriler)}/{len(semboller)} hissenin verisi geldi.", f)

        endeks_df = vk.endeks_gecmisi(YIL)
        endeks = None
        if endeks_df is not None and len(endeks_df):
            endeks = pd.to_numeric(endeks_df["Close"], errors="coerce")
            _log(f"  Endeks verisi: {len(endeks)} gün.", f)
        else:
            _log("  ⚠️ Endeks verisi alınamadı — endeks üstü hesabı yapılamayacak.", f)

        _log("\n  Özellikler hesaplanıyor...", f)
        d = veri_topla(veriler, endeks, f)
        if d.empty:
            _log("\n  ❌ Hiç veri üretilemedi. İşlem durduruldu.", f)
            return
        d.to_csv(CSV_DOSYASI, index=False)
        _log(f"\n  {len(d):,} gözlem üretildi ({d['sembol'].nunique()} hisse, "
             f"{d['tarih'].nunique()} rebalans tarihi).", f)
        _log(f"  Ham veri: {os.path.basename(CSV_DOSYASI)}", f)

        ongoru_gucu(d, f)
        strateji_testi(d, f)
        walk_forward(d, f)

        _log("\n" + "═" * 74, f)
        _log("  SINIRLAR — bu sonuçları okurken dikkat", f)
        _log("═" * 74, f)
        _log("  • HAYATTA KALMA YANLILIĞI: Sadece bugün işlem gören hisseler var.", f)
        _log("    Borsadan çıkmış/battı olanlar yok — sonuçlar İYİMSER.", f)
        _log("  • Tek bir dönem: BIST'in bu 5 yılı yüksek enflasyon ve güçlü", f)
        _log("    yükseliş dönemiydi. Başka rejimde sonuç farklı olabilir.", f)
        _log("  • Tavan/taban ve likidite kısıtları basitleştirilmiştir.", f)
        _log("  • Walk-forward 'karışık' veya 'işe yaramaz' çıkan bir yöntem", f)
        _log("    KULLANILMAMALIDIR — tek dönemde iyi görünmesi tesadüf olabilir.", f)
        _log("\n  Rapor: " + os.path.basename(SONUC_DOSYASI), f)
        _log("═" * 74, f)


if __name__ == "__main__":
    main()
