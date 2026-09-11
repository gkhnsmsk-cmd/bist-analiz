# -*- coding: utf-8 -*-
"""
portfoy_takip.py — Portföy Takip + Rebalans/Takas Sinyal Motoru
════════════════════════════════════════════════════════════════
SADECE TAKİP VE TAVSİYE — hiçbir alım-satım emri vermez veya simüle etmez.

Bu modül:
  1) Kullanıcının portföyünü (hisse, lot, maliyet) yerel "portfoy.json"
     dosyasında saklar (SQLite yok — talep edilen JSON tabanlı basit format).
  2) Güncel fiyatlarla anlık kâr/zarar hesaplar (Portföy Analiz Matrisi).
  3) Rebalans & Takas Sinyal Motoru: portföydeki zayıf hisseler için "KAYIP
     KES", güçlü hisseler için "AL / AĞIRLIK ARTIR" ve zayıf bir hissenin
     yerine izleme listesinden güçlü bir adayla değiştirilmesini öneren
     "TAKAS TAVSİYESİ" üretir.
  4) Sektörel yoğunlaşma (tek hisse/sektör %30 üstü ağırlık) uyarısı verir.

Tüm eşikler ve puanlar analiz_motoru.py'nin ürettiği 0-100 motor puanına
dayanır; bu modül kendi başına fiyat/gösterge hesaplamaz.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pandas as pd

import sektor_haritasi as sh

KLASOR = os.path.dirname(os.path.abspath(__file__))
PORTFOY_DOSYASI = os.path.join(KLASOR, "portfoy.json")
DEGER_GECMISI_DOSYASI = os.path.join(KLASOR, "portfoy_deger_gecmisi.json")

# ── Rebalans eşikleri ────────────────────────────────────────────────────────
ESIK_KAYIP_KES = 35.0      # bu puanın altı → doğrudan SAT
ESIK_ZAYIF = 45.0          # bu puanın altı (ama kayıp-kes üstü) → takas adayı
ESIK_GUCLU = 70.0          # bu puanın üstü → TAŞI / AĞIRLIK ARTIR
ESIK_TAKAS_ADAY = 75.0     # aday havuzunda bu puanın üstü → takas önerisine değer
MAKS_TEK_HISSE_ORANI = 0.30    # portföyün %30'undan fazlası tek hissede → uyarı
MAKS_SEKTOR_ORANI = 0.30       # portföyün %30'undan fazlası tek sektörde → uyarı


# ─────────────────────────────────────────────────────────────────────────────
# JSON depolama
# ─────────────────────────────────────────────────────────────────────────────
def _portfoy_oku() -> list:
    if not os.path.exists(PORTFOY_DOSYASI):
        return []
    try:
        with open(PORTFOY_DOSYASI, encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, list) else []
    except Exception:
        return []


def _portfoy_yaz(liste: list):
    with open(PORTFOY_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=2)


def pozisyonlari_getir() -> list:
    """[{'sembol':..., 'adet':..., 'maliyet':..., 'eklenme_tarihi':...}, ...]"""
    return _portfoy_oku()


def portfoyu_degistir(satirlar: list):
    """Streamlit st.data_editor çıktısını (liste-of-dict / DataFrame kayıtları)
    doğrudan portföy olarak kaydeder. Geçersiz satırlar (boş hisse, sıfır adet)
    otomatik elenir."""
    temiz = []
    simdi = dt.datetime.now().isoformat()
    mevcut = {p["sembol"]: p.get("eklenme_tarihi", simdi) for p in _portfoy_oku()}
    for satir in satirlar:
        sembol = str(satir.get("Hisse Kodu") or satir.get("sembol") or "").strip().upper().replace(".IS", "")
        try:
            adet = float(satir.get("Lot Miktarı") if satir.get("Lot Miktarı") is not None else satir.get("adet", 0))
            maliyet = float(satir.get("Maliyet Fiyatı") if satir.get("Maliyet Fiyatı") is not None else satir.get("maliyet", 0))
        except (TypeError, ValueError):
            continue
        if not sembol or adet <= 0 or maliyet <= 0:
            continue
        temiz.append({
            "sembol": sembol, "adet": adet, "maliyet": maliyet,
            "eklenme_tarihi": mevcut.get(sembol, simdi),
        })
    _portfoy_yaz(temiz)


def pozisyon_ekle(sembol: str, adet: float, maliyet: float):
    """Ağırlıklı ortalama ile ekler/birleştirir (ek alım yapılmış gibi)."""
    sembol = sembol.strip().upper().replace(".IS", "")
    liste = _portfoy_oku()
    for p in liste:
        if p["sembol"] == sembol:
            toplam_adet = p["adet"] + adet
            p["maliyet"] = (p["adet"] * p["maliyet"] + adet * maliyet) / toplam_adet if toplam_adet else maliyet
            p["adet"] = toplam_adet
            _portfoy_yaz(liste)
            return
    liste.append({"sembol": sembol, "adet": adet, "maliyet": maliyet,
                  "eklenme_tarihi": dt.datetime.now().isoformat()})
    _portfoy_yaz(liste)


def pozisyon_guncelle(sembol: str, adet: float, maliyet: float):
    sembol = sembol.strip().upper().replace(".IS", "")
    liste = _portfoy_oku()
    for p in liste:
        if p["sembol"] == sembol:
            p["adet"], p["maliyet"] = adet, maliyet
            _portfoy_yaz(liste)
            return
    liste.append({"sembol": sembol, "adet": adet, "maliyet": maliyet,
                  "eklenme_tarihi": dt.datetime.now().isoformat()})
    _portfoy_yaz(liste)


def pozisyon_sil(sembol: str):
    sembol = sembol.strip().upper().replace(".IS", "")
    liste = [p for p in _portfoy_oku() if p["sembol"] != sembol]
    _portfoy_yaz(liste)


# ─────────────────────────────────────────────────────────────────────────────
# Portföy Analiz Matrisi (kâr/zarar)
# ─────────────────────────────────────────────────────────────────────────────
def portfoy_durumu(guncel_fiyatlar: dict | None = None) -> dict:
    guncel_fiyatlar = guncel_fiyatlar or {}
    pozisyonlar = []
    toplam_maliyet = 0.0
    toplam_deger = 0.0
    for p in _portfoy_oku():
        sembol, adet, maliyet = p["sembol"], p["adet"], p["maliyet"]
        fiyat = guncel_fiyatlar.get(sembol)
        # ÖNEMLİ: vk.canli_fiyat_cek() tüm kaynaklar başarısız olduğunda
        # float('nan') döndürür. NaN, "is not None" kontrolünü GEÇER ve
        # toplama karıştığında portföyün TAMAMINI nan yapar. Geçersiz
        # (NaN/sonsuz/sıfır-altı) fiyatlar burada elenir — ilgili pozisyon
        # "veri yok" olarak gösterilir, toplamlar bozulmaz.
        if fiyat is not None and (fiyat != fiyat or fiyat <= 0 or fiyat in (float("inf"), float("-inf"))):
            fiyat = None
        deger = fiyat * adet if fiyat is not None else None
        maliyet_tutari = adet * maliyet
        kar_zarar = (deger - maliyet_tutari) if deger is not None else None
        kar_zarar_yuzde = (100 * (fiyat / maliyet - 1)) if fiyat is not None and maliyet else None
        pozisyonlar.append({
            "Hisse": sembol, "Adet": round(adet, 4), "Maliyet": round(maliyet, 2),
            "Güncel Fiyat": round(fiyat, 2) if fiyat is not None else None,
            "Maliyet Tutarı": round(maliyet_tutari, 2),
            "Güncel Değer": round(deger, 2) if deger is not None else None,
            "Kâr/Zarar": round(kar_zarar, 2) if kar_zarar is not None else None,
            "Kâr/Zarar %": round(kar_zarar_yuzde, 2) if kar_zarar_yuzde is not None else None,
            "Sektör": sh.sektor_bul(sembol),
            "Eklenme Tarihi": p.get("eklenme_tarihi", "")[:10],
        })
        toplam_maliyet += maliyet_tutari
        if deger is not None:
            toplam_deger += deger

    toplam_kar_zarar = toplam_deger - toplam_maliyet if pozisyonlar else 0.0
    toplam_kar_zarar_yuzde = (100 * toplam_kar_zarar / toplam_maliyet) if toplam_maliyet else 0.0

    return {
        "pozisyonlar": pozisyonlar,
        "toplam_maliyet": round(toplam_maliyet, 2),
        "toplam_deger": round(toplam_deger, 2),
        "toplam_kar_zarar": round(toplam_kar_zarar, 2),
        "toplam_kar_zarar_yuzde": round(toplam_kar_zarar_yuzde, 2),
    }


def deger_kaydet(guncel_fiyatlar: dict):
    durum = portfoy_durumu(guncel_fiyatlar)
    if not durum["pozisyonlar"]:
        return
    try:
        gecmis = json.load(open(DEGER_GECMISI_DOSYASI, encoding="utf-8")) if os.path.exists(DEGER_GECMISI_DOSYASI) else []
    except Exception:
        gecmis = []
    zaman = dt.datetime.now().replace(microsecond=0).isoformat()
    gecmis = [g for g in gecmis if g.get("zaman") != zaman]
    gecmis.append({"zaman": zaman, "toplam_deger": durum["toplam_deger"]})
    with open(DEGER_GECMISI_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(gecmis[-2000:], f, ensure_ascii=False)


def deger_egrisi() -> pd.DataFrame:
    if not os.path.exists(DEGER_GECMISI_DOSYASI):
        return pd.DataFrame(columns=["zaman", "toplam_deger"])
    try:
        gecmis = json.load(open(DEGER_GECMISI_DOSYASI, encoding="utf-8"))
    except Exception:
        gecmis = []
    if not gecmis:
        return pd.DataFrame(columns=["zaman", "toplam_deger"])
    df = pd.DataFrame(gecmis)
    # NOT: dt.datetime.now().isoformat(), mikrosaniye tam sıfırsa ".ffffff"
    # kısmını ATLAR (örn. saat tam saniyeye denk gelirse). Aynı sütunda hem
    # mikrosaniyeli hem mikrosaniyesiz metin karışabilir; pandas'ın katı format
    # eşleştirmesi bu durumda çöker. format='mixed' her satırı ayrı ayrı çözer.
    df["zaman"] = pd.to_datetime(df["zaman"], format="mixed")
    return df.sort_values("zaman")


# ─────────────────────────────────────────────────────────────────────────────
# Rebalans & Takas Sinyal Motoru
# ─────────────────────────────────────────────────────────────────────────────
def portfoy_puanlarini_hesapla(am, fiyat_getirici, endeks_df) -> dict:
    """Portföydeki her hisse için analiz_motoru.hizli_puan ile 0-100 motor
    puanını hesaplar. fiyat_getirici(sembol) -> pd.DataFrame (OHLCV) alan bir
    çağrılabilir olmalıdır (app.py'deki önbellekli _gecmis fonksiyonu gibi)."""
    sonuc = {}
    for p in _portfoy_oku():
        sembol = p["sembol"]
        try:
            df = fiyat_getirici(sembol)
            if df is None or df.empty:
                sonuc[sembol] = {"puan": None, "karar": "VERİ YOK", "fiyat": None}
                continue
            hp = am.hizli_puan(df, endeks_df)
            sonuc[sembol] = {"puan": hp["Puan"], "karar": hp["Karar"], "fiyat": hp["Fiyat"]}
        except Exception as e:
            sonuc[sembol] = {"puan": None, "karar": f"HATA: {e}", "fiyat": None}
    return sonuc


def aday_havuzunu_tara(am, aday_semboller: list, fiyat_getirici, endeks_df,
                       mevcut_semboller: set) -> list:
    """İzleme listesindeki (portföyde olmayan) hisselerin puanlarını hesaplar.
    Yalnızca ESIK_TAKAS_ADAY üzerindeki adaylar takas önerisi için kullanılır."""
    adaylar = []
    for sembol in aday_semboller:
        sembol = sembol.strip().upper().replace(".IS", "")
        if sembol in mevcut_semboller or not sembol:
            continue
        try:
            df = fiyat_getirici(sembol)
            if df is None or df.empty:
                continue
            hp = am.hizli_puan(df, endeks_df)
            # hizli_puan yetersiz veride Puan=None döndürür; None ile float
            # karşılaştırması aşağıdaki sorted() çağrısını çökertir.
            if hp["Puan"] is None or hp["Puan"] != hp["Puan"]:
                continue
            adaylar.append({"sembol": sembol, "puan": hp["Puan"], "fiyat": hp["Fiyat"]})
        except Exception:
            continue
    return sorted(adaylar, key=lambda a: a["puan"], reverse=True)


def rebalans_onerileri(portfoy_puanlari: dict, aday_havuzu: list) -> list:
    """Portföy puanlarına göre AL / SAT / TAKAS aksiyon listesini üretir.
    Dönüş: [{'sembol', 'eylem', 'mesaj', 'puan', 'takas_adayi'}]

    ÖNEMLİ DÜZELTME — HER ZAYIF HİSSEYE FARKLI ADAY:
    Önceki sürüm, aday havuzundaki TEK en iyi hisseyi (aday_havuzu[0]) bütün zayıf
    pozisyonlar için öneriyordu. Portföyde 3 zayıf hisse varsa üçü için de aynı
    hisseyi öneriyor, yani "üç pozisyonunu sat, hepsini tek bir hisseye koy"
    demiş oluyordu. Bu, portföyü tek hisseye yığarak yoğunlaşma riskini
    artırırdı — üstelik modülün kendi MAKS_TEK_HISSE_ORANI kuralıyla çelişerek.
    Artık her zayıf pozisyona havuzdan FARKLI bir aday atanır (puan sırasına
    göre); aday kalmazsa takas yerine "izle" denir.
    """
    oneriler = []
    # Eşiği geçen adaylar, puan sırasıyla; her biri yalnızca BİR kez önerilir.
    uygun_adaylar = [a for a in aday_havuzu
                     if a.get("puan") is not None and a["puan"] >= ESIK_TAKAS_ADAY]
    aday_sirasi = iter(uygun_adaylar)

    for sembol, veri in portfoy_puanlari.items():
        puan = veri["puan"]
        if puan is None:
            oneriler.append({"sembol": sembol, "eylem": "VERİ YOK", "puan": None,
                            "takas_adayi": None,
                            "mesaj": f"{sembol}: güncel veri alınamadığından değerlendirilemedi."})
            continue

        if puan < ESIK_KAYIP_KES:
            oneriler.append({
                "sembol": sembol, "eylem": "KAYIP KES / ELDEN ÇIKAR (SAT)", "puan": puan,
                "takas_adayi": None,
                "mesaj": f"KAYIP KES / ELDEN ÇIKAR (SAT): {sembol} (Puan: {puan:.0f}) — "
                        "motor puanı kritik eşiğin altında, pozisyonun gözden geçirilmesi önerilir.",
            })
        elif puan < ESIK_ZAYIF:
            # Bu zayıf pozisyona, daha önce kullanılmamış bir aday ata.
            aday = None
            for olasi in aday_sirasi:
                if olasi["sembol"] != sembol:
                    aday = olasi
                    break
            if aday is not None:
                oneriler.append({
                    "sembol": sembol, "eylem": "TAKAS", "puan": puan,
                    "takas_adayi": aday,
                    "mesaj": (f"TAKAS TAVSİYESİ: Eldeki {sembol} hissesini (Puan: {puan:.0f}) satarak "
                             f"yerine daha güçlü momentum gösteren {aday['sembol']} hissesini "
                             f"(Puan: {aday['puan']:.0f}) ekleyin."),
                })
            else:
                oneriler.append({
                    "sembol": sembol, "eylem": "ZAYIF / İZLE", "puan": puan,
                    "takas_adayi": None,
                    "mesaj": f"ZAYIF / İZLE: {sembol} (Puan: {puan:.0f}) — kayıp-kes eşiğine yakın, "
                            "ancak izleme listesinde yeterince güçlü (Puan≥"
                            f"{ESIK_TAKAS_ADAY:.0f}) bir takas adayı yok; yakından takip edilmeli.",
                })
        elif puan > ESIK_GUCLU:
            oneriler.append({
                "sembol": sembol, "eylem": "TAŞIMAYA DEVAM ET / AĞIRLIK ARTIR (AL)", "puan": puan,
                "takas_adayi": None,
                "mesaj": f"TAŞIMAYA DEVAM ET / AĞIRLIK ARTIR (AL): {sembol} (Puan: {puan:.0f}) — "
                        "motor puanı güçlü bölgede, pozisyonun korunması/artırılması değerlendirilebilir.",
            })
        else:
            oneriler.append({
                "sembol": sembol, "eylem": "TUT", "puan": puan, "takas_adayi": None,
                "mesaj": f"TUT: {sembol} (Puan: {puan:.0f}) — nötr bölgede, aksiyon gerektirmiyor.",
            })
    return oneriler


def risk_metrikleri(durum: dict, portfoy_puanlari: dict, deger_egrisi_df: pd.DataFrame | None = None) -> dict:
    """Portföyün 'ne kadar sağlıklı dağıtılmış ve ne kadar riskli' sorusuna
    profesyonel yatırım panellerindeki gibi tek bakışta cevap verir.

    Hesaplananlar:
      - agirlikli_puan   : pozisyonların değerle ağırlıklandırılmış ortalama
                            motor puanı (portföyün 'genel sağlığı').
      - en_iyi / en_kotu : puana göre en güçlü ve en zayıf pozisyon.
      - hhi / cesitlendirme_skoru : Herfindahl-Hirschman yoğunlaşma endeksi
                            (0=çok dağınık, 1=tek hissede) ve bunun tersinden
                            türetilen 0-100 çeşitlendirme skoru. N hisseye eşit
                            dağılmış bir portföy 100'e yakın çıkar.
      - gunluk_volatilite / yillik_volatilite : portföy değer geçmişinden
                            günlük getiri standart sapması (yeterli veri varsa).
      - maks_dusus        : değer geçmişindeki en büyük tepe-dip düşüş yüzdesi
                            (maximum drawdown) — kayıt tutulduğu süre için.
    """
    pozisyonlar = durum.get("pozisyonlar", [])
    toplam_deger = durum.get("toplam_deger", 0.0) or 0.0

    # ── Ağırlıklı ortalama puan + en iyi/en kötü ────────────────────────────
    agirlikli_toplam, agirlik_toplam = 0.0, 0.0
    puanli = []
    for poz in pozisyonlar:
        sembol = poz["Hisse"]
        veri = portfoy_puanlari.get(sembol, {})
        puan = veri.get("puan")
        deger = poz.get("Güncel Değer") or 0.0
        if puan is not None:
            agirlikli_toplam += puan * deger
            agirlik_toplam += deger
            puanli.append({"sembol": sembol, "puan": puan, "deger": deger})
    agirlikli_puan = (agirlikli_toplam / agirlik_toplam) if agirlik_toplam else None
    en_iyi = max(puanli, key=lambda x: x["puan"]) if puanli else None
    en_kotu = min(puanli, key=lambda x: x["puan"]) if puanli else None

    # ── Yoğunlaşma / çeşitlendirme (HHI) ────────────────────────────────────
    hhi = None
    cesitlendirme_skoru = None
    if toplam_deger > 0 and pozisyonlar:
        paylar = [(poz.get("Güncel Değer") or 0.0) / toplam_deger for poz in pozisyonlar]
        hhi = sum(p * p for p in paylar)
        n = len(pozisyonlar)
        hhi_esit_dagitilmis = 1.0 / n if n else 1.0
        # HHI'yi [hhi_esit(=en iyi), 1(=en kötü, tek hisse)] aralığından 0-100'e ölçekle.
        if hhi <= hhi_esit_dagitilmis or hhi_esit_dagitilmis >= 1.0:
            cesitlendirme_skoru = 100.0
        else:
            cesitlendirme_skoru = max(0.0, 100.0 * (1 - (hhi - hhi_esit_dagitilmis) / (1 - hhi_esit_dagitilmis)))

    # ── Volatilite + maksimum düşüş (portföy değer geçmişinden) ─────────────
    gunluk_volatilite = yillik_volatilite = maks_dusus = None
    if deger_egrisi_df is not None and len(deger_egrisi_df) > 5:
        seri = deger_egrisi_df.sort_values("zaman")["toplam_deger"].astype(float)
        getiriler = seri.pct_change().dropna()
        if len(getiriler) >= 3:
            gunluk_volatilite = float(getiriler.std()) * 100
            yillik_volatilite = float(getiriler.std()) * (252 ** 0.5) * 100
        tepe = seri.cummax()
        dususler = (seri - tepe) / tepe.replace(0, float("nan"))
        if len(dususler.dropna()):
            maks_dusus = float(dususler.min()) * 100

    return {
        "agirlikli_puan": round(agirlikli_puan, 1) if agirlikli_puan is not None else None,
        "en_iyi": en_iyi, "en_kotu": en_kotu,
        "hhi": round(hhi, 3) if hhi is not None else None,
        "cesitlendirme_skoru": round(cesitlendirme_skoru, 0) if cesitlendirme_skoru is not None else None,
        "pozisyon_sayisi": len(pozisyonlar),
        "gunluk_volatilite": round(gunluk_volatilite, 2) if gunluk_volatilite is not None else None,
        "yillik_volatilite": round(yillik_volatilite, 1) if yillik_volatilite is not None else None,
        "maks_dusus": round(maks_dusus, 1) if maks_dusus is not None else None,
    }


def sektor_yogunlasma_kontrolu(guncel_fiyatlar: dict) -> list:
    """Tek hisse veya tek sektörde %30'dan fazla ağırlık varsa uyarı üretir."""
    durum = portfoy_durumu(guncel_fiyatlar)
    toplam = durum["toplam_deger"]
    uyarilar = []
    if toplam <= 0:
        return uyarilar

    sektor_toplam = {}
    for poz in durum["pozisyonlar"]:
        deger = poz["Güncel Değer"] or 0.0
        oran = deger / toplam
        if oran > MAKS_TEK_HISSE_ORANI:
            uyarilar.append(
                f"⚠️ SEKTÖREL/HİSSE YOĞUNLAŞMA RİSKİ: {poz['Hisse']} tek başına portföyün "
                f"%{oran*100:.1f}'ini oluşturuyor (eşik: %{MAKS_TEK_HISSE_ORANI*100:.0f}). "
                "Çeşitlendirme değerlendirilmelidir.")
        sektor = poz["Sektör"]
        sektor_toplam[sektor] = sektor_toplam.get(sektor, 0.0) + deger

    for sektor, deger in sektor_toplam.items():
        oran = deger / toplam
        if oran > MAKS_SEKTOR_ORANI:
            uyarilar.append(
                f"⚠️ SEKTÖREL YOĞUNLAŞMA RİSKİ: \"{sektor}\" sektörü portföyün %{oran*100:.1f}'ini "
                f"oluşturuyor (eşik: %{MAKS_SEKTOR_ORANI*100:.0f}). "
                + ("(Bu sektör haritası kısmi/elle derlenmiştir — bkz. sektor_haritasi.py.)"
                   if sektor == sh.DIGER else ""))
    return uyarilar


# ═════════════════════════════════════════════════════════════════════════════
# GÜNLÜK ÇIKIŞ KARARI — "bugün satmalı mıyım?"
# ═════════════════════════════════════════════════════════════════════════════
# NEDEN VAR (kullanıcının gerçek kullanım şekli, 18.08.2026):
#   "Yüksek puanlı bir hisseyi bakarak alıyorum. Her gün takip ediyorum.
#    Artıyorsa satmıyorum, sat verirse satıyorum."
#
# Bu iş eskiden Favoriler panelinden yapılmaya çalışılıyordu ama orada ALIŞ
# FİYATI yok; alış fiyatı olmadan ne kâr/zarar ne de stop seviyesi
# hesaplanabilir. Bu bölüm, alış fiyatının ZATEN kayıtlı olduğu bu modüle
# eklendi.
#
# ÇIKIŞ KURALI: TAKİP EDEN STOP (trailing stop) — kullanıcı seçimi.
#   Stop = (alıştan bugüne görülen EN YÜKSEK kapanış) - STOP_ATR_KATSAYISI x ATR
#   Fiyat bu seviyenin altına inerse SAT.
#
# NEDEN PUAN EŞİĞİ DEĞİL: 94.144 noktalık backtestte motor puanının ileri
# getiriyle korelasyonu +0,012 çıktı — yani puan, hissenin yükselip
# düşeceğini pratikte öngörmüyor. "Puan düşene kadar bekle" demek, hisse
# %20 düşerken puanın 55'te takılı kalmasına ve çıkışın kaçmasına yol
# açabilir. Takip eden stop fiyatın KENDİSİNE bakar, tahmine değil.
#
# ZİRVE UYDURULMAZ: Alış tarihinden bugüne kadarki gerçek kapanış serisinden
# hesaplanır. Bu yüzden fonksiyon fiyat geçmişi (df) ister; df yoksa karar
# üretmez ve bunu açıkça söyler — sessizce "TUT" demez.
# ═════════════════════════════════════════════════════════════════════════════

STOP_ATR_KATSAYISI = 2.5
# Stop, alış fiyatının en fazla bu kadar altında olabilir (yüzde).
# None yapılırsa tavan kalkar, saf ATR stop'u kullanılır.
STOP_TAVAN_YUZDE = 10.0


def cikis_karari(sembol: str, maliyet: float, alis_tarihi, df,
                 atr_fn=None) -> dict:
    """Tek bir pozisyon için günlük TUT/SAT kararı.

    sembol       : hisse kodu
    maliyet      : alış fiyatı
    alis_tarihi  : "YYYY-AA-GG" veya ISO tarih (zirve bu tarihten itibaren aranır)
    df           : OHLCV fiyat geçmişi (alış tarihini KAPSAMALIDIR)
    atr_fn       : ATR hesaplayıcı (varsayılan: analiz_motoru.atr)

    Dönüş: {"karar", "gerekce", "fiyat", "zirve", "stop", "mesafe_yuzde",
            "kar_zarar_yuzde", "gun", "kirik_gun", "tavan_devrede", "veri_var"}
    "karar" ∈ {"TUT", "SAT", "—"}   ("—" = karar verilemedi, veri yok)
    """
    bos = {"karar": "—", "gerekce": "fiyat verisi yok — karar üretilemedi",
           "fiyat": None, "zirve": None, "stop": None, "mesafe_yuzde": None,
           "kar_zarar_yuzde": None, "gun": None, "kirik_gun": None,
           "tavan_devrede": False, "veri_var": False}
    if df is None or len(df) == 0 or "Close" not in getattr(df, "columns", []):
        return bos

    kapanis = pd.to_numeric(df["Close"], errors="coerce")
    gecerli = kapanis.notna() & (kapanis > 0)
    if not bool(gecerli.any()):
        return bos

    # ── ATR serisi (tek tek değil, TÜM geçmiş için) ─────────────────────────
    # Geçmişteki her gün için o GÜNÜN stop'u gerekiyor; bugünkü ATR'yi geçmişe
    # uygulamak look-ahead hatası olurdu.
    if atr_fn is None:
        try:
            import analiz_motoru as _am
            atr_fn = _am.atr
        except Exception:
            atr_fn = None
    atr_serisi = None
    if atr_fn is not None:
        try:
            a = atr_fn(df)
            atr_serisi = pd.Series(pd.to_numeric(a, errors="coerce").values,
                                   index=df.index)
        except Exception:
            atr_serisi = None

    fiyat = float(kapanis[gecerli].iloc[-1])
    kz = round(100 * (fiyat / maliyet - 1), 2) if maliyet else None

    # ── Alış tarihinden sonrasına kırp ───────────────────────────────────────
    # Alıştan ÖNCEKİ bir tepe zirve sayılırsa stop olduğundan yukarı çıkar ve
    # pozisyon daha ilk günden "satılmalı" görünür — gerçek bir hata olurdu.
    gun = None
    pencere = kapanis[gecerli]
    try:
        t = pd.Timestamp(str(alis_tarihi)[:10])
        sonrasi = pencere[pencere.index >= t]
        if len(sonrasi) > 0:
            pencere = sonrasi
        gun = (dt.date.today() - t.date()).days
    except Exception:
        pass

    if atr_serisi is None or not bool(atr_serisi.reindex(pencere.index).notna().any()):
        return {**bos, "veri_var": True, "fiyat": round(fiyat, 2),
                "zirve": round(float(max(pencere.max(), maliyet or 0)), 2),
                "kar_zarar_yuzde": kz, "gun": gun,
                "gerekce": "ATR hesaplanamadı (veri çok kısa) — stop seviyesi üretilemedi"}

    # ── Her gün için o günün zirvesi ve o günün stop'u ──────────────────────
    zirve_serisi = pencere.cummax()
    if maliyet:
        # Hisse alındıktan sonra hiç yükselmediyse zirve = alış fiyatıdır.
        zirve_serisi = zirve_serisi.clip(lower=float(maliyet))
    atr_p = atr_serisi.reindex(pencere.index).ffill()
    atr_stop = zirve_serisi - STOP_ATR_KATSAYISI * atr_p

    # ── STOP TAVANI ─────────────────────────────────────────────────────────
    # Stop, alış fiyatının STOP_TAVAN_YUZDE'sinden daha aşağıda olamaz.
    # NEDEN: Gerçek örnek — AKSEN'in ATR'si yüksek olduğu için 2,5×ATR stop'u
    # alış fiyatının %13,8 ALTINA düşüyordu; pozisyon %-8,49'dayken bile "TUT"
    # görünüyordu. Volatil hisselerde saf ATR stop'u çok geniş zarara izin
    # veriyor. Tavan bu toleransı sınırlar.
    # ÖNEMLİ: Tavan stop'u yalnızca YUKARI çeker. Hisse yükselip zirve arttıkça
    # ATR stop'u tavanın üstüne çıkar ve normal takip eden stop devam eder —
    # yani tavan kazancı kısıtlamaz, sadece zararı sınırlar.
    tavan_devrede = False
    if maliyet and STOP_TAVAN_YUZDE is not None:
        taban_stop = float(maliyet) * (1 - STOP_TAVAN_YUZDE / 100.0)
        stop_serisi = atr_stop.clip(lower=taban_stop)
        tavan_devrede = bool(float(stop_serisi.iloc[-1]) > float(atr_stop.iloc[-1]) + 1e-9)
    else:
        stop_serisi = atr_stop

    stop = float(stop_serisi.iloc[-1])
    zirve = float(zirve_serisi.iloc[-1])
    mesafe = round(100 * (fiyat / stop - 1), 2) if stop > 0 else None

    # ── Stop kaç GÜNDÜR kırık? (kesintisiz son seri) ────────────────────────
    # Kırılıp sonra toparlanıp yine kırıldıysa, anlamlı olan GÜNCEL seridir.
    kirik = (pencere < stop_serisi)
    kirik_gun = 0
    for v in reversed(kirik.tolist()):
        if not v:
            break
        kirik_gun += 1

    if kirik_gun > 0:
        karar = "SAT"
        gecikme = (f" — sinyal {kirik_gun} işlem günüdür açık"
                   if kirik_gun > 1 else " — sinyal bugün doğdu")
        gerekce = (f"takip eden stop tetiklendi: fiyat {fiyat:.2f} ₺ < "
                   f"stop {stop:.2f} ₺{gecikme}")
        if tavan_devrede:
            gerekce += f" (stop tavanı devrede: alışın %{STOP_TAVAN_YUZDE:g} altı)"
    else:
        karar = "TUT"
        gerekce = f"stop {stop:.2f} ₺ — fiyat %{mesafe:.1f} yukarıda" if mesafe is not None \
                  else f"stop {stop:.2f} ₺ — fiyat üzerinde"
        if tavan_devrede:
            gerekce += f" (stop tavanı devrede: alışın %{STOP_TAVAN_YUZDE:g} altı)"

    return {"karar": karar, "gerekce": gerekce, "fiyat": round(fiyat, 2),
            "zirve": round(zirve, 2), "stop": round(stop, 2),
            "mesafe_yuzde": mesafe, "kar_zarar_yuzde": kz, "gun": gun,
            "kirik_gun": kirik_gun or None, "tavan_devrede": tavan_devrede,
            "veri_var": True}


def gunluk_cikis_tablosu(fiyat_getirici, atr_fn=None) -> list:
    """Portföydeki HER pozisyon için günlük TUT/SAT satırı üretir.

    fiyat_getirici(sembol) -> OHLCV DataFrame (veya None)
    Karar verilemeyen pozisyonlar "—" ile ve gerekçesiyle döner; listeden
    SESSİZCE düşürülmez — kullanıcı hangi hissede karar üretilemediğini
    görmelidir.
    """
    satirlar = []
    for p in _portfoy_oku():
        sembol = p["sembol"]
        try:
            df = fiyat_getirici(sembol)
        except Exception:
            df = None
        k = cikis_karari(sembol, p.get("maliyet"), p.get("eklenme_tarihi"),
                         df, atr_fn=atr_fn)
        satirlar.append({
            "Hisse": sembol,
            "Karar": k["karar"],
            "Alış": round(float(p.get("maliyet") or 0), 2),
            "Fiyat": k["fiyat"],
            "K/Z %": k["kar_zarar_yuzde"],
            "Zirve": k["zirve"],
            "Stop": k["stop"],
            "Stop'a Pay %": k["mesafe_yuzde"],
            "Gün": k["gun"],
            "Kaç Gündür SAT": k["kirik_gun"],
            "Gerekçe": k["gerekce"],
        })
    # SAT olanlar en üstte — kullanıcının ilk göreceği şey aksiyon gerektirenler
    oncelik = {"SAT": 0, "—": 1, "TUT": 2}
    satirlar.sort(key=lambda r: (oncelik.get(r["Karar"], 3),
                                 r["Stop'a Pay %"] if r["Stop'a Pay %"] is not None else 999))
    return satirlar
