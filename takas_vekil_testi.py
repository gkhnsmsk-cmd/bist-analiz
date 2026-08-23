# -*- coding: utf-8 -*-
"""
takas_vekil_testi.py — "Birikim/dağıtım" BIST'te geleceği öngörüyor mu?
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR
─────────
Gerçek takas verisine ulaşamıyoruz: İş Yatırım kaynağı ölü, MKK'nın ücretsiz
verisi 10 iş günü gecikmeli ve erişimi belirsiz, güncel veri ücretli.

AMA motorun mevcut "Takas" puanı zaten CMF ve Toplama/Dağıtım çizgisi
kullanıyor. Bu göstergeler tam olarak takas analizinin ölçmeye çalıştığı şeyi
—BİRİKİM (accumulation) / DAĞITIM (distribution)— fiyat ve hacimden tahmin
etmeye çalışır. Yani elimizde zaten bir VEKİL takas göstergesi var ve bugüne
kadar hiç ölçülmedi.

Bu testin mantığı:
  • Vekil gösterge BIST'te ÖNGÖRÜYORSA → birikim/dağıtım fikri BIST'te
    çalışıyor demektir; gerçek takas verisi muhtemelen daha da iyi olur,
    ona para/emek harcamak gerekçelenir.
  • Vekil gösterge HİÇBİR ŞEY öngörmüyorsa → ya fikir BIST'te çalışmıyor,
    ya da hacimden türetilen vekiller yetersiz. İkinci ihtimal gerçek veriyi
    hâlâ değerli kılar ama beklenti düşürülmelidir.

TEST EDİLENLER
──────────────
1) takas_analizi() puanı — motorun KENDİ bileşeni (hiç ölçülmedi)
2) CMF   — Chaikin Money Flow (para giriş/çıkışı)
3) MFI   — Money Flow Index (hacim ağırlıklı RSI)
4) A/D eğimi — Toplama/Dağıtım çizgisinin yönü
5) OBV eğimi — On-Balance Volume yönü
6) UYUŞMAZLIK (divergence) — takas analizinin EN SOMUT kuralı:
      Fiyat ↑ + birikim ↑  → trend sağlam
      Fiyat ↑ + birikim ↓  → yükseliş sürdürülemez ("gizli dağıtım")
   Bu kural Gedik/Matriks kaynaklarında açıkça geçiyor ve test edilebilir.

DİSİPLİN: strateji_arastirma.py ile AYNI. Hiçbir sonuç peşinen kabul
edilmez — Spearman korelasyon, desil monotonluğu, walk-forward tutarlılık,
t-testi anlamlılık ve işlem maliyeti düşülmüş strateji simülasyonu.
Walk-forward'da "karışık" çıkan bir gösterge KULLANILMAZ.

ÇALIŞTIRMA:  TAKAS_VEKIL_TESTI.bat   (30-60 dakika)
Sonuç: takas_vekil_sonuc.txt  ·  Ham veri: takas_vekil_veri.csv
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
SONUC_DOSYASI = os.path.join(KLASOR, "takas_vekil_sonuc.txt")
CSV_DOSYASI = os.path.join(KLASOR, "takas_vekil_veri.csv")

YIL = 5.0
KAPSAM = "TUM"
TUR_MALIYETI = 0.50
MIN_HACIM_MTL = 5.0
UST_N = 10
REBALANS_GUN = 21
ILERI = 21

_C = []


def yaz(m=""):
    print(m)
    _C.append(str(m))


def _egim(seri, n=40):
    """Bir serinin son n gündeki normalize edilmiş eğimi.

    ÖLÇEKLEME NEDEN STANDART SAPMAYLA:
    İlk sürüm ortalama mutlak değere (|y|.mean()) bölüyordu. Bu, FİYAT gibi
    hep pozitif seriler için çalışır ama A/D ve OBV KÜMÜLATİF serilerdir ve
    sıfır civarında salınabilirler. Ortalama sıfıra yaklaşınca bölme ya
    patlıyor ya da NaN dönüyordu — testte A/D eğimi 600 satırın 200'ünde
    NaN çıktı ve o gösterge analizden düştü.
    Standart sapma bu sorunu yaşamaz: serinin kendi oynaklığına göre
    ölçekler, sıfır etrafındaki seriler için de anlamlıdır.
    Sapma sıfırsa (seri tamamen düz) eğim gerçekten 0'dır — NaN değil.
    """
    try:
        s = pd.to_numeric(seri, errors="coerce").dropna().tail(n)
        if len(s) < max(10, n // 2):
            return np.nan
        y = s.values.astype(float)
        if not np.all(np.isfinite(y)):
            return np.nan
        x = np.arange(len(y), dtype=float)
        egim = float(np.polyfit(x, y, 1)[0])
        olcek = float(np.std(y))
        if olcek <= 0:
            return 0.0                 # seri düz → eğim yok (veri eksik DEĞİL)
        return float(egim / olcek)     # birim: standart sapma / gün
    except Exception:
        return np.nan


def ozellikler(df: pd.DataFrame, i: int) -> dict | None:
    """t=i anındaki birikim/dağıtım özellikleri.
    i'den SONRAKİ hiçbir veri kullanılmaz (sızıntı yok)."""
    if i < 260 or i >= len(df):
        return None
    p = df.iloc[:i + 1]                      # ← t'ye kadar (t dahil)
    c = pd.to_numeric(p["Close"], errors="coerce")
    son = float(c.iloc[-1])
    if not np.isfinite(son) or son <= 0:
        return None

    o = {"fiyat": son}

    # 1) Motorun KENDİ takas bileşeni (gerçek takas verisi OLMADAN — vekil hâli)
    try:
        tp, _ = am.takas_analizi(p, {}, None)
        o["takas_puani"] = float(tp)
    except Exception:
        o["takas_puani"] = np.nan

    # 2) CMF — Chaikin Money Flow
    try:
        o["cmf"] = float(am.cmf(p).iloc[-1])
    except Exception:
        o["cmf"] = np.nan

    # 3) MFI — Money Flow Index
    try:
        o["mfi"] = float(am.mfi(p).iloc[-1])
    except Exception:
        o["mfi"] = np.nan

    # 4) A/D çizgisi eğimi
    try:
        ad = am.ad_cizgisi(p)
        o["ad_egim"] = _egim(ad, 40)
    except Exception:
        o["ad_egim"] = np.nan

    # 5) OBV eğimi (varsa)
    try:
        if hasattr(am, "obv"):
            o["obv_egim"] = _egim(am.obv(p), 40)
        else:
            yon = np.sign(c.diff().fillna(0.0))
            hacim = pd.to_numeric(p["Volume"], errors="coerce").fillna(0.0)
            o["obv_egim"] = _egim((yon * hacim).cumsum(), 40)
    except Exception:
        o["obv_egim"] = np.nan

    # 6) UYUŞMAZLIK — fiyat eğimi ile birikim eğimi aynı yönde mi?
    fiyat_egim = _egim(c, 40)
    o["fiyat_egim"] = fiyat_egim
    ad_e = o.get("ad_egim", np.nan)
    if np.isfinite(fiyat_egim) and np.isfinite(ad_e):
        # Pozitif = uyumlu (ikisi aynı yönde), negatif = uyuşmazlık
        o["uyum"] = float(np.sign(fiyat_egim) * np.sign(ad_e))
        o["uyum_gucu"] = float(ad_e - fiyat_egim)   # birikim fiyattan güçlü mü?
        # Takas analizinin klasik kuralı: fiyat YÜKSELİRKEN birikim de artıyor mu
        if fiyat_egim > 0:
            o["yukselirken_birikim"] = float(ad_e)
        else:
            o["yukselirken_birikim"] = np.nan
    else:
        o["uyum"] = np.nan
        o["uyum_gucu"] = np.nan
        o["yukselirken_birikim"] = np.nan

    # Likidite
    try:
        h = pd.to_numeric(p["Volume"], errors="coerce").tail(20)
        o["hacim_mtl"] = float((c.tail(20) * h).mean()) / 1e6
    except Exception:
        o["hacim_mtl"] = np.nan
    return o


