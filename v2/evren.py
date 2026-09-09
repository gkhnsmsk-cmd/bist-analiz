# -*- coding: utf-8 -*-
"""
v2/evren.py — Pusula V2 evren (işlem yapılabilir hisse kümesi) filtresi.

Ağ çağrısı YAPMAZ (§11 kuralı: ağ yalnız veri.py'de). Bu dosya saf
fonksiyondur: veri.py ile önceden indirilip gostergeler() uygulanmış
DataFrame'leri girdi olarak alır, §3.1 kurallarını uygular.

Kaynak notu: Repo kökündeki veri_katmani.py içinde sembol_listesi() adlı
canlı (ağ üzerinden İş Yatırım/KAP/borsapy'den) bir kaynak var, ama o dosya
ağ çağrısı yapıyor ve v2'nin "ağ yalnız veri.py'de" kuralını ihlal eder.
Yine de aynı dosyadaki YEDEK_XU100 sabit listesi (elle derlenmiş, ağsız,
100 BIST100 sembolü) HAM VERİ olarak burada yeniden kullanılıyor — V1'in
filtreleme MANTIĞI değil, yalnızca sembol kodları alınmıştır.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Statik aday evren (BIST100 = XU100).
# BIST50 (XU050), BIST100'ün bir alt kümesi olduğundan bu liste otomatik
# olarak BIST50'yi de kapsar — ayrıca bir BIST50 listesine gerek yoktur.
# Kaynak: Borsa yazılımı1/veri_katmani.py::YEDEK_XU100 (elle derlenmiş,
# ağ gerektirmeyen yedek liste; 09.2026 itibarıyla güncel).
#
# TODO: Bu liste zamanla eskiyebilir (yeni halka arz, endeks bileşen
# değişikliği). İleride ağ çağrısı yalnız veri.py'de kalacak şekilde,
# örn. haftalık bir GitHub Actions adımında bu listeyi resmi bir kaynaktan
# (İş Yatırım / KAP) güncelleyip buraya statik olarak yazan bir yardımcı
# betik eklenebilir. Şimdilik elle bakım gerektiren statik liste yeterli.
# ─────────────────────────────────────────────────────────────────────────────
TEMEL_SEMBOLLER: list[str] = sorted(set([
    "AKBNK", "ALARK", "ARCLK", "ASELS", "ASTOR", "BIMAS", "BRSAN", "CIMSA", "EKGYO", "ENKAI",
    "EREGL", "FROTO", "GARAN", "GUBRF", "HEKTS", "ISCTR", "KCHOL", "KOZAL", "KRDMD", "MGROS",
    "ODAS", "OYAKC", "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "TCELL", "THYAO", "TOASO",
    "TUPRS", "YKBNK",
    "AEFES", "AGHOL", "AHGAZ", "AKCNS", "AKFGY", "AKSA", "AKSEN", "ALBRK", "ALFAS", "ANSGR",
    "AYDEM", "BAGFS", "BERA", "BIENY", "BIOEN", "BOBET", "BRYAT", "BUCIM", "CANTE", "CCOLA",
    "CVKMD", "CWENE", "DOAS", "DOHOL", "ECILC", "ECZYT", "EGEEN", "ENERY", "ENJSA", "EUPWR",
    "FENER", "GENIL", "GESAN", "GLYHO", "GSDHO", "GWIND", "HALKB", "IPEKE", "ISDMR", "ISGYO",
    "ISMEN", "IZENR", "KARSN", "KAYSE", "KCAER", "KMPUR", "KONTR", "KONYA", "KORDS", "KOZAA",
    "KZBGY", "MAVI", "MIATK", "MPARK", "OTKAR", "PENTA", "QUAGR", "SAYAS", "SDTTR", "SELEC",
    "SKBNK", "SMRTG", "SOKM", "TABGD", "TAVHL", "TKFEN", "TSKB", "TTKOM", "TTRAK", "TUKAS",
    "TURSG", "ULKER", "VAKBN", "VESBE", "VESTL", "YEOTK", "YYLGD", "ZOREN",
]))

# BIST hisse kodları harflerden oluşur ve genelde 3-6 karakterdir. Varant /
# sertifika kodları çoğunlukla rakam içerir (örn. "AKBNKC1" gibi türev
# kodları) ya da bu uzunluk aralığının dışına taşar. TEMEL_SEMBOLLER zaten
# yalnız pay senedi kodları içeriyor; bu kontrol, ileride evren_olustur()'a
# başka bir kaynaktan (örn. genişletilmiş bir evren) sembol gelirse savunma
# amaçlı ikinci bir süzgeç görevi görür.
_MIN_KOD_UZUNLUK = 3
_MAKS_KOD_UZUNLUK = 6


def _pay_senedi_mi(sembol: str) -> bool:
    """Sembol kodunun BIST pay senedi biçimine uyup uymadığını kontrol eder."""
    k = sembol.strip().upper()
    return k.isalpha() and _MIN_KOD_UZUNLUK <= len(k) <= _MAKS_KOD_UZUNLUK


def evren_olustur(veriler: dict[str, pd.DataFrame], tarih: pd.Timestamp) -> list[str]:
    """§3.1 evren filtrelerini `tarih` itibarıyla uygular.

    Kurallar (HEPSİ sağlanmalı):
      - 20 günlük medyan TL hacim >= 20.000.000 TL
      - Kapanış >= 2.00 TL
      - En az 250 işlem günü geçmiş (tarih itibarıyla)
      - Son 5 günde tavan/taban kapanışı yok
      - Yalnız pay senetleri (varant/sertifika/BYF hariç)

    veriler: {sembol: DataFrame} — DataFrame'ler en az Close/Volume kolonlarını
             içermeli (gostergeler() uygulanmış olması şart değil, bu fonksiyon
             yalnız Close/Volume kullanır).
    tarih: karar tarihi. Bu tarihten SONRAKİ hiçbir satıra bakılmaz
           (look-ahead yasağı — haftalık yeniden hesaplama tarihte "durup"
           geriye bakmalıdır).
    """
    tarih = pd.Timestamp(tarih)
    uygun: list[str] = []

    for sembol, df in (veriler or {}).items():
        if df is None or df.empty:
            continue
        if not _pay_senedi_mi(sembol):
            continue

        # Look-ahead yasağı: tarihten sonraki satırlar tamamen dışlanır.
        gecmis = df.loc[df.index <= tarih]
        if gecmis.empty:
            continue

        # En az 250 işlem günü geçmiş olmalı — yeni halka arzlar / çok kısa
        # geçmişli semboller güvenilir istatistik üretemez (ör. GETIRI60
        # yüzdelik sıralaması anlamsızlaşır).
        if len(gecmis) < 250:
            continue

        bugun = gecmis.iloc[-1]
        kapanis = bugun.get("Close")
        hacim = bugun.get("Volume")
        if pd.isna(kapanis) or kapanis < 2.00:
            continue

        # 20 günlük medyan TL hacim. Ortalama değil medyan kullanılıyor çünkü
        # tek bir aşırı hacimli gün (örn. haber günü) ortalamayı yapay şekilde
        # şişirip likit olmayan bir hisseyi evrene sokabilir; medyan buna karşı
        # dayanıklıdır.
        son20 = gecmis.tail(20)
        if len(son20) < 20:
            continue
        hacim_tl_medyan = (son20["Close"] * son20["Volume"]).median()
        if pd.isna(hacim_tl_medyan) or hacim_tl_medyan < 20_000_000:
            continue

        # Son 5 günde tavan/taban kapanışı: BIST günlük hareket bandı resmî
        # olarak ±%10 civarındadır. Sadece OHLC'den kesin tavan/taban tespiti
        # yapılamaz (tam limit fiyatı borsadan alınmalı); bu yüzden günlük
        # kapanış getirisinin mutlak değeri %9.5'i geçen günler PROXY olarak
        # tavan/taban sayılıyor. Amaç: ertesi gün emrin gerçekleşemeyeceği
        # (işlem durmuş/tek yönlü kilitli) sembolleri evren dışı bırakmak.
        son5_getiri = gecmis["Close"].pct_change().tail(5)
        if (son5_getiri.abs() >= 0.095).any():
            continue

        uygun.append(sembol)

    return sorted(uygun)


if __name__ == "__main__":
    # Ağ çağrısı içermeyen kendi kendine kontrol: sentetik veriyle §3.1
    # filtrelerinin her birinin doğru çalıştığını doğrular.
    tarih_araligi = pd.date_range("2023-01-01", periods=260, freq="B")
    tarih = tarih_araligi[-1]

    def _sentetik_df(kapanis_sabit: float, hacim_sabit: float, gun_sayisi: int,
                      son5_tavan: bool = False) -> pd.DataFrame:
        tarihler = tarih_araligi[-gun_sayisi:]
        kapanislar = np.full(len(tarihler), kapanis_sabit, dtype=float)
        if son5_tavan:
            kapanislar[-3] = kapanislar[-4] * 1.10  # %10 sıçrama → tavan proxy'si
        return pd.DataFrame({
            "Open": kapanislar,
            "High": kapanislar * 1.01,
            "Low": kapanislar * 0.99,
            "Close": kapanislar,
            "Volume": np.full(len(tarihler), hacim_sabit, dtype=float),
        }, index=tarihler)

    veriler = {
        # 1) Her şart sağlanıyor → evrene girmeli.
        "IYIHS": _sentetik_df(kapanis_sabit=50.0, hacim_sabit=1_000_000, gun_sayisi=260),
        # 2) Kapanış 2 TL altı → elenmeli.
        "UCUZH": _sentetik_df(kapanis_sabit=1.50, hacim_sabit=5_000_000, gun_sayisi=260),
        # 3) Hacim çok düşük (medyan TL hacim eşik altı) → elenmeli.
        "DUSUKH": _sentetik_df(kapanis_sabit=10.0, hacim_sabit=100, gun_sayisi=260),
        # 4) Yeterli geçmişi yok (250 günden az) → elenmeli.
        "YENIH": _sentetik_df(kapanis_sabit=20.0, hacim_sabit=1_000_000, gun_sayisi=100),
        # 5) Son 5 günde tavan → elenmeli.
        "TAVANH": _sentetik_df(kapanis_sabit=30.0, hacim_sabit=1_000_000, gun_sayisi=260,
                                son5_tavan=True),
        # 6) Pay senedi biçiminde değil (rakam içeriyor) → elenmeli. Diğer
        #    tüm şartları (hacim/fiyat/geçmiş) bilerek sağlıyor ki test
        #    yalnızca sembol-biçimi süzgecini izole etsin.
        "ABC123": _sentetik_df(kapanis_sabit=15.0, hacim_sabit=2_000_000, gun_sayisi=260),
    }

    sonuc = evren_olustur(veriler, tarih)
    assert sonuc == ["IYIHS"], f"Beklenmeyen evren sonucu: {sonuc}"

    # Look-ahead kontrolü: tarihten SONRAKİ satırları bozup sonucun
    # değişmediğini doğrula (fonksiyon o satırlara bakmamalı).
    veriler_bozuk = dict(veriler)
    bozuk_df = veriler["IYIHS"].copy()
    gelecek_tarihler = pd.date_range(tarih + pd.Timedelta(days=1), periods=5, freq="B")
    gelecek = pd.DataFrame({
        "Open": [0.01] * 5, "High": [0.01] * 5, "Low": [0.01] * 5,
        "Close": [0.01] * 5, "Volume": [0] * 5,
    }, index=gelecek_tarihler)
    bozuk_df = pd.concat([bozuk_df, gelecek])
    veriler_bozuk["IYIHS"] = bozuk_df
    sonuc2 = evren_olustur(veriler_bozuk, tarih)
    assert sonuc2 == ["IYIHS"], "Gelecek tarihli veri sonucu etkiledi — look-ahead riski var"

    assert len(TEMEL_SEMBOLLER) >= 90, "TEMEL_SEMBOLLER beklenenden kısa"

    print("evren.py kendi kendine kontrol: BAŞARILI")
    print(f"TEMEL_SEMBOLLER sayısı: {len(TEMEL_SEMBOLLER)}")
    print(f"Test evreni sonucu: {sonuc}")
