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
    return True


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


def hepsi():
    a = tarama_uret()
    b = portfoy_uret()
    print("tarama/yukselecek:", "OK" if a else "atlandı (dosya yok)")
    print("portfoy:", "OK" if b else "atlandı (dosya yok)")


if __name__ == "__main__":
    hepsi()