def veri_topla(veriler: dict, endeks: pd.Series) -> pd.DataFrame:
    satirlar = []
    toplam = len(veriler)
    for sira, (sembol, df) in enumerate(veriler.items(), 1):
        if sira % 50 == 0:
            yaz(f"    ... {sira}/{toplam} hisse")
        try:
            if df is None or len(df) < 300:
                continue
            if not {"Close", "High", "Low", "Volume"}.issubset(df.columns):
                continue
            c = pd.to_numeric(df["Close"], errors="coerce")
            n = len(df)
            for i in range(260, n - ILERI, REBALANS_GUN):
                o = ozellikler(df, i)
                if o is None:
                    continue
                ileri = float(c.iloc[i + ILERI])
                if not np.isfinite(ileri) or ileri <= 0:
                    continue
                o["sembol"] = sembol
                o["tarih"] = df.index[i]
                o["ileri_getiri"] = 100 * (ileri / o["fiyat"] - 1)
                o["endeks_getiri"] = np.nan
                if endeks is not None:
                    try:
                        e = endeks.reindex(df.index).ffill()
                        e0, e1 = float(e.iloc[i]), float(e.iloc[i + ILERI])
                        if np.isfinite(e0) and e0 > 0:
                            o["endeks_getiri"] = 100 * (e1 / e0 - 1)
                    except Exception:
                        pass
                satirlar.append(o)
        except Exception:
            continue
    return pd.DataFrame(satirlar)


