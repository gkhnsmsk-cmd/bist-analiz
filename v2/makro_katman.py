# -*- coding: utf-8 -*-
"""
v2/makro_katman.py — Petrol fiyatı tabanlı makro rejim çarpanı (YENİ katman).

BAĞLAM: Kullanıcı talebi üzerine V2/V3'ün "sadece fiyat/hacim" mimarisine
fiyat-DIŞI bir katman eklemek için yazıldı. Aşama-1 veri erişilebilirlik
araştırmasında (bkz. oturum raporu) GERÇEKTEN otomatik/ücretsiz/kayıtsız
çekilebildiği DOĞRULANMIŞ TEK piyasa-dışı-ama-sayısal kaynak budur:

  Brent ham petrol vadeli işlemi (Yahoo Finance "BZ=F"), v2/veri.py'nin
  ZATEN kullandığı yfinance kütüphanesiyle, BIST hisseleriyle AYNI şekilde
  indirilir. Bu yüzden ağ çağrısı burada TEKRAR YAZILMADI — mevcut
  veri.fiyat_indir() ÇAĞRILIYOR, §11 kuralı ("ağ çağrısı yalnız veri.py'de")
  böylece korunuyor.

  KAP (bilanço/özel durum) API'si bu oturumda GET isteğiyle BOŞ döndü (JS
  uygulaması, POST+oturum gerektiriyor) — kullanılamadı.
  TCMB EVDS gerçek bir API sunuyor ama kayıtlı kullanıcı + API anahtarı
  gerektiriyor (evds3.tcmb.gov.tr, manuel tek seferlik kayıt) — bu oturumda
  anahtar alınamadığından KULLANILMADI. İleride kullanıcı bir EVDS API
  anahtarı alırsa, bu dosyaya benzer bir `enflasyon_faiz_carpani()` fonksiyonu
  eklenebilir; iskelet aşağıda TODO olarak not edilmiştir.

GEREKÇE (neden petrol → BIST rejim çarpanı): Türkiye net petrol ithalatçısı;
ani ve büyük bir Brent yükselişi (i) cari açığı ve TL üzerindeki baskıyı
artırır, (ii) enflasyon beklentilerini bozar, (iii) TCMB'yi sıkılaştırmaya
zorlayabilir — hepsi BIST çarpanları için risk-azaltıcı sinyallerdir. Bu
yüzden petrol ANİ ve BÜYÜK yükseliyorsa (20 günlük getiri eşiği), rejim.py'nin
zaten ürettiği hedef_oran'ı AŞAĞI çeken çarpımsal bir ek kapı kuruyoruz —
rejim.py'nin kendisi DEĞİŞTİRİLMEDİ, bu saf bir ek katmandır.

Ağ çağrısı yapmaz (veri.fiyat_indir dışarıdan çağrılır) → saf fonksiyon,
test edilebilir; diğer v2 modülleriyle aynı desen.
"""

from __future__ import annotations

import pandas as pd

# Brent ham petrol vadeli işlem sembolü (Yahoo Finance). WTI ("CL=F")
# alternatif olarak denenebilir; Brent, Avrupa/Türkiye rafineri girdisine
# daha yakın olduğu için birincil tercih edildi.
PETROL_SEMBOLU = "BZ=F"

# 20 işlem günlük getiri eşikleri — ANİ şok tanımı (kademeli değil, sert eşik;
# rejim.py'deki genişlik teyidi gibi basit ve yorumlanabilir kalması amaçlandı).
_ESIK_ORTA = 0.15    # +%15/20 gün → çarpan 0.70
_ESIK_YUKSEK = 0.25  # +%25/20 gün → çarpan 0.50

_CARPAN_NORMAL = 1.00
_CARPAN_ORTA = 0.70
_CARPAN_YUKSEK = 0.50

_GETIRI_PENCERESI = 20


def petrol_getirisi(petrol_df: pd.DataFrame, tarih) -> float:
    """T tarihine KADAR (T dahil, SONRASI YOK) son 20 işlem günlük Brent getirisi.

    Look-ahead güvenliği: rejim.rejim_hesapla ile AYNI desen — yalnız
    tarih <= T satırları kullanılır.
    """
    tarih = pd.Timestamp(tarih)
    if petrol_df is None or petrol_df.empty:
        return float("nan")
    gecmis = petrol_df.loc[petrol_df.index <= tarih]
    if len(gecmis) < _GETIRI_PENCERESI + 1:
        return float("nan")
    kapanis = gecmis["Close"]
    bugun = float(kapanis.iloc[-1])
    pencere_once = float(kapanis.iloc[-1 - _GETIRI_PENCERESI])
    if pencere_once <= 0:
        return float("nan")
    return bugun / pencere_once - 1.0


