# -*- coding: utf-8 -*-
"""
oruntu_motoru.py — Çok Değişkenli Geçmiş Örüntü Eşleştirme ve Metinsel Sinyal Motoru
═════════════════════════════════════════════════════════════════════════════════
GÖRSEL/GRAFİK İÇERMEZ. Girdi olarak mevcut veri katmanından (veri_katmani.py) gelen
OHLCV geçmişini ve temel oranları alır; çıktı olarak SADECE metinsel bir sinyal
raporu ve yapısal bir sözlük üretir.

DÜRÜST MÜHENDİSLİK NOTU:
  Orijinal istekte isyatirimhisse (çeyreklik bilanço) ve TCMB EVDS (reel faiz,
  TÜFE) gibi ek kaynaklar geçiyordu. Bu iki kaynak: (a) ek kurulum/anahtar
  gerektirir, (b) mevcut platformun veri_katmani.py'sinde YOKTUR. Bu motor,
  var olan Mynet/yfinance/İş Yatırım zincirini kullanarak dürüst ve çalışan bir
  sürüm sunar: "cross-sectional" (tüm BIST için ortak günlük özellik veritabanı)
  yerine HER HİSSENİN KENDİ ÇOK YILLI GEÇMİŞİNİ tarayan bir örüntü eşleştirmesi
  yapar — bugünkü teknik durumuna en çok benzeyen geçmiş anları bulur ve o
  anlardan sonra hissenin gerçekte ne yaptığını istatistiksel olarak raporlar.
  Temel oranlar (F/K, PD/DD) varsa metne dahil edilir ama günlük tarihsel serisi
  olmadığından benzerlik vektörüne değil, sadece bağlam cümlesine eklenir.

KULLANIM:
    import oruntu_motoru as om
    sonuc = om.oruntu_analizi("THYAO", df, temel)
    print(om.metin_raporu(sonuc, temel))
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
import pandas as pd

import analiz_motoru as am
import ozet_metni as _ozm   # nihai karar kuralı TEK yerde dursun diye

# ── Ayarlar ───────────────────────────────────────────────────────────────────
EN_YAKIN_N = 12                 # kaç geçmiş benzer gün aranacak
ILERI_GUNLER = (3, 5, 10, 20)   # örüntü sonrası kaç işlem günü izlenecek
MIN_GUN = 300                   # anlamlı örüntü araması için gereken min. geçmiş
MIN_ADAY_HAVUZU = 60            # benzerlik hesaplanabilecek min. gün sayısı

_AGIRLIKLAR = {
    "RSI": 1.2, "BOLL_%B": 1.2, "MACD_EGIM": 0.8, "EMA_SAPMA": 1.0,
    "GETIRI_1A": 0.8, "GETIRI_3A": 0.6, "HACIM_Z": 0.6,
}

_VADE_ETIKET = {3: "Günlük (birkaç iş günü)", 5: "Haftalık (~1 hafta)",
                10: "Kısa Vade (~2 hafta)", 20: "Aylık (~1 ay)",
                60: "Orta Vade (~3 ay)", 120: "Uzun Vade (~6 ay)"}

# ── VADE SİSTEMİ ─────────────────────────────────────────────────────────────
# Örüntü motoru artık tek bir "Sinyal" yerine ÜÇ VADE için ayrı sinyal üretir.
# Ufuklar, puanlama motorunun vade tanımlarıyla (analiz_motoru: Kısa 1-4 hafta,
# Orta 1-6 ay, Uzun 6 ay+) hizalanacak şekilde seçildi:
#   Kısa  → 10 işlem günü (~2 hafta)
#   Orta  → 60 işlem günü (~3 ay)
#   Uzun  → 120 işlem günü (~6 ay)
# UYARI: Ufuk uzadıkça örneklem azalır (120 gün ileri bakabilmek için o kadar
# geçmiş gerekir). Bu yüzden her vadenin ÖRNEK SAYISI da raporlanır; az
# örnekli bir "GÜÇLÜ AL" tek başına güvenilir değildir.
VADE_UFUKLARI = {"Kısa": 10, "Orta": 60, "Uzun": 120}


# ── Özellik vektörü çıkarımı ──────────────────────────────────────────────────
def _bollinger_yuzde_b(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    ust, orta, alt = am.bollinger(close, n, k)
    genislik = (ust - alt).replace(0, np.nan)
    return ((close - alt) / genislik).clip(-0.4, 1.4)


def _ozellik_matrisi(df: pd.DataFrame) -> pd.DataFrame:
    """Her gün için normalize edilmiş çok boyutlu özellik vektörünü üretir."""
    c = df["Close"]
    rsi_s = am.rsi(c, 14)
    yb = _bollinger_yuzde_b(c, 20, 2.0) * 100
    _, _, hist = am.macd(c)
    macd_egim = hist.diff(5)
    ema20 = am.ema(c, 20)
    ema50 = am.ema(c, 50)
    ema_sapma = (ema20 - ema50) / ema50 * 100
    getiri_1a = c.pct_change(21) * 100
    getiri_3a = c.pct_change(63) * 100
    hac_ort = df["Volume"].rolling(60).mean()
    hac_std = df["Volume"].rolling(60).std().replace(0, np.nan)
    hacim_z = (df["Volume"] - hac_ort) / hac_std

    return pd.DataFrame({
        "RSI": rsi_s, "BOLL_%B": yb, "MACD_EGIM": macd_egim,
        "EMA_SAPMA": ema_sapma, "GETIRI_1A": getiri_1a, "GETIRI_3A": getiri_3a,
        "HACIM_Z": hacim_z,
    }, index=df.index)


def _kosinus_benzerlik(bugun: np.ndarray, matris: np.ndarray) -> np.ndarray:
    """(ESKİ YÖNTEM — yalnızca geriye dönük uyumluluk için korunuyor.)
    Ham (ölçeklenmemiş) veride kosinüs benzerliği kullanmak yanıltıcıdır;
    bunun yerine _benzerlik_hesapla() kullanılır. Gerekçe orada açıklanmıştır."""
    n_bugun = np.linalg.norm(bugun)
    n_matris = np.linalg.norm(matris, axis=1)
    payda = n_bugun * n_matris
    with np.errstate(invalid="ignore", divide="ignore"):
        benzerlik = (matris @ bugun) / payda
    benzerlik[payda == 0] = np.nan
    return benzerlik


def _benzerlik_hesapla(bugun_ham: pd.Series, havuz: pd.DataFrame,
                        agirlik: np.ndarray) -> pd.Series:
    """Standartlaştırılmış, ağırlıklı uzaklığa dayalı benzerlik (0-100).

    ESKİ YÖNTEMİN İKİ HATASI (ölçülerek tespit edildi):

    1) AĞIRLIKLAR GERÇEKTE UYGULANMIYORDU. Kosinüs benzerliği HAM büyüklüğe
       duyarlıdır. RSI (~45) ve Bollinger %B (~43) gibi büyük ölçekli
       özelliklerin yanında MACD eğimi (~0,2) ve hacim z-skoru (~0,8) yok
       hükmündedir. Ölçüm: tanımlı ağırlıklara rağmen benzerliğin %86,6'sını
       yalnızca RSI + %B belirliyordu; MACD eğiminin katkısı %0,1 idi. Yani
       _AGIRLIKLAR sözlüğü fiilen çalışmıyordu.

    2) BENZERLİK YÜZDESİ AYIRT EDİCİ DEĞİLDİ. (kosinüs+1)/2*100 dönüşümü,
       tümü pozitif olan bu özelliklerde her şeyi %60-100 aralığına sıkıştırıyor;
       en benzer 12 gün her zaman %98-100 çıkıyordu. Kullanıcı arayüzde her
       hisse için "Benzerlik %100" görüyordu — yani sütun hiçbir bilgi
       taşımıyordu.

    ÇÖZÜM: Her özellik, HAVUZUN KENDİ ortalama/standart sapmasıyla z-skora
    çevrilir (böylece hepsi aynı ölçeğe gelir ve ağırlıklar anlam kazanır),
    sonra ağırlıklı Öklid uzaklığı hesaplanır. Uzaklık, havuzun MEDYAN
    uzaklığına göre kalibre edilerek yüzdeye çevrilir:
        uzaklık 0        → %100 (birebir aynı durum)
        uzaklık = medyan → %50  (rastgele bir günle aynı derecede benzer)
    Bu, "%50 = sıradan bir gün kadar benzer" şeklinde YORUMLANABİLİR bir
    ölçektir. Standartlaştırma yalnızca GEÇMİŞ havuzdan hesaplanır; geleceğe
    ait hiçbir bilgi kullanılmaz.
    """
    ort = havuz.mean()
    std = havuz.std().replace(0.0, np.nan)
    z_havuz = ((havuz - ort) / std).fillna(0.0).values
    z_bugun = ((bugun_ham - ort) / std).fillna(0.0).values

    fark = z_havuz - z_bugun
    uzaklik = np.sqrt((fark ** 2 * agirlik).sum(axis=1))

    gecerli = uzaklik[np.isfinite(uzaklik)]
    if len(gecerli) == 0:
        return pd.Series(np.nan, index=havuz.index)
    medyan = float(np.median(gecerli))
    if not np.isfinite(medyan) or medyan <= 1e-12:
        yuzde = np.where(uzaklik <= 1e-12, 100.0, 0.0)
    else:
        # 100 * 2^(-uzaklık/medyan): medyan uzaklıkta tam %50 verir.
        yuzde = 100.0 * np.power(2.0, -uzaklik / medyan)
    return pd.Series(yuzde, index=havuz.index)


# ── Ana örüntü analizi ────────────────────────────────────────────────────────
def oruntu_analizi(sembol: str, df: pd.DataFrame, temel: dict = None,
                    en_yakin_n: int = EN_YAKIN_N,
                    ileri_gunler=ILERI_GUNLER) -> dict:
    """
    Hissenin bugünkü teknik durumunu KENDİ çok yıllı geçmişindeki en benzer
    N güne göre kıyaslar; o günlerden sonra fiyatın gerçekte ne yaptığını
    (ortalama getiri, medyan getiri, pozitif gün oranı) çıkarır.
    Yetersiz veri varsa {'sembol':..., 'yetersiz_veri': True} döner.
    """
    temel = temel or {}
    if df is None or len(df) < MIN_GUN:
        return {"sembol": sembol, "yetersiz_veri": True,
                "neden": f"Geçmiş veri {MIN_GUN} günden az (mevcut: {0 if df is None else len(df)})."}

    ozellik = _ozellik_matrisi(df)
    gecerli = ozellik.dropna()
    if len(gecerli) < MIN_ADAY_HAVUZU + en_yakin_n:
        return {"sembol": sembol, "yetersiz_veri": True,
                "neden": "Göstergeler için yeterli temiz veri yok."}

    agirlik = np.array([_AGIRLIKLAR[k] for k in ozellik.columns])
    bugun_ham = gecerli.iloc[-1]

    # Son 15 günü havuzdan çıkar — kendine çok yakın günlerin yapay
    # yüksek benzerlik üretmesini engellemek için.
    aday_havuzu = gecerli.iloc[:-15]
    if len(aday_havuzu) < MIN_ADAY_HAVUZU:
        return {"sembol": sembol, "yetersiz_veri": True,
                "neden": "Örüntü havuzu için yeterli geçmiş gün yok."}

    # Standartlaştırılmış ağırlıklı uzaklık — gerekçesi _benzerlik_hesapla'da.
    benzerlik_s = _benzerlik_hesapla(bugun_ham, aday_havuzu, agirlik).dropna()
    if len(benzerlik_s) < en_yakin_n:
        return {"sembol": sembol, "yetersiz_veri": True,
                "neden": "Benzerlik hesaplanabilen gün sayısı yetersiz."}

    en_benzer = benzerlik_s.sort_values(ascending=False).head(en_yakin_n)
    ortalama_benzerlik_yuzde = float(en_benzer.mean())

    kapanis = df["Close"]
    konum_haritasi = {tarih: kapanis.index.get_loc(tarih) for tarih in en_benzer.index}
    ufuk_sonuclari = {}
    for ileri in ileri_gunler:
        getiriler = []
        for tarih, konum in konum_haritasi.items():
            if konum + ileri < len(kapanis):
                baslangic = kapanis.iloc[konum]
                bitis = kapanis.iloc[konum + ileri]
                if baslangic and baslangic == baslangic:
                    getiriler.append((bitis / baslangic - 1) * 100)
        if getiriler:
            ufuk_sonuclari[ileri] = {
                "etiket": _VADE_ETIKET.get(ileri, f"{ileri} iş günü"),
                "ortalama_getiri": float(np.mean(getiriler)),
                "medyan_getiri": float(np.median(getiriler)),
                "pozitif_oran": float(np.mean([g > 0 for g in getiriler]) * 100),
                "adet": len(getiriler),
            }

    # Karar ufku olarak 10 işlem günü (≈2 hafta) tercih edilir.
    #
    # DÜZELTİLEN HATA: Eski kod yalnızca 10 → 5 → 20 sırasına bakıyordu. Ancak
    # "Yükselebilecek Hisseler" sekmesinin GÜNLÜK taraması bu fonksiyonu
    # ileri_gunler=(3,) ile çağırıyor; bu durumda üç anahtarın hiçbiri
    # bulunmadığından karar_ufku None kalıyor ve _sinyal_uret(None) her zaman
    # "NÖTR" döndürüyordu. Sonuç: günlük listedeki Sinyal sütunu, hisse %83
    # pozitif orana ve +%1,8 beklenen getiriye sahip olsa bile HER ZAMAN NÖTR
    # görünüyordu — yani o sütun hiçbir bilgi taşımıyordu.
    # Artık istenen ufuk listede yoksa MEVCUT olan ufuklardan biri kullanılır.
    karar_ufku = None
    for tercih in (10, 5, 20, 3):
        if tercih in ufuk_sonuclari:
            karar_ufku = ufuk_sonuclari[tercih]
            break
    if karar_ufku is None and ufuk_sonuclari:
        karar_ufku = next(iter(ufuk_sonuclari.values()))
    sinyal, guven = _sinyal_uret(karar_ufku)

    son_fiyat = float(kapanis.iloc[-1])
    atr_son = float(am.atr(df).iloc[-1])
    stop_fiyat = round(son_fiyat - 1.5 * atr_son, 2)
    if sinyal in ("GÜÇLÜ AL", "AL"):
        hedef_fiyat = round(son_fiyat + 2.2 * atr_son, 2)
    elif sinyal in ("GÜÇLÜ SAT", "SAT"):
        hedef_fiyat = round(son_fiyat - 2.2 * atr_son, 2)
    else:
        hedef_fiyat = round(son_fiyat + 1.5 * atr_son, 2)

    return {
        "sembol": sembol,
        "yetersiz_veri": False,
        "tarih": _dt.date.today().strftime("%d.%m.%Y"),
        "son_fiyat": son_fiyat,
        "sinyal": sinyal,
        "guven_skoru": guven,
        "benzerlik_yuzde": ortalama_benzerlik_yuzde,
        "benzer_gun_sayisi": int(len(en_benzer)),
        "benzer_tarihler": [t.strftime("%d.%m.%Y") for t in en_benzer.index],
        "ufuk_sonuclari": ufuk_sonuclari,
        # Sinyalin ÜRETİLDİĞİ ufkun istatistikleri. Nihai karar açıklamasının
        # "geçmişte benzer 12 günün %58'i yükselmiş" gibi somut sayı verebilmesi
        # için dışarı açılır (eskiden sadece fonksiyon içinde kalıyordu).
        "karar_ufku": karar_ufku,
        "guncel_gostergeler": {
            "RSI": float(bugun_ham["RSI"]),
            "BOLL_%B": float(bugun_ham["BOLL_%B"]),
            "EMA_SAPMA": float(bugun_ham["EMA_SAPMA"]),
            "GETIRI_1A": float(bugun_ham["GETIRI_1A"]),
            "GETIRI_3A": float(bugun_ham["GETIRI_3A"]),
        },
        "fk": temel.get("fk"),
        "pddd": temel.get("pddd"),
        "hedef_fiyat": hedef_fiyat,
        "stop_fiyat": stop_fiyat,
    }


def _uyum_etiketi(oruntu_sinyali: str, teknik_puan) -> str:
    """İki motorun aynı fikirde olup olmadığını tek bakışta gösterir.

    NEDEN: Örüntü motoru "GÜÇLÜ AL", puanlama motoru "UZAK DUR/SAT" diyebiliyor
    ve kullanıcı hangisine güveneceğini bilemiyordu. Bu sütun, çelişkiyi
    gizlemek yerine SINIFLANDIRIR: iki motorun da olumlu olduğu hisseler en
    yüksek güvenilirlikte, çeliştikleri hisseler ise "temkinli" kabul edilmelidir.
    """
    try:
        p = float(teknik_puan)
        if p != p:
            return "⚪ Bilinmiyor"
    except (TypeError, ValueError):
        return "⚪ Bilinmiyor"

    oruntu_olumlu = oruntu_sinyali in ("AL", "GÜÇLÜ AL")
    oruntu_olumsuz = oruntu_sinyali in ("SAT", "GÜÇLÜ SAT")
    teknik_olumlu = p >= 62.0
    teknik_notr = 52.0 <= p < 62.0
    teknik_olumsuz = p < 52.0

    if oruntu_olumlu and teknik_olumlu:
        return "✅ İkisi de olumlu"
    if oruntu_olumlu and teknik_notr:
        return "🟡 Kısmen uyumlu"
    if oruntu_olumlu and teknik_olumsuz:
        return "⚠️ Çelişkili"
    if oruntu_olumsuz and teknik_olumsuz:
        return "🔴 İkisi de olumsuz"
    return "➖ Belirsiz"


def _sinyal_uret(ufuk: dict | None) -> tuple:
    """Karar ufkundaki istatistiklerden SİNYAL + güven skoru (0-100) üretir."""
    if not ufuk:
        return "NÖTR", 50.0
    poz = ufuk["pozitif_oran"]
    ort = ufuk["ortalama_getiri"]
    if poz >= 65 and ort > 1.5:
        return "GÜÇLÜ AL", round(poz, 1)
    if poz >= 55 and ort > 0:
        return "AL", round(poz, 1)
    if poz <= 35 and ort < -1.5:
        return "GÜÇLÜ SAT", round(100 - poz, 1)
    if poz <= 45 and ort < 0:
        return "SAT", round(100 - poz, 1)
    return "NÖTR", round(50 + (poz - 50) * 0.3, 1)


# ── Metinsel rapor ─────────────────────────────────────────────────────────────
def metin_raporu(sonuc: dict) -> str:
    """oruntu_analizi() çıktısından, kullanıcıya gösterilecek ayrıntılı Türkçe
    metin raporu üretir (grafik içermez, tamamen metinsel)."""
    if sonuc.get("yetersiz_veri"):
        return (f"'{sonuc.get('sembol')}' için örüntü analizi yapılamadı: "
                f"{sonuc.get('neden', 'yeterli geçmiş veri yok.')} "
                "(En az ~14 aylık günlük geçmiş gereklidir.)")

    s = sonuc
    fk_metin = f"{float(s['fk']):.1f}" if s.get("fk") else "veri yok"
    pddd_metin = f"{float(s['pddd']):.2f}" if s.get("pddd") else "veri yok"
    g = s["guncel_gostergeler"]

    satirlar = []
    satirlar.append("=" * 52)
    satirlar.append(f"SİNYAL RAPORU: {s['sembol']}")
    satirlar.append(f"Tarih: {s['tarih']}")
    satirlar.append("-" * 52)
    satirlar.append(f"SİNYAL: {s['sinyal']}")
    satirlar.append(f"Güven Skoru / Geçmiş Başarı Oranı: %{s['guven_skoru']:.0f}")
    satirlar.append("")
    satirlar.append("RASYONEL VE TARİHSEL GEREKÇE:")
    satirlar.append(
        f"1. Temel Durum: Hisse F/K {fk_metin}, PD/DD {pddd_metin} oranıyla işlem görüyor. "
        f"Son 1 ayda %{g['GETIRI_1A']:+.1f}, son 3 ayda %{g['GETIRI_3A']:+.1f} getiri sağladı.")

    if s["benzer_gun_sayisi"] > 0:
        satirlar.append(
            f"2. Örüntü Analizi: Hissenin kendi çok yıllı geçmişi tarandığında, bugünkü teknik "
            f"duruma (RSI, Bollinger konumu, MACD eğimi, EMA trendi, momentum, hacim) ortalama "
            f"%{s['benzerlik_yuzde']:.0f} benzerlikte {s['benzer_gun_sayisi']} farklı tarihsel an "
            f"tespit edildi (örn. {', '.join(s['benzer_tarihler'][:4])}).")
        for ileri, u in s["ufuk_sonuclari"].items():
            satirlar.append(
                f"   → {u['etiket']} ufukta: bu {u['adet']} örüntüden sonra hisse ortalama "
                f"%{u['ortalama_getiri']:+.1f} (medyan %{u['medyan_getiri']:+.1f}) hareket etti; "
                f"vakaların %{u['pozitif_oran']:.0f}'i pozitif sonuçlandı.")
    else:
        satirlar.append("2. Örüntü Analizi: Yeterli sayıda benzer tarihsel an bulunamadı.")

    boll = g["BOLL_%B"]
    boll_yorum = ("üst bandın üzerinde (aşırı alım bölgesi)" if boll > 100 else
                  "üst banda yakın" if boll > 75 else
                  "alt banda yakın" if boll < 25 else
                  "alt bandın altında (aşırı satım bölgesi)" if boll < 0 else "orta bantta")
    ema_yorum = "kısa vadeli ortalama uzun vadelinin üzerinde (yükseliş eğilimi)" if g["EMA_SAPMA"] > 0 \
        else "kısa vadeli ortalama uzun vadelinin altında (düşüş eğilimi)"
    satirlar.append(
        f"3. Teknik Durum: RSI {g['RSI']:.0f} seviyesinde, fiyat Bollinger bandında {boll_yorum}. "
        f"EMA20/EMA50 ilişkisi: {ema_yorum}.")
    satirlar.append("")
    satirlar.append("RİSK YÖNETİMİ:")
    satirlar.append(f"- Güncel Fiyat: {s['son_fiyat']:.2f} TL")
    satirlar.append(f"- Hedef Fiyat (Referans): {s['hedef_fiyat']:.2f} TL "
                     f"(%{(s['hedef_fiyat']/s['son_fiyat']-1)*100:+.1f})")
    satirlar.append(f"- Stop-Loss (Zarar Kes, ATR tabanlı): {s['stop_fiyat']:.2f} TL "
                     f"(%{(s['stop_fiyat']/s['son_fiyat']-1)*100:+.1f})")
    satirlar.append("=" * 52)
    satirlar.append("⚠️ Bu rapor bilgilendirme amaçlıdır, yatırım tavsiyesi değildir. "
                     "Geçmiş örüntülerin gelecekte tekrarlanacağının garantisi yoktur.")
    return "\n".join(satirlar)


# ── Günlük / haftalık yükselebilecek hisse taraması ────────────────────────────
def yukselecek_adaylari_tara(veri_sozlugu: dict, ufuk: int = 5, ust_sinir: int = 15,
                              ilerleme=None, endeks_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    ÖNEMLİ (performans): Bu fonksiyon hisse başına AYRI bir ağ isteği YAPMAZ.
    `veri_sozlugu` = {"SEMBOL": pd.DataFrame(OHLCV), ...} biçiminde, önceden
    TOPLU olarak çekilmiş veriyi bekler (örn. veri_katmani.toplu_fiyat()).
    Böylece 100+ hisseyi tararken tek bir toplu indirme yeterli olur; günlük
    ve haftalık taramalar da AYNI önceden-çekilmiş veriyi tekrar kullanarak
    ikinci bir indirme yapmadan saniyeler içinde tamamlanır.

    Seçilen ufukta (varsayılan 5 iş günü = ~1 hafta) en yüksek istatistiksel
    yükseliş potansiyeline sahip hisseleri sıralı bir tabloda döner.

    `endeks_df` verilirse tabloya ayrıca "Teknik Puan" sütunu eklenir. Bu ÖNEMLİDİR:
    bu tarama ÖRÜNTÜ motorunu kullanır ("geçmişte bu duruma benzediğinde ne oldu?"),
    "Hisse Araştır" sekmesi ise PUANLAMA motorunu ("şu anki teknik göstergeler ne
    kadar iyi?"). İkisi farklı sorular sorduğu için AYNI hisse için farklı sonuç
    verebilirler — örneğin çok düşmüş bir hissenin teknik puanı zayıftır ama
    geçmişte benzer diplerden toparlandığı için örüntü sinyali olumlu olabilir.
    Bu tutarsızlık değil, iki farklı bakış açısıdır; kullanıcının bunu GÖREBİLMESİ
    için iki değer yan yana gösterilir.
    """
    satirlar = []
    semboller = list(veri_sozlugu.keys())
    toplam = len(semboller)
    for i, sembol in enumerate(semboller):
        try:
            df = veri_sozlugu[sembol]
            sonuc = oruntu_analizi(sembol, df, {}, ileri_gunler=(ufuk,))
            if sonuc.get("yetersiz_veri"):
                continue
            u = sonuc["ufuk_sonuclari"].get(ufuk)
            if not u:
                continue
            skor = u["pozitif_oran"] + u["ortalama_getiri"] * 3
            satir = {
                "Hisse": sembol,
                "Sinyal": sonuc["sinyal"],
                "Beklenen Getiri %": round(u["ortalama_getiri"], 1),
                "Pozitif Gün Oranı %": round(u["pozitif_oran"], 0),
                "Benzerlik %": round(sonuc["benzerlik_yuzde"], 0),
                "Fiyat": round(sonuc["son_fiyat"], 2),
                "_skor": skor,
            }
            # İkinci motorun (puanlama) görüşü + iki motorun UYUMU.
            try:
                hp = am.hizli_puan(df, endeks_df)
                satir["Teknik Puan"] = hp["Puan"]
                satir["Teknik Karar"] = hp["Karar"]
                satir["Uyum"] = _uyum_etiketi(sonuc["sinyal"], hp["Puan"])
            except Exception:
                satir["Teknik Puan"] = None
                satir["Teknik Karar"] = None
                satir["Uyum"] = "⚪ Bilinmiyor"
            satirlar.append(satir)
        except Exception:
            continue
        if ilerleme and (i % 10 == 0 or i == toplam - 1):
            ilerleme((i + 1) / max(toplam, 1))

    if not satirlar:
        return pd.DataFrame(columns=["Hisse", "Sinyal", "Beklenen Getiri %",
                                      "Pozitif Gün Oranı %", "Benzerlik %", "Fiyat",
                                      "Teknik Puan", "Teknik Karar", "Uyum"])

    tablo = pd.DataFrame(satirlar).sort_values("_skor", ascending=False)
    tablo = tablo[tablo["Beklenen Getiri %"] > 0].drop(columns="_skor")
    # Sütun sırası: önce UYUM (en önemli özet), sonra iki motorun ayrıntısı.
    tercih_sira = ["Hisse", "Uyum", "Sinyal", "Beklenen Getiri %", "Pozitif Gün Oranı %",
                   "Benzerlik %", "Fiyat", "Teknik Puan", "Teknik Karar"]
    tablo = tablo[[k for k in tercih_sira if k in tablo.columns]]
    return tablo.head(ust_sinir).reset_index(drop=True)


