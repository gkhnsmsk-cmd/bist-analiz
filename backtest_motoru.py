# -*- coding: utf-8 -*-
"""
backtest_motoru.py — Skorlama sisteminin (analiz_motoru.hizli_puan / karar_ver)
GEÇMİŞ VERİ üzerinde ampirik doğrulaması (walk-forward backtest).

AMAÇ
────
Şu ana kadar AGIRLIKLAR (kisa/orta/uzun/takas ağırlıkları) ve karar_ver eşikleri
(72/62/52/40) tamamen SEZGİSEL seçildi — hiçbir gerçek getiriyle test edilmedi.
Bu modül şu soruyu yanıtlar: "Puan gerçekten daha sonraki getiriyi öngörüyor mu,
yoksa rastgele mi?"

YÖNTEM — LOOK-AHEAD BIAS'TAN KAÇINMA
─────────────────────────────────────
Her tarihsel gün i için, hizli_puan SADECE o güne kadarki (i dahil) veriyle
hesaplanır — gelecekteki hiçbir bilgi kullanılmaz. Sabit boyutlu kayan bir
pencere (PENCERE gün) kullanılır; bu hem O(n²) yerine O(n) karmaşıklık sağlar
hem de canlı kullanımı gerçekçi biçimde taklit eder (MA200/2 yıllık trend
kontrolleri zaten en fazla ~500 günlük geçmişe bakıyor, daha eskisi zaten
etkisiz kalıyor).

Her puanlama noktasından ADIM (varsayılan 5 iş günü ≈ 1 hafta) sonra bir sonraki
noktaya geçilir — hem hesaplama maliyetini azaltır hem de ardışık günlerin
aşırı örtüşen/otokorelasyonlu örnekler üretmesini sınırlar.

KAPSAM SINIRI (dürüstçe belirtilmeli)
──────────────────────────────────────
Bu backtest yalnızca TEKNİK puanlamayı (varsayılan hizli_puan — temel/yabancı
parametresi olmadan) doğrular. Çünkü F/K, PD/DD gibi temel oranların ve gerçek
yabancı takas oranının TARİHSEL (o günkü) değerlerine sahip değiliz — sadece
GÜNCEL anlık görüntüye erişimimiz var. Bu yüzden "🔬 Temel oranları dahil et"
seçeneğiyle zenginleştirilmiş puanlama bu backtestin kapsamı DIŞINDADIR.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import analiz_motoru as am

# PENCERE UZUNLUĞU NEDEN ÖNEMLİ (ölçülmüş gerçek):
# Aynı hisse, aynı gün, farklı geçmiş uzunluğuyla FARKLI puan alır. Çünkü
# uzun_vade() içindeki "2 yıllık getiri" bonusu `len(c) > 400` koşuluna bağlı;
# 375 günlük veriyle bu bonus hiç devreye girmez, 450/500 günlükle girer.
# Ölçüm: aynı gün → 375 gün: Puan 58.0 (Uzun 60) · 450/500 gün: Puan 59.0 (Uzun 65).
# Bu yüzden backtest'in penceresi, taklit etmek istediğiniz CANLI kullanımla
# eşleşmelidir. Uygulamadaki veri uzunlukları:
#   • "🚀 Öne Çıkan Hisseler" taraması → yil=1.5 → ~375 iş günü
#   • "🔍 Hisse Araştır" ve sanal portföy motoru → yil=2.0 → ~500 iş günü
# Varsayılan olarak 500 seçildi: otomatik AL/SAT kararını fiilen veren sanal
# portföy motorunun kullandığı uzunluk budur.
PENCERE_VARSAYILAN = 500       # kayan pencere uzunluğu (iş günü) — bkz. yukarıdaki not
PENCERE_TARAMA = 375           # "Öne Çıkan Hisseler" taramasını taklit etmek için
ADIM_VARSAYILAN = 5            # kaç iş gününde bir yeniden puanlama yapılsın
ILERI_GUNLER_VARSAYILAN = (5, 10, 20)
MIN_GECMIS_VARSAYILAN = 260    # ilk puanlama için gereken asgari geçmiş (MA200 + pay)

# ═════════════════════════════════════════════════════════════════════════════
# GERÇEKÇİLİK PARAMETRELERİ — backtest'i iyimserlikten arındıran ayarlar
# ═════════════════════════════════════════════════════════════════════════════
# NEDEN GEREKLİ: Backtest'ler neredeyse her zaman gerçekte elde edilemeyecek
# kadar iyi sonuç verir. Üç ana sebep vardır ve üçü de burada ele alınır:
#
#  1) İŞLEM MALİYETİ — komisyon + alım-satım farkı (spread) + kayma (slippage).
#     Sık işlem yapan bir stratejide bu maliyet, elde edilen avantajın
#     TAMAMINI silebilir. Önceki sürümde HİÇ hesaba katılmıyordu.
#
#  2) TAVAN KURALI (BIST'e özgü, en kritiği) — bir hisse tavan yaptığında
#     (günlük +%10 sınırı) satıcı çıkmadığı için pratikte ALINAMAZ. Momentum
#     tabanlı bir sistem tam da bu hisseleri seçtiği için, backtest "aldım"
#     varsayar ve o günün büyük kazancını kendine yazar — gerçekte o emir
#     dolmazdı. Bu, en iyimser hata türüdür.
#
#  3) LİKİDİTE — BIST'te ~560 hissenin çoğu sığdır; kâğıt üzerindeki getiri
#     anlamlı bir tutarla gerçekleştirilemez.
#
# Değerler MUHAFAZAKÂR seçildi: gerçek maliyet daha düşükse sonuç yalnızca
# daha iyi çıkar; tersi durumda yanıltıcı olmaz.
KOMISYON_ORANI = 0.0015        # tek yön (%0,15) — aracı kurum + borsa payı
SLIPPAGE_ORANI = 0.0010        # tek yön (%0,10) — emir kayması/spread
TUR_MALIYETI = 2 * (KOMISYON_ORANI + SLIPPAGE_ORANI)   # al+sat = %0,50
TAVAN_ESIGI_YUZDE = 9.5        # günlük değişim bunun üstündeyse tavan kabul edilir
TABAN_ESIGI_YUZDE = -9.5       # taban (satılamaz)
MIN_HACIM_MILYON_TL = 5.0      # bu tutarın altındaki hisseler işlem dışı sayılır

_KOVA_SIRA = {
    "🔴 UZAK DUR/SAT (<40)": 0,
    "🟠 ZAYIF/BEKLE (40-52)": 1,
    "🟡 İZLE/TUT (52-62)": 2,
    "🟢 AL (62-72)": 3,
    "🟢 GÜÇLÜ AL (72+)": 4,
}


def _kova(puan: float) -> str:
    if puan < 40:  return "🔴 UZAK DUR/SAT (<40)"
    if puan < 52:  return "🟠 ZAYIF/BEKLE (40-52)"
    if puan < 62:  return "🟡 İZLE/TUT (52-62)"
    if puan < 72:  return "🟢 AL (62-72)"
    return "🟢 GÜÇLÜ AL (72+)"


def _zaman_serisi_hazirla(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV verisini backtest için güvenli hale getirir.

    KRİTİK: veri_katmani'ndaki bazı kaynak yolları (borsapy dalı ve _yf_duzelt)
    indeksi SIRALAMIYOR. Sırasız bir indekste `df.iloc[i + ileri]` artık
    "gelecekteki gün" DEĞİLDİR — geçmişteki rastgele bir gün olabilir. Ölçülen
    etki: sırası karıştırılmış aynı veride 10 günlük "ileri getiri" %198'e kadar
    saptı ve puanlar 30 puana kadar kaydı. Yani sıralama yapılmazsa backtest'in
    tüm sonucu sessizce çöp olur. Bu yüzden burada koşulsuz sıralama yapılır.
    Ayrıca mükerrer tarihler (aynı gün iki kayıt) ve pozitif olmayan kapanışlar
    ayıklanır.
    """
    if df is None or len(df) == 0 or "Close" not in getattr(df, "columns", []):
        return pd.DataFrame()
    df = df.copy()
    try:
        df.index = pd.to_datetime(df.index)
    except Exception:
        return pd.DataFrame()
    df = df[df.index.notna()]
    df = df[df["Close"].notna()]
    df = df[pd.to_numeric(df["Close"], errors="coerce") > 0]
    if df.empty:
        return pd.DataFrame()
    df = df[~df.index.duplicated(keep="last")]
    return df.sort_index()


