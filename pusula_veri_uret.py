# -*- coding: utf-8 -*-
"""
pusula_veri_uret.py — Pusula (React SPA, docs/pusula/) için statik veri
üretici.
══════════════════════════════════════════════════════════════════════════
NEDEN VAR: Pusula, GitHub Pages'te barınan STATİK bir sayfa (Python
çalıştıramaz). Gerçek verinin Pusula'ya ulaşması için tarama_onbellek.json
ve sanal_portfoy.json gibi "zengin" (pandas split-JSON, iç içe) formatları,
tarayıcının doğrudan fetch() ile okuyabileceği SADE, düz JSON dizilerine
dönüştürülüp docs/pusula/data/ altına yazılır.

NE ZAMAN ÇALIŞIR: Bu script tek başına da çalıştırılabilir, ama asıl amacı
mevcut otomasyonun (arka_plan_tarama.py, gunluk_sanal_yatirim.py) sonunda
otomatik tetiklenmektir — böylece veriler kaynak dosyalar güncellendiği an
Pusula'ya da yansır. Bkz. bu iki dosyanın sonundaki çağrı ve
.github/workflows/gunluk_otomasyon.yml'deki "Pusula verisini güncelle" adımı.

ÇIKTI DOSYALARI (docs/pusula/data/):
  tarama.json      — "Öne Çıkan Hisseler" (tarama_onbellek.json:"tarama")
  yukselecek.json  — "Yükselebilecek Hisseler" (tarama_onbellek.json:"yukselecek_vade")
  portfoy.json     — Sanal portföy (sanal_portfoy.json, güncel fiyatlarla)
"""
from __future__ import annotations

import io
import json
import os

import pandas as pd

KLASOR = os.path.dirname(os.path.abspath(__file__))
HEDEF_KLASOR = os.path.join(KLASOR, "docs", "pusula", "data")


def _adlar():
    try:
        import hisse_adlari as ha
        return ha.adlari_getir()
    except Exception:
        return {}


def _karar_to_trend(karar_veya_sinyal: str) -> str:
    """Türkçe emoji+metin karar etiketini Pusula'nın rozet stiline eşler."""
    if not karar_veya_sinyal:
        return "Tut"
    s = str(karar_veya_sinyal)
    if "GÜÇLÜ AL" in s or "GUCLU AL" in s.upper():
        return "Güçlü Al"
    if "GÜÇLÜ SAT" in s or "GUCLU SAT" in s.upper():
        return "Güçlü Sat"
    if "AL" in s.upper():
        return "Al"
    if "SAT" in s.upper():
        return "Sat"
    return "Tut"


def _yaz(dosya_adi: str, veri):
    os.makedirs(HEDEF_KLASOR, exist_ok=True)
    yol = os.path.join(HEDEF_KLASOR, dosya_adi)
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False)
    os.replace(gecici, yol)


def tarama_uret():
    """tarama_onbellek.json -> tarama.json + yukselecek.json"""
    onbellek_yolu = os.path.join(KLASOR, "tarama_onbellek.json")
    if not os.path.exists(onbellek_yolu):
        return False
    try:
        with open(onbellek_yolu, encoding="utf-8") as f:
            icerik = json.load(f)
    except Exception as e:
        print("tarama_onbellek.json okunamadı:", e)
        return False

    adlar = _adlar()
    zaman = icerik.get("zaman")

    def _df(parca):
        if not parca:
            return None
        try:
            return pd.read_json(io.StringIO(parca), orient="split")
        except Exception:
            return None

    tarama_df = _df(icerik.get("tarama"))
    vade_df = _df(icerik.get("yukselecek_vade"))

    def _tarama_satirlari(df):
        if df is None or len(df) == 0:
            return []
        out = []
        for _, r in df.iterrows():
            sembol = str(r.get("Hisse", ""))
            trend_dizisi = r.get("Trend")
            if not isinstance(trend_dizisi, list):
                trend_dizisi = []
            out.append({
                "symbol": sembol,
                "ad": adlar.get(sembol, sembol),
                "fiyat": float(r.get("Fiyat", 0) or 0),
                "degisim1ay": float(r.get("1 Ay %", 0) or 0),
                "degisim3ay": float(r.get("3 Ay %", 0) or 0),
                "puan": float(r.get("Puan", 0) or 0),
                "trend": _karar_to_trend(r.get("Karar")),
                "karar": str(r.get("Karar", "")),
                "hacim": float(r.get("Hacim(M₺)", 0) or 0),
                "spark": [float(x) for x in trend_dizisi][-15:],
            })
        return out

    def _vade_satirlari(df):
        if df is None or len(df) == 0:
            return []
        out = []
        for _, r in df.iterrows():
            sembol = str(r.get("Hisse", ""))
            trend_dizisi = r.get("Trend")
            if not isinstance(trend_dizisi, list):
                trend_dizisi = []
            out.append({
                "symbol": sembol,
                "ad": adlar.get(sembol, sembol),
                "fiyat": float(r.get("Fiyat", 0) or 0),
                "genelPuan": float(r.get("Genel Puan", 0) or 0),
                "kisa": str(r.get("Kısa", "")),
                "orta": str(r.get("Orta", "")),
                "uzun": str(r.get("Uzun", "")),
                "trend": _karar_to_trend(r.get("Kısa")),
                "degisim1ay": float(r.get("1 Ay %", 0) or 0),
                "degisim3ay": float(r.get("3 Ay %", 0) or 0),
                "hacim": float(r.get("Hacim(M₺)", 0) or 0),
                "spark": [float(x) for x in trend_dizisi][-15:],
            })
        return out

    _yaz("tarama.json", {"zaman": zaman, "hisseler": _tarama_satirlari(tarama_df)})
    _yaz("yukselecek.json", {"zaman": zaman, "hisseler": _vade_satirlari(vade_df)})
    _yaz("dip_donusu.json", {"zaman": zaman, "hisseler": _dip_donusu_satirlari(tarama_df, adlar)})
    return True