ALANLAR = ["takas_puani", "cmf", "mfi", "ad_egim", "obv_egim",
           "uyum_gucu", "yukselirken_birikim"]


def bolum_korelasyon(d):
    yaz("\n" + "═" * 74)
    yaz("  1) ÖNGÖRÜ GÜCÜ (Spearman korelasyon)")
    yaz("═" * 74)
    yaz("  |0,05| üstü zayıf ama anlamlı; |0,10| üstü BIST için iyi sayılır.")
    yaz("  Karşılaştırma: motorun genel puanı bu testlerde +0,012 çıkmıştı.\n")
    yaz(f"  {'Gösterge':22s}{'ham getiri':>13s}{'endeks üstü':>14s}{'n':>10s}")
    yaz("  " + "─" * 60)
    d = d.copy()
    d["endeks_ustu"] = d["ileri_getiri"] - d["endeks_getiri"]
    for a in ALANLAR:
        if a not in d.columns:
            continue
        x = d[[a, "ileri_getiri", "endeks_ustu"]].dropna()
        if len(x) < 200:
            yaz(f"  {a:22s}{'veri az':>13s}")
            continue
        r1 = x[a].corr(x["ileri_getiri"], method="spearman")
        r2 = x[a].corr(x["endeks_ustu"], method="spearman")
        yaz(f"  {a:22s}{r1:>+12.4f}{r2:>+13.4f}{len(x):>10,}")


def bolum_desil(d, alan="takas_puani"):
    yaz("\n" + "═" * 74)
    yaz(f"  2) DESİL ANALİZİ — '{alan}' etkisi MONOTON mu?")
    yaz("═" * 74)
    yaz("  Etki gerçekse desiller boyunca düzenli artmalı. Sadece bir uçtan")
    yaz("  geliyorsa tek bir aykırı gruptan kaynaklanıyor olabilir.\n")
    x = d.dropna(subset=[alan, "ileri_getiri", "endeks_getiri"]).copy()
    x["endeks_ustu"] = x["ileri_getiri"] - x["endeks_getiri"]
    if len(x) < 500:
        yaz("  Yeterli veri yok.")
        return
    try:
        x["desil"] = pd.qcut(x[alan], 10, labels=False, duplicates="drop")
    except Exception:
        yaz("  Desil oluşturulamadı (değerler çok tekrarlı).")
        return
    g = x.groupby("desil").agg(n=(alan, "size"), deger=(alan, "mean"),
                               ustu=("endeks_ustu", "mean"))
    for i, r in g.iterrows():
        yaz(f"    D{int(i)+1:2d}  {alan}={r['deger']:>8.2f} → endeks üstü "
            f"%{r['ustu']:+6.2f}   n={int(r['n']):,}")
    if len(g) > 3:
        kor = float(np.corrcoef(g.index.values.astype(float), g["ustu"].values)[0, 1])
        yaz(f"\n  Düzenlilik: {kor:+.3f}  "
            + ("✓ monoton" if abs(kor) > 0.7 else "⚠ düzensiz"))