def backtest_tek_hisse(sembol: str, df: pd.DataFrame, endeks_df: pd.DataFrame = None,
                        adim: int = ADIM_VARSAYILAN, pencere: int = PENCERE_VARSAYILAN,
                        ileri_gunler: tuple = ILERI_GUNLER_VARSAYILAN,
                        min_gecmis: int = MIN_GECMIS_VARSAYILAN) -> pd.DataFrame:
    """Tek bir hissenin tüm geçmişini gün-gün (adim aralıklarla) tarayıp,
    her noktada 'o gün bilinebilecek' puanı hesaplar ve ileri getiriyle eşler.

    Dönüş: sembol, tarih, puan, karar, getiri_{h}g (her ufuk için) sütunlu tablo.
    """
    df = _zaman_serisi_hazirla(df)
    if df.empty:
        return pd.DataFrame()

    endeks_hazir = _zaman_serisi_hazirla(endeks_df) if endeks_df is not None else pd.DataFrame()

    n = len(df)
    max_ileri = max(ileri_gunler)
    if n < min_gecmis + max_ileri + 1:
        return pd.DataFrame()

    sonuclar = []
    for i in range(min_gecmis, n - max_ileri, adim):
        pencere_df = df.iloc[max(0, i - pencere + 1): i + 1]

        endeks_pencere = None
        if not endeks_hazir.empty:
            tarih = df.index[i]
            try:
                # Yalnızca o güne KADAR olan endeks verisi — gelecek sızmasın.
                ep = endeks_hazir[endeks_hazir.index <= tarih]
                if len(ep) > pencere:
                    ep = ep.iloc[-pencere:]
                endeks_pencere = ep if len(ep) > 0 else None
            except Exception:
                endeks_pencere = None

        try:
            # ayrinti=True: şişkinlik/erken-giriş hesaplarını hizli_puan'ın
            # İÇİNDEN al. Bunları ayrıca çağırmak satır başına ~%13 fazladan
            # süre demekti ve 100.000+ satırlık koşularda dakikalara mal
            # oluyordu.
            sonuc = am.hizli_puan(pencere_df, endeks_pencere, ayrinti=True)
        except Exception:
            continue
        if sonuc["Puan"] is None:
            continue

        kapanis_bugun = float(df["Close"].iloc[i])
        if not np.isfinite(kapanis_bugun) or kapanis_bugun <= 0:
            continue

        # ── ÖNCE/SONRA KARŞILAŞTIRMASI için ek sütunlar ──────────────────
        # hizli_puan() artık aşırı uzama cezasını İÇERİYOR. Değişikliğin
        # gerçekten iyileştirip iyileştirmediğini ölçebilmek için, cezayı
        # geri ekleyerek ESKİ puanı da aynı koşuda kaydediyoruz. Böylece
        # tek bir backtest çalıştırmasında iki sürüm birebir aynı veri ve
        # aynı tarihlerde karşılaştırılır (farklı koşular kıyaslanamazdı).
        _uz = sonuc.get("_uzama") or {}
        _sis = _uz.get("skor")
        _ceza = _uz.get("ceza") or 0.0
        _giris = (sonuc.get("_erken") or {}).get("skor")

        # ── GERÇEKÇİLİK BAYRAKLARI ───────────────────────────────────────
        # Bu satır gerçek hayatta işleme dönüştürülebilir miydi?
        try:
            onceki_kapanis = float(df["Close"].iloc[i - 1]) if i > 0 else kapanis_bugun
            gun_degisim = 100.0 * (kapanis_bugun / onceki_kapanis - 1.0) if onceki_kapanis else 0.0
        except Exception:
            gun_degisim = 0.0
        tavanda = gun_degisim >= TAVAN_ESIGI_YUZDE
        tabanda = gun_degisim <= TABAN_ESIGI_YUZDE
        try:
            hacim_mtl = float((df["Close"] * df["Volume"]).iloc[max(0, i - 19): i + 1].mean()) / 1e6
        except Exception:
            hacim_mtl = None
        likit = (hacim_mtl is not None and hacim_mtl >= MIN_HACIM_MILYON_TL)

        # ── GÖSTERGE ENSTRÜMANTASYONU (Görev #128) ───────────────────────
        # "Bir gösterge tek başına mı, yoksa ana trendle TEYİTLİ olduğunda mı
        # daha isabetli?" sorusunu ampirik ölçebilmek için, hizli_puan'ın
        # ayrinti=True ile açığa çıkardığı ham sinyal listesini ve o günün
        # trend yönünü kompakt JSON olarak kaydediyoruz. Satır başına küçük
        # bir ek yük (birkaç yüz bayt) — CSV'yi büyütür ama yeni bir backtest
        # koşusu gerektirmeden, sonradan Python'da parse edilip
        # "AL sinyali + trend teyitli" vs "AL sinyali + trend teyitsiz"
        # şeklinde gruplanıp getiriyle karşılaştırılabilir.
        _sinyaller = sonuc.get("_sinyaller") or []
        _trend_yonu = sonuc.get("_trendYonu")
        try:
            _sinyaller_json = json.dumps(
                [{"e": s["etiket"], "y": s["yon"]} for s in _sinyaller],
                ensure_ascii=False, separators=(",", ":"))
        except Exception:
            _sinyaller_json = None

        satir = {"sembol": sembol, "tarih": df.index[i],
                 "puan": sonuc["Puan"], "karar": sonuc["Karar"],
                 "puan_eski": min(100.0, sonuc["Puan"] + _ceza),
                 "siskinlik": _sis, "giris_skoru": _giris,
                 "gun_degisim": round(gun_degisim, 2),
                 "hacim_mtl": round(hacim_mtl, 1) if hacim_mtl is not None else None,
                 # islenebilir=False → o gün gerçekte ALINAMAZDI. Raporlar bu
                 # satırları ayrıca eleyerek "gerçekçi" sonucu hesaplar.
                 "islenebilir": bool(likit and not tavanda and not tabanda),
                 "tavanda": bool(tavanda),
                 "trend_yonu": _trend_yonu,
                 "sinyaller_json": _sinyaller_json}

        gecersiz = False
        for ileri in ileri_gunler:
            kapanis_ileri = float(df["Close"].iloc[i + ileri])
            if not np.isfinite(kapanis_ileri) or kapanis_ileri <= 0:
                gecersiz = True
                break
            ham = 100.0 * (kapanis_ileri / kapanis_bugun - 1.0)
            satir[f"getiri_{ileri}g"] = ham
            # NET getiri: al+sat turu maliyeti düşülmüş hâli. Gerçekte cebe
            # giren budur.
            satir[f"net_getiri_{ileri}g"] = ham - 100.0 * TUR_MALIYETI

            # ── ENDEKS KARŞILAŞTIRMASI (§10) ─────────────────────────────
            # "Kâr etti mi" değil "ENDEKSİ YENDİ Mİ" sorusu. Endeks aynı
            # dönemde daha çok kazandıysa, pozitif getiri bile başarısızlıktır.
            if not endeks_hazir.empty:
                try:
                    tarih_bugun = df.index[i]
                    ep = endeks_hazir[endeks_hazir.index <= tarih_bugun]
                    tarih_ileri = df.index[i + ileri]
                    ei = endeks_hazir[endeks_hazir.index <= tarih_ileri]
                    if len(ep) and len(ei):
                        e0 = float(ep["Close"].iloc[-1])
                        e1 = float(ei["Close"].iloc[-1])
                        if e0 > 0:
                            endeks_getiri = 100.0 * (e1 / e0 - 1.0)
                            satir[f"endeks_getiri_{ileri}g"] = endeks_getiri
                            satir[f"endeks_ustu_{ileri}g"] = ham - endeks_getiri
                except Exception:
                    pass
        if gecersiz:
            continue
        sonuclar.append(satir)

    return pd.DataFrame(sonuclar)


