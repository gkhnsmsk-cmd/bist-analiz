# -*- coding: utf-8 -*-
"""
gunluk_tarama.py — Streamlit ARAYÜZÜ OLMADAN çalışan günlük tavsiye taraması.
════════════════════════════════════════════════════════════════════════════
HİÇBİR alım-satım emri vermez veya simüle etmez. Portföyünüz + izleme
listenizdeki hisseler için AL/SAT/TAKAS önerisi üretir ve "gunluk_log.txt"
dosyasına yazar. Uygulamayı açmadan, Windows Görev Zamanlayıcısı ile her gün
otomatik çalıştırabilmeniz için vardır (bkz. OKU_BENI.txt).

Canlı fiyatlar için birincil kaynak Mynet Finans'tır (veri_katmani.canli_fiyat_cek).

ÇALIŞTIRMA:
  - Elle: GUNLUK_TARAMA.bat dosyasına çift tıklayın.
  - Otomatik: Windows Görev Zamanlayıcısı'na GUNLUK_TARAMA.bat'ı ekleyin.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import veri_katmani as vk
import analiz_motoru as am
import portfoy_takip as pt
import llm_ajanlari as la
import tavsiye_kaydi as tkd

KLASOR = os.path.dirname(os.path.abspath(__file__))
IZLEME_DOSYASI = os.path.join(KLASOR, "izleme_listesi.txt")
LOG_DOSYASI = os.path.join(KLASOR, "gunluk_log.txt")

VARSAYILAN_IZLEME = ["THYAO", "ASELS", "SISE", "KCHOL", "EREGL", "BIMAS", "TUPRS", "GARAN"]


def _izleme_listesi_oku() -> list:
    if not os.path.exists(IZLEME_DOSYASI):
        with open(IZLEME_DOSYASI, "w", encoding="utf-8") as f:
            f.write("# Her satıra bir hisse kodu yazın (örn. THYAO). '#' ile başlayan satırlar yok sayılır.\n")
            for s in VARSAYILAN_IZLEME:
                f.write(s + "\n")
        return VARSAYILAN_IZLEME
    liste = []
    with open(IZLEME_DOSYASI, encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip().upper().replace(".IS", "")
            if satir and not satir.startswith("#"):
                liste.append(satir)
    return liste or VARSAYILAN_IZLEME


def _log_yaz(satirlar: list):
    zaman = dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    with open(LOG_DOSYASI, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*70}\n{zaman} — Günlük tavsiye taraması\n{'='*70}\n")
        for s in satirlar:
            f.write(s + "\n")


def _canli_fiyat(sembol: str):
    try:
        f = vk.canli_fiyat_cek(sembol)
        if f == f and f > 0:
            return float(f)
    except Exception:
        pass
    try:
        df = vk.fiyat_gecmisi(sembol, 0.2)
        if not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return None


def calistir():
    izleme_listesi = _izleme_listesi_oku()
    portfoy_semboller = [p["sembol"] for p in pt.pozisyonlari_getir()]
    hisseler = list(dict.fromkeys(portfoy_semboller + izleme_listesi))

    log_satirlari = [f"İzlenen hisseler: {', '.join(hisseler)}"]

    try:
        endeks = vk.endeks_gecmisi(2.0)
    except Exception as e:
        log_satirlari.append(f"UYARI: Endeks verisi alınamadı ({e}), rejim düzeltmesi olmadan devam.")
        endeks = None

    guncel_fiyatlar = {}
    for s in hisseler:
        fiyat = _canli_fiyat(s)
        if fiyat is not None:
            guncel_fiyatlar[s] = fiyat

    tavsiye_satirlari = []
    for s in hisseler:
        if s not in guncel_fiyatlar:
            log_satirlari.append(f"{s}: veri bulunamadı, atlandı.")
            continue
        try:
            df = vk.fiyat_gecmisi(s, 1.0)
            hp = am.hizli_puan(df, endeks)
            # hizli_puan yetersiz veride Puan=None döndürür; None'a ':.0f'
            # biçimlendirmesi uygulamak TypeError fırlatır.
            if hp["Puan"] is None:
                log_satirlari.append(f"{s}: yeterli geçmiş veri yok, puanlanamadı.")
            else:
                log_satirlari.append(
                    f"{s}: puan={hp['Puan']:.0f} fiyat={guncel_fiyatlar[s]:.2f} → {hp['Karar']}")
                tavsiye_satirlari.append({
                    "sembol": s, "sinyal": hp["Karar"], "puan": hp["Puan"],
                    "fiyat": guncel_fiyatlar[s],
                    "ek": {"kisa": hp.get("Kısa"), "orta": hp.get("Orta"),
                           "uzun": hp.get("Uzun"), "takas": hp.get("Takas")}})
        except Exception as e:
            log_satirlari.append(f"{s}: HATA — {e}")

    # Tavsiyeleri kalıcı kaydet — performansları sonradan gerçek fiyatlarla ölçülsün.
    if tavsiye_satirlari:
        try:
            sonuc_kayit = tkd.kaydet(tkd.KAYNAK_GUNLUK_SCRIPT, tavsiye_satirlari)
            log_satirlari.append(
                f"Tavsiye kaydı: {sonuc_kayit['eklenen']} yeni kayıt eklendi "
                f"({sonuc_kayit['atlanan_mukerrer']} mükerrer atlandı, "
                f"toplam {sonuc_kayit['toplam']} kayıt). "
                "Performansı uygulamadaki 'Tavsiye Geçmişi' sekmesinden izleyebilirsiniz.")
        except Exception as e:
            log_satirlari.append(f"Tavsiye kaydı yapılamadı: {e}")

    # Portföy kâr/zarar + rebalans/takas önerileri (varsa)
    if portfoy_semboller:
        pt.deger_kaydet(guncel_fiyatlar)
        durum = pt.portfoy_durumu(guncel_fiyatlar)
        log_satirlari.append(
            f"Portföy: maliyet={durum['toplam_maliyet']:,.0f} ₺ · güncel değer={durum['toplam_deger']:,.0f} ₺ · "
            f"kâr/zarar={durum['toplam_kar_zarar']:+,.0f} ₺ (%{durum['toplam_kar_zarar_yuzde']:+.2f})"
        )

        portfoy_puanlari = pt.portfoy_puanlarini_hesapla(am, lambda s, y=1.0: vk.fiyat_gecmisi(s, y), endeks)
        aday_havuzu = pt.aday_havuzunu_tara(am, izleme_listesi,
                                            lambda s, y=1.0: vk.fiyat_gecmisi(s, y), endeks,
                                            mevcut_semboller=set(portfoy_semboller))
        oneriler = pt.rebalans_onerileri(portfoy_puanlari, aday_havuzu)
        log_satirlari.append("Rebalans & Takas Sinyal Motoru:")
        for o in oneriler:
            log_satirlari.append("  - " + o["mesaj"])

        for uyari in pt.sektor_yogunlasma_kontrolu(guncel_fiyatlar):
            log_satirlari.append("  " + uyari)

        if la.herhangi_biri_aktif():
            try:
                ozet = la.yonetici_ozeti(durum, oneriler)
                if ozet:
                    log_satirlari.append(f"Yönetici Özeti (LLM): {ozet}")
            except Exception as e:
                log_satirlari.append(f"Yönetici özeti oluşturulamadı: {e}")

    log_satirlari.append("⚠️ Bu tavsiyeler bilgilendirme amaçlıdır, YATIRIM TAVSİYESİ DEĞİLDİR. "
                         "Hiçbir alım-satım emri otomatik gönderilmedi.")

    _log_yaz(log_satirlari)
    print("\n".join(log_satirlari))


if __name__ == "__main__":
    calistir()
