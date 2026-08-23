# -*- coding: utf-8 -*-
"""
tavsiye_kaydi.py — Motorun ürettiği TAVSİYELERİ kaydeder ve sonradan gerçek
getiriyle puanlar (ileriye dönük / "forward" performans ölçümü).
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR: "Öne Çıkan Hisseler" ve "Yükselebilecek Hisseler" sekmeleri
sonuçlarını yalnızca Streamlit oturum belleğine (st.session_state) yazıyordu;
uygulama kapanınca hepsi siliniyordu. Yani motor aylarca tavsiye üretse bile
"bu tavsiyeler tuttu mu?" sorusunun cevabı ÖLÇÜLEMEZ kalıyordu. Bu modül o
boşluğu doldurur.

BACKTEST'TEN FARKI (ikisi birbirini tamamlar, biri diğerinin yerine geçmez):
  • backtest_motoru : GEÇMİŞ veriyi yeniden oynatır. Hızlı ve çok örnekli ama
                      "hayatta kalma yanlılığı" ve parametre seçiminin geçmişe
                      bakarak yapılmış olma riski taşır.
  • tavsiye_kaydi   : Motorun GERÇEK ZAMANDA, sonucu bilinmezken ne dediğini
                      kaydeder. Yavaş birikir ama en dürüst kanıttır — çünkü
                      kayıt anında gelecek kimse tarafından bilinmiyordu.

DÜRÜSTLÜK KURALLARI (koda gömülü):
  1. OLGUNLAŞMA: 3 gün önce verilmiş bir tavsiyenin 20 günlük getirisi HENÜZ
     YOKTUR. Bu kayıtlar "olgunlaşmadı" olarak ayrı tutulur; sıfır sayılmaz,
     sessizce atılmaz — aksi halde ortalama yapay olarak iyileşir/kötüleşir.
  2. GİRİŞ FİYATI: Getiri, kayıt anındaki anlık fiyattan değil, tavsiye
     tarihindeki KAPANIŞTAN hesaplanır ve çıkış da kapanıştır. Böylece iki uç
     aynı temele oturur (anlık fiyat ile kapanışı karıştırmak sahte getiri
     üretir). Kayıt anındaki fiyat ayrıca saklanır, kıyaslanabilsin diye.
  3. ENDEKS KIYASI: Mutlak getiri tek başına aldatıcıdır — piyasa %10 çıktıysa
     %6 kazanmak aslında kaybetmektir. Bu yüzden aynı dönemin BIST100 getirisi
     de hesaplanır ve "endeks üstü getiri" ayrıca raporlanır.
  4. MÜKERRER KAYIT: Aynı gün, aynı kaynaktan, aynı hisse için ikinci kayıt
     ALINMAZ. Aksi halde taramayı 5 kez çalıştırmak o günün tavsiyesini 5 kat
     ağırlıklandırıp istatistiği bozardı.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import numpy as np
import pandas as pd

KLASOR = os.path.dirname(os.path.abspath(__file__))
TAVSIYE_DOSYASI = os.path.join(KLASOR, "tavsiye_gecmisi.json")

UFUKLAR = (5, 10, 20)          # kaç iş günü sonrası ölçülsün
KAYNAK_TARAMA = "One Cikan Hisseler"
KAYNAK_ORUNTU_GUNLUK = "Yukselebilecek (gunluk)"      # eski sistem — geçmiş kayıtlar için korunur
KAYNAK_ORUNTU_HAFTALIK = "Yukselebilecek (haftalik)"  # eski sistem — geçmiş kayıtlar için korunur
KAYNAK_GUNLUK_SCRIPT = "Gunluk Tarama (script)"
# Yeni VADE sistemi: sinyal artık tek değil, kısa/orta/uzun vade ayrı ayrı
# üretiliyor ve performansları da ayrı ölçülüyor (hangi vadede daha isabetli
# olduğunu görebilmek için).
KAYNAK_VADE_KISA = "Vade: Kisa (~2 hafta)"
KAYNAK_VADE_ORTA = "Vade: Orta (~3 ay)"
KAYNAK_VADE_UZUN = "Vade: Uzun (~6 ay)"


# ─────────────────────────────────────────────────────────────────────────────
# Depolama
# ─────────────────────────────────────────────────────────────────────────────
def _oku() -> list:
    if not os.path.exists(TAVSIYE_DOSYASI):
        return []
    try:
        with open(TAVSIYE_DOSYASI, encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, list) else []
    except Exception:
        return []


def _yaz(kayitlar: list):
    with open(TAVSIYE_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(kayitlar, f, ensure_ascii=False, indent=2)


def kaydet(kaynak: str, satirlar: list, tarih: str = None) -> dict:
    """Bir tarama sonucunu kaydeder.

    satirlar: [{"sembol": "THYAO", "sinyal": "AL", "puan": 68.0,
                "fiyat": 285.5, "ek": {...}}, ...]
    Dönüş: {"eklenen": n, "atlanan_mukerrer": m, "toplam": k}
    """
    tarih = tarih or dt.date.today().isoformat()
    mevcut = _oku()
    # Aynı gün + aynı kaynak + aynı hisse zaten varsa tekrar eklenmez (bkz. kural 4).
    var_olan = {(k.get("tarih"), k.get("kaynak"), k.get("sembol")) for k in mevcut}

    eklenen, atlanan = 0, 0
    for s in satirlar:
        sembol = str(s.get("sembol") or "").strip().upper().replace(".IS", "")
        if not sembol:
            continue
        anahtar = (tarih, kaynak, sembol)
        if anahtar in var_olan:
            atlanan += 1
            continue
        fiyat = s.get("fiyat")
        try:
            fiyat = float(fiyat) if fiyat is not None else None
            if fiyat is not None and (fiyat != fiyat or fiyat <= 0):
                fiyat = None
        except (TypeError, ValueError):
            fiyat = None

        mevcut.append({
            "tarih": tarih,
            "kaynak": kaynak,
            "sembol": sembol,
            "sinyal": s.get("sinyal"),
            "puan": s.get("puan"),
            "kayit_anindaki_fiyat": fiyat,
            "ek": s.get("ek") or {},
            "kayit_zamani": dt.datetime.now().isoformat(timespec="seconds"),
        })
        var_olan.add(anahtar)
        eklenen += 1

    _yaz(mevcut)
    return {"eklenen": eklenen, "atlanan_mukerrer": atlanan, "toplam": len(mevcut)}


def gecmisi_getir() -> pd.DataFrame:
    kayitlar = _oku()
    if not kayitlar:
        return pd.DataFrame(columns=["tarih", "kaynak", "sembol", "sinyal", "puan",
                                      "kayit_anindaki_fiyat"])
    df = pd.DataFrame(kayitlar)
    df["tarih"] = pd.to_datetime(df["tarih"], errors="coerce")
    return df.dropna(subset=["tarih"]).sort_values("tarih")


def temizle():
    """Tüm tavsiye geçmişini siler (geri alınamaz)."""
    if os.path.exists(TAVSIYE_DOSYASI):
        os.remove(TAVSIYE_DOSYASI)


# ─────────────────────────────────────────────────────────────────────────────
# Performans hesabı
# ─────────────────────────────────────────────────────────────────────────────
def _kapanis_serisi(df: pd.DataFrame):
    if df is None or len(df) == 0 or "Close" not in getattr(df, "columns", []):
        return None
    s = df["Close"].copy()
    try:
        s.index = pd.to_datetime(s.index)
    except Exception:
        return None
    s = s[s.index.notna()]
    s = pd.to_numeric(s, errors="coerce")
    s = s[s.notna() & (s > 0)]
    if s.empty:
        return None
    return s[~s.index.duplicated(keep="last")].sort_index()


def _ileri_getiri(seri: pd.Series, tarih, ufuk: int):
    """(giris_fiyati, cikis_fiyati, getiri_yuzde, olgun_mu) döner.

    Tavsiye tarihinde işlem yoksa (tatil/hafta sonu) SONRAKİ ilk işlem günü
    giriş kabul edilir — gerçekte de o gün alım yapılabilirdi.
    """
    if seri is None or len(seri) == 0:
        return None, None, None, False
    konumlar = seri.index.searchsorted(pd.Timestamp(tarih), side="left")
    i = int(konumlar)
    if i >= len(seri):
        return None, None, None, False       # tavsiye verideki son günden sonra
    giris = float(seri.iloc[i])
    j = i + ufuk
    if j >= len(seri):
        return giris, None, None, False      # henüz olgunlaşmadı
    cikis = float(seri.iloc[j])
    if giris <= 0:
        return None, None, None, False
    return giris, cikis, 100.0 * (cikis / giris - 1.0), True


def performans_hesapla(fiyat_getirici, endeks_df=None, ufuklar: tuple = UFUKLAR,
                        ilerleme=None) -> pd.DataFrame:
    """Kaydedilmiş her tavsiyeyi gerçek fiyatlarla puanlar.

    fiyat_getirici: sembol -> OHLCV DataFrame döndüren fonksiyon
                    (örn. lambda s: vk.fiyat_gecmisi(s, 2.0))
    endeks_df     : BIST100 OHLCV (endeks üstü getiri için; None ise atlanır)
    """
    gecmis = gecmisi_getir()
    if gecmis.empty:
        return pd.DataFrame()

    endeks_seri = _kapanis_serisi(endeks_df)
    seri_onbellek = {}
    satirlar = []
    semboller = list(dict.fromkeys(gecmis["sembol"].tolist()))

    for idx, sembol in enumerate(semboller):
        if ilerleme is not None:
            try:
                ilerleme(idx, len(semboller), sembol)
            except Exception:
                pass
        try:
            seri_onbellek[sembol] = _kapanis_serisi(fiyat_getirici(sembol))
        except Exception:
            seri_onbellek[sembol] = None

    for _, k in gecmis.iterrows():
        seri = seri_onbellek.get(k["sembol"])
        satir = {
            "tarih": k["tarih"], "kaynak": k["kaynak"], "sembol": k["sembol"],
            "sinyal": k.get("sinyal"), "puan": k.get("puan"),
            "kayit_fiyati": k.get("kayit_anindaki_fiyat"),
        }
        veri_var = seri is not None
        satir["veri_bulundu"] = veri_var
        for ufuk in ufuklar:
            if not veri_var:
                satir[f"getiri_{ufuk}g"] = None
                satir[f"olgun_{ufuk}g"] = False
                satir[f"endeks_ustu_{ufuk}g"] = None
                continue
            giris, cikis, getiri, olgun = _ileri_getiri(seri, k["tarih"], ufuk)
            satir[f"getiri_{ufuk}g"] = getiri
            satir[f"olgun_{ufuk}g"] = olgun
            if olgun and endeks_seri is not None:
                _, _, endeks_getiri, endeks_olgun = _ileri_getiri(endeks_seri, k["tarih"], ufuk)
                satir[f"endeks_ustu_{ufuk}g"] = (
                    getiri - endeks_getiri if (endeks_olgun and endeks_getiri is not None) else None)
            else:
                satir[f"endeks_ustu_{ufuk}g"] = None
            if ufuk == ufuklar[0]:
                satir["giris_fiyati"] = giris
        satirlar.append(satir)

    return pd.DataFrame(satirlar)


def performans_ozeti(perf_df: pd.DataFrame, ufuklar: tuple = UFUKLAR) -> dict:
    """Kaynak bazlı ve sinyal bazlı dürüst özet."""
    if perf_df is None or perf_df.empty:
        return {"n_toplam": 0, "kaynak_tablo": pd.DataFrame(),
                "sinyal_tablo": pd.DataFrame(), "olgunluk": {}}

    olgunluk = {}
    for ufuk in ufuklar:
        kolon = f"olgun_{ufuk}g"
        if kolon in perf_df.columns:
            olgunluk[f"{ufuk}g"] = {
                "olgun": int(perf_df[kolon].sum()),
                "bekleyen": int((~perf_df[kolon].astype(bool)).sum()),
            }

    def _grupla(anahtar):
        satirlar = []
        for deger, grup in perf_df.groupby(anahtar, dropna=False):
            satir = {anahtar: deger, "kayit": len(grup)}
            for ufuk in ufuklar:
                gk, ok = f"getiri_{ufuk}g", f"olgun_{ufuk}g"
                if gk not in grup.columns:
                    continue
                olgun = grup[grup[ok].astype(bool)]
                satir[f"olgun_{ufuk}g"] = len(olgun)
                if len(olgun) == 0:
                    satir[f"ort_{ufuk}g"] = None
                    satir[f"pozitif_{ufuk}g"] = None
                    satir[f"endeks_ustu_{ufuk}g"] = None
                    continue
                satir[f"ort_{ufuk}g"] = float(olgun[gk].mean())
                satir[f"pozitif_{ufuk}g"] = float(100.0 * (olgun[gk] > 0).mean())
                ek = f"endeks_ustu_{ufuk}g"
                gecerli = olgun[ek].dropna() if ek in olgun.columns else pd.Series(dtype=float)
                satir[ek] = float(gecerli.mean()) if len(gecerli) else None
            satirlar.append(satir)
        return pd.DataFrame(satirlar)

    return {"n_toplam": len(perf_df),
            "kaynak_tablo": _grupla("kaynak"),
            "sinyal_tablo": _grupla("sinyal"),
            "olgunluk": olgunluk}


def metin_raporu(ozet: dict, ufuklar: tuple = UFUKLAR) -> str:
    if not ozet or ozet.get("n_toplam", 0) == 0:
        return ("Henüz kaydedilmiş tavsiye yok. 'Öne Çıkan Hisseler' veya "
                "'Yükselebilecek Hisseler' taramasını çalıştırdığınızda sonuçlar "
                "otomatik kaydedilmeye başlayacak.")

    s = [f"Toplam {ozet['n_toplam']} tavsiye kaydı var.\n"]

    olg = ozet.get("olgunluk", {})
    if olg:
        parcalar = [f"{u}: {d['olgun']} olgun / {d['bekleyen']} bekliyor"
                    for u, d in olg.items()]
        s.append("Olgunlaşma durumu — " + " · ".join(parcalar))
        s.append("  (Yeni verilmiş bir tavsiyenin uzun ufuk getirisi henüz OLUŞMAMIŞTIR; "
                 "bu kayıtlar ortalamaya KATILMAZ, ayrı sayılır.)")

    ana = ufuklar[len(ufuklar) // 2]
    kt = ozet["kaynak_tablo"]
    if kt is not None and not kt.empty:
        s.append(f"\nKaynak bazlı sonuçlar ({ana} iş günlük ufuk):")
        for _, r in kt.iterrows():
            n_olgun = int(r.get(f"olgun_{ana}g") or 0)
            if n_olgun == 0:
                s.append(f"  {r['kaynak']}: {int(r['kayit'])} kayıt — henüz olgunlaşan yok.")
                continue
            ort = r.get(f"ort_{ana}g")
            poz = r.get(f"pozitif_{ana}g")
            eu = r.get(f"endeks_ustu_{ana}g")
            metin = (f"  {r['kaynak']}: {n_olgun} olgun kayıt — ortalama %{ort:+.2f}, "
                     f"pozitif oran %{poz:.0f}")
            if eu is not None:
                metin += f", ENDEKS ÜSTÜ %{eu:+.2f}"
            s.append(metin)

    st_ = ozet["sinyal_tablo"]
    if st_ is not None and not st_.empty and len(st_) > 1:
        s.append(f"\nSinyal bazlı sonuçlar ({ana} iş günlük ufuk):")
        for _, r in st_.iterrows():
            n_olgun = int(r.get(f"olgun_{ana}g") or 0)
            if n_olgun == 0:
                continue
            ort = r.get(f"ort_{ana}g")
            poz = r.get(f"pozitif_{ana}g")
            s.append(f"  {r['sinyal']}: {n_olgun} olgun — ortalama %{ort:+.2f} "
                     f"(pozitif oran %{poz:.0f})")

    s.append("\n⚠️ NASIL OKUNMALI: Mutlak getiri tek başına yanıltıcıdır — piyasa yükselirken "
             "kazanmak marifet değildir. Asıl ölçüt ENDEKS ÜSTÜ getiridir. Ayrıca komisyon ve "
             "işlem maliyeti bu hesaba DAHİL DEĞİLDİR. Az sayıda kayıtla (örn. 20'den az olgun "
             "kayıt) çıkarılan sonuç istatistiksel olarak anlamsızdır; birkaç ay veri birikmesini "
             "bekleyin.")
    return "\n".join(s)