def backtest_evren(sembol_gecmis_haritasi: dict, endeks_df: pd.DataFrame = None,
                    adim: int = ADIM_VARSAYILAN, pencere: int = PENCERE_VARSAYILAN,
                    ileri_gunler: tuple = ILERI_GUNLER_VARSAYILAN,
                    min_gecmis: int = MIN_GECMIS_VARSAYILAN, ilerleme=None) -> pd.DataFrame:
    """Birden çok hisse için backtest_tek_hisse'yi çalıştırıp birleştirir.

    sembol_gecmis_haritasi: {sembol: DataFrame} (örn. vk.toplu_fiyat çıktısı)
    ilerleme: opsiyonel callback(index, toplam, sembol) — ilerleme çubuğu için.
    """
    parcalar = []
    adlar = list(sembol_gecmis_haritasi.items())
    for i, (sembol, df) in enumerate(adlar):
        if ilerleme is not None:
            try:
                ilerleme(i, len(adlar), sembol)
            except Exception:
                pass
        try:
            r = backtest_tek_hisse(sembol, df, endeks_df, adim, pencere, ileri_gunler, min_gecmis)
        except Exception:
            continue
        if not r.empty:
            parcalar.append(r)
    if not parcalar:
        return pd.DataFrame()
    return pd.concat(parcalar, ignore_index=True)


