# -*- coding: utf-8 -*-
"""
gunluk_sanal_yatirim.py — Streamlit ARAYÜZÜ OLMADAN çalışan sanal portföy motoru.
══════════════════════════════════════════════════════════════════════════════
SANAL PARAYLA TEST/KANITLAMA amaçlıdır — GERÇEK bir aracı kuruma HİÇBİR emir
gönderilmez. Kullanıcının belirlediği sanal bütçeyle (varsayılan 1.000.000 TL),
motorun kendi kararıyla otonom şekilde sanal hisse alıp satar:

  • Her gün (bu script çalıştığında)  : portföy değeri kaydedilir, pozisyonlar
                                        puanlanır ve KURAL TABANLI alım-satım
                                        kararı verilir.

TAKVİM KISITI YOKTUR (18.08.2026'da kullanıcı kararıyla kaldırıldı). Motor her
gün karar verir ama YALNIZCA GEREKÇE VARSA işlem yapar:
    SAT   → puan < 45  veya  takip eden stop tetiklendi
    AL    → boş pozisyon yeri + puan >= 52
    TAKAS → portföy doluysa, yeni aday en zayıftan 8 puan daha iyiyse
Bir hissenin ne kadar elde tutulacağına takvim değil, hissenin kendi durumu
karar verir; ayrıntı için bkz. sanal_yatirimci.gunluk_karar().

Sonuçlar "sanal_yatirim_log.txt" dosyasına eklenir. Windows Görev
Zamanlayıcısı'na GUNLUK_SANAL_YATIRIM.bat eklenerek her gün (borsa
kapanışından sonra, örn. 18:30) otomatik çalıştırılması önerilir.

⚠️ DÜRÜSTLÜK UYARISI: Bu bir simülasyondur. Geçmiş performans gelecekteki
sonuçların garantisi değildir. %10/aylık hedef bir ölçüttür, bir vaat değildir;
motor bu hedefi tutturmak için puanları veya sinyalleri çarpıtmaz.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import veri_katmani as vk
import analiz_motoru as am
import sanal_yatirimci as sv

KLASOR = os.path.dirname(os.path.abspath(__file__))
LOG_DOSYASI = os.path.join(KLASOR, "sanal_yatirim_log.txt")

# Tarama evreni: Tüm BIST (~600 hisse). Bu script arka planda/zamanlanmış
# çalıştığı için (Streamlit içinde bekleyen bir kullanıcı yok) daha yavaş
# olması sorun değildir — en geniş kapsam tercih edilir. Daraltmak isterseniz
# aşağıdaki satırı "XU100" veya "XU030" yapabilirsiniz.
TARAMA_KAPSAMI = "TUM"


def _log_yaz(satirlar: list):
    zaman = dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    with open(LOG_DOSYASI, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*70}\n{zaman} — Sanal Portföy Motoru\n{'='*70}\n")
        for s in satirlar:
            f.write(s + "\n")


def calistir():
    log = []
    sv.baslat_veya_getir()  # ilk çalıştırmada varsayılan 1.000.000 TL ile kurar

    if not sv.motor_aktif_mi():
        log.append("Motor kullanıcı tarafından DURAKLATILMIŞ (Sanal Portföy sekmesinden "
                   "kapatılmış). Bugün hiçbir izleme veya alım-satım yapılmadı. Devam etmek "
                   "için uygulamadaki 'Motoru Aç' düğmesini kullanın.")
        _log_yaz(log)
        print("\n".join(log))
        return

    try:
        endeks = vk.endeks_gecmisi(2.0)
    except Exception as e:
        log.append(f"UYARI: Endeks verisi alınamadı ({e}), rejim düzeltmesi olmadan devam.")
        endeks = None

    try:
        semboller = vk.sembol_listesi(TARAMA_KAPSAMI)
    except Exception as e:
        log.append(f"HATA: Tarama evreni alınamadı ({e}). Bugünkü çalıştırma iptal edildi.")
        _log_yaz(log)
        print("\n".join(log))
        return

    log.append(f"Tarama evreni: {TARAMA_KAPSAMI} ({len(semboller)} hisse)")

    # Toplu veri çekimi — performans için (bkz. app.py 'Yükselebilecek Hisseler').
    veriler = vk.toplu_fiyat(semboller, yil=2.0)
    log.append(f"Toplu veri indirildi: {len(veriler)}/{len(semboller)} hisse için geçmiş veri mevcut.")

    def fiyat_getirici(sembol):
        df = veriler.get(sembol)
        if df is not None and len(df):
            return df
        # ÖNEMLİ: toplu indirmede bazı semboller (geçici ağ sorunu, o günkü
        # veri kaynağı aksaklığı vb.) eksik kalabiliyor. Bu, özellikle motorun
        # SATMAK istediği bir pozisyon için fiyat bulunamayışına ve satışın
        # süresiz ertelenip pozisyonun 'askıda' kalmasına yol açıyordu (bkz.
        # sv.askidaki_satislari_bul). Bu yüzden eksik kalan sembol için tek
        # tek (daha yavaş ama güvenilir) bir yedek deneme yapılır.
        try:
            tekil = vk.fiyat_gecmisi(sembol, 1.0)
            return tekil if tekil is not None and len(tekil) else None
        except Exception:
            return None

    # Mevcut sanal portföydeki hisselerin güncel canlı fiyatlarını çek
    portfoy = sv.portfoy_getir()
    guncel_fiyatlar = {}
    for p in portfoy["pozisyonlar"]:
        sembol = p["sembol"]
        df = veriler.get(sembol)
        if df is not None and len(df):
            guncel_fiyatlar[sembol] = float(df["Close"].iloc[-1])

    # 1) GÜNLÜK İZLEME — her çalıştırmada, işlem yapmadan
    izleme = sv.gunluk_izle(am, fiyat_getirici, endeks, guncel_fiyatlar)
    durum = izleme["durum"]
    log.append(
        f"Günlük izleme: toplam değer={durum['toplam_deger']:,.0f} ₺ "
        f"(başlangıç: {durum['baslangic_butce']:,.0f} ₺, "
        f"kümülatif getiri: %{durum['toplam_getiri_yuzde']:+.2f})")
    for sembol, puan in izleme["puanlar"].items():
        log.append(f"  {sembol}: puan={'—' if puan is None else f'{puan:.0f}'}")

    # 2) KURAL TABANLI KARAR — her gün, takvim kısıtı yok
    sonuc = sv.gunluk_karar(am, fiyat_getirici, endeks, semboller)
    if sonuc["calisti"]:
        log.append(f"Karar motoru çalıştı. {sonuc['neden']}")
        tut = sonuc.get("tutulanlar") or []
        if tut:
            log.append("  ELDE TUTULANLAR (satım gerekçesi oluşmadı):")
            for t in sorted(tut, key=lambda x: -x["puan"]):
                log.append(f"    {t['sembol']}: puan={t['puan']:.0f}")
        if sonuc["zayif_piyasa_uyarisi"]:
            log.append("  ⚠️ ZAYIF PİYASA UYARISI: alım eşiğini (52) geçen hiçbir aday yok. "
                       "Motor uygun aday çıkana kadar nakitte bekliyor — zorla pozisyon açmıyor.")
        if sonuc["islemler"]:
            for islem in sonuc["islemler"]:
                gerekce = islem.get("gerekce", "")
                tutar_metin = f"{islem['tutar']:,.0f} ₺" if islem.get("tutar") is not None else "—"
                log.append(f"  {islem['yon']} {islem['sembol']}: {tutar_metin} — {gerekce}")
        else:
            log.append("  Bugün hiçbir işlem gerekmedi.")
    else:
        log.append(f"Karar motoru çalışamadı: {sonuc['neden']}")

    askida = sv.askidaki_satislari_bul()
    if askida:
        log.append("⚠️ ASKIDA SATIŞ UYARISI — motor aşağıdaki pozisyonları satmak istiyor "
                   "ama fiyat bulunamadığı için satamıyor, günlerdir elde kalmışlar:")
        for a in askida:
            log.append(f"  {a['sembol']}: {a['ilk_tarih']}'den beri ({a['deneme']} başarısız deneme) — "
                       f"{a['gerekce']}")

    # 3) Dürüst performans özeti
    for islem in sonuc.get("islemler", []):
        if islem.get("tutma_gunu") is not None:
            _g = islem.get("getiri_yuzde")
            log.append(f"  ⏱ {islem['sembol']}: {islem['tutma_gunu']} gün tutuldu"
                       + (f", getiri %{_g:+.2f}" if _g is not None else ""))
    guncel_fiyatlar_son = {**guncel_fiyatlar}
    for islem in sonuc.get("islemler", []):
        if islem.get("fiyat") is not None:
            guncel_fiyatlar_son[islem["sembol"]] = islem["fiyat"]
    rapor = sv.performans_raporu(guncel_fiyatlar_son, endeks)
    log.append(
        f"Performans: {rapor['gun_sayisi']} gün ({rapor['ay_sayisi']:.1f} ay) — "
        f"gerçekleşen kümülatif getiri %{rapor['gerceklesen_kumulatif_yuzde']:+.2f}, "
        f"hedefin gerektirdiği %{rapor['hedefe_gore_beklenen_kumulatif_yuzde']:+.2f} "
        f"(hedef: aylık %{rapor['hedef_aylik_yuzde']:.0f})")
    # ── ASIL ÖLÇÜT: endeksi yeniyor mu? ─────────────────────────────────────
    # Mutlak getiri tek başına anlamsız: piyasa düşerken -%2 iyidir, piyasa
    # +%6 çıkarken -%2 kötüdür. Bu satırlar 22.08.2026'da eklendi; o güne
    # kadar rapor "%-1,59" diyordu ama endeksin aynı dönemde %+5,89 yükseldiği
    # (yani motorun %7,49 geride olduğu) hiçbir yerde görünmüyordu.
    _e = rapor.get("endeks") or {}
    if _e.get("veri_var"):
        log.append(f"ENDEKS KARŞILAŞTIRMASI (asıl başarı ölçütü):")
        log.append(f"  Portföy : %{_e['portfoy_yuzde']:+.2f}")
        log.append(f"  BIST 100: %{_e['endeks_yuzde']:+.2f}  "
                   f"({_e['endeks_bas']:,.2f} → {_e['endeks_son']:,.2f})")
        log.append(f"  ENDEKS ÜSTÜ: %{_e['endeks_ustu_yuzde']:+.2f}  "
                   + ("✅ endeksi YENİYOR" if _e["yeniyor_mu"]
                      else "⚠️ endeksin GERİSİNDE — endekse yatırmak daha iyi olurdu"))
    else:
        log.append("ENDEKS KARŞILAŞTIRMASI: endeks verisi alınamadı, "
                   "karşılaştırma yapılamadı (mutlak getiri tek başına yanıltıcıdır).")

    if rapor["hedefi_yakaliyor_mu"] is not None:
        log.append("  Hedefi " + ("YAKALIYOR ✅" if rapor["hedefi_yakaliyor_mu"] else "YAKALAYAMIYOR ⚠️ (dürüst rapor — gizlenmez)"))
    if rapor["maksimum_dusus_yuzde"] is not None:
        log.append(f"  Şimdiye kadarki maksimum düşüş: %{rapor['maksimum_dusus_yuzde']:.2f}")

    log.append("⚠️ Bu SANAL bir portföydür, gerçek para kullanılmamıştır. "
               "Hiçbir gerçek alım-satım emri gönderilmedi.")

    _log_yaz(log)
    print("\n".join(log))


if __name__ == "__main__":
    calistir()