# ── "Düşeni Kıran Hisseler" (dip dönüşü) ────────────────────────────────
# NEDEN AYRI BİR ANALİZ MOTORU YOK: tarama_onbellek.json:"tarama" tablosu
# (TÜM BIST, ~421 hisse) zaten her hisse için Kısa/Orta/Uzun vade PUANLARINI
# (0-100) içeriyor — bunlar analiz_motoru.kisa_vade/orta_vade/uzun_vade'nin
# çıktısı. "Düşen ama dönüşe geçen" hisse, matematiksel olarak şudur: orta/
# uzun vade puanı hâlâ zayıf (geçmiş düşüşü yansıtıyor) AMA kısa vade puanı
# belirgin biçimde yükselmiş (RSI/MACD gibi kısa vadeli göstergeler dönüş
# sinyali veriyor) — yani "dönüş gücü" = Kısa − min(Orta, Uzun). Bu, YENİ bir
# gösterge ama var olan puanlardan türetildiği için yeni bir tarama/indirme
# gerektirmez, anında hesaplanır.
_DIP_MIN_3AY_DUSUS = -8.0    # en az %8 düşmüş olmalı ("düşeni" koşulu)
_DIP_MIN_KISA_PUAN = 55.0   # kısa vade puanı zaten toparlanmaya başlamış olmalı
_DIP_MIN_DONUS_GUCU = 10.0  # kısa vade ile orta/uzun arasındaki makas


def _dip_donusu_satirlari(tarama_df, adlar, ust_sinir: int = 40):
    if tarama_df is None or len(tarama_df) == 0:
        return []
    df = tarama_df.copy()
    gerekli = {"Kısa", "Orta", "Uzun", "3 Ay %"}
    if not gerekli.issubset(df.columns):
        return []
    df["min_orta_uzun"] = df[["Orta", "Uzun"]].min(axis=1)
    df["donus_gucu"] = df["Kısa"] - df["min_orta_uzun"]
    aday = df[
        (df["3 Ay %"] <= _DIP_MIN_3AY_DUSUS)
        & (df["Kısa"] >= _DIP_MIN_KISA_PUAN)
        & (df["donus_gucu"] >= _DIP_MIN_DONUS_GUCU)
    ].sort_values("donus_gucu", ascending=False).head(ust_sinir)

    out = []
    for _, r in aday.iterrows():
        sembol = str(r.get("Hisse", ""))
        trend_dizisi = r.get("Trend")
        if not isinstance(trend_dizisi, list):
            trend_dizisi = []
        out.append({
            "symbol": sembol,
            "ad": adlar.get(sembol, sembol),
            "fiyat": float(r.get("Fiyat", 0) or 0),
            "kisaPuan": float(r.get("Kısa", 0) or 0),
            "ortaPuan": float(r.get("Orta", 0) or 0),
            "uzunPuan": float(r.get("Uzun", 0) or 0),
            "donusGucu": float(r.get("donus_gucu", 0) or 0),
            "degisim1ay": float(r.get("1 Ay %", 0) or 0),
            "degisim3ay": float(r.get("3 Ay %", 0) or 0),
            "hacim": float(r.get("Hacim(M₺)", 0) or 0),
            "trend": "Al" if r.get("Kısa", 0) >= 65 else "Tut",
            "spark": [float(x) for x in trend_dizisi][-15:],
        })
    return out