def backtest_ozet(sonuc_df: pd.DataFrame, ileri_gunler: tuple = ILERI_GUNLER_VARSAYILAN,
                   adim: int = ADIM_VARSAYILAN) -> dict:
    """Puan aralığına (karar_ver kovalarına) göre ileri getiri istatistikleri.

    `adim`: örneklerin kaç iş günü arayla alındığı — ÖRTÜŞME düzeltmesi için
    gereklidir (bkz. aşağıdaki etkin örnek sayısı hesabı).

    Dönüş: {"ozet_tablo": DataFrame, "korelasyonlar": dict, "monotonluk": dict,
            "genel_ortalama": dict, "n_toplam": int, "anlamlilik": dict}
    """
    if sonuc_df is None or sonuc_df.empty:
        return {"ozet_tablo": pd.DataFrame(), "korelasyonlar": {}, "monotonluk": {},
                "genel_ortalama": {}, "n_toplam": 0, "anlamlilik": {}}

    df = sonuc_df.copy()
    df["kova"] = df["puan"].apply(_kova)

    satirlar = []
    for kova_adi, grup in df.groupby("kova"):
        satir = {"kova": kova_adi, "n": len(grup)}
        for h in ileri_gunler:
            col = f"getiri_{h}g"
            if col not in grup.columns:
                continue
            satir[f"ort_getiri_{h}g"] = float(grup[col].mean())
            satir[f"medyan_getiri_{h}g"] = float(grup[col].median())
            satir[f"pozitif_oran_{h}g"] = float(100.0 * (grup[col] > 0).mean())
        satirlar.append(satir)

    ozet_df = pd.DataFrame(satirlar)
    if not ozet_df.empty:
        ozet_df["_sira"] = ozet_df["kova"].map(_KOVA_SIRA)
        ozet_df = ozet_df.sort_values("_sira").drop(columns="_sira").reset_index(drop=True)

    genel_ortalama = {}
    korelasyonlar = {}
    anlamlilik = {}
    for h in ileri_gunler:
        col = f"getiri_{h}g"
        if col not in df.columns:
            continue
        genel_ortalama[col] = float(df[col].mean())

        # Korelasyon NaN olabilir (örn. tüm puanlar aynıysa standart sapma sıfırdır).
        # NaN'ı olduğu gibi bırakmak TEHLİKELİDİR: NaN ile yapılan her karşılaştırma
        # False döndüğü için rapor "NEGATİF ilişki var — ters sinyal" gibi tamamen
        # yanlış bir uyarı basıyordu. Bu yüzden NaN açıkça None'a çevrilir.
        try:
            r = float(df["puan"].corr(df[col]))
        except Exception:
            r = float("nan")
        korelasyonlar[f"korelasyon_{h}g"] = None if (r != r) else r

        # ETKİN ÖRNEK SAYISI: ileri getiri penceresi (h gün), örnekleme adımından
        # (adim gün) uzunsa ardışık örnekler AYNI günleri paylaşır (örtüşme).
        # Örn. adim=5, h=20 → her getiri 4 örnekte tekrar sayılır. Ham n ile
        # yapılan anlamlılık testi bu yüzden aldatıcı derecede güçlü çıkar.
        ortusme = max(1.0, float(h) / max(float(adim), 1.0))
        n_etkin = len(df) / ortusme
        t = None
        if korelasyonlar[f"korelasyon_{h}g"] is not None and n_etkin > 3:
            rr = korelasyonlar[f"korelasyon_{h}g"]
            payda = 1.0 - rr * rr
            if payda > 1e-12:
                t = float(rr * np.sqrt(n_etkin - 2) / np.sqrt(payda))
        anlamlilik[f"anlamlilik_{h}g"] = {
            "ortusme_katsayisi": ortusme,
            "n_etkin": n_etkin,
            "t": t,
            # |t| > 2 kabaca %5 anlamlılık eşiğidir (iki yönlü, büyük örneklem).
            "anlamli_mi": (abs(t) > 2.0) if t is not None else None,
        }

    monotonluk = {}
    for h in ileri_gunler:
        kolon = f"ort_getiri_{h}g"
        if ozet_df.empty or kolon not in ozet_df.columns:
            monotonluk[f"monoton_{h}g"] = None
            continue
        degerler = ozet_df[kolon].values
        # En az 3 kova olmadan "monoton artıyor" demek anlamsızdır: 2 kovada
        # sıralamanın doğru çıkma ihtimali zaten ~%50'dir, bu bir kanıt değildir.
        if len(degerler) < 3:
            monotonluk[f"monoton_{h}g"] = None
        else:
            monotonluk[f"monoton_{h}g"] = bool(
                all(degerler[i + 1] >= degerler[i] - 1e-9 for i in range(len(degerler) - 1)))

    # Ham tablo raporda önce/sonra karşılaştırması için gerekli
    # (_onceki_sonraki_bolumu okur). Alt çizgiyle başlaması "iç kullanım"
    # demektir; arayüz bu alanı göstermez.
    return {"_ham_tablo": df, "ozet_tablo": ozet_df, "korelasyonlar": korelasyonlar,
            "monotonluk": monotonluk, "genel_ortalama": genel_ortalama,
            "n_toplam": len(df), "anlamlilik": anlamlilik}


