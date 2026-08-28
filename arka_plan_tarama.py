# -*- coding: utf-8 -*-
"""
arka_plan_tarama.py — Streamlit ARAYÜZÜ OLMADAN "Öne Çıkan Hisseler" ve
"Yükselebilecek Hisseler" taramalarını çalıştırır, sonucu tarama_onbellek.py
üzerinden diske yazar ve tavsiyeleri tavsiye_kaydi'ne kaydeder.
══════════════════════════════════════════════════════════════════════════════
NEDEN VAR: Bu iki tarama TÜM BIST'i (~600 hisse) indirip analiz ediyor; canlı
kullanıcı bekletmeden, günde 1-2 kez arka planda (Windows Görev Zamanlayıcısı)
çalıştırıp sonucu önbelleğe yazmak içindir. Uygulama açıldığında bu önbelleği
okur, tazeyse anında gösterir; kullanıcı isterse yine de "canlı tara" ile
anlık veriyle yeniden hesaplatabilir.

ÇALIŞTIRMA:
  - Elle: ARKA_PLAN_TARAMA.bat dosyasına çift tıklayın.
  - Otomatik: Windows Görev Zamanlayıcısı'na ARKA_PLAN_TARAMA.bat'ı ekleyin
    (örn. hafta içi 09:00 ve 18:00 — bkz. OKU_BENI.txt).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
KLASOR = os.path.dirname(os.path.abspath(__file__))

import pandas as pd

import veri_katmani as vk
import analiz_motoru as am
import tavsiye_kaydi as tkd
import tarama_onbellek as tob

KAPSAM = "TUM"
MIN_HACIM_MILYON_TL = 20.0


def _log(msg):
    zaman = dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    print(f"[{zaman}] {msg}")


def _tarama_calistir(veriler: dict, endeks, rejim=None) -> pd.DataFrame:
    """'Öne Çıkan Hisseler' ile birebir aynı mantık — bkz. app.py sekme_tarama."""
    sonuclar = []
    for s, df in veriler.items():
        try:
            ort_hacim_tl = float((df["Close"] * df["Volume"]).tail(20).mean()) / 1e6
            if ort_hacim_tl < MIN_HACIM_MILYON_TL:
                continue
            satir = am.hizli_puan(df, endeks, rejim=rejim)
            if satir["Puan"] is None:
                continue
            satir["Hisse"] = s
            # Dipten dönüş güvenlik teyidi (CMF + hacim + ardışık yükseliş) —
            # sadece "düşeni kıran hisseler" göstergesinde rozet olarak
            # kullanılıyor, henüz sert filtre değil (bkz. analiz_motoru.py).
            try:
                g = am.dip_guvenlik_kontrolu(df)
                satir["GuvenliDonus"] = g.get("guvenliDonus")
                satir["GuvenlikNedeni"] = g.get("neden")
            except Exception:
                satir["GuvenliDonus"] = None
                satir["GuvenlikNedeni"] = None
            sonuclar.append(satir)
        except Exception:
            continue
    if not sonuclar:
        return pd.DataFrame()
    tablo = pd.DataFrame(sonuclar)
    kolonlar = ["Hisse", "Puan", "Karar", "Kısa", "Orta", "Uzun", "Takas",
                "Fiyat", "1 Hafta %", "1 Ay %", "3 Ay %", "1 Yıl %", "Hacim(M₺)",
                "GuvenliDonus", "GuvenlikNedeni"]
    tablo = tablo[kolonlar].sort_values("Puan", ascending=False).reset_index(drop=True)
    tablo.index += 1
    return tablo


İSIM_BACKFILL_LIMIT = 700  # kullanıcı isteği: parçalı doldurma çok yavaş kaldı — pratikte tüm BIST'i tek seferde kapsar


def _sirket_adlarini_tazele(semboller):
    """Şirket adı önbelleğini (hisse_adlari.json) eksik semboller için
    tamamlar. NEDEN VAR: kullanıcı geri bildirimi — "hâlâ etiketlerde
    firmaların tam adı yazmıyor". Kart bileşenleri her zaman h.ad'ı
    gösteriyordu (bkz. Task #11), ama hisse_adlari.json hiç üretilmemişti;
    adlari_indir() sadece app.py'deki elle tıklanan bir düğmeden
    çağrılıyordu, bulut otomasyonunda hiç çalışmamıştı. Bu yüzden yerleşik
    ~48 tanınmış hisse dışında HER sembol için ad==kod'du (görünürde hiçbir
    şey değişmemiş gibi görünüyordu). Ağ yükünü tek çalıştırmada şişirmemek
    için, önbellekte eksik sembollerden en fazla İSIM_BACKFILL_LIMIT tanesi
    indirilir — kalan günlerde otomatik olarak tamamlanır."""
    try:
        import hisse_adlari as ha
        mevcut = ha.adlari_getir()
        eksik = [s for s in semboller if s not in mevcut][:İSIM_BACKFILL_LIMIT]
        if not eksik:
            _log("Şirket adı önbelleği zaten tam.")
            return
        _log(f"{len(eksik)} hissenin şirket adı eksik — indiriliyor...")
        ha.adlari_indir(eksik, vk.toplu_temel_veriler)
        _log("Şirket adı önbelleği güncellendi: hisse_adlari.json")
    except Exception as e:
        _log(f"UYARI: Şirket adları indirilemedi: {e}")


def calistir():
    _log("Arka plan taraması başlıyor...")
    semboller = vk.sembol_listesi(KAPSAM)
    _log(f"{len(semboller)} hisse için veri indiriliyor (kapsam={KAPSAM})...")
    _sirket_adlarini_tazele(semboller)
    veriler = vk.toplu_fiyat(semboller, yil=2.0)
    endeks = vk.endeks_gecmisi(2.0)
    _log(f"{len(veriler)} hissenin verisi hazır. Puanlama taraması çalışıyor...")

    # Piyasa rejimi — riskli ortamda tüm puanlar otomatik kısılır. Bu, canlı
    # taramayla (app.py) aynı sonucu vermesi için ŞART.
    try:
        rejim = am.piyasa_rejimi(endeks, vk.usdtry_gecmisi(1.5), vk.tefas_hisse_trendi(6))
        _log(f"Piyasa rejimi: {rejim['puan']:.0f}/100 — {rejim['durum']}")
    except Exception as e:
        rejim = None
        _log(f"UYARI: Piyasa rejimi hesaplanamadı ({e}) — düzeltme uygulanmayacak.")

    tarama_tablo = _tarama_calistir(veriler, endeks, rejim)
    tarama_tablo = tob.trend_ekle(tarama_tablo, veriler)
    _log(f"Puanlama taraması bitti: {len(tarama_tablo)} hisse puanlandı.")

    _log("Vade taraması (Kısa/Orta/Uzun, teknik puan tabanlı) çalışıyor...")
    vade_tablo = am.vade_taramasi(veriler, ust_sinir=40, endeks_df=endeks, rejim=rejim)
    vade_tablo = tob.trend_ekle(vade_tablo, veriler)
    _log(f"Vade taraması bitti: {len(vade_tablo)} hisse üç vadede değerlendirildi.")

    tob.yaz(tarama_tablo, vade_tablo, kapsam=KAPSAM)
    _log(f"Önbellek yazıldı: {tob.ONBELLEK_DOSYASI}")

    # MA kırılım taraması (Task #19, kullanıcının paylaştığı örnek tabloya
    # dayanır) — puanlamadan bağımsız, ayrı bilgi amaçlı liste.
    try:
        kirilim = am.ma_kirilim_taramasi(veriler)
        with open(os.path.join(KLASOR, "ma_kirilim.json"), "w", encoding="utf-8") as f:
            json.dump({"zaman": dt.datetime.now().isoformat(), **kirilim}, f, ensure_ascii=False)
        _log("MA kırılım taraması yazıldı: ma_kirilim.json")
    except Exception as e:
        _log(f"UYARI: MA kırılım taraması başarısız ({e}) — atlandı.")

    # Tavsiyeleri kalıcı kaydet — app.py'deki canlı taramayla AYNI kayıt mantığı.
    #
    # ÖĞRENME MOTORU (ogrenme_motoru.py): Her kayda, KARAR ANINDA bilinen
    # özelliklerin anlık görüntüsü (snapshot) eklenir. Sonradan "bu karar neden
    # yanlış çıktı?" sorusu ancak o anda ne bildiğimiz kayıtlıysa
    # cevaplanabilir. Snapshot yalnızca geçmiş veriden üretilir — ileriye
    # dönük hiçbir bilgi içermez (veri sızıntısı yok).
    try:
        import ogrenme_motoru as om
    except Exception:
        om = None

    def _snapshot(sembol):
        if om is None:
            return {}
        try:
            return om.ozellik_anlik_goruntusu(veriler.get(sembol), rejim)
        except Exception:
            return {}

    try:
        if len(tarama_tablo):
            ust20 = tarama_tablo.head(20)
            sonuc = tkd.kaydet(tkd.KAYNAK_TARAMA, [
                {"sembol": r["Hisse"], "sinyal": r.get("Karar"), "puan": r.get("Puan"),
                 "fiyat": r.get("Fiyat"),
                 "ek": {"kisa": r.get("Kısa"), "orta": r.get("Orta"), "uzun": r.get("Uzun"),
                        "takas": r.get("Takas"), **_snapshot(r["Hisse"])}}
                for _, r in ust20.iterrows()])
            _log(f"Tavsiye kaydı (Öne Çıkan): {sonuc['eklenen']} yeni, {sonuc['atlanan_mukerrer']} mükerrer.")
        # Her VADE ayrı kaynak — hangi vadede daha isabetli olduğunu
        # sonradan ayrı ayrı ölçebilmek için.
        for vade, kaynak_k in (("Kısa", tkd.KAYNAK_VADE_KISA),
                               ("Orta", tkd.KAYNAK_VADE_ORTA),
                               ("Uzun", tkd.KAYNAK_VADE_UZUN)):
            if vade not in vade_tablo.columns:
                continue
            secim = vade_tablo[vade_tablo[vade].astype(str).str.contains("🟢")]
            if len(secim):
                sonuc = tkd.kaydet(kaynak_k, [
                    {"sembol": r["Hisse"], "sinyal": r.get(vade),
                     "puan": r.get(f"{vade} Puan"), "fiyat": r.get("Fiyat"),
                     "ek": {"genel_puan": r.get("Genel Puan"),
                            "bir_ay": r.get("1 Ay %"),
                            "uc_ay": r.get("3 Ay %"),
                            **_snapshot(r["Hisse"])}}
                    for _, r in secim.iterrows()])
                _log(f"Tavsiye kaydı ({vade} vade): {sonuc['eklenen']} yeni, "
                     f"{sonuc['atlanan_mukerrer']} mükerrer.")
    except Exception as e:
        _log(f"UYARI: Tavsiye kaydı yapılamadı: {e}")

    _log("Arka plan taraması tamamlandı ✅")


if __name__ == "__main__":
    calistir()
    # Pusula (docs/pusula/ — GitHub Pages statik SPA) verisi bu taramanın
    # sonucuna bağımlı; tarama bitince otomatik tazelenir (bkz. pusula_veri_uret.py).
    try:
        import pusula_veri_uret as pvu
        pvu.tarama_uret()
        pvu.performans_uret()
        pvu.fon_kurumsal_uret()
        pvu.sistem_durumu_uret()
        pvu.backtest_uret()
        _log("Pusula verisi güncellendi.")
    except Exception as e:
        _log(f"UYARI: Pusula verisi güncellenemedi: {e}")
