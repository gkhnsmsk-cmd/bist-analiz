# -*- coding: utf-8 -*-
"""
haftalik_kontrol.py — Her hafta kendiliğinden çalışan tek kontrol raporu.
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR: Ölçümler bugüne kadar tek tek elle çalıştırılıyor, çıktısı elle
paylaşılıyordu. Bu script hepsini otomatik yapar ve TEK bir okunabilir rapor
üretir: haftalik_rapor.txt

RAPORDA NE VAR
──────────────
  0) ÖZET — 30 saniyede okunacak; aksiyon gerekiyorsa en üstte yazar
  1) SANAL PORTFÖY — endeks üstü getiri (ASIL ölçüt), pozisyonlar, işlemler
  2) TAVSİYE KALİTESİ — tavsiyeler gerçekten kazandırdı mı (yanlılıksız)
  3) GERÇEK PORTFÖY — çıkış sinyali veren pozisyonların var mı
  4) SİSTEM SAĞLIĞI — otomasyon çalışıyor mu, veriler taze mi
  5) ÖĞRENME MOTORU — yeterli veri biriktiyse hata analizi

ÖLÇÜM DÜRÜSTLÜĞÜ: Tavsiye getirileri hesaplanırken her sembolün güncel
fiyatı AYRICA çekilir — hisse listeden düşmüş olsa bile. Aksi halde sadece
listede kalmaya devam eden (= iyi giden) hisseler ölçülür ve sonuç
sistematik olarak iyimser çıkar.

ÇALIŞTIRMA: HAFTALIK_KONTROL.bat  (Görev Zamanlayıcı: Cumartesi 10:00)
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

KLASOR = os.path.dirname(os.path.abspath(__file__))
RAPOR_DOSYASI = os.path.join(KLASOR, "haftalik_rapor.txt")

_C = []
_UYARI = []          # özet bölümünde en üstte gösterilecek aksiyon maddeleri


def yaz(m=""):
    print(m)
    _C.append(str(m))


def baslik(no, ad):
    yaz("\n" + "═" * 76)
    yaz(f"  {no}) {ad}")
    yaz("═" * 76)


def _sayi(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _dosya_yasi_saat(ad):
    p = os.path.join(KLASOR, ad)
    if not os.path.exists(p):
        return None
    return (dt.datetime.now() - dt.datetime.fromtimestamp(os.path.getmtime(p))).total_seconds() / 3600


# ═════════════════════════════════════════════════════════════════════════════
# 1) SANAL PORTFÖY
# ═════════════════════════════════════════════════════════════════════════════
def bolum_sanal(endeks_df):
    baslik(1, "SANAL PORTFÖY — endeksi yeniyor mu?")
    try:
        import sanal_yatirimci as sv
    except Exception as e:
        yaz(f"  Modül yüklenemedi: {e}")
        return None
    try:
        e = sv.endeks_karsilastirmasi(endeks_df)
        p = sv.portfoy_getir()
        if e.get("veri_var"):
            yaz(f"  Portföy   : %{e['portfoy_yuzde']:+.2f}")
            yaz(f"  BIST 100  : %{e['endeks_yuzde']:+.2f}   "
                f"({e['endeks_bas']:,.0f} → {e['endeks_son']:,.0f})")
            yaz(f"  ENDEKS ÜSTÜ: %{e['endeks_ustu_yuzde']:+.2f}  "
                + ("✅ YENİYOR" if e["yeniyor_mu"] else "⚠️ GERİDE"))
            if not e["yeniyor_mu"]:
                _UYARI.append(f"Sanal portföy endeksin %{abs(e['endeks_ustu_yuzde']):.1f} gerisinde.")
        else:
            yaz("  Endeks verisi alınamadı — karşılaştırma yapılamadı.")

        _poz = len(p["pozisyonlar"])
        yaz(f"\n  Pozisyon: {_poz}/{sv.MAKS_POZISYON}   "
            f"Nakit: {p.get('nakit', 0):,.0f} ₺   "
            f"Son karar: {p.get('son_rebalans_tarihi', '—')}")
        # Sınır aşımı: ayar değiştiğinde (örn. 12→5) portföy bir sonraki
        # koşuya kadar eski sayıda kalır. Sessizce geçmek yerine bildirilir.
        if _poz > sv.MAKS_POZISYON:
            yaz(f"  ⚠️ Pozisyon sayısı sınırın ({sv.MAKS_POZISYON}) ÜSTÜNDE — "
                "motor bir sonraki koşuda fazlasını satacak.")
            _UYARI.append(f"Sanal portföyde {_poz} pozisyon var, sınır {sv.MAKS_POZISYON}. "
                          "Motor bir sonraki koşuda düzeltir.")
        if p["pozisyonlar"]:
            yaz(f"\n  {'Hisse':8s}{'Maliyet':>10s}{'Son':>10s}{'K/Z %':>9s}{'Gün':>6s}")
            yaz("  " + "─" * 43)
            for q in p["pozisyonlar"]:
                m = _sayi(q.get("maliyet")) or 0
                s = _sayi(q.get("son_fiyat")) or m
                kz = 100 * (s / m - 1) if m else 0
                try:
                    g = (dt.date.today() - dt.date.fromisoformat(str(q.get("eklenme_tarihi"))[:10])).days
                except Exception:
                    g = 0
                yaz(f"  {q['sembol']:8s}{m:>10.2f}{s:>10.2f}{kz:>+8.2f}%{g:>6d}")

        gecmis = sv.islem_gecmisi()
        bugun = dt.date.today()
        son7 = [x for x in gecmis
                if (bugun - dt.date.fromisoformat(str(x.get("tarih"))[:10])).days <= 7]
        yaz(f"\n  Son 7 günde {len(son7)} işlem:")
        for x in son7[-10:]:
            t = f" [{x['tutma_gunu']}g]" if x.get("tutma_gunu") is not None else ""
            yaz(f"    {x['yon']:16s}{x['sembol']:7s}{t:6s} {str(x.get('gerekce',''))[:48]}")
        askida = sv.askidaki_satislari_bul()
        if askida:
            yaz(f"\n  ⚠️ Satılamayan pozisyon: {[a['sembol'] for a in askida]}")
            _UYARI.append(f"{len(askida)} pozisyon satılamıyor (fiyat alınamıyor).")
        return e
    except Exception as e:
        yaz(f"  HATA: {type(e).__name__}: {e}")
        return None


# ═════════════════════════════════════════════════════════════════════════════
# 2) TAVSİYE KALİTESİ
# ═════════════════════════════════════════════════════════════════════════════
def bolum_tavsiye(vk, endeks_seri):
    baslik(2, "TAVSİYE KALİTESİ — tavsiyeler kazandırdı mı?")
    kayit_dosyasi = os.path.join(KLASOR, "tavsiye_gecmisi.json")
    if not os.path.exists(kayit_dosyasi):
        yaz("  tavsiye_gecmisi.json yok.")
        return
    kayitlar = json.load(open(kayit_dosyasi, encoding="utf-8"))
    bugun = dt.date.today()

    gecerli = []
    for k in kayitlar:
        f = _sayi(k.get("kayit_anindaki_fiyat"))
        if not f or f <= 0:
            continue
        try:
            t = dt.date.fromisoformat(str(k.get("tarih"))[:10])
        except Exception:
            continue
        if (bugun - t).days < 3:
            continue
        gecerli.append({"sembol": str(k.get("sembol", "")).upper(),
                        "kaynak": k.get("kaynak", "?"), "tarih": t,
                        "fiyat": f, "gun": (bugun - t).days,
                        "puan": _sayi(k.get("puan"))})
    if not gecerli:
        yaz("  Henüz olgunlaşmış tavsiye yok.")
        return

    semboller = sorted({g["sembol"] for g in gecerli})
    yaz(f"  {len(gecerli):,} olgunlaşmış tavsiye · {len(semboller)} hisse")
    yaz("  Güncel fiyatlar çekiliyor (listeden düşenler DAHİL — yanlılık yok)...")
    guncel = {}
    for s in semboller:
        try:
            df = vk.fiyat_gecmisi(s, 0.5)
            if df is not None and len(df) and "Close" in df.columns:
                seri = pd.to_numeric(df["Close"], errors="coerce").dropna()
                seri = seri[seri > 0]
                if len(seri):
                    guncel[s] = float(seri.iloc[-1])
        except Exception:
            pass
    yaz(f"  {len(guncel)}/{len(semboller)} fiyat alındı.")

    def endeks_getirisi(t):
        if endeks_seri is None or not len(endeks_seri):
            return None
        try:
            onc = endeks_seri[endeks_seri.index <= pd.Timestamp(t)]
            return 100 * (float(endeks_seri.iloc[-1]) / float(onc.iloc[-1]) - 1) if len(onc) else None
        except Exception:
            return None

    for g in gecerli:
        fs = guncel.get(g["sembol"])
        g["getiri"] = (100 * (fs / g["fiyat"] - 1)) if fs else None
        eg = endeks_getirisi(g["tarih"])
        g["ustu"] = (g["getiri"] - eg) if (g["getiri"] is not None and eg is not None) else None
    olc = [g for g in gecerli if g["getiri"] is not None]
    if not olc:
        yaz("  Ölçülebilen tavsiye yok.")
        return

    gruplar = defaultdict(list)
    for g in olc:
        gruplar[(g["tarih"], g["kaynak"])].append(g)

    def sirala(l):
        return sorted(l, key=lambda x: -x["puan"]) if all(x["puan"] is not None for x in l) else l

    yaz(f"\n  {'Seçim':22s}{'n':>6s}{'ortalama':>11s}{'endeks üstü':>13s}{'kazanan':>9s}")
    yaz("  " + "─" * 61)
    sonuc_ust = None
    for ad, kes in [("EN ÜSTTEKİ (1)", 1), ("İlk 3", 3), ("İlk 5", 5), ("Tüm liste", None)]:
        alinan = []
        for _, l in gruplar.items():
            s = sirala(l)
            alinan += (s if kes is None else s[:kes])
        if not alinan:
            continue
        gg = np.array([x["getiri"] for x in alinan], dtype=float)
        uu = [x["ustu"] for x in alinan if x["ustu"] is not None]
        yaz(f"  {ad:22s}{len(gg):>6d}{gg.mean():>+10.2f}%"
            + (f"{np.mean(uu):>+12.2f}%" if uu else f"{'—':>13s}")
            + f"{100*(gg>0).mean():>8.0f}%")
        if kes == 1 and uu:
            sonuc_ust = float(np.mean(uu))

    tum_u = [x["ustu"] for x in olc if x["ustu"] is not None]
    if tum_u:
        ort = float(np.mean(tum_u))
        if ort < -0.5:
            _UYARI.append(f"Tavsiyeler endeksin %{abs(ort):.1f} gerisinde.")
    if sonuc_ust is not None and tum_u and sonuc_ust < np.mean(tum_u) - 1.0:
        yaz("\n  ⚠️ EN ÜSTTEKİ hisse, listenin geri kalanından DAHA KÖTÜ.")
        yaz("     Listenin en üstüne güvenmeyin; ilk 3-5 arasından seçmek daha iyi.")
        _UYARI.append("Listenin EN ÜSTÜNDEKİ hisse en kötü performansı veriyor.")

    yaz(f"\n  {'Kaynak':32s}{'n':>6s}{'ortalama':>11s}{'endeks üstü':>13s}")
    yaz("  " + "─" * 62)
    kb = defaultdict(list)
    for g in olc:
        kb[g["kaynak"]].append(g)
    for kaynak, l in sorted(kb.items(), key=lambda kv: -len(kv[1])):
        gg = np.array([x["getiri"] for x in l], dtype=float)
        uu = [x["ustu"] for x in l if x["ustu"] is not None]
        yaz(f"  {kaynak:32s}{len(gg):>6d}{gg.mean():>+10.2f}%"
            + (f"{np.mean(uu):>+12.2f}%" if uu else f"{'—':>13s}"))


# ═════════════════════════════════════════════════════════════════════════════
# 3) GERÇEK PORTFÖY — çıkış sinyalleri
# ═════════════════════════════════════════════════════════════════════════════
def bolum_gercek_portfoy(vk, am):
    baslik(3, "GERÇEK PORTFÖYÜNÜZ — çıkış sinyali var mı?")
    try:
        import portfoy_takip as pt
    except Exception as e:
        yaz(f"  Modül yüklenemedi: {e}")
        return
    if not pt.pozisyonlari_getir():
        yaz("  Portföyünüz boş.")
        return

    def getir(s):
        try:
            return vk.fiyat_gecmisi(s, 2.0)
        except Exception:
            return None
    try:
        satirlar = pt.gunluk_cikis_tablosu(getir, atr_fn=am.atr)
    except Exception as e:
        yaz(f"  HATA: {e}")
        return
    sat = [r for r in satirlar if r["Karar"] == "SAT"]
    yaz(f"  {'Hisse':8s}{'Karar':7s}{'Alış':>9s}{'Fiyat':>9s}{'K/Z %':>9s}"
        f"{'Stop':>9s}{'Pay %':>8s}{'Gün':>5s}")
    yaz("  " + "─" * 64)
    # NOT: sütun adı kesme işareti içeriyor ("Stop'a Pay %"). f-string içinde
    # ters bölü ile kaçırmak Python'da SÖZDİZİMİ HATASIDIR; bu yüzden anahtar
    # önce değişkene alınır.
    PAY = "Stop'a Pay %"
    def _f(v, d=2):
        return "—" if v is None else format(v, f".{d}f")
    for r in satirlar:
        gun = r["Gün"] if r["Gün"] is not None else "—"
        yaz(f"  {r['Hisse']:8s}{r['Karar']:7s}{_f(r['Alış']):>9s}{_f(r['Fiyat']):>9s}"
            f"{_f(r['K/Z %']):>9s}{_f(r['Stop']):>9s}{_f(r[PAY], 1):>8s}"
            f"{gun:>5}")
    if sat:
        yaz(f"\n  🔴 ÇIKIŞ SİNYALİ: {', '.join(r['Hisse'] for r in sat)}")
        for r in sat:
            yaz(f"     {r['Hisse']}: {r['Gerekçe']}")
        _UYARI.append(f"Gerçek portföyünüzde {len(sat)} pozisyon çıkış sinyali veriyor: "
                      + ", ".join(r["Hisse"] for r in sat))
    else:
        yaz("\n  ✅ Hiçbir pozisyon çıkış sinyali vermiyor.")


# ═════════════════════════════════════════════════════════════════════════════
# 4) SİSTEM SAĞLIĞI
# ═════════════════════════════════════════════════════════════════════════════
def bolum_saglik():
    baslik(4, "SİSTEM SAĞLIĞI")
    kontroller = [
        ("tarama_onbellek.json", 48, "Arka plan taraması"),
        ("sanal_portfoy.json", 48, "Sanal portföy motoru"),
        ("tavsiye_gecmisi.json", 48, "Tavsiye kaydı"),
    ]
    for dosya, esik, ad in kontroller:
        h = _dosya_yasi_saat(dosya)
        if h is None:
            yaz(f"  ✗ {ad:26s} DOSYA YOK")
            _UYARI.append(f"{ad} hiç çalışmamış ({dosya} yok).")
        elif h > esik:
            yaz(f"  ⚠ {ad:26s} {h:.0f} saat önce (bayat)")
            _UYARI.append(f"{ad} {h:.0f} saattir güncellenmiyor.")
        else:
            yaz(f"  ✓ {ad:26s} {h:.0f} saat önce")

    for log in ("arka_plan_tarama_log.txt", "sanal_yatirim_calisma.txt"):
        p = os.path.join(KLASOR, log)
        if not os.path.exists(p):
            continue
        try:
            son = open(p, encoding="utf-8", errors="replace").read()[-3000:]
        except Exception:
            continue
        if "Traceback" in son or "ModuleNotFoundError" in son:
            yaz(f"  ⚠ {log}: son çalışmada HATA izi var")
            _UYARI.append(f"{log} dosyasında hata izi var — kontrol edin.")


# ═════════════════════════════════════════════════════════════════════════════
# 5) ÖĞRENME MOTORU
# ═════════════════════════════════════════════════════════════════════════════
def bolum_ogrenme():
    baslik(5, "ÖĞRENME MOTORU")
    try:
        import ogrenme_motoru as om
    except Exception as e:
        yaz(f"  Modül yüklenemedi: {e}")
        return
    kd = os.path.join(KLASOR, "tavsiye_gecmisi.json")
    if not os.path.exists(kd):
        yaz("  Kayıt yok.")
        return
    kayitlar = json.load(open(kd, encoding="utf-8"))
    snap = [k for k in kayitlar if isinstance(k.get("ek"), dict) and "rsi14" in k["ek"]]
    yaz(f"  Özellik anlık görüntüsü içeren karar: {len(snap):,}")
    if not snap:
        yaz("  Henüz snapshot toplanmamış — arka plan taraması çalışmalı.")
        return
    try:
        en_eski = min(dt.date.fromisoformat(str(k["tarih"])[:10]) for k in snap)
        yas = (dt.date.today() - en_eski).days
    except Exception:
        yas = 0
    yaz(f"  En eski snapshot: {yas} gün önce")
    gerekli = 20
    if yas < gerekli:
        yaz(f"  ⏳ Hata analizi için ~{gerekli - yas} gün daha veri gerekiyor")
        yaz("     (10 günlük ufkun olgunlaşması + yeterli örnek).")
        return
    try:
        yaz("  Hata analizi çalıştırılıyor...")
        sonuc = om.ogrenme_dongusu()
        yaz(sonuc.get("rapor", "  (rapor üretilemedi)"))
    except Exception as e:
        yaz(f"  Analiz çalıştırılamadı: {type(e).__name__}: {e}")


def main():
    yaz("═" * 76)
    yaz("  HAFTALIK KONTROL RAPORU")
    yaz(f"  {dt.datetime.now():%d.%m.%Y %H:%M}")
    yaz("═" * 76)

    import veri_katmani as vk
    import analiz_motoru as am

    endeks_df, endeks_seri = None, None
    try:
        endeks_df = vk.endeks_gecmisi(1.0)
        if endeks_df is not None and len(endeks_df):
            endeks_seri = pd.to_numeric(endeks_df["Close"], errors="coerce").dropna()
    except Exception:
        pass

    ozet_yeri = len(_C)          # özeti sonra buraya ekleyeceğiz

    bolum_sanal(endeks_df)
    bolum_tavsiye(vk, endeks_seri)
    bolum_gercek_portfoy(vk, am)
    bolum_saglik()
    bolum_ogrenme()

    # ── ÖZETİ EN ÜSTE YERLEŞTİR ──────────────────────────────────────────────
    ozet = ["", "─" * 76, "  ÖZET — önce bunu okuyun", "─" * 76]
    if _UYARI:
        ozet.append("  ⚠️ DİKKAT GEREKTİRENLER:")
        for u in _UYARI:
            ozet.append(f"     • {u}")
    else:
        ozet.append("  ✅ Dikkat gerektiren bir durum yok.")
    ozet += ["", "  Ayrıntılar aşağıda. Sorularınız için bu dosyayı paylaşabilirsiniz.",
             "─" * 76]
    _C[ozet_yeri:ozet_yeri] = ozet
    # Özet _C listesine SONRADAN eklendiği için konsola basılmamış olur;
    # elle basıyoruz ki scripti canlı izleyen de görebilsin.
    for satir in ozet:
        print(satir)

    yaz("\n" + "═" * 76)
    yaz("  Bu rapor haftada bir otomatik üretilir (HAFTALIK_KONTROL.bat).")
    yaz("  ⚠️ Sonuçlar kısa dönemlidir ve kanıt değil eğilim gösterir.")
    yaz("═" * 76)


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            with open(RAPOR_DOSYASI, "w", encoding="utf-8") as f:
                f.write("\n".join(_C))
            print(f"\n  Rapor: {os.path.basename(RAPOR_DOSYASI)}")
        except Exception as e:
            print(f"\n  UYARI: rapor yazılamadı: {e}")