def petrol_carpani(petrol_df: pd.DataFrame, tarih) -> dict:
    """Petrol şoku büyüklüğüne göre 0.50-1.00 arası bir çarpan üretir.

    Veri yetersizse (yeni sembol, ilk ~20 gün) çarpan NÖTR (1.0) kalır —
    "veri yok = güvenli varsay" ilkesi rejim.py'de MA200 eksikliğinde tam
    tersi (en temkinli) yönde uygulanıyor; burada tam tersini seçtik çünkü
    bu katman EK bir kısıtlama, TEMEL rejim kapısı değil — petrol verisi
    eksikse sistemin tamamen nakde çekilmesi orantısız olur, o sorumluluk
    zaten rejim.py'nin MA200 kuralında var.
    """
    getiri = petrol_getirisi(petrol_df, tarih)
    if pd.isna(getiri):
        return {"carpan": _CARPAN_NORMAL, "petrol_getiri_20g": float("nan"),
                "gerekce": "Petrol verisi yetersiz (ilk ~20 gün) — nötr çarpan."}

    if getiri >= _ESIK_YUKSEK:
        return {"carpan": _CARPAN_YUKSEK, "petrol_getiri_20g": getiri,
                "gerekce": (f"Brent 20 günde %{getiri*100:.1f} yükseldi (eşik %{_ESIK_YUKSEK*100:.0f}) "
                            f"— ithalat/enflasyon şoku riski yüksek, hedef oran çarpanı 0.50.")}
    if getiri >= _ESIK_ORTA:
        return {"carpan": _CARPAN_ORTA, "petrol_getiri_20g": getiri,
                "gerekce": (f"Brent 20 günde %{getiri*100:.1f} yükseldi (eşik %{_ESIK_ORTA*100:.0f}) "
                            f"— orta şiddette şok, hedef oran çarpanı 0.70.")}
    return {"carpan": _CARPAN_NORMAL, "petrol_getiri_20g": getiri,
            "gerekce": f"Brent 20 gün getirisi %{getiri*100:.1f} — eşik altı, çarpan nötr."}


def makro_hedef_oran(rejim_sonucu: dict, petrol_df: pd.DataFrame, tarih) -> dict:
    """rejim.rejim_hesapla() çıktısına petrol çarpanını uygular.

    rejim_sonucu: rejim.rejim_hesapla(...) çıktısı (DEĞİŞTİRİLMEDEN kullanılır).
    Döner: rejim_sonucu'nun bir KOPYASI + 'hedef_oran' güncellenmiş +
           'makro_carpan' ve 'makro_gerekce' eklenmiş.
    """
    petrol_bilgi = petrol_carpani(petrol_df, tarih)
    sonuc = dict(rejim_sonucu)
    sonuc["hedef_oran"] = rejim_sonucu["hedef_oran"] * petrol_bilgi["carpan"]
    sonuc["makro_carpan"] = petrol_bilgi["carpan"]
    sonuc["makro_petrol_getiri_20g"] = petrol_bilgi["petrol_getiri_20g"]
    sonuc["gerekce"] = rejim_sonucu.get("gerekce", "") + " | MAKRO: " + petrol_bilgi["gerekce"]
    return sonuc


# TODO (yalnız kullanıcı bir TCMB EVDS API anahtarı alırsa uygulanabilir):
# def enflasyon_faiz_carpani(evds_seri_df: pd.DataFrame, tarih) -> dict:
#     """TÜFE yıllık artış trendi kötüleşiyorsa (ivmeleniyor) ek çarpan.
#     EVDS API anahtarı https://evds2.tcmb.gov.tr adresinden manuel kayıtla
#     alınır; bu oturumda alınamadı, bu yüzden UYGULANMADI."""
#     raise NotImplementedError("EVDS API anahtarı gerekli — bkz. modül başlığı.")


if __name__ == "__main__":
    # Ağ çağrısı YOK — sentetik Brent serisiyle kendi kendine kontrol.
    tarihler = pd.date_range("2023-01-01", periods=100, freq="B")

    def _petrol_df(kapanislar):
        return pd.DataFrame({
            "Open": kapanislar, "High": kapanislar, "Low": kapanislar,
            "Close": kapanislar, "Volume": [1_000_000.0] * len(kapanislar),
        }, index=tarihler)

    # Senaryo 1: düz fiyat → getiri 0 → çarpan nötr.
    duz = [80.0] * 100
    df1 = _petrol_df(duz)
    sonuc1 = petrol_carpani(df1, tarihler[-1])
    assert abs(sonuc1["carpan"] - 1.0) < 1e-9, sonuc1

    # Senaryo 2: son 20 günde %30 sıçrama → yüksek şok → çarpan 0.50.
    sok = [80.0] * 79 + [80.0 * (1 + 0.30 * i / 20) for i in range(21)]
    assert len(sok) == 100
    df2 = _petrol_df(sok)
    sonuc2 = petrol_carpani(df2, tarihler[-1])
    assert sonuc2["carpan"] == _CARPAN_YUKSEK, sonuc2

    # Senaryo 3: look-ahead kontrolü — gelecekteki veriyi bozunca sonuç
    # (T tarihindeki karar) değişmemeli.
    df1_bozuk = df1.copy()
    df1_bozuk.loc[df1_bozuk.index > tarihler[-1], "Close"] = 9999.0  # zaten son tarih, ekleme yok ama örnek amaçlı no-op
    sonuc1b = petrol_carpani(df1_bozuk, tarihler[-1])
    assert sonuc1b["carpan"] == sonuc1["carpan"]

    # makro_hedef_oran entegrasyon kontrolü.
    rejim_ornek = {"rejim": "R1", "hedef_oran": 1.0, "genislik": 0.5, "gerekce": "test"}
    birlesik = makro_hedef_oran(rejim_ornek, df2, tarihler[-1])
    assert abs(birlesik["hedef_oran"] - 0.50) < 1e-9, birlesik

    print("makro_katman.py kendi kendine kontrol: BAŞARILI")
    print("Düz fiyat:", sonuc1)
    print("Şok senaryosu:", sonuc2)
    print("Birleşik (rejim x makro):", birlesik)
