# -*- coding: utf-8 -*-
"""
ogrenme_motoru.py — Kararları kaydeden, hatalarını sınıflandıran ve
                    ders çıkaran katman.
══════════════════════════════════════════════════════════════════════════════
AMAÇ: "Neden yanıldım? Bu hatayı daha önce de yaptım mı? Hangi koşullarda
tekrarlıyor?" sorularına VERİYLE cevap verebilmek.

╔════════════════════════════════════════════════════════════════════════════╗
║  EN ÖNEMLİ TASARIM KARARI — sistem kendi kurallarını KENDİ DEĞİŞTİRMEZ     ║
╠════════════════════════════════════════════════════════════════════════════╣
║  "Kendi kendini geliştiren yazılım" iki şekilde anlaşılabilir:             ║
║                                                                            ║
║   ❌ YANLIŞ: Hata yaptım → ağırlığı değiştir → yarın canlıda kullan.        ║
║      Bu, gürültüyü öğrenmek demektir. Birkaç kötü işlemden sonra sistem    ║
║      kendini bozar ve bunu kimse fark etmez.                               ║
║                                                                            ║
║   ✅ DOĞRU: Hata yaptım → kaydet → sınıflandır → aynı hatanın tekrarını     ║
║      istatistiksel olarak ölç → ADAY kural önerisi üret → backtest'te      ║
║      sına → İNSAN ONAYINDAN sonra üretime al.                              ║
║                                                                            ║
║  Bu modül SADECE ✅ tarafını yapar. Hiçbir puanlama kuralını kendiliğinden  ║
║  değiştirmez; "şunu değiştirmeyi düşünebilirsin" raporu üretir.            ║
╚════════════════════════════════════════════════════════════════════════════╝

VERİ SIZINTISI KORUMASI: Özellik anlık görüntüsü (snapshot) yalnızca KARAR
ANINDA bilinebilen değerlerden oluşur. Sonuç bilgisi (ileri getiri) snapshot'a
ASLA geri yazılmaz; ayrı bir alanda, ayrı zamanda hesaplanır.

DOSYALAR:
  ogrenme_sorgu_log.json  — sohbet asistanına sorulan her soru
  ogrenme_hata_log.json   — sınıflandırılmış hatalar (önbellek)
  (tavsiye kayıtları zaten tavsiye_gecmisi.json'da — o tekrarlanmaz)
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os

import numpy as np
import pandas as pd

KLASOR = os.path.dirname(os.path.abspath(__file__))
SORGU_LOG = os.path.join(KLASOR, "ogrenme_sorgu_log.json")
HATA_LOG = os.path.join(KLASOR, "ogrenme_hata_log.json")

# Bir kararın "olgunlaştığı" kabul edilen ufuk (iş günü). tavsiye_kaydi ile aynı.
ANA_UFUK = 10


# ─────────────────────────────────────────────────────────────────────────────
# Dosya yardımcıları
# ─────────────────────────────────────────────────────────────────────────────
def _oku(yol, varsayilan):
    if not os.path.exists(yol):
        return varsayilan
    try:
        with open(yol, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return varsayilan


def _yaz(yol, veri):
    gecici = yol + ".tmp"
    with open(gecici, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=1)
    os.replace(gecici, yol)


def _sayi(x, ondalik=2):
    try:
        d = float(x)
        if not np.isfinite(d):
            return None
        return round(d, ondalik)
    except (TypeError, ValueError):
        return None


# ═════════════════════════════════════════════════════════════════════════════
# 1) ÖZELLİK ANLIK GÖRÜNTÜSÜ (feature snapshot)
# ═════════════════════════════════════════════════════════════════════════════
def ozellik_anlik_goruntusu(df: pd.DataFrame, rejim: dict = None) -> dict:
    """Bir karar anında bilinebilen TÜM özellikleri tek sözlükte toplar.

    Bu sözlük tavsiye kaydının "ek" alanına yazılır. Sonradan hata analizi
    yapılırken "o an ne biliyorduk?" sorusunun cevabı budur.

    SIZINTI YOK: Yalnızca df'in SON satırına kadar olan veri kullanılır;
    ileriye dönük hiçbir bilgi yoktur.
    """
    try:
        import analiz_motoru as am
    except Exception:
        return {}
    if df is None or len(df) < 60:
        return {"snapshot_durumu": "yetersiz veri"}

    try:
        c = df["Close"]
        son = float(c.iloc[-1])

        def ma_uzaklik(n):
            m = am.sma(c, n).iloc[-1]
            if m != m or m <= 0:
                return None
            return round(100 * (son / float(m) - 1), 2)

        def getiri(gun):
            if len(c) <= gun:
                return None
            return round(100 * (son / float(c.iloc[-gun - 1]) - 1), 2)

        zirve52 = float(c.tail(252).max())
        _, _, hist = am.macd(c)
        baglam = am.trend_baglami(df)
        hacim_oran = float(df["Volume"].tail(5).mean() /
                           max(df["Volume"].tail(60).mean(), 1))
        atr_deger = float(am.atr(df).iloc[-1])

        return {
            "snapshot_durumu": "tam",
            "rsi14": _sayi(am.rsi(c).iloc[-1], 1),
            "macd_hist": _sayi(hist.iloc[-1], 3),
            # ── AŞIRI UZAMA ölçütleri: hata analizinin en kritik girdisi ──
            "ma20_uzaklik_yuzde": ma_uzaklik(20),
            "ma50_uzaklik_yuzde": ma_uzaklik(50),
            "ma200_uzaklik_yuzde": ma_uzaklik(200),
            "zirve52_uzaklik_yuzde": _sayi(100 * (son / zirve52 - 1), 2) if zirve52 else None,
            # ── Önceki hareket (momentum kovalama tespiti için) ──
            "onceki_1ay_getiri": getiri(21),
            "onceki_3ay_getiri": getiri(63),
            # ── Bağlam ──
            "trend_yonu": baglam.get("yon"),
            "hacim_orani_5g_60g": round(hacim_oran, 2),
            "atr_yuzde": _sayi(100 * atr_deger / son, 2) if son else None,
            "yillik_volatilite": _sayi(c.pct_change().tail(252).std() * math.sqrt(252) * 100, 1),
            "piyasa_rejim_puani": _sayi((rejim or {}).get("puan"), 1),
            "piyasa_rejim_durumu": (rejim or {}).get("durum"),
        }
    except Exception as e:
        return {"snapshot_durumu": f"hata: {e}"}


# ═════════════════════════════════════════════════════════════════════════════
# 2) SOHBET SORGU GÜNLÜĞÜ
# ═════════════════════════════════════════════════════════════════════════════
def sorgu_kaydet(soru: str, komutlar: list, saglayici: str = None,
                  basarili: bool = True, hata: str = None):
    """Asistana sorulan her soruyu kaydeder.

    NEDEN: Hangi soruların sık sorulduğunu ve hangilerinin CEVAPSIZ kaldığını
    bilmek, yazılımın eksik yeteneklerini bulmanın en doğrudan yoludur.
    (Ör. "araç seçilemedi" oranı yüksekse katalog yetersiz demektir.)
    """
    kayit = _oku(SORGU_LOG, [])
    kayit.append({
        "zaman": dt.datetime.now().isoformat(timespec="seconds"),
        "soru": str(soru)[:500],
        "kullanilan_araclar": [k.get("arac") for k in (komutlar or [])],
        "arac_sayisi": len(komutlar or []),
        "saglayici": saglayici,
        "basarili": bool(basarili),
        "hata": hata,
    })
    _yaz(SORGU_LOG, kayit[-3000:])


def sorgu_istatistikleri() -> dict:
    kayit = _oku(SORGU_LOG, [])
    if not kayit:
        return {"toplam": 0}
    araclar = {}
    cevapsiz = 0
    for k in kayit:
        if not k.get("kullanilan_araclar"):
            cevapsiz += 1
        for a in k.get("kullanilan_araclar") or []:
            araclar[a] = araclar.get(a, 0) + 1
    return {
        "toplam": len(kayit),
        "arac_secilemeyen": cevapsiz,
        "arac_secilemeyen_oran": round(100 * cevapsiz / len(kayit), 1),
        "en_cok_kullanilan_araclar": sorted(araclar.items(), key=lambda x: -x[1])[:10],
        "ilk_kayit": kayit[0]["zaman"],
        "son_kayit": kayit[-1]["zaman"],
    }


# ═════════════════════════════════════════════════════════════════════════════
# 3) HATA SINIFLANDIRMA
# ═════════════════════════════════════════════════════════════════════════════
# Her kategori: (kod, açıklama, koşul fonksiyonu)
# Koşullar SNAPSHOT'a bakar — yani "karar anında zaten belli olan" risk.
HATA_KATEGORILERI = [
    ("OVEREXTENDED_ENTRY",
     "Fiyat 50 günlük ortalamadan çok uzaktayken alındı (şişmiş giriş)",
     lambda s: (s.get("ma50_uzaklik_yuzde") or 0) > 20),

    ("MOMENTUM_CHASE",
     "Zaten çok yükselmiş hisse kovalandı (son 1 ayda %25+)",
     lambda s: (s.get("onceki_1ay_getiri") or 0) > 25),

    ("OVERBOUGHT_ENTRY",
     "RSI aşırı alım bölgesindeyken (75+) alındı",
     lambda s: (s.get("rsi14") or 0) > 75),

    ("FALSE_BREAKOUT",
     "52 haftalık zirveye yapışıkken alındı, kırılım tutmadı",
     lambda s: (s.get("zirve52_uzaklik_yuzde") or -99) > -2),

    ("REGIME_MISMATCH",
     "Piyasa rejimi olumsuzken (50 altı) pozisyon açıldı",
     lambda s: (s.get("piyasa_rejim_puani") is not None
                and s["piyasa_rejim_puani"] < 50)),

    ("FALLING_KNIFE",
     "Düşüş trendindeyken alındı (düşen bıçak)",
     lambda s: s.get("trend_yonu") == "dusus"),

    ("HIGH_VOLATILITY_ENTRY",
     "Aşırı oynak hissede pozisyon açıldı (yıllık volatilite %80+)",
     lambda s: (s.get("yillik_volatilite") or 0) > 80),
]


def _wilson_araligi(basari: int, toplam: int, z: float = 1.96):
    """Oran için Wilson güven aralığı.

    NEDEN NORMAL ARALIK DEĞİL: Küçük örneklemde (bizim durumumuz) klasik
    normal yaklaşım saçma sonuçlar verir (ör. %-5 ile %105 arası). Wilson
    aralığı küçük n'de bile 0-100 arasında kalır ve dürüst genişlik gösterir.
    """
    if toplam == 0:
        return (None, None)
    p = basari / toplam
    payda = 1 + z * z / toplam
    merkez = (p + z * z / (2 * toplam)) / payda
    yari = z * math.sqrt(p * (1 - p) / toplam + z * z / (4 * toplam * toplam)) / payda
    return (round(100 * max(0.0, merkez - yari), 1),
            round(100 * min(1.0, merkez + yari), 1))


def hatalari_sinifla(ufuk: int = ANA_UFUK, fiyat_getirici=None,
                      endeks_df=None) -> pd.DataFrame:
    """Olgunlaşmış tavsiyeleri sonuçlarıyla eşleştirip hata etiketi atar.

    Dönüş: her satır bir karar; sütunlar = snapshot özellikleri + sonuç +
           hata kategorileri.
    """
    try:
        import tavsiye_kaydi as tkd
    except Exception:
        return pd.DataFrame()

    if fiyat_getirici is None:
        try:
            import veri_katmani as vk
            fiyat_getirici = lambda s: vk.fiyat_gecmisi(s, 1.0)
        except Exception:
            return pd.DataFrame()

    try:
        perf = tkd.performans_hesapla(fiyat_getirici, endeks_df=endeks_df,
                                      ufuklar=(ufuk,))
    except Exception:
        return pd.DataFrame()
    if perf is None or len(perf) == 0:
        return pd.DataFrame()

    olgun_k, getiri_k = f"olgun_{ufuk}g", f"getiri_{ufuk}g"
    if olgun_k not in perf.columns:
        return pd.DataFrame()
    perf = perf[perf[olgun_k].astype(bool)].copy()
    if len(perf) == 0:
        return pd.DataFrame()

    # Snapshot'ları ham kayıttan al (performans tablosunda "ek" yok)
    ham = {(k.get("tarih"), k.get("kaynak"), k.get("sembol")): (k.get("ek") or {})
           for k in tkd._oku()}

    satirlar = []
    for _, r in perf.iterrows():
        anahtar = (str(r.get("tarih"))[:10], r.get("kaynak"), r.get("sembol"))
        snap = ham.get(anahtar, {})
        getiri = r.get(getiri_k)
        if getiri is None or getiri != getiri:
            continue
        basarili = getiri > 0
        satir = {"tarih": r.get("tarih"), "sembol": r.get("sembol"),
                 "kaynak": r.get("kaynak"), "sinyal": r.get("sinyal"),
                 "puan": r.get("puan"), "getiri_yuzde": round(float(getiri), 2),
                 "basarili": basarili,
                 "endeks_ustu": r.get(f"endeks_ustu_{ufuk}g"),
                 "snapshot_var": snap.get("snapshot_durumu") == "tam"}
        satir.update({k: v for k, v in snap.items() if k != "snapshot_durumu"})

        # Hata etiketleri YALNIZCA başarısız kararlar için anlamlıdır;
        # ama koşulun kendisi başarılı kararlarda da işaretlenir ki
        # "bu koşul gerçekten kötü mü?" karşılaştırması yapılabilsin.
        for kod, _aciklama, kosul in HATA_KATEGORILERI:
            try:
                satir[kod] = bool(kosul(snap)) if snap else False
            except Exception:
                satir[kod] = False
        satirlar.append(satir)

    return pd.DataFrame(satirlar)


# ═════════════════════════════════════════════════════════════════════════════
# 4) HİPOTEZ ÜRETİCİ — "ders çıkarma" burada olur
# ═════════════════════════════════════════════════════════════════════════════
MIN_ORNEK = 15          # bu sayının altında hiçbir sonuç raporlanmaz


def hipotez_uret(hata_df: pd.DataFrame) -> dict:
    """Hata kümelerini istatistiksel olarak inceler ve ADAY iyileştirme önerir.

    Kritik ilke: Bu fonksiyon HİÇBİR KURALI DEĞİŞTİRMEZ. Yalnızca
    "şu koşulda kararların başarı oranı düşük görünüyor, şunu denemeye değer"
    der ve örneklem yetersizse bunu AÇIKÇA söyler.
    """
    if hata_df is None or len(hata_df) == 0:
        return {"durum": "veri yok",
                "mesaj": "Henüz olgunlaşmış karar yok. Günlük otomasyon "
                         "çalıştıkça bu rapor dolmaya başlar."}

    toplam = len(hata_df)
    genel_basari = int(hata_df["basarili"].sum())
    genel_oran = 100 * genel_basari / toplam
    genel_alt, genel_ust = _wilson_araligi(genel_basari, toplam)

    sonuc = {
        "durum": "ölçüldü",
        "toplam_olgun_karar": toplam,
        "genel_basari_orani": round(genel_oran, 1),
        "genel_basari_guven_araligi": [genel_alt, genel_ust],
        "ortalama_getiri": round(float(hata_df["getiri_yuzde"].mean()), 2),
        "yeterli_veri_mi": toplam >= MIN_ORNEK,
        "bulgular": [],
        "uyarilar": [],
    }

    if toplam < MIN_ORNEK:
        sonuc["uyarilar"].append(
            f"Sadece {toplam} olgun karar var. En az {MIN_ORNEK} gerekir — "
            "aşağıdaki bulgular tesadüf olabilir, KARAR VERMEK İÇİN KULLANMAYIN.")

    snapshotlu = hata_df[hata_df["snapshot_var"]] if "snapshot_var" in hata_df else hata_df
    if len(snapshotlu) == 0:
        sonuc["uyarilar"].append(
            "Hiçbir kararda özellik anlık görüntüsü yok — bu kayıtlar öğrenme "
            "motoru eklenmeden önce oluşturulmuş. Bundan sonraki kayıtlar "
            "otomatik olarak snapshot içerecek.")
        return sonuc

    for kod, aciklama, _kosul in HATA_KATEGORILERI:
        if kod not in snapshotlu.columns:
            continue
        grup = snapshotlu[snapshotlu[kod]]
        n = len(grup)
        if n == 0:
            continue
        basari = int(grup["basarili"].sum())
        oran = 100 * basari / n
        alt, ust = _wilson_araligi(basari, n)
        ort_getiri = float(grup["getiri_yuzde"].mean())

        # Kontrol grubu: aynı koşulu TAŞIMAYAN kararlar
        kontrol = snapshotlu[~snapshotlu[kod]]
        kontrol_oran = (100 * kontrol["basarili"].sum() / len(kontrol)
                        if len(kontrol) else None)
        fark = (oran - kontrol_oran) if kontrol_oran is not None else None

        bulgu = {
            "kategori": kod,
            "aciklama": aciklama,
            "ornek_sayisi": n,
            "basari_orani": round(oran, 1),
            "guven_araligi": [alt, ust],
            "ortalama_getiri": round(ort_getiri, 2),
            "kontrol_grubu_basari": round(kontrol_oran, 1) if kontrol_oran is not None else None,
            "fark_puan": round(fark, 1) if fark is not None else None,
        }

        # Aday öneri SADECE hem yeterli örnek hem belirgin fark varsa
        if n >= MIN_ORNEK and fark is not None and fark < -10:
            bulgu["aday_oneri"] = (
                f"'{aciklama}' koşulunu taşıyan kararlar, taşımayanlara göre "
                f"%{abs(fark):.0f} daha düşük başarı gösteriyor. Bu koşula "
                f"PUAN CEZASI eklemeyi backtest'te denemeye değer.")
            bulgu["oncelik"] = "yüksek" if fark < -20 else "orta"
        elif n < MIN_ORNEK:
            bulgu["not"] = (f"Sadece {n} örnek — sonuç güvenilir değil, "
                            "yalnızca izleme amaçlı.")
        sonuc["bulgular"].append(bulgu)

    # En sık tekrarlanan hata (öncelikli araştırma alanı)
    sonuc["bulgular"].sort(key=lambda b: (b.get("fark_puan") or 0))
    basarisizlar = snapshotlu[~snapshotlu["basarili"]]
    if len(basarisizlar):
        sayim = {kod: int(basarisizlar[kod].sum())
                 for kod, _, _ in HATA_KATEGORILERI if kod in basarisizlar.columns}
        sonuc["basarisiz_kararlarda_hata_sayimi"] = dict(
            sorted(sayim.items(), key=lambda x: -x[1]))

    sonuc["uyarilar"].append(
        "Bu rapor bir ÖNERİ listesidir. Hiçbir kural otomatik değiştirilmedi. "
        "Bir öneriyi uygulamadan önce backtest'te önce/sonra karşılaştırması "
        "yapılmalıdır.")
    return sonuc


def rapor_metni(hipotez: dict) -> str:
    """Hipotez çıktısını okunabilir metne çevirir."""
    if not hipotez or hipotez.get("durum") == "veri yok":
        return (hipotez or {}).get("mesaj", "Veri yok.")

    s = []
    s.append(f"ÖLÇÜLEN KARAR SAYISI : {hipotez['toplam_olgun_karar']}")
    ga = hipotez["genel_basari_guven_araligi"]
    s.append(f"GENEL BAŞARI ORANI   : %{hipotez['genel_basari_orani']} "
             f"(güven aralığı %{ga[0]}–%{ga[1]})")
    s.append(f"ORTALAMA GETİRİ      : %{hipotez['ortalama_getiri']:+}")
    s.append("")

    if hipotez.get("bulgular"):
        s.append("HATA KÜMELERİ (en kötüden iyiye):")
        s.append("-" * 68)
        for b in hipotez["bulgular"]:
            fark = b.get("fark_puan")
            isaret = "🔴" if (fark or 0) < -10 else ("🟡" if (fark or 0) < 0 else "🟢")
            s.append(f"{isaret} {b['kategori']}  (n={b['ornek_sayisi']})")
            s.append(f"   {b['aciklama']}")
            s.append(f"   Başarı: %{b['basari_orani']} "
                     f"[%{b['guven_araligi'][0]}–%{b['guven_araligi'][1]}] · "
                     f"Ort. getiri: %{b['ortalama_getiri']:+}")
            if b.get("kontrol_grubu_basari") is not None:
                s.append(f"   Bu koşulu taşımayanlar: %{b['kontrol_grubu_basari']} "
                         f"→ fark {fark:+.1f} puan")
            if b.get("aday_oneri"):
                s.append(f"   💡 ADAY ÖNERİ: {b['aday_oneri']}")
            if b.get("not"):
                s.append(f"   ⚠️  {b['not']}")
            s.append("")

    if hipotez.get("basarisiz_kararlarda_hata_sayimi"):
        s.append("BAŞARISIZ KARARLARDA EN SIK GÖRÜLEN KOŞULLAR:")
        for kod, adet in hipotez["basarisiz_kararlarda_hata_sayimi"].items():
            if adet:
                s.append(f"   {kod:24s} {adet}")
        s.append("")

    for u in hipotez.get("uyarilar", []):
        s.append(f"⚠️  {u}")
    return "\n".join(s)


# ═════════════════════════════════════════════════════════════════════════════
# 5) TEK ÇAĞRI — tüm döngüyü çalıştır
# ═════════════════════════════════════════════════════════════════════════════
def ogrenme_dongusu(fiyat_getirici=None, endeks_df=None, ufuk: int = ANA_UFUK) -> dict:
    """Kaydet → sınıflandır → ders çıkar döngüsünün tamamını çalıştırır."""
    hata_df = hatalari_sinifla(ufuk=ufuk, fiyat_getirici=fiyat_getirici,
                                endeks_df=endeks_df)
    hipotez = hipotez_uret(hata_df)
    try:
        _yaz(HATA_LOG, {"guncelleme": dt.datetime.now().isoformat(timespec="seconds"),
                        "ufuk": ufuk, "hipotez": hipotez})
    except Exception:
        pass
    return {"hata_tablosu": hata_df, "hipotez": hipotez,
            "rapor": rapor_metni(hipotez),
            "sorgu_istatistikleri": sorgu_istatistikleri()}