def backtest_yarilama(sonuc_df: pd.DataFrame, ileri_gunler: tuple = ILERI_GUNLER_VARSAYILAN,
                       adim: int = ADIM_VARSAYILAN) -> dict:
    """Walk-forward sağlaması: veriyi tarihe göre ikiye böl, her yarı için ayrı
    özet çıkar. İlişki sadece BİR döneme özgüyse (overfitting işareti), iki
    yarı arasında tutarsızlık görülür.

    NOT: Bölme TARİHE göre yapılır (satır sayısına göre değil) — böylece aynı
    güne ait farklı hisselerin kayıtları iki yarıya bölünmez ve iki dönem
    gerçekten ayrık zaman aralıkları olur.
    """
    if sonuc_df is None or sonuc_df.empty or "tarih" not in sonuc_df.columns:
        return {"ilk_yari": None, "ikinci_yari": None, "kesme_tarihi": None}
    df = sonuc_df.sort_values("tarih").reset_index(drop=True)
    benzersiz = pd.Index(df["tarih"].unique()).sort_values()
    if len(benzersiz) < 2:
        return {"ilk_yari": None, "ikinci_yari": None, "kesme_tarihi": None}
    kesme = benzersiz[len(benzersiz) // 2]
    ilk = df[df["tarih"] < kesme]
    ikinci = df[df["tarih"] >= kesme]
    return {
        "ilk_yari": backtest_ozet(ilk, ileri_gunler, adim) if len(ilk) > 0 else None,
        "ikinci_yari": backtest_ozet(ikinci, ileri_gunler, adim) if len(ikinci) > 0 else None,
        "kesme_tarihi": kesme,
    }


def strateji_metrikleri(sonuc_df, ana_ufuk: int = 10, ust_n: int = 10,
                         sadece_islenebilir: bool = True) -> dict:
    """Basit bir "en yüksek puanlı N hisseyi al" stratejisini simüle eder ve
    PORTFÖY seviyesinde metrik üretir (tasarım dokümanı §10, §38-C).

    NEDEN GEREKLİ: Korelasyon ve kova ortalamaları "puan işe yarıyor mu"
    sorusunu ölçer ama "bu sistemle para kazanır mıydım" sorusunu ölçmez.
    Bir strateji pozitif korelasyona sahip olup yine de endeksin gerisinde
    kalabilir veya dayanılmaz bir düşüş (drawdown) yaşatabilir.

    sadece_islenebilir: True ise tavan/taban/likidite sorunlu satırlar atılır
    — yani "gerçekte alabileceğim hisseler" üzerinden hesap yapılır.
    """
    bos = {"durum": "veri yok"}
    if sonuc_df is None or len(sonuc_df) == 0:
        return bos
    d = sonuc_df.copy()
    net_k = f"net_getiri_{ana_ufuk}g"
    ham_k = f"getiri_{ana_ufuk}g"
    endeks_k = f"endeks_getiri_{ana_ufuk}g"
    if ham_k not in d.columns:
        return bos
    if net_k not in d.columns:
        d[net_k] = d[ham_k] - 100.0 * TUR_MALIYETI

    elenen = 0
    if sadece_islenebilir and "islenebilir" in d.columns:
        onceki = len(d)
        d = d[d["islenebilir"].astype(bool)]
        elenen = onceki - len(d)
    if len(d) == 0:
        return bos

    d = d.dropna(subset=["puan", net_k])
    if len(d) == 0:
        return bos

    # Her tarihte en yüksek puanlı N hisse seçilir → o dönemin portföy getirisi
    donem_getiri, donem_endeks, tarihler = [], [], []
    for tarih, grup in d.groupby("tarih"):
        if len(grup) < 3:
            continue
        secim = grup.nlargest(min(ust_n, len(grup)), "puan")
        donem_getiri.append(float(secim[net_k].mean()))
        if endeks_k in grup.columns and grup[endeks_k].notna().any():
            donem_endeks.append(float(grup[endeks_k].dropna().mean()))
        else:
            donem_endeks.append(np.nan)
        tarihler.append(tarih)

    if len(donem_getiri) < 5:
        return {"durum": "yetersiz dönem", "donem_sayisi": len(donem_getiri)}

    g = np.array(donem_getiri, dtype=float)
    e = np.array(donem_endeks, dtype=float)

    # Kümülatif değer eğrisi (bileşik) — dönemler örtüşmesin diye ana ufuk
    # kadar aralıklı örneklenir.
    adim_donem = max(1, ana_ufuk // max(1, int(np.median(np.diff(
        np.arange(len(g)))) or 1)))
    g_ortusmez = g[::max(1, ana_ufuk // 5)] if len(g) > ana_ufuk else g
    egri = np.cumprod(1 + g_ortusmez / 100.0)
    zirve = np.maximum.accumulate(egri)
    dusus = (egri - zirve) / zirve * 100.0
    max_dusus = float(dusus.min()) if len(dusus) else 0.0

    kazanan = g > 0
    kazanclar = g[kazanan]
    kayiplar = g[~kazanan]
    profit_factor = (float(kazanclar.sum() / abs(kayiplar.sum()))
                     if len(kayiplar) and kayiplar.sum() != 0 else None)

    std = float(g.std(ddof=1)) if len(g) > 1 else 0.0
    sharpe = float(g.mean() / std) if std > 0 else None
    negatif = g[g < 0]
    std_neg = float(negatif.std(ddof=1)) if len(negatif) > 1 else 0.0
    sortino = float(g.mean() / std_neg) if std_neg > 0 else None

    endeks_ort = float(np.nanmean(e)) if np.isfinite(e).any() else None
    return {
        "durum": "ölçüldü",
        "ust_n": ust_n,
        "donem_sayisi": len(g),
        "islem_disi_elenen_satir": elenen,
        "ortalama_donem_getirisi_net": round(float(g.mean()), 3),
        "endeks_ortalama_getirisi": round(endeks_ort, 3) if endeks_ort is not None else None,
        "endeks_ustu_fark": (round(float(g.mean()) - endeks_ort, 3)
                             if endeks_ort is not None else None),
        "kazanma_orani": round(100.0 * kazanan.mean(), 1),
        "ortalama_kazanc": round(float(kazanclar.mean()), 2) if len(kazanclar) else None,
        "ortalama_kayip": round(float(kayiplar.mean()), 2) if len(kayiplar) else None,
        "profit_factor": round(profit_factor, 2) if profit_factor else None,
        "sharpe_donemsel": round(sharpe, 3) if sharpe else None,
        "sortino_donemsel": round(sortino, 3) if sortino else None,
        "maksimum_dusus_yuzde": round(max_dusus, 2),
        "tur_maliyeti_yuzde": round(100 * TUR_MALIYETI, 2),
    }


def _gerceklik_bolumu(sonuc_df, ana_ufuk: int) -> str:
    """İşlem maliyeti, tavan/taban ve endeks karşılaştırmasını raporlar."""
    if sonuc_df is None or len(sonuc_df) == 0:
        return ""
    s = ["\n" + "=" * 70,
         "GERÇEKÇİLİK KATMANI — maliyet, tavan/taban, endeks karşılaştırması",
         "=" * 70]

    if "islenebilir" in sonuc_df.columns:
        toplam = len(sonuc_df)
        islenemez = int((~sonuc_df["islenebilir"].astype(bool)).sum())
        tavan = int(sonuc_df.get("tavanda", pd.Series(dtype=bool)).sum()) \
            if "tavanda" in sonuc_df.columns else 0
        s.append(f"Toplam gözlem                         : {toplam:,}")
        s.append(f"Gerçekte İŞLEME DÖNÜŞTÜRÜLEMEZ olan   : {islenemez:,} "
                 f"(%{100*islenemez/max(toplam,1):.1f})")
        s.append(f"  bunlardan TAVANDA olanlar           : {tavan:,}")
        s.append("  (tavandaki hisse alınamaz; sığ hisseler de işlem dışı sayıldı)")
        s.append("")

    m = strateji_metrikleri(sonuc_df, ana_ufuk=ana_ufuk, ust_n=10)
    if m.get("durum") != "ölçüldü":
        s.append(f"Portföy simülasyonu yapılamadı ({m.get('durum')}).")
        return "\n".join(s)

    s.append(f"PORTFÖY SİMÜLASYONU — her dönem en yüksek puanlı {m['ust_n']} hisse")
    s.append(f"  (işlem maliyeti düşülmüş: al+sat turu %{m['tur_maliyeti_yuzde']})")
    s.append("-" * 70)
    s.append(f"  Dönem sayısı                    : {m['donem_sayisi']}")
    s.append(f"  Ortalama dönem getirisi (NET)   : %{m['ortalama_donem_getirisi_net']:+}")
    if m["endeks_ortalama_getirisi"] is not None:
        s.append(f"  Aynı dönemde ENDEKS             : %{m['endeks_ortalama_getirisi']:+}")
        s.append(f"  ENDEKS ÜSTÜ FARK                : %{m['endeks_ustu_fark']:+}")
        if m["endeks_ustu_fark"] is not None and m["endeks_ustu_fark"] <= 0:
            s.append("  ⚠️  Strateji endeksi YENEMİYOR — bu durumda tek tek hisse "
                     "seçmek yerine endeks fonu almak daha mantıklıdır.")
    s.append(f"  Kazanma oranı                   : %{m['kazanma_orani']}")
    s.append(f"  Ortalama kazanç / kayıp         : %{m['ortalama_kazanc']:+} / %{m['ortalama_kayip']:+}")
    s.append(f"  Profit factor                   : {m['profit_factor']}")
    s.append(f"  Sharpe (dönemsel)               : {m['sharpe_donemsel']}")
    s.append(f"  Sortino (dönemsel)              : {m['sortino_donemsel']}")
    s.append(f"  Maksimum düşüş (drawdown)       : %{m['maksimum_dusus_yuzde']}")
    s.append("")
    s.append("  NOT: Sharpe/Sortino DÖNEMSELDİR (yıllıklaştırılmamıştır); "
             "farklı ufuklar arasında kıyaslanmamalıdır.")
    return "\n".join(s)


def _onceki_sonraki_bolumu(sonuc_df, ana_ufuk: int) -> str:
    """ESKİ (aşırı uzama cezasız) ve YENİ puanlamayı AYNI veri üzerinde kıyaslar.

    NEDEN AYNI KOŞUDA: İki ayrı backtest çalıştırıp sonuçları kıyaslamak
    yanıltıcı olurdu — veri, tarih aralığı ve rastgelelik farklı olabilirdi.
    Burada her iki puan da aynı satırda, aynı gün, aynı hisse için hesaplanır;
    fark yalnızca cezadan gelir.
    """
    if sonuc_df is None or len(sonuc_df) == 0:
        return ""
    getiri_k = f"getiri_{ana_ufuk}g"
    if getiri_k not in sonuc_df.columns or "puan_eski" not in sonuc_df.columns:
        return ""

    d = sonuc_df[[c for c in ("puan", "puan_eski", "siskinlik", getiri_k)
                  if c in sonuc_df.columns]].dropna()
    if len(d) < 50:
        return ""

    s = ["\n" + "=" * 70,
         "AŞIRI UZAMA CEZASI — ÖNCE / SONRA KARŞILAŞTIRMASI",
         "=" * 70,
         f"Aynı {len(d):,} gözlem üzerinde iki puanlama sürümü kıyaslandı.",
         ""]

    def olc(sutun, ad):
        try:
            kor = float(d[sutun].corr(d[getiri_k], method="spearman"))
        except Exception:
            kor = float("nan")
        try:
            ust_esik = d[sutun].quantile(0.80)
            alt_esik = d[sutun].quantile(0.20)
            ust = float(d[d[sutun] >= ust_esik][getiri_k].mean())
            alt = float(d[d[sutun] <= alt_esik][getiri_k].mean())
        except Exception:
            ust = alt = float("nan")
        s.append(f"{ad}")
        s.append(f"   Sıralama gücü (Spearman)     : {kor:+.4f}")
        s.append(f"   En yüksek puanlı %20 getirisi : %{ust:+.2f}")
        s.append(f"   En düşük  puanlı %20 getirisi : %{alt:+.2f}")
        s.append(f"   Aradaki fark (spread)         : %{ust - alt:+.2f}")
        s.append("")
        return kor, ust - alt

    k_eski, sp_eski = olc("puan_eski", "ESKİ puanlama (aşırı uzama cezası YOK)")
    k_yeni, sp_yeni = olc("puan", "YENİ puanlama (aşırı uzama cezası VAR)")

    s.append("-" * 70)
    s.append(f"Sıralama gücü değişimi : {k_eski:+.4f} → {k_yeni:+.4f} "
             f"({k_yeni - k_eski:+.4f})")
    s.append(f"Spread değişimi        : %{sp_eski:+.2f} → %{sp_yeni:+.2f} "
             f"({sp_yeni - sp_eski:+.2f} puan)")
    if (k_yeni - k_eski) > 0.005 and (sp_yeni - sp_eski) > 0.05:
        s.append("SONUÇ: Yeni puanlama her iki ölçütte de daha iyi — ceza işe yaramış.")
    elif (k_yeni - k_eski) < -0.005 or (sp_yeni - sp_eski) < -0.05:
        s.append("SONUÇ: Yeni puanlama DAHA KÖTÜ. Ceza katsayısı düşürülmeli "
                 "veya kaldırılmalı. (analiz_motoru.asiri_uzama_skoru içindeki "
                 "12.0 çarpanı)")
    else:
        s.append("SONUÇ: İki sürüm arasında anlamlı fark yok. Ceza zarar vermiyor "
                 "ama ölçülebilir bir fayda da göstermiyor.")

    # Şişkinliğin KENDİSİ gelecek getiriyi öngörüyor mu? Cezanın gerekçesi budur.
    if "siskinlik" in d.columns:
        try:
            ks = float(d["siskinlik"].corr(d[getiri_k], method="spearman"))
            en_sismis = float(d[d["siskinlik"] >= d["siskinlik"].quantile(0.80)][getiri_k].mean())
            en_sakin = float(d[d["siskinlik"] <= d["siskinlik"].quantile(0.20)][getiri_k].mean())
            s.append("")
            s.append("CEZANIN GEREKÇESİ — şişkinlik tek başına ne söylüyor?")
            s.append(f"   Şişkinlik ↔ gelecek getiri korelasyonu : {ks:+.4f}")
            s.append(f"   En şişkin %20 → ort. getiri            : %{en_sismis:+.2f}")
            s.append(f"   En sakin  %20 → ort. getiri            : %{en_sakin:+.2f}")
            if en_sakin - en_sismis > 0.1:
                s.append("   → Şişkin hisseler gerçekten daha kötü performans göstermiş; "
                         "ceza VERİYLE DESTEKLENİYOR.")
            else:
                s.append("   → Şişkin hisseler daha kötü performans GÖSTERMEMİŞ; "
                         "ceza bu veri setinde gerekçelendirilemiyor.")
        except Exception:
            pass
    return "\n".join(s)


def metin_raporu(ozet: dict, yarilama: dict = None, ileri_gunler: tuple = ILERI_GUNLER_VARSAYILAN) -> str:
    """Sonuçları düz Türkçe metne çevirir (Streamlit / konsol için)."""
    if not ozet or ozet.get("n_toplam", 0) == 0:
        return "Yeterli veri üretilemedi — daha uzun geçmiş veya daha fazla hisse gerekli."

    satirlar = [f"Toplam {ozet['n_toplam']} tarihsel puanlama noktası test edildi.\n"]

    ana_ufuk = ileri_gunler[len(ileri_gunler) // 2] if ileri_gunler else 10
    kor = ozet["korelasyonlar"].get(f"korelasyon_{ana_ufuk}g")
    if kor is None:
        # NaN/hesaplanamaz korelasyon (örn. tüm puanlar aynı → standart sapma 0).
        # Bunu sayı gibi yorumlamak yanlış sonuç doğurur, açıkça belirtilir.
        satirlar.append(f"{ana_ufuk} günlük ufukta korelasyon HESAPLANAMADI "
                         "(puanlarda yeterli değişkenlik yok) — bu bir sonuç değil, veri yetersizliğidir.")
    else:
        if kor > 0.15:
            yorum = "puan ile ileri getiri arasında anlamlı POZİTİF ilişki var — sistem gerçekten öngörücü görünüyor."
        elif kor > 0.05:
            yorum = "zayıf ama pozitif bir ilişki var — tamamen rastgele değil ama güçlü de değil."
        elif kor > -0.05:
            yorum = "ölçülebilir bir ilişki YOK — puan bu ufukta ileri getiriyi öngörmüyor gibi görünüyor."
        else:
            yorum = "NEGATİF ilişki var — dikkat, bu puanlamanın ters sinyal verdiğine işaret edebilir."
        satirlar.append(f"{ana_ufuk} günlük ufukta korelasyon: {kor:+.3f} → {yorum}")

        # İstatistiksel anlamlılık — örtüşme düzeltmeli.
        anl = (ozet.get("anlamlilik") or {}).get(f"anlamlilik_{ana_ufuk}g")
        if anl and anl.get("t") is not None:
            satirlar.append(
                f"  İstatistiksel kontrol: örnekler {anl['ortusme_katsayisi']:.1f} kat örtüştüğü için "
                f"etkin örnek sayısı ~{anl['n_etkin']:.0f} (ham {ozet['n_toplam']} değil); "
                f"t≈{anl['t']:+.1f} → "
                + ("bu ilişki rastlantıyla açıklanamayacak kadar güçlü."
                   if anl["anlamli_mi"] else
                   "bu ilişki İSTATİSTİKSEL OLARAK ANLAMLI DEĞİL, rastlantı olabilir."))

    mono = ozet["monotonluk"].get(f"monoton_{ana_ufuk}g")
    if mono is True:
        satirlar.append(f"Puan kovaları arttıkça ortalama {ana_ufuk} günlük getiri de MONOTON şekilde arttı "
                         "(düşükten yükseğe düzenli bir sıralama var).")
    elif mono is False:
        satirlar.append(f"Puan kovaları arasında {ana_ufuk} günlük getiri MONOTON artmıyor — "
                         "eşikler (72/62/52/40) ideal ayrım noktaları olmayabilir.")
    else:
        satirlar.append("Monotonluk değerlendirilemedi — anlamlı bir sıralama yorumu için "
                         "en az 3 farklı puan kovasında veri gerekiyor.")

    if not ozet["ozet_tablo"].empty:
        satirlar.append("\nKova bazlı sonuçlar:")
        for _, r in ozet["ozet_tablo"].iterrows():
            parca = [f"  {r['kova']} (n={int(r['n'])}):"]
            for h in ileri_gunler:
                col = f"ort_getiri_{h}g"
                poz = f"pozitif_oran_{h}g"
                if col in r and pd.notna(r[col]):
                    parca.append(f" {h}g ort=%{r[col]:+.2f} (pozitif oran %{r[poz]:.0f})")
            satirlar.append("".join(parca))

    if yarilama and yarilama.get("ilk_yari") and yarilama.get("ikinci_yari"):
        k1 = yarilama["ilk_yari"]["korelasyonlar"].get(f"korelasyon_{ana_ufuk}g")
        k2 = yarilama["ikinci_yari"]["korelasyonlar"].get(f"korelasyon_{ana_ufuk}g")
        if k1 is not None and k2 is not None and k1 == k1 and k2 == k2:
            satirlar.append(f"\nWalk-forward kontrolü — ilk yarı korelasyon: {k1:+.3f}, "
                             f"ikinci yarı korelasyon: {k2:+.3f}.")
            if (k1 > 0.05) == (k2 > 0.05) and (k1 > 0) == (k2 > 0):
                satirlar.append("İki dönemde de yön tutarlı — bulgu tek bir döneme özgü (overfit) görünmüyor.")
            else:
                satirlar.append("İki dönem arasında yön/tutarlılık farklı — bulguya temkinli yaklaşılmalı, "
                                 "muhtemelen tek bir piyasa rejimine özgü.")

    satirlar.append(_gerceklik_bolumu(ozet.get("_ham_tablo"), ana_ufuk))
    satirlar.append(_onceki_sonraki_bolumu(ozet.get("_ham_tablo"), ana_ufuk))

    satirlar.append("\n⚠️ KAPSAM VE SINIRLAR — sonuçları yorumlarken bunları göz önünde tutun:")
    satirlar.append("  • Yalnızca VARSAYILAN teknik puanlama test edilir (F/K, PD/DD ve gerçek yabancı "
                     "takas oranı OLMADAN); bu verilerin GEÇMİŞ değerlerine erişim olmadığı için "
                     "'🔬 Temel oranları dahil et' seçeneği kapsam dışıdır.")
    satirlar.append("  • Aynı güne ait farklı hisseler birlikte yükselip düştüğü için (piyasa etkisi) "
                     "örnekler birbirinden tam bağımsız değildir; yukarıdaki etkin örnek sayısı "
                     "yalnızca zaman örtüşmesini düzeltir, bu piyasa etkisini düzeltmez — yani "
                     "gerçek anlamlılık raporlanandan bir miktar DAHA DÜŞÜKTÜR.")
    satirlar.append(f"  • İşlem maliyeti ARTIK hesaba katılmaktadır (al+sat turu "
                     f"%{100*TUR_MALIYETI:.2f}: komisyon %{100*KOMISYON_ORANI:.2f} + "
                     f"kayma %{100*SLIPPAGE_ORANI:.2f}, tek yön). Yukarıdaki 'net' "
                     "değerler bu maliyeti içerir; ham getiriler içermez.")
    satirlar.append("  • Tavan/taban günleri ve sığ hisseler 'işlem dışı' olarak "
                     "işaretlenir; portföy simülasyonu bunları eler. Ancak emrin "
                     "kısmen dolması, gün içi fiyat farkı gibi etkiler hâlâ "
                     "modellenmemektedir.")
    satirlar.append("  • Yalnızca bugün BIST'te işlem gören hisseler test edilir; geçmişte borsadan "
                     "çıkmış/battı olanlar veri setinde yoktur (hayatta kalma yanlılığı) — bu, "
                     "sonuçları OLDUĞUNDAN İYİ gösterme eğilimindedir.")
    return "\n".join(satirlar)


# ─────────────────────────────────────────────────────────────────────────────
# NOT: Bu dosyada eskiden "ÖRÜNTÜ MOTORU DOĞRULAMASI" başlığı altında
# backtest_oruntu / oruntu_ozet / oruntu_metin_raporu fonksiyonları vardı.
# Geçmiş örüntü analizi kullanıcı deneyiminde yanıltıcı bulunduğu için
# sistemden tamamen çıkarıldı (bkz. OKU_BENI.txt) — bu fonksiyonlar da onunla
# birlikte kaldırıldı. Bu dosyada kalan tek backtest, yukarıdaki TEKNİK
# puanlama (hizli_puan) doğrulamasıdır.
# ─────────────────────────────────────────────────────────────────────────────
_ESKI_ORUNTU_BACKTEST_KALDIRILDI = True