def portfoy_uret():
    """sanal_portfoy.json -> portfoy.json (Pusula'nın okuyacağı sade biçim)."""
    yol = os.path.join(KLASOR, "sanal_portfoy.json")
    if not os.path.exists(yol):
        return False
    try:
        with open(yol, encoding="utf-8") as f:
            p = json.load(f)
    except Exception as e:
        print("sanal_portfoy.json okunamadı:", e)
        return False

    adlar = _adlar()
    pozisyonlar = []
    for poz in p.get("pozisyonlar", []):
        sembol = poz.get("sembol", "")
        pozisyonlar.append({
            "symbol": sembol,
            "ad": adlar.get(sembol, sembol),
            "adet": poz.get("adet", 0),
            "maliyet": poz.get("maliyet", 0),
            "sonFiyat": poz.get("son_fiyat", poz.get("maliyet", 0)),
            "eklenmeTarihi": poz.get("eklenme_tarihi"),
        })

    _yaz("portfoy.json", {
        "nakit": p.get("nakit", 0),
        "baslangicButce": p.get("baslangic_butce", 0),
        "baslangicTarihi": p.get("baslangic_tarihi"),
        "sonRebalansTarihi": p.get("son_rebalans_tarihi"),
        "aktif": p.get("aktif", True),
        "pozisyonlar": pozisyonlar,
    })
    return True


def performans_uret():
    """sanal_deger_gecmisi.json + tavsiye_gecmisi.json -> performans.json.

    NEDEN CANLI HESAPLAMIYORUZ: tavsiye_kaydi.performans_hesapla() her tavsiye
    için GÜNCEL fiyat indirmesi gerektirir (yüzlerce sembol) — bu, her
    otomasyon çalışmasında ekstra dakikalarca sürer. Onun yerine ZATEN
    biriken iki hafif kaynağı kullanıyoruz: sanal portföyün günlük değer
    geçmişi (gerçek, ölçülmüş getiri) ve son tavsiye kayıtları (liste
    halinde, performans hesabı olmadan) — ikisi de anında, ağ isteği
    olmadan üretilir.
    """
    deger_yolu = os.path.join(KLASOR, "sanal_deger_gecmisi.json")
    tavsiye_yolu = os.path.join(KLASOR, "tavsiye_gecmisi.json")

    esitegri = []
    if os.path.exists(deger_yolu):
        try:
            with open(deger_yolu, encoding="utf-8") as f:
                gecmis = json.load(f)
            esitegri = [{
                "tarih": g.get("tarih"),
                "deger": g.get("toplam_deger", 0),
                "endeks": g.get("endeks"),
            } for g in gecmis]
        except Exception as e:
            print("sanal_deger_gecmisi.json okunamadı:", e)

    son_tavsiyeler = []
    toplam_tavsiye = 0
    if os.path.exists(tavsiye_yolu):
        try:
            with open(tavsiye_yolu, encoding="utf-8") as f:
                tavsiyeler = json.load(f)
            toplam_tavsiye = len(tavsiyeler)
            for t in sorted(tavsiyeler, key=lambda x: x.get("kayit_zamani") or "", reverse=True)[:20]:
                son_tavsiyeler.append({
                    "tarih": t.get("tarih"),
                    "sembol": t.get("sembol"),
                    "kaynak": t.get("kaynak"),
                    "sinyal": t.get("sinyal"),
                    "fiyat": t.get("kayit_anindaki_fiyat"),
                })
        except Exception as e:
            print("tavsiye_gecmisi.json okunamadı:", e)

    # Başlangıca göre getiri yüzdesi — endeks karşılaştırmalı, dürüst bakış.
    getiri_yuzde = None
    endeks_getiri_yuzde = None
    if len(esitegri) >= 2:
        ilk, son = esitegri[0], esitegri[-1]
        if ilk.get("deger"):
            getiri_yuzde = 100 * (son["deger"] / ilk["deger"] - 1)
        if ilk.get("endeks") and son.get("endeks"):
            endeks_getiri_yuzde = 100 * (son["endeks"] / ilk["endeks"] - 1)

    _yaz("performans.json", {
        "esitegri": esitegri,
        "getiriYuzde": getiri_yuzde,
        "endeksGetiriYuzde": endeks_getiri_yuzde,
        "sonTavsiyeler": son_tavsiyeler,
        "toplamTavsiyeSayisi": toplam_tavsiye,
    })
    return True


def hepsi():
    a = tarama_uret()
    b = portfoy_uret()
    c = performans_uret()
    print("tarama/yukselecek/dip_donusu:", "OK" if a else "atlandı (dosya yok)")
    print("portfoy:", "OK" if b else "atlandı (dosya yok)")
    print("performans:", "OK" if c else "atlandı (dosya yok)")


if __name__ == "__main__":
    hepsi()