def coklu_ufuk_tara(veri_sozlugu: dict, ufuklar=(3, 5), ust_sinir: int = 15,
                     ilerleme=None, endeks_df: pd.DataFrame = None) -> dict:
    """Birden çok ufku TEK GEÇİŞTE tarar. Dönüş: {ufuk: DataFrame}

    HIZ GEREKÇESİ: yukselecek_adaylari_tara() her çağrıldığında her hisse için
    özellik matrisini (RSI, Bollinger, MACD, EMA, momentum, hacim) ve teknik
    puanı SIFIRDAN hesaplar. Günlük (3 gün) ve haftalık (5 gün) listeler ayrı
    ayrı çağrıldığında bu ağır hesap her hisse için İKİ KEZ yapılıyordu; oysa
    tek fark, benzer günlerden sonra kaç gün ileriye bakıldığıdır. Bu fonksiyon
    örüntü eşleştirmesini ve teknik puanı bir kez yapıp tüm ufukların sonucunu
    birlikte üretir — bu sekmedeki hesap süresini yaklaşık YARIYA indirir.
    """
    ufuklar = tuple(ufuklar)
    birikim = {u: [] for u in ufuklar}
    semboller = list(veri_sozlugu.keys())
    toplam = len(semboller)

    for i, sembol in enumerate(semboller):
        try:
            df = veri_sozlugu[sembol]
            sonuc = oruntu_analizi(sembol, df, {}, ileri_gunler=ufuklar)
            if sonuc.get("yetersiz_veri"):
                continue
            try:
                hp = am.hizli_puan(df, endeks_df)
                teknik_puan, teknik_karar = hp["Puan"], hp["Karar"]
            except Exception:
                teknik_puan, teknik_karar = None, None

            for u in ufuklar:
                bilgi = sonuc["ufuk_sonuclari"].get(u)
                if not bilgi:
                    continue
                # Sinyal, her ufuk için O UFUĞUN istatistiğinden üretilir —
                # aksi halde 3 ve 5 günlük listeler aynı sinyali gösterirdi.
                sinyal_u, _ = _sinyal_uret(bilgi)
                birikim[u].append({
                    "Hisse": sembol,
                    # NİHAİ: iki motoru birleştiren TEK karar. Hisse detay
                    # sayfasındaki büyük karar kutusuyla aynı kuraldan türer
                    # (ozet_metni.nihai_karar_kisa), böylece listedeki cevapla
                    # detaydaki cevap asla çelişmez.
                    "Nihai": _ozm.nihai_karar_kisa(sinyal_u, teknik_puan),
                    "Uyum": _uyum_etiketi(sinyal_u, teknik_puan),
                    "Sinyal": sinyal_u,
                    "Beklenen Getiri %": round(bilgi["ortalama_getiri"], 1),
                    "Pozitif Gün Oranı %": round(bilgi["pozitif_oran"], 0),
                    "Benzerlik %": round(sonuc["benzerlik_yuzde"], 0),
                    "Fiyat": round(sonuc["son_fiyat"], 2),
                    "Teknik Puan": teknik_puan,
                    "Teknik Karar": teknik_karar,
                    "_skor": bilgi["pozitif_oran"] + bilgi["ortalama_getiri"] * 3,
                })
        except Exception:
            continue
        if ilerleme and (i % 10 == 0 or i == toplam - 1):
            ilerleme((i + 1) / max(toplam, 1))

    kolonlar = ["Hisse", "Nihai", "Uyum", "Sinyal", "Beklenen Getiri %", "Pozitif Gün Oranı %",
                "Benzerlik %", "Fiyat", "Teknik Puan", "Teknik Karar"]
    sonuc_tablolari = {}
    for u in ufuklar:
        if not birikim[u]:
            sonuc_tablolari[u] = pd.DataFrame(columns=kolonlar)
            continue
        t = pd.DataFrame(birikim[u]).sort_values("_skor", ascending=False)
        t = t[t["Beklenen Getiri %"] > 0].drop(columns="_skor")
        sonuc_tablolari[u] = t[[k for k in kolonlar if k in t.columns]] \
            .head(ust_sinir).reset_index(drop=True)
    return sonuc_tablolari


