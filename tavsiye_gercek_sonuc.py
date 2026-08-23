# -*- coding: utf-8 -*-
"""
tavsiye_gercek_sonuc.py — "O hisseyi alsaydım kazanır mıydım?"
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR
─────────
Yazılım Ağustos 2026'dan beri her gün tavsiye üretiyor ve kaydediyor
(tavsiye_gecmisi.json). Ama şu soru hiç DÜRÜST şekilde cevaplanmadı:

  "Kullanıcı listenin EN ÜSTÜNDEKİ hisseye baktı ve aldı. Kazandı mı?"

ÖNCEKİ ÖLÇÜMÜM SAKATTI: Getiriyi hesaplamak için tavsiye kayıtlarındaki
fiyatları kullanıyordum. Ama bir hisse listeden düştüğünde artık kaydı
oluşmuyor, dolayısıyla fiyatı da bilinmiyordu — yani SADECE listede kalmaya
devam eden (= iyi giden) hisseler ölçülebiliyordu. Kötü gidenler ölçümün
dışında kalıyordu. Bu, sonucu sistematik olarak İYİMSER gösteriyordu.
7 Ağustos tavsiyelerinin %75'i bu şekilde ölçüm dışı kalmıştı.

BU SCRIPT FARKLI: Tavsiye edilen HER sembolün bugünkü fiyatını doğrudan
veri kaynağından çeker — hisse listeden düşmüş olsa da, çökmüş olsa da.
Böylece hayatta kalma yanlılığı ORTADAN KALKAR.

NE ÖLÇER
────────
  • Her tavsiye kaynağı için (Öne Çıkan, Yükselebilecek, Kısa/Orta/Uzun vade)
  • SIRALAMAYA göre ayrı ayrı: en üstteki 1 hisse, ilk 3, ilk 5, tümü
  • Aynı dönemdeki BIST 100 getirisiyle karşılaştırmalı
  • Kazanan/kaybeden oranı ve en iyi/en kötü örnekler

"En üstteki" = o gün, o kaynakta EN YÜKSEK PUANLI hisse.

ÇALIŞTIRMA: TAVSIYE_SONUC.bat   (~2-5 dakika)
Sonuç: tavsiye_gercek_sonuc.txt
"""
from __future__ import annotations

import os
import sys
import json
import datetime as dt
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import veri_katmani as vk

KLASOR = os.path.dirname(os.path.abspath(__file__))
KAYIT_DOSYASI = os.path.join(KLASOR, "tavsiye_gecmisi.json")
SONUC_DOSYASI = os.path.join(KLASOR, "tavsiye_gercek_sonuc.txt")

MIN_GUN = 3          # bu kadar gün geçmemiş tavsiyeler "henüz olgunlaşmadı"
_C = []


def yaz(m=""):
    print(m)
    _C.append(str(m))


def cizgi(k="─"):
    yaz(k * 76)


