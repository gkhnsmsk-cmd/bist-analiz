# -*- coding: utf-8 -*-
"""
tarama_onbellek.py — "Öne Çıkan Hisseler" ve "Yükselebilecek Hisseler"
taramalarının sonucunu DİSKE yazar/okur.
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR: Bu iki tarama ~600 hissenin verisini indirip her birini analiz
ediyor; uygulama içinde canlı çalıştırıldığında bir kullanıcı için bile
onlarca saniye sürebilir. Ama sonuç GÜN İÇİNDE pek değişmez (teknik göstergeler
günlük kapanışla güncellenir). O yüzden bu taramayı Windows Görev
Zamanlayıcısı ile günde 1-2 kez arka planda (ARKA_PLAN_TARAMA.bat) çalıştırıp
sonucu buraya yazmak, uygulamayı her açtığında/her tıklamada yeniden
hesaplamaktan çok daha hızlıdır. Uygulama önce bu önbelleği okur; önbellek
yoksa veya kullanıcı özellikle isterse canlı taramaya döner.

Bu modül SADECE okuma/yazma yapar — tarama mantığının kendisi app.py ve
arka_plan_tarama.py'de ayrı ayrı tanımlı DEĞİL; ikisi de aynı fonksiyonları
(om.coklu_ufuk_tara, am.hizli_puan üzerinden) çağırır, burada sadece
sonuçlar taşınır.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os

import pandas as pd

KLASOR = os.path.dirname(os.path.abspath(__file__))
ONBELLEK_DOSYASI = os.path.join(KLASOR, "tarama_onbellek.json")

# Önbellek bu süreden eskiyse "bayat" sayılır; uygulama canlı taramayı önerir.
VARSAYILAN_TAZELIK_SAAT = 6.0


def trend_ekle(tablo: pd.DataFrame | None, veriler: dict, sutun: str = "Hisse",
                n: int = 15) -> pd.DataFrame | None:
    """Tabloya, her hissenin son N kapanış fiyatından oluşan bir 'Trend'
    sütunu ekler — sparkline sütun (st.column_config.LineChartColumn) için.
    Hem canlı taramada (app.py) hem arka plan taramasında (arka_plan_tarama.py)
    aynı toplu-indirilen `veriler` sözlüğü zaten elimizde olduğu için ek ağ
    isteği gerektirmez."""
    if tablo is None or len(tablo) == 0 or sutun not in tablo.columns:
        return tablo
    tablo = tablo.copy()
    def _trend(sembol):
        df = veriler.get(sembol)
        if df is None or "Close" not in df.columns or len(df) == 0:
            return None
        return df["Close"].tail(n).tolist()
    tablo["Trend"] = tablo[sutun].map(_trend)
    return tablo


def yaz(tarama_tablo: pd.DataFrame | None, yukselecek_vade: pd.DataFrame | None,
        eski_kullanilmiyor: pd.DataFrame | None = None, kapsam: str = "TUM"):
    """Tabloları + zaman damgasını tek dosyaya yazar (var olanı değiştirir).

    İkinci parametre artık VADE tablosudur (Kısa/Orta/Uzun tek tabloda).
    Üçüncü parametre eski iki-tablolu sistemden kalma; kullanılmıyor ama
    çağrı imzası bozulmasın diye korunuyor.
    """
    icerik = {
        "zaman": dt.datetime.now().isoformat(),
        "kapsam": kapsam,
        "surum": 2,
        "tarama": tarama_tablo.to_json(orient="split") if tarama_tablo is not None and len(tarama_tablo) else None,
        "yukselecek_vade": yukselecek_vade.to_json(orient="split") if yukselecek_vade is not None and len(yukselecek_vade) else None,
    }
    gecici = ONBELLEK_DOSYASI + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(icerik, f, ensure_ascii=False)
    os.replace(gecici, ONBELLEK_DOSYASI)  # atomik: yarım yazılmış dosya kalmasın


def _df_yukle(parca):
    if not parca:
        return None
    try:
        return pd.read_json(io.StringIO(parca), orient="split")
    except Exception:
        return None


def oku(tazelik_saat: float = VARSAYILAN_TAZELIK_SAAT):
    """(tarama_df, vade_df, None, zaman_metni, taze_mi) döndürür.

    Eski sürüm (surum<2) önbellek dosyaları vade tablosu içermez; o durumda
    vade_df None döner ve uygulama kullanıcıdan yeniden taramasını ister.
    """
    if not os.path.exists(ONBELLEK_DOSYASI):
        return None, None, None, None, False
    try:
        with open(ONBELLEK_DOSYASI, encoding="utf-8") as f:
            icerik = json.load(f)
    except Exception:
        return None, None, None, None, False

    zaman_iso = icerik.get("zaman")
    try:
        zaman_dt = dt.datetime.fromisoformat(zaman_iso)
    except Exception:
        return None, None, None, None, False

    yas_saat = (dt.datetime.now() - zaman_dt).total_seconds() / 3600
    taze = yas_saat <= tazelik_saat

    tarama_df = _df_yukle(icerik.get("tarama"))
    vade_df = _df_yukle(icerik.get("yukselecek_vade"))
    zaman_metni = zaman_dt.strftime("%d.%m.%Y %H:%M")
    return tarama_df, vade_df, None, zaman_metni, taze