# ─────────────────────────────────────────────────────────────────────────────
# VADE BAZLI TARAMA — tek "Sinyal" yerine Kısa / Orta / Uzun ayrı ayrı
# ─────────────────────────────────────────────────────────────────────────────
def vade_taramasi(veri_sozlugu: dict, ust_sinir: int = 40, ilerleme=None,
                  endeks_df: pd.DataFrame = None) -> pd.DataFrame:
    """Her hisse için KISA / ORTA / UZUN vadede ayrı nihai karar üretir.

    Neden böyle: Tek bir "GÜÇLÜ AL" etiketi hangi vadeyi kastettiğini
    söylemiyordu. Oysa bir hisse kısa vadede aşırı alım (riskli), uzun vadede
    olumlu olabilir — bunlar çelişki değil, farklı vadelerdir. Artık her vade
    için:
      • örüntü motoru O VADEYE ait ufukta kendi sinyalini üretir,
      • puanlama motorunun AYNI VADEYE ait puanı (Kısa/Orta/Uzun) alınır,
      • ikisi ozet_metni.nihai_karar_kisa ile TEK bir karara indirgenir.
    Böylece "Kısa: BEKLE · Orta: AL · Uzun: AL" gibi okunabilir bir tablo çıkar.
    """
    ufuklar = tuple(VADE_UFUKLARI.values())          # (10, 60, 120)
    vade_adlari = list(VADE_UFUKLARI.keys())         # ["Kısa","Orta","Uzun"]
    satirlar = []
    semboller = list(veri_sozlugu.keys())
    toplam = len(semboller)

    for i, sembol in enumerate(semboller):
        try:
            df = veri_sozlugu[sembol]
            sonuc = oruntu_analizi(sembol, df, {}, ileri_gunler=ufuklar)
            if sonuc.get("yetersiz_veri"):
                continue
            try:
                hp = am.hizli_puan(df, endeks_df)
            except Exception:
                continue
            if hp.get("Puan") is None:
                continue

            satir = {"Hisse": sembol, "Fiyat": round(sonuc["son_fiyat"], 2)}
            skor_toplam, gecerli_vade = 0.0, 0
            for vade in vade_adlari:
                u = VADE_UFUKLARI[vade]
                bilgi = sonuc["ufuk_sonuclari"].get(u)
                # Puanlama motorunun AYNI vadeye ait puanı.
                teknik_vade_puan = hp.get(vade)
                if not bilgi:
                    # Bu ufuk için yeterli geçmiş yok (uzun vadede sık olur).
                    satir[vade] = "⚪ Veri yok"
                    satir[f"{vade} Bek.%"] = None
                    satir[f"{vade} Poz.%"] = None
                    satir[f"{vade} Örnek"] = 0
                    continue
                sinyal_u, _ = _sinyal_uret(bilgi)
                satir[vade] = _ozm.nihai_karar_kisa(sinyal_u, teknik_vade_puan)
                satir[f"{vade} Bek.%"] = round(bilgi["ortalama_getiri"], 1)
                satir[f"{vade} Poz.%"] = round(bilgi["pozitif_oran"], 0)
                satir[f"{vade} Örnek"] = int(bilgi["adet"])
                satir[f"{vade} Sinyal"] = sinyal_u
                satir[f"{vade} Teknik"] = teknik_vade_puan
                skor_toplam += bilgi["pozitif_oran"] + bilgi["ortalama_getiri"] * 3
                gecerli_vade += 1

            if gecerli_vade == 0:
                continue
            satir["Genel Puan"] = hp["Puan"]
            satir["Benzerlik %"] = round(sonuc["benzerlik_yuzde"], 0)
            satir["_skor"] = skor_toplam / gecerli_vade
            satirlar.append(satir)
        except Exception:
            continue
        if ilerleme and (i % 10 == 0 or i == toplam - 1):
            ilerleme((i + 1) / max(toplam, 1))

    kolonlar = (["Hisse"] + vade_adlari + ["Genel Puan", "Fiyat", "Benzerlik %"]
                + [f"{v} {e}" for v in vade_adlari
                   for e in ("Bek.%", "Poz.%", "Örnek", "Sinyal", "Teknik")])
    if not satirlar:
        return pd.DataFrame(columns=kolonlar)
    t = pd.DataFrame(satirlar).sort_values("_skor", ascending=False).drop(columns="_skor")
    return t[[k for k in kolonlar if k in t.columns]].head(ust_sinir).reset_index(drop=True)