def _aylik(d, alan, n=UST_N, ters=False, filtre=None):
    x = d if filtre is None else d[filtre(d)]
    o = []
    for t, g in x.groupby("tarih"):
        g = g.dropna(subset=[alan, "ileri_getiri", "endeks_getiri"])
        if len(g) < max(30, n):
            continue
        s = g.nsmallest(n, alan) if ters else g.nlargest(n, alan)
        o.append(s["ileri_getiri"].mean() - TUR_MALIYETI - s["endeks_getiri"].mean())
    return np.array(o)


def bolum_strateji(d):
    yaz("\n" + "═" * 74)
    yaz(f"  3) STRATEJİ TESTİ — her ay en iyi {UST_N} hisse, 1 ay tut")
    yaz("═" * 74)
    yaz(f"  Maliyet %{TUR_MALIYETI:.2f}/tur DÜŞÜLMÜŞTÜR. Sayılar ENDEKS ÜSTÜ getiridir.")
    yaz("  p<0,05 değilse sonuç rastlantı olabilir — güvenilmez.\n")
    try:
        from scipy import stats
    except Exception:
        stats = None
    likit = lambda x: x["hacim_mtl"].fillna(0) >= MIN_HACIM_MTL

    ev = []
    for t, g in d[d["hacim_mtl"].fillna(0) >= MIN_HACIM_MTL].groupby("tarih"):
        g = g.dropna(subset=["ileri_getiri", "endeks_getiri"])
        if len(g) < 30:
            continue
        ev.append(g["ileri_getiri"].mean() - g["endeks_getiri"].mean())
    ev = np.array(ev)
    yaz(f"  {'Strateji':34s}{'endeks üstü':>13s}{'t':>8s}{'p':>9s}")
    yaz("  " + "─" * 64)
    if len(ev):
        t, p = (stats.ttest_1samp(ev, 0) if stats else (np.nan, np.nan))
        yaz(f"  {'Tüm hisseler (al-tut, maliyet yok)':34s}{ev.mean():>+12.2f}%{t:>+8.2f}{p:>9.4f}")
    yaz("")
    for a in ALANLAR:
        if a not in d.columns:
            continue
        r = _aylik(d, a, filtre=likit)
        if len(r) < 10:
            yaz(f"  {('En yüksek ' + a):34s}{'veri az':>13s}")
            continue
        t, p = (stats.ttest_1samp(r, 0) if stats else (np.nan, np.nan))
        yaz(f"  {('En yüksek ' + a):34s}{r.mean():>+12.2f}%{t:>+8.2f}{p:>9.4f}")
    # Ters yon: dagitim (en dusuk) kotu mu?
    r = _aylik(d, "takas_puani", filtre=likit, ters=True)
    if len(r) >= 10:
        t, p = (stats.ttest_1samp(r, 0) if stats else (np.nan, np.nan))
        yaz(f"\n  {'En DÜŞÜK takas_puani (kontrol)':34s}{r.mean():>+12.2f}%{t:>+8.2f}{p:>9.4f}")
        yaz("    (Bu NEGATİF çıkmalı — dağıtım kötüyse. Pozitifse gösterge ters çalışıyor.)")


def bolum_walk_forward(d):
    yaz("\n" + "═" * 74)
    yaz("  4) WALK-FORWARD — sonuç TESADÜF mü, TUTARLI mı?")
    yaz("═" * 74)
    yaz("  Bir gösterge SADECE bir yarıda işe yarıyorsa KULLANILMAMALIDIR.\n")
    orta = d["tarih"].quantile(0.5)
    d1, d2 = d[d["tarih"] < orta], d[d["tarih"] >= orta]
    yaz(f"  1. yarı: {d['tarih'].min():%d.%m.%Y} → {orta:%d.%m.%Y}")
    yaz(f"  2. yarı: {orta:%d.%m.%Y} → {d['tarih'].max():%d.%m.%Y}\n")
    yaz(f"  {'Gösterge':24s}{'1.yarı':>11s}{'2.yarı':>11s}{'karar':>16s}")
    yaz("  " + "─" * 64)
    likit = lambda x: x["hacim_mtl"].fillna(0) >= MIN_HACIM_MTL
    for a in ALANLAR:
        if a not in d.columns:
            continue
        r1, r2 = _aylik(d1, a, filtre=likit), _aylik(d2, a, filtre=likit)
        if len(r1) < 5 or len(r2) < 5:
            yaz(f"  {a:24s}{'veri az':>11s}")
            continue
        m1, m2 = r1.mean(), r2.mean()
        if m1 > 0 and m2 > 0:
            karar = "✓ TUTARLI"
        elif m1 > 0 or m2 > 0:
            karar = "~ karışık"
        else:
            karar = "✗ işe yaramaz"
        yaz(f"  {a:24s}{m1:>+10.2f}%{m2:>+10.2f}%{karar:>16s}")