def _sayi(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def main():
    yaz("═" * 76)
    yaz("  TAVSİYELER GERÇEKTEN KAZANDIRDI MI?")
    yaz(f"  {dt.datetime.now():%d.%m.%Y %H:%M}")
    yaz("═" * 76)
    yaz("  Tavsiye edilen HER hissenin bugünkü fiyatı ayrıca çekilir —")
    yaz("  listeden düşmüş olsa bile. Hayatta kalma yanlılığı YOKTUR.")

    if not os.path.exists(KAYIT_DOSYASI):
        yaz("\n  ❌ tavsiye_gecmisi.json bulunamadı.")
        return
    kayitlar = json.load(open(KAYIT_DOSYASI, encoding="utf-8"))
    yaz(f"\n  Toplam kayıt: {len(kayitlar):,}")

    bugun = dt.date.today()
    gecerli = []
    for k in kayitlar:
        f = _sayi(k.get("kayit_anindaki_fiyat"))
        if f is None or f <= 0:
            continue
        try:
            t = dt.date.fromisoformat(str(k.get("tarih"))[:10])
        except Exception:
            continue
        gun = (bugun - t).days
        if gun < MIN_GUN:
            continue
        gecerli.append({"sembol": str(k.get("sembol", "")).upper(),
                        "kaynak": k.get("kaynak", "?"), "tarih": t,
                        "fiyat": f, "gun": gun,
                        "puan": _sayi(k.get("puan"))})
    yaz(f"  Olgunlaşmış ({MIN_GUN}+ gün): {len(gecerli):,}")
    if not gecerli:
        yaz("\n  Henüz değerlendirilecek kadar zaman geçmemiş.")
        return

    semboller = sorted({g["sembol"] for g in gecerli})
    yaz(f"  Benzersiz hisse: {len(semboller)}")
    yaz("\n  Güncel fiyatlar çekiliyor (listeden düşenler dahil)...")

    guncel = {}
    for i, s in enumerate(semboller, 1):
        if i % 25 == 0:
            yaz(f"    ... {i}/{len(semboller)}")
        try:
            df = vk.fiyat_gecmisi(s, 0.5)
            if df is not None and len(df) and "Close" in df.columns:
                seri = pd.to_numeric(df["Close"], errors="coerce").dropna()
                seri = seri[seri > 0]
                if len(seri):
                    guncel[s] = float(seri.iloc[-1])
        except Exception:
            pass
    yaz(f"  {len(guncel)}/{len(semboller)} hissenin güncel fiyatı alındı.")
    kayip = [s for s in semboller if s not in guncel]
    if kayip:
        yaz(f"  Fiyatı alınamayan ({len(kayip)}): {', '.join(kayip[:12])}"
            + (" ..." if len(kayip) > 12 else ""))
        yaz("    (Bunlar çoğunlukla işlem görmeyen/çıkarılmış hisselerdir;")
        yaz("     ölçüme katılamazlar ama sayıları raporlanır.)")

    # ── Endeks karşılaştırması ───────────────────────────────────────────────
    endeks = None
    try:
        edf = vk.endeks_gecmisi(1.0)
        if edf is not None and len(edf):
            endeks = pd.to_numeric(edf["Close"], errors="coerce").dropna()
    except Exception:
        pass

    def endeks_getirisi(t):
        if endeks is None or len(endeks) == 0:
            return None
        try:
            onceki = endeks[endeks.index <= pd.Timestamp(t)]
            if not len(onceki):
                return None
            return 100 * (float(endeks.iloc[-1]) / float(onceki.iloc[-1]) - 1)
        except Exception:
            return None

    for g in gecerli:
        f_son = guncel.get(g["sembol"])
        g["getiri"] = (100 * (f_son / g["fiyat"] - 1)) if f_son else None
        e = endeks_getirisi(g["tarih"])
        g["endeks"] = e
        g["ustu"] = (g["getiri"] - e) if (g["getiri"] is not None and e is not None) else None

    olculebilir = [g for g in gecerli if g["getiri"] is not None]
    yaz(f"\n  ÖLÇÜLEBİLEN TAVSİYE: {len(olculebilir):,}/{len(gecerli):,}"
        f"  (%{100*len(olculebilir)/len(gecerli):.0f})")

    # ── EN ÜSTTEKİ HİSSE — asıl soru ─────────────────────────────────────────
    yaz("\n" + "═" * 76)
    yaz("  1) 'EN ÜSTTEKİ HİSSEYİ ALDIM' — gerçekte ne oldu?")
    yaz("═" * 76)
    yaz("  Her gün, her kaynakta EN YÜKSEK PUANLI hisse alınsaydı.\n")

    # tarih+kaynak bazinda siralama
    gruplar = defaultdict(list)
    for g in olculebilir:
        gruplar[(g["tarih"], g["kaynak"])].append(g)

    def sirali(liste):
        # Puan varsa ona göre, yoksa kayıt sırasına göre
        if all(x["puan"] is not None for x in liste):
            return sorted(liste, key=lambda x: -x["puan"])
        return liste

    def ozet(secici, ad):
        alinanlar = []
        for _, liste in gruplar.items():
            s = sirali(liste)
            alinanlar += secici(s)
        if not alinanlar:
            yaz(f"  {ad:24s} veri yok")
            return None
        g = np.array([x["getiri"] for x in alinanlar], dtype=float)
        u = np.array([x["ustu"] for x in alinanlar if x["ustu"] is not None], dtype=float)
        kazanan = 100 * (g > 0).mean()
        yaz(f"  {ad:24s} n={len(g):4d}  ort=%{g.mean():+6.2f}  "
            f"medyan=%{np.median(g):+6.2f}  kazanan=%{kazanan:3.0f}"
            + (f"  endeks üstü=%{u.mean():+5.2f}" if len(u) else ""))
        return alinanlar

    yaz(f"  {'Seçim':24s}{'':6s}{'ortalama':>12s}{'medyan':>13s}{'kazanan':>11s}")
    cizgi()
    en_ust = ozet(lambda s: s[:1], "EN ÜSTTEKİ (1 hisse)")
    ozet(lambda s: s[:3], "İlk 3")
    ozet(lambda s: s[:5], "İlk 5")
    ozet(lambda s: s, "Tüm liste")

    # ── Kaynak bazında ───────────────────────────────────────────────────────
    yaz("\n" + "═" * 76)
    yaz("  2) KAYNAK BAZINDA — hangi liste daha iyi?")
    yaz("═" * 76)
    yaz(f"  {'Kaynak':34s}{'n':>6s}{'ortalama':>11s}{'endeks üstü':>13s}{'kazanan':>9s}")
    cizgi()
    kb = defaultdict(list)
    for g in olculebilir:
        kb[g["kaynak"]].append(g)
    for kaynak, liste in sorted(kb.items(), key=lambda kv: -len(kv[1])):
        g = np.array([x["getiri"] for x in liste], dtype=float)
        u = [x["ustu"] for x in liste if x["ustu"] is not None]
        yaz(f"  {kaynak:34s}{len(g):>6d}{g.mean():>+10.2f}%"
            + (f"{np.mean(u):>+12.2f}%" if u else f"{'—':>13s}")
            + f"{100*(g>0).mean():>8.0f}%")

    tum = np.array([x["getiri"] for x in olculebilir], dtype=float)
    tum_u = [x["ustu"] for x in olculebilir if x["ustu"] is not None]
    cizgi()
    yaz(f"  {'TÜM TAVSİYELER':34s}{len(tum):>6d}{tum.mean():>+10.2f}%"
        + (f"{np.mean(tum_u):>+12.2f}%" if tum_u else f"{'—':>13s}")
        + f"{100*(tum>0).mean():>8.0f}%")

    # ── En iyi / en kötü ─────────────────────────────────────────────────────
    yaz("\n" + "═" * 76)
    yaz("  3) EN İYİ VE EN KÖTÜ TAVSİYELER")
    yaz("═" * 76)
    sirali_hepsi = sorted(olculebilir, key=lambda x: -x["getiri"])
    yaz("  EN İYİ 8:")
    for x in sirali_hepsi[:8]:
        yaz(f"    {x['sembol']:7s} {x['tarih']:%d.%m}  {x['gun']:2d} gün  "
            f"%{x['getiri']:+7.2f}   {x['kaynak'][:28]}")
    yaz("\n  EN KÖTÜ 8:")
    for x in sirali_hepsi[-8:]:
        yaz(f"    {x['sembol']:7s} {x['tarih']:%d.%m}  {x['gun']:2d} gün  "
            f"%{x['getiri']:+7.2f}   {x['kaynak'][:28]}")

    # ── Dürüst değerlendirme ─────────────────────────────────────────────────
    yaz("\n" + "═" * 76)
    yaz("  DEĞERLENDİRME")
    yaz("═" * 76)
    if tum_u:
        ort_u = float(np.mean(tum_u))
        if ort_u > 0.5:
            yaz(f"  Tavsiyeler endeksi ortalama %{ort_u:+.2f} GEÇMİŞ.")
        elif ort_u < -0.5:
            yaz(f"  Tavsiyeler endeksin %{abs(ort_u):.2f} GERİSİNDE kalmış.")
            yaz("  Yani bu tavsiyelere uymak yerine endeks fonu almak daha iyiydi.")
        else:
            yaz(f"  Tavsiyeler endeksle hemen hemen AYNI (%{ort_u:+.2f}).")
    if en_ust:
        gu = np.array([x["getiri"] for x in en_ust], dtype=float)
        uu = [x["ustu"] for x in en_ust if x["ustu"] is not None]
        yaz(f"\n  'En üstteki hisse' stratejisi: ortalama %{gu.mean():+.2f}"
            + (f", endeks üstü %{np.mean(uu):+.2f}" if uu else ""))
        if uu and np.mean(uu) > np.mean(tum_u) + 0.3:
            yaz("  → Sıralama ANLAMLI: üsttekiler alttakilerden iyi.")
        elif uu:
            yaz("  → Sıralamanın ek faydası görünmüyor; en üstteki hisse")
            yaz("    listenin geri kalanından belirgin şekilde iyi değil.")

    gun_ort = np.mean([x["gun"] for x in olculebilir])
    yaz(f"\n  ⚠️ SINIRLAR")
    yaz(f"  • Ortalama tutma süresi sadece {gun_ort:.0f} gün — çok kısa.")
    yaz("    Bu sonuçlar bir eğilim gösterir, KANIT değildir.")
    yaz(f"  • {len(kayip)} hissenin fiyatı alınamadı, ölçüme giremedi.")
    yaz("  • Komisyon/slipaj düşülmemiştir (gerçekte tur başına ~%0,5).")
    yaz("  • Tek bir piyasa dönemi.")
    yaz("═" * 76)


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