def main():
    yaz("═" * 74)
    yaz("  TAKAS VEKİL GÖSTERGELERİ TESTİ")
    yaz(f"  {dt.datetime.now():%d.%m.%Y %H:%M}")
    yaz("═" * 74)
    yaz("  Gerçek takas verisi yok. Bu test, takas analizinin ölçmeye çalıştığı")
    yaz("  BİRİKİM/DAĞITIM kavramının fiyat-hacim vekilleriyle BIST'te")
    yaz("  yakalanıp yakalanamadığını ölçer.")
    yaz(f"\n  Kapsam {KAPSAM} · {YIL:.0f} yıl · rebalans {REBALANS_GUN} gün · "
        f"en iyi {UST_N} · maliyet %{TUR_MALIYETI}")

    yaz("\n  Veri indiriliyor...")
    semboller = vk.sembol_listesi(KAPSAM)
    veriler = vk.toplu_fiyat(semboller, yil=YIL)
    yaz(f"  {len(veriler)}/{len(semboller)} hisse geldi.")

    endeks_df = vk.endeks_gecmisi(YIL)
    endeks = None
    if endeks_df is not None and len(endeks_df):
        endeks = pd.to_numeric(endeks_df["Close"], errors="coerce")
        yaz(f"  Endeks: {len(endeks)} gün.")
    else:
        yaz("  ⚠️ Endeks alınamadı — endeks üstü hesaplanamayacak.")

    yaz("\n  Birikim/dağıtım göstergeleri hesaplanıyor...")
    d = veri_topla(veriler, endeks)
    if d.empty:
        yaz("\n  ❌ Veri üretilemedi.")
        return
    d.to_csv(CSV_DOSYASI, index=False)
    yaz(f"\n  {len(d):,} gözlem ({d['sembol'].nunique()} hisse, "
        f"{d['tarih'].nunique()} tarih).  Ham veri: {os.path.basename(CSV_DOSYASI)}")

    bolum_korelasyon(d)
    bolum_desil(d, "takas_puani")
    bolum_desil(d, "cmf")
    bolum_strateji(d)
    bolum_walk_forward(d)

    yaz("\n" + "═" * 74)
    yaz("  NASIL OKUNMALI")
    yaz("═" * 74)
    yaz("  • Hiçbiri anlamlı değilse: birikim/dağıtım fiyat-hacim verisinden")
    yaz("    çıkarılamıyor. Gerçek takas verisi hâlâ farklı bilgi taşıyabilir")
    yaz("    (kim tuttuğu, yabancı payı) ama beklenti düşük tutulmalıdır.")
    yaz("  • Bir gösterge tutarlı VE anlamlıysa: gerçek takas verisine")
    yaz("    yatırım yapmak için sağlam gerekçe oluşur.")
    yaz("  • 'takas_puani' zaten motorun içinde ve genel puana katkı veriyor.")
    yaz("    İşe yaramıyorsa ağırlığı sorgulanmalıdır.")
    yaz("\n  SINIRLAR: hayatta kalma yanlılığı (batan hisseler yok, sonuçlar")
    yaz("  iyimser), tek dönem (2021-2026 yüksek enflasyon + güçlü yükseliş),")
    yaz("  tavan/taban ve gerçek slipaj basitleştirilmiş.")
    yaz("═" * 74)


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            with open(SONUC_DOSYASI, "w", encoding="utf-8") as f:
                f.write("\n".join(_C))
            print(f"\n  Sonuç kaydedildi: {os.path.basename(SONUC_DOSYASI)}")
        except Exception as e:
            print(f"\n  UYARI: dosyaya yazılamadı: {e}")
