# -*- coding: utf-8 -*-
"""
v2/v21_analiz_motoru.py — analiz_motoru.py ile AYNI ARAYÜZE (fonksiyon adı /
imza / dönüş şeması) sahip ADAPTÖR modülü.

NEDEN VAR: Günlük tarama/tavsiye üretim hattı (arka_plan_tarama.py,
gunluk_tarama.py) v2/analiz_motoru.py'yi (V1'den birebir kopya, HİÇ
değiştirilmedi) `import analiz_motoru as am` ile çağırıyordu — yani
kullanıcıya gösterilen tarama.json / yukselecek.json / dip_donusu.json /
ma_kirilim.json hâlâ V1 puanlama mantığıyla üretiliyordu, oysa backtest
edilip PF 2.72 / expectancy 0.59R sonucu veren asıl algoritma v2.1
(v21_gosterge / v21_rejim / v21_secim / v21_portfoy) idi.

v2/analiz_motoru.py'ye DOKUNULMADI (şartname gereği — bkz. proje notları).
Bunun yerine bu modül `am.<fonksiyon>(...)` çağıranların hiçbir satırını
değiştirmeye gerek bırakmadan aynı isim/imza/dönüş sözlüğü/DataFrame şemasını
üretir; TEK fark, iç hesaplamaların v2.1 göstergelerine (MA20/50/200, CMF20,
Donchian(10), GETIRI20, §3.B "teknik zorunluluklar", §2 Risk-On/Risk-Off ana
şalteri) dayanmasıdır. Çağıran taraflar yalnızca

    import analiz_motoru as am        →        import v21_analiz_motoru as am

satırını değiştirir; başka HİÇBİR satıra dokunulmaz.

KAPSAM DIŞI BIRAKILAN TEK ALAN (bilinçli, gerekçeli):
  StochRSI %K/%D kesişimi (vade_taramasi'nin "StochRsiSinyal" /
  "StochRsiAciklama" kolonları). analiz_motoru.py'nin kendi dokstring'i bile
  bunun SADECE bilgi amaçlı olduğunu, puanlamaya/karara HİÇ karışmadığını
  söylüyor. v2.1 şartnamesiyle bir ilgisi yok ve iki motor arasında tarafsız,
  ortak bir teknik gösterge olduğundan burada yeniden yazılmak yerine
  analiz_motoru'ndan SALT OKUNUR biçimde import edilip aynen kullanılır
  (analiz_motoru.py dosyası bu importla DEĞİŞTİRİLMEZ/ETKİLENMEZ).

Şema kaynağı (analiz_motoru.py'deki satır numaraları, adaptör yazılırken
okunduğu haliyle): piyasa_rejimi ~739, vade_taramasi ~861,
ma_kirilim_taramasi ~995, hizli_puan ~1495, dip_guvenlik_kontrolu ~1649,
secim_skoru ~1693.
"""
from __future__ import annotations

import os
import sys

# Bu dosya bazen (örn. kendi kendine kontrol için) doğrudan `python
# v21_analiz_motoru.py` ile çalıştırılabilir; arka_plan_tarama.py/
# gunluk_tarama.py zaten kendi sys.path ayarını yapıyor ama burada da
# BAĞIMSIZ çalışılabilsin diye aynı önlem tekrarlanır (zararsız, tekrar
# eklense de sys.path'te yalnız bir kez etkili olur).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

import veri as _veri
import v21_gosterge as _vg
import v21_rejim as _vr
import v21_secim as _vs
import v21_portfoy as _vp

# Bkz. modül başındaki "KAPSAM DIŞI BIRAKILAN TEK ALAN" notu — SADECE bilgi
# amaçlı, puana/karara karışmayan, motordan bağımsız/tarafsız bir gösterge.
# analiz_motoru.py bu importla OKUNUYOR, HİÇBİR ŞEKİLDE DEĞİŞTİRİLMİYOR.
from analiz_motoru import stoch_rsi_sinyali as _stoch_rsi_sinyali

# ─────────────────────────────────────────────────────────────────────────
# v2.1 §3.B eşikleri — TEK kaynaktan (v21_secim.py) okunur, burada
# TEKRARLANMAZ (sabit sürüklenmesini önlemek için).
# ─────────────────────────────────────────────────────────────────────────
_GETIRI20_ALT = _vs._GETIRI20_ALT              # 0.05
_GETIRI20_UST = _vs._GETIRI20_UST              # 0.25
_HACIM_CARPAN = _vs._HACIM5_HACIM20_CARPAN     # 1.20

# analiz_motoru.py'deki AYNI bileşik ağırlıklar ve rejim düzeltme çarpanı —
# şema/tutarlılık için korunuyor (bu sabitlerin kendisi "V1 mantığı" değil,
# nötr bir ağırlıklandırma/ölçekleme kuralıdır).
AGIRLIKLAR = {"kisa": 0.25, "orta": 0.30, "uzun": 0.20, "takas": 0.25}
REJIM_DUZELTME_CARPANI = 0.28

SECIM_MIN_GECMIS = 210          # MA200 + pay için gereken asgari gün (jenerik eşik)

MA_KIRILIM_PENCERELERI = (5, 10, 22, 50)
MA_KIRILIM_CIFTLERI = ((5, 10), (10, 22))


def _ekle(liste, etiket, yon, aciklama):
    liste.append({"etiket": etiket, "yon": yon, "aciklama": aciklama})


def _f(x):
    """NaN/None güvenli float dönüşümü — geçersizse None döner."""
    try:
        if x is None:
            return None
        xf = float(x)
        return xf if np.isfinite(xf) else None
    except Exception:
        return None


def _basit_ortalama(seri: pd.Series, n: int) -> pd.Series:
    """Basit (simple) hareketli ortalama — v2.1'in 'düz MA' yorumuyla
    (bkz. v21_gosterge.py başlığı: EMA DEĞİL, basit ortalama) tutarlı."""
    return seri.rolling(n, min_periods=n).mean()


def _hazirla(df: pd.DataFrame) -> pd.DataFrame:
    """v2.1'in ihtiyaç duyduğu tüm göstergeleri (MA20/50/200, ATR14, CMF20,
    Donchian(10), GETIRI20, HACIM_ORT5/20, ...) ekler. df zaten işlenmişse
    (CMF20 ve MA200 sütunları mevcutsa) tekrar HESAPLAMAZ — gereksiz CPU
    yükünü önler ve tekrar çağrılırsa idempotent kalır."""
    if "CMF20" in df.columns and "MA200" in df.columns:
        return df
    temel = _veri.gostergeler(df)
    return _vg.ek_gostergeler(temel)


# ═══════════════════════════════════════════════════════════════════════
# piyasa_rejimi — v21_rejim'in §2 Risk-On/Risk-Off ana şalterini analiz_
# motoru.piyasa_rejimi ile AYNI 0-100 skor + sinyal listesi şemasına çevirir.
# ═══════════════════════════════════════════════════════════════════════
def piyasa_rejimi(xu100_df, usdtry_df=None, tefas_s=None) -> dict:
    """Dönüş: {"puan": float 0-100, "durum": str, "emoji": str,
    "sinyaller": [{"etiket","yon","aciklama"}, ...]} — analiz_motoru ile
    BİREBİR aynı şema.

    usdtry_df / tefas_s parametreleri ARAYÜZ UYUMLULUĞU için imzada TUTULUR
    (arka_plan_tarama.py bunları pozisyonel geçiriyor) ama v2.1 §2
    şartnamesi rejimi yalnız XU100 kapanışı + MA200/MA50'ye dayandırdığından
    (bkz. v21_rejim.py) KULLANILMAZ.
    """
    sinyaller = []
    if xu100_df is None or getattr(xu100_df, "empty", True):
        _ekle(sinyaller, "V2.1 Ana Şalter (Risk-On/Risk-Off)", "SAT", "XU100 verisi yok — güvenli varsayım: Risk-Off")
        return {"puan": 0.0, "durum": "RİSK KAPALI — Savunma modu (veri yok)",
                "emoji": "🔴", "sinyaller": sinyaller}
    try:
        tarih = xu100_df.index[-1]
        r = _vr.rejim_hesapla(xu100_df, tarih)
    except Exception as e:
        _ekle(sinyaller, "V2.1 Ana Şalter (Risk-On/Risk-Off)", "SAT", f"Rejim hesaplanamadı: {type(e).__name__}")
        return {"puan": 0.0, "durum": "RİSK KAPALI — Savunma modu (hata)",
                "emoji": "🔴", "sinyaller": sinyaller}

    puan = float(np.clip(r["hedef_hisse_orani"] * 100.0, 0.0, 100.0))
    yon = "AL" if r["durum"] == "Risk-On" else "SAT"
    _ekle(sinyaller, "V2.1 Ana Şalter (Risk-On/Risk-Off)", yon, r["gerekce"])
    _ekle(sinyaller, "Makro Teyit Notu (§2)", "NÖTR", r["makro_notu"])

    if puan >= 62:
        durum, emoji = "RİSK AÇIK — Boğa ortamı (v2.1 Risk-On)", "🟢"
    elif puan >= 45:
        durum, emoji = "NÖTR — Seçici olun", "🟡"
    else:
        durum, emoji = "RİSK KAPALI — Savunma modu (v2.1 Risk-Off)", "🔴"
    return {"puan": puan, "durum": durum, "emoji": emoji, "sinyaller": sinyaller}


def rejim_duzeltmesi(genel_puan: float, rejim_puani: float) -> tuple:
    """analiz_motoru.rejim_duzeltmesi ile AYNI formül/imza — hisse puanını
    piyasa rejimine göre kısar/destekler."""
    duzeltme = (rejim_puani - 50.0) * REJIM_DUZELTME_CARPANI
    yeni = float(np.clip(genel_puan + duzeltme, 0, 100))
    return yeni, round(duzeltme, 1)


def karar_ver(puan: float) -> tuple:
    """analiz_motoru.karar_ver ile AYNI eşikler/etiketler."""
    if puan >= 62:
        return "AL", "🟢"
    if puan >= 52:
        return "İZLE / TUT", "🟡"
    if puan >= 40:
        return "ZAYIF / BEKLE", "🟠"
    return "UZAK DUR / SAT", "🔴"


def vade_karari(puan) -> str:
    """analiz_motoru.vade_karari ile AYNI eşikler/etiketler."""
    if puan is None:
        return "⚪ Veri yok"
    if puan >= 60:
        return "🟢 AL"
    if puan >= 50:
        return "🟡 İZLE"
    if puan >= 40:
        return "🟠 ZAYIF"
    return "🔴 UZAK DUR"


# ═══════════════════════════════════════════════════════════════════════
# hizli_puan — v2.1 §3.B teknik zorunluluklarına ve v2.1 göstergelerine
# (MA20/50/200, CMF20, Donchian10, GETIRI20, hacim oranı) dayalı puanlama.
# ═══════════════════════════════════════════════════════════════════════
def hizli_puan(df: pd.DataFrame, endeks_df: pd.DataFrame = None,
               temel: dict = None, yabanci_s: pd.Series = None,
               rejim: dict = None, ayrinti: bool = False) -> dict:
    """analiz_motoru.hizli_puan ile AYNI imza/dönüş şeması.

    `temel` / `yabanci_s` (KAP/TEFAS temel veriler) v2.1 şartnamesinde zaten
    "VERİ YOK, ATLANDI" (§3.A Zombi Koruması, §3.C kurumsal/TEFAS notu —
    bkz. v21_secim.py başlığı) olduğundan burada da KULLANILMAZ; yalnızca
    ARAYÜZ UYUMLULUĞU için parametre olarak tutulur.
    `rejim` (piyasa_rejimi çıktısı) verilirse §2 ana şalterine göre puan
    düzeltilir — analiz_motoru ile aynı davranış.
    """
    if df is None or df.empty or len(df) < 30 or "Close" not in df.columns:
        return {
            "Puan": None, "Karar": "⚫ VERİ YOK",
            "Kısa": None, "Orta": None, "Uzun": None, "Takas": None,
            "Şişkinlik": None, "Giriş": None,
            "Fiyat": None, "1 Hafta %": None, "1 Ay %": None, "3 Ay %": None,
            "1 Yıl %": None, "Hacim(M₺)": None,
        }

    h = _hazirla(df)
    satir = h.iloc[-1]
    c = h["Close"]

    kapanis = _f(satir.get("Close"))
    ma20 = _f(satir.get("MA20")); ma50 = _f(satir.get("MA50")); ma200 = _f(satir.get("MA200"))
    cmf20 = _f(satir.get("CMF20"))
    getiri20 = _f(satir.get("GETIRI20"))
    donchian_ust = _f(satir.get("DONCHIAN_UST10")); donchian_alt = _f(satir.get("DONCHIAN_ALT10"))
    hacim5 = _f(satir.get("HACIM_ORT5")); hacim20 = _f(satir.get("HACIM_ORT20"))

    kp_sinyaller, op_sinyaller, up_sinyaller, tp_sinyaller = [], [], [], []

    # ── KISA VADE: MA20 konumu + CMF20 + §3.B getiri20 penceresi + hacim ──
    kp = 50.0
    if kapanis is not None and ma20 is not None:
        if kapanis > ma20:
            kp += 15.0; _ekle(kp_sinyaller, "MA20 Konumu", "AL", "Fiyat MA20 üzerinde")
        else:
            kp -= 15.0; _ekle(kp_sinyaller, "MA20 Konumu", "SAT", "Fiyat MA20 altında")
    if cmf20 is not None:
        if cmf20 > 0:
            kp += 15.0; _ekle(kp_sinyaller, "CMF20", "AL", f"Para akışı pozitif ({cmf20:+.3f})")
        else:
            kp -= 15.0; _ekle(kp_sinyaller, "CMF20", "SAT", f"Para akışı negatif ({cmf20:+.3f})")
    if getiri20 is not None:
        if _GETIRI20_ALT <= getiri20 <= _GETIRI20_UST:
            kp += 10.0
            _ekle(kp_sinyaller, "20G Getiri Penceresi (§3.B)", "AL",
                  f"20 günlük getiri %{getiri20*100:.1f} — v2.1'in sağlıklı momentum aralığında (%5-%25)")
        elif getiri20 > _GETIRI20_UST:
            kp -= 10.0
            _ekle(kp_sinyaller, "20G Getiri Penceresi (§3.B)", "SAT",
                  f"20 günlük getiri %{getiri20*100:.1f} — aralığın (%5-%25) üstünde, aşırı uzamış")
        elif getiri20 < 0:
            kp -= 5.0
            _ekle(kp_sinyaller, "20G Getiri Penceresi (§3.B)", "SAT",
                  f"20 günlük getiri negatif (%{getiri20*100:.1f})")
    if hacim5 is not None and hacim20 is not None and hacim20 > 0 and hacim5 >= _HACIM_CARPAN * hacim20:
        kp += 10.0
        _ekle(kp_sinyaller, "Hacim Teyidi (§3.B)", "AL", "Son 5G hacim, 20G ortalamanın en az %20 üzerinde")
    kp = float(np.clip(kp, 0, 100))

    # ── ORTA VADE: MA50>MA200 yapısı + MA50 konumu + CMF + Donchian(10) ──
    op = 50.0
    if ma50 is not None and ma200 is not None:
        if ma50 > ma200:
            op += 15.0; _ekle(op_sinyaller, "MA50>MA200 Yapısı (§3.B)", "AL", "Orta vadeli trend yapısı yukarı")
        else:
            op -= 15.0; _ekle(op_sinyaller, "MA50>MA200 Yapısı (§3.B)", "SAT", "Orta vadeli trend yapısı bozuk")
    if kapanis is not None and ma50 is not None:
        if kapanis > ma50:
            op += 15.0; _ekle(op_sinyaller, "MA50 Konumu", "AL", "Fiyat MA50 üzerinde")
        else:
            op -= 10.0; _ekle(op_sinyaller, "MA50 Konumu", "SAT", "Fiyat MA50 altında")
    if cmf20 is not None:
        op += 10.0 if cmf20 > 0 else -10.0
    if kapanis is not None and donchian_ust is not None and donchian_alt is not None:
        if kapanis > donchian_ust:
            op += 10.0; _ekle(op_sinyaller, "Donchian(10) Kırılımı", "AL", "Fiyat son 10 günlük zirveyi kırdı")
        elif kapanis < donchian_alt:
            op -= 10.0; _ekle(op_sinyaller, "Donchian(10) Kırılımı", "SAT", "Fiyat son 10 günlük dibin altında")
    op = float(np.clip(op, 0, 100))

    # ── UZUN VADE: MA200 konumu + MA50>MA200 + 1 yıllık getiri ──
    up = 50.0
    if kapanis is not None and ma200 is not None:
        if kapanis > ma200:
            up += 20.0; _ekle(up_sinyaller, "MA200 Konumu (§3.B)", "AL", "Fiyat MA200 üzerinde — uzun vadeli trend yukarı")
        else:
            up -= 20.0; _ekle(up_sinyaller, "MA200 Konumu (§3.B)", "SAT", "Fiyat MA200 altında — uzun vadeli trend aşağı")
    if ma50 is not None and ma200 is not None:
        up += 10.0 if ma50 > ma200 else -10.0
    yillik = _f(100 * (c.iloc[-1] / c.iloc[-252] - 1)) if len(c) > 252 else None
    if yillik is not None:
        if yillik > 15:
            up += 20.0; _ekle(up_sinyaller, "1 Yıllık Getiri", "AL", f"1 yılda +%{yillik:.0f}")
        elif yillik < -15:
            up -= 20.0; _ekle(up_sinyaller, "1 Yıllık Getiri", "SAT", f"1 yılda %{yillik:.0f}")
    elif getiri20 is not None:
        # 1 yıllık geçmiş yoksa (yeni işlem gören/kısa geçmişli hisse), 20G
        # getiriyle ZAYIF bir ikame yapılır — asıl vade uzun olduğundan bu
        # ikamenin ağırlığı küçük tutulur.
        up += 5.0 if getiri20 > 0 else -5.0
    up = float(np.clip(up, 0, 100))

    # ── TAKAS (para akışı): CMF20 büyüklüğü + hacim oranı ──
    tp = 50.0
    if cmf20 is not None:
        tp += float(np.clip(cmf20 * 100.0, -30.0, 30.0))
        _ekle(tp_sinyaller, "CMF20 Büyüklüğü", "AL" if cmf20 > 0 else "SAT", f"CMF20 {cmf20:+.3f}")
    if hacim5 is not None and hacim20 is not None and hacim20 > 0:
        if hacim5 >= _HACIM_CARPAN * hacim20:
            tp += 10.0; _ekle(tp_sinyaller, "Hacim Oranı", "AL", "5G/20G hacim oranı >= 1.2")
        elif hacim5 < 0.8 * hacim20:
            tp -= 10.0; _ekle(tp_sinyaller, "Hacim Oranı", "SAT", "5G hacim, 20G ortalamanın belirgin altında")
    tp = float(np.clip(tp, 0, 100))

    genel = (AGIRLIKLAR["kisa"] * kp + AGIRLIKLAR["orta"] * op +
             AGIRLIKLAR["uzun"] * up + AGIRLIKLAR["takas"] * tp)

    # ── Şişkinlik / Giriş ──────────────────────────────────────────────
    # YORUM KARARI: v2.1 şartnamesi "Şişkinlik"/"Giriş" diye ayrı bir kavram
    # TANIMLAMAZ — bunlar analiz_motoru'nun UI şeması için var olan alanlar.
    # Burada v2.1'in KENDİ referans seviyelerinden türetildi:
    #   Şişkinlik = GETIRI20'nin §3.B üst sınırına (%25) göre ne kadar
    #               "dolu" olduğu (0-100; >= %25'te tavan).
    #   Giriş     = fiyatın v21_portfoy.limit_seviyesi() (§4 alım bölgesi
    #               referansı: MA20 / Donchian(10)-1xATR) üstünde ne kadar
    #               uzakta olduğu — yakın/altında olmak İYİ giriş sayılır.
    if getiri20 is not None and getiri20 > 0:
        siskinlik = float(np.clip((getiri20 / _GETIRI20_UST) * 100.0, 0.0, 100.0))
    else:
        siskinlik = 0.0

    giris_seviyesi = None
    try:
        gs = _vp.limit_seviyesi(satir)
        if gs is not None and np.isfinite(gs):
            giris_seviyesi = float(gs)
    except Exception:
        giris_seviyesi = None
    if giris_seviyesi is not None and kapanis is not None and giris_seviyesi > 0:
        mesafe = (kapanis - giris_seviyesi) / giris_seviyesi
        giris_skoru = float(np.clip(100.0 - mesafe * 300.0, 0.0, 100.0))
    else:
        giris_skoru = 50.0  # veri yetersiz -> nötr varsayım

    if rejim is not None:
        genel, _ = rejim_duzeltmesi(genel, rejim["puan"])
    genel = float(np.clip(genel, 0, 100))
    karar, emoji = karar_ver(genel)

    sonuc = {
        "Puan": round(genel, 1), "Karar": f"{emoji} {karar}",
        "Kısa": round(kp), "Orta": round(op), "Uzun": round(up), "Takas": round(tp),
        "Şişkinlik": round(siskinlik), "Giriş": round(giris_skoru),
        "Fiyat": round(float(c.iloc[-1]), 2),
        "1 Hafta %": round(100 * (c.iloc[-1] / c.iloc[-6] - 1), 1) if len(c) > 6 else None,
        "1 Ay %": round(100 * (c.iloc[-1] / c.iloc[-22] - 1), 1) if len(c) > 22 else None,
        "3 Ay %": round(100 * (c.iloc[-1] / c.iloc[-66] - 1), 1) if len(c) > 66 else None,
        "1 Yıl %": round(100 * (c.iloc[-1] / c.iloc[-252] - 1), 1) if len(c) > 252 else None,
        "Hacim(M₺)": round(float((h["Close"] * h["Volume"]).tail(20).mean()) / 1e6, 1),
    }
    if ayrinti:
        # SADECE toplu işlemler (v1 backtest_motoru gibi) kullanır — canlı
        # tarama tabloları bu anahtarı geçmediğinden arayüzde görünmez.
        sonuc["_uzama"] = {"skor": round(siskinlik), "ceza": 0.0}
        sonuc["_erken"] = {"skor": round(giris_skoru)}
        sonuc["_sinyaller"] = kp_sinyaller + op_sinyaller + tp_sinyaller + up_sinyaller
        if ma50 is not None and ma200 is not None:
            sonuc["_trendYonu"] = "yukselis" if ma50 > ma200 else "dusus"
        else:
            sonuc["_trendYonu"] = "yatay"
    return sonuc


# ═══════════════════════════════════════════════════════════════════════
# dip_guvenlik_kontrolu — CMF20 dönüşü + hacim teyidi (v21_gosterge.cmf).
# ═══════════════════════════════════════════════════════════════════════
def dip_guvenlik_kontrolu(df: pd.DataFrame) -> dict:
    """analiz_motoru.dip_guvenlik_kontrolu ile AYNI imza/dönüş şeması;
    CMF hesabı v21_gosterge.cmf() (v2.1 §3.B'de kullanılan TANIM) ile
    yapılır."""
    bos = {"cmfDonus": None, "hacimTeyit": None, "ardArdaYukselis": None,
           "guvenliDonus": None, "neden": "veri yetersiz"}
    if df is None or len(df) < 40:
        return bos
    if not {"High", "Low", "Close", "Volume"}.issubset(getattr(df, "columns", [])):
        return bos
    try:
        c = df["Close"]
        cmf_s = _vg.cmf(df, pencere=20)
        if len(cmf_s.dropna()) < 6:
            return bos
        cmf_son = float(cmf_s.iloc[-1])
        cmf_5g_once = float(cmf_s.iloc[-6])
        cmf_donus = bool(np.isfinite(cmf_son) and np.isfinite(cmf_5g_once)
                          and cmf_son > 0 and cmf_5g_once <= cmf_son - 0.02)

        hacim_oran = float(df["Volume"].tail(5).mean() / max(df["Volume"].tail(60).mean(), 1))
        hacim_teyit = bool(np.isfinite(hacim_oran) and hacim_oran >= 1.15)

        son3 = c.tail(4).values
        ard_arda = bool(len(son3) == 4 and son3[3] > son3[2] > son3[1])

        guvenli = bool(cmf_donus and hacim_teyit and ard_arda)
        parcalar = []
        parcalar.append("para akışı dönüyor (CMF20)" if cmf_donus else "para akışı henüz dönmedi")
        parcalar.append("hacim teyitli" if hacim_teyit else "hacim teyidi yok")
        parcalar.append("art arda yükseliyor" if ard_arda else "tek günlük sıçrama olabilir")
        neden = ", ".join(parcalar)
        return {"cmfDonus": cmf_donus, "hacimTeyit": hacim_teyit,
                "ardArdaYukselis": ard_arda, "guvenliDonus": guvenli,
                "neden": neden}
    except Exception as e:
        return {**bos, "neden": f"hata: {type(e).__name__}"}


# ═══════════════════════════════════════════════════════════════════════
# secim_skoru — tek hisseli değerlendirme; v21_secim §3.B'nin TAMAMINI
# ("uygun") + CMF20/GETIRI20 tabanlı skoru (v21_secim.secim_yap'in RS'siz
# hali — bu fonksiyon endeks parametresi almadığından RS bonusu hesaplanamaz).
# ═══════════════════════════════════════════════════════════════════════
def secim_skoru(df: pd.DataFrame) -> dict:
    """analiz_motoru.secim_skoru ile AYNI imza/dönüş şeması:
    {"skor": float|None, "cmf": float|None, "ma200_ustunde": bool,
     "uygun": bool, "neden": str}.
    `uygun=True` <=> v21_secim §3.B'nin TÜM teknik zorunlulukları (fiyat>
    MA200 VE MA50>MA200, GETIRI20 ∈ [%5,%25], CMF20>0, hacim5>=1.2×hacim20)
    karşılanıyor demektir (analiz_motoru'nun orijinalinde yalnız MA200 testi
    vardı — burada görev talimatınca §3.B'nin TAMAMINA genişletildi)."""
    bos = {"skor": None, "cmf": None, "ma200_ustunde": False,
           "uygun": False, "neden": "veri yetersiz"}
    if df is None or len(df) < SECIM_MIN_GECMIS:
        return bos
    if not {"High", "Low", "Close", "Volume"}.issubset(getattr(df, "columns", [])):
        return bos
    try:
        h = _hazirla(df)
        satir = h.iloc[-1]
        kapanis = _f(satir.get("Close"))
        ma50 = _f(satir.get("MA50")); ma200 = _f(satir.get("MA200"))
        cmf20 = _f(satir.get("CMF20"))
        getiri20 = _f(satir.get("GETIRI20"))
        hacim5 = _f(satir.get("HACIM_ORT5")); hacim20 = _f(satir.get("HACIM_ORT20"))

        if kapanis is None or kapanis <= 0 or ma200 is None:
            return bos
        ustunde = kapanis > ma200

        if cmf20 is None:
            return {**bos, "ma200_ustunde": ustunde, "neden": "CMF20 hesaplanamadı"}

        getiri_ok = getiri20 is not None and _GETIRI20_ALT <= getiri20 <= _GETIRI20_UST
        hacim_ok = (hacim5 is not None and hacim20 is not None and hacim20 > 0
                    and hacim5 >= _HACIM_CARPAN * hacim20)
        ma_ok = ustunde and ma50 is not None and ma50 > ma200
        cmf_ok = cmf20 > 0
        uygun = bool(ma_ok and getiri_ok and cmf_ok and hacim_ok)

        if not uygun:
            eksikler = []
            if not ma_ok:
                eksikler.append(f"fiyat/MA50 MA200 şartını sağlamıyor (kapanış {kapanis:.2f}, MA200 {ma200:.2f})")
            if not getiri_ok:
                eksikler.append(f"GETIRI20 %5-%25 aralığı dışında ({getiri20})")
            if not cmf_ok:
                eksikler.append(f"CMF20<=0 ({cmf20:+.3f})")
            if not hacim_ok:
                eksikler.append("hacim teyidi yok (5G ort < 20G ort × 1.2)")
            return {"skor": None, "cmf": round(cmf20, 4), "ma200_ustunde": ustunde,
                    "uygun": False, "neden": "§3.B karşılanmıyor: " + "; ".join(eksikler)}

        skor = (getiri20 * 100.0) + (cmf20 * 10.0)
        return {"skor": float(skor), "cmf": round(cmf20, 4), "ma200_ustunde": True,
                "uygun": True,
                "neden": f"§3.B tüm zorunluluklar karşılandı (CMF20 {cmf20:+.3f}, GETIRI20 %{getiri20*100:.1f})"}
    except Exception as e:
        return {**bos, "neden": f"hata: {type(e).__name__}"}


# ═══════════════════════════════════════════════════════════════════════
# vade_taramasi — hizli_puan'ın Kısa/Orta/Uzun bileşenlerinden DataFrame.
# ═══════════════════════════════════════════════════════════════════════
def vade_taramasi(veri_sozlugu: dict, ust_sinir: int = 40, endeks_df=None,
                   ilerleme=None, min_hacim_milyon_tl: float = 5.0,
                   rejim: dict = None) -> pd.DataFrame:
    """analiz_motoru.vade_taramasi ile AYNI imza/dönüş şeması/sıralama
    mantığı (doğrulanmış — yani §3.B'nin TAMAMINI karşılayan — adaylar
    CMF'ye göre azalan sırada ÜSTTE, kalanlar Genel Puan'a göre azalan
    sırada ALTTA)."""
    sonuclar = []
    toplam = len(veri_sozlugu)

    def _ilerlet(sayac, sembol=None):
        if not ilerleme:
            return
        oran = sayac / toplam if toplam else 1.0
        try:
            ilerleme(oran)                      # eski/tek argümanlı imza
        except TypeError:
            try:
                ilerleme(sayac, toplam, sembol)  # yeni/üç argümanlı imza
            except Exception:
                pass
        except Exception:
            pass

    for i, (sembol, df) in enumerate(veri_sozlugu.items()):
        _ilerlet(i + 1, sembol)
        try:
            if df is None or df.empty or "Close" not in df.columns:
                continue
            ort_hacim_tl = float((df["Close"] * df["Volume"]).tail(20).mean()) / 1e6
            if ort_hacim_tl < min_hacim_milyon_tl:
                continue
            satir = hizli_puan(df, endeks_df, rejim=rejim)
            if satir.get("Puan") is None:
                continue
            secim = secim_skoru(df)
            stoch = _stoch_rsi_sinyali(df)
            kayit = {
                "Hisse": sembol,
                "Kısa": vade_karari(satir.get("Kısa")),
                "Orta": vade_karari(satir.get("Orta")),
                "Uzun": vade_karari(satir.get("Uzun")),
                "Genel Puan": satir["Puan"],
                "Fiyat": satir.get("Fiyat"),
                "Kısa Puan": satir.get("Kısa"),
                "Orta Puan": satir.get("Orta"),
                "Uzun Puan": satir.get("Uzun"),
                "Takas Puan": satir.get("Takas"),
                "1 Ay %": satir.get("1 Ay %"),
                "3 Ay %": satir.get("3 Ay %"),
                "Hacim(M₺)": satir.get("Hacim(M₺)"),
                "CMF": secim.get("cmf"),
                "MA200Ustunde": bool(secim.get("ma200_ustunde")),
                "Dogrulanmis": bool(secim.get("uygun") and (secim.get("cmf") or 0) > 0),
                # StochRSI — bilgi amaçlı, puana KARIŞMAZ (bkz. dosya başı notu).
                "StochRsiSinyal": stoch.get("sinyal"),
                "StochRsiAciklama": stoch.get("aciklama"),
            }
            sonuclar.append(kayit)
        except Exception:
            continue

    if not sonuclar:
        return pd.DataFrame()
    tablo = pd.DataFrame(sonuclar)
    dogrulanmis = tablo[tablo["Dogrulanmis"]].sort_values("CMF", ascending=False)
    digerleri = tablo[~tablo["Dogrulanmis"]].sort_values("Genel Puan", ascending=False)
    tablo = pd.concat([dogrulanmis, digerleri]).reset_index(drop=True)
    tablo = tablo.head(ust_sinir).reset_index(drop=True)
    tablo.index += 1
    return tablo


# ═══════════════════════════════════════════════════════════════════════
# ma_kirilim_taramasi — saf teknik kırılım taraması (v2.1'e özgü bir yorum
# gerektirmez; analiz_motoru'nunkiyle AYNI mantık, "düz/basit MA" kaynağı
# v21_gosterge.py'nin MA yorumuyla tutarlı tutuldu — EMA DEĞİL).
# ═══════════════════════════════════════════════════════════════════════
def ma_kirilim_taramasi(veri_sozlugu: dict, min_hacim_milyon_tl: float = 5.0) -> dict:
    """analiz_motoru.ma_kirilim_taramasi ile AYNI imza/dönüş şeması.

    Dönüş: {"fiyatKiriyor": {5: [...], 10: [...], 22: [...], 50: [...]},
            "maKiriyor": {"5_10": [...], "10_22": [...]}}
    """
    fiyat_kiriyor = {n: [] for n in MA_KIRILIM_PENCERELERI}
    ma_kiriyor = {f"{a}_{b}": [] for a, b in MA_KIRILIM_CIFTLERI}

    for sembol, df in veri_sozlugu.items():
        try:
            if df is None or df.empty or "Close" not in df.columns or len(df) < 55:
                continue
            ort_hacim_tl = float((df["Close"] * df["Volume"]).tail(20).mean()) / 1e6
            if ort_hacim_tl < min_hacim_milyon_tl:
                continue
            c = df["Close"]
            son, onceki = float(c.iloc[-1]), float(c.iloc[-2])

            for n in MA_KIRILIM_PENCERELERI:
                m = _basit_ortalama(c, n)
                if len(m) < 2 or np.isnan(m.iloc[-1]) or np.isnan(m.iloc[-2]):
                    continue
                if onceki <= float(m.iloc[-2]) and son > float(m.iloc[-1]):
                    fiyat_kiriyor[n].append(sembol)

            for a, b in MA_KIRILIM_CIFTLERI:
                ma_a, ma_b = _basit_ortalama(c, a), _basit_ortalama(c, b)
                if len(ma_a) < 2 or any(np.isnan(x) for x in
                                        (ma_a.iloc[-1], ma_a.iloc[-2], ma_b.iloc[-1], ma_b.iloc[-2])):
                    continue
                if float(ma_a.iloc[-2]) <= float(ma_b.iloc[-2]) and float(ma_a.iloc[-1]) > float(ma_b.iloc[-1]):
                    ma_kiriyor[f"{a}_{b}"].append(sembol)
        except Exception:
            continue

    return {"fiyatKiriyor": fiyat_kiriyor, "maKiriyor": ma_kiriyor}


if __name__ == "__main__":
    # Ağ çağrısı içermeyen kendi kendine kontrol — sentetik veriyle.
    # NOT: bash/CLI erişimi olmadığından bu blok bu görev sırasında
    # ÇALIŞTIRILAMADI (yalnız gözden geçirildi) — kullanıcı isterse
    # `python v21_analiz_motoru.py` ile elle doğrulayabilir.
    tarihler = pd.date_range("2022-01-01", periods=400, freq="B")
    rng = np.random.default_rng(11)

    def _df_kur(egilim: float, oynaklik: float = 1.0):
        fiyat = 100 + np.cumsum(rng.normal(egilim, oynaklik, size=len(tarihler)))
        fiyat = np.maximum(fiyat, 5.0)
        return pd.DataFrame({
            "Open": fiyat + rng.normal(0, 0.2, len(tarihler)),
            "High": fiyat + np.abs(rng.normal(0.5, 0.3, len(tarihler))),
            "Low": fiyat - np.abs(rng.normal(0.5, 0.3, len(tarihler))),
            "Close": fiyat,
            "Volume": rng.integers(1_000_000, 5_000_000, len(tarihler)),
        }, index=tarihler)

    xu100 = _df_kur(0.6)
    yukselen = _df_kur(0.5)
    dusen = _df_kur(-0.5)
    veriler = {"YUKSELEN": yukselen, "DUSEN": dusen}

    rejim = piyasa_rejimi(xu100, None, None)
    assert 0.0 <= rejim["puan"] <= 100.0
    assert rejim["sinyaller"] and set(rejim["sinyaller"][0].keys()) == {"etiket", "yon", "aciklama"}

    hp = hizli_puan(yukselen, xu100, rejim=rejim)
    for anahtar in ("Puan", "Karar", "Kısa", "Orta", "Uzun", "Takas", "Şişkinlik", "Giriş",
                    "Fiyat", "1 Hafta %", "1 Ay %", "3 Ay %", "1 Yıl %", "Hacim(M₺)"):
        assert anahtar in hp, f"hizli_puan şemasında eksik anahtar: {anahtar}"
    assert hp["Puan"] is not None and 0.0 <= hp["Puan"] <= 100.0

    assert hizli_puan(pd.DataFrame())["Puan"] is None

    dip = dip_guvenlik_kontrolu(dusen)
    assert set(dip.keys()) == {"cmfDonus", "hacimTeyit", "ardArdaYukselis", "guvenliDonus", "neden"}

    sec = secim_skoru(yukselen)
    assert set(sec.keys()) == {"skor", "cmf", "ma200_ustunde", "uygun", "neden"}

    vade = vade_taramasi(veriler, ust_sinir=10, endeks_df=xu100, rejim=rejim)
    if len(vade):
        for kolon in ("Hisse", "Kısa", "Orta", "Uzun", "Genel Puan", "Fiyat",
                      "Kısa Puan", "Orta Puan", "Uzun Puan", "Takas Puan",
                      "1 Ay %", "3 Ay %", "Hacim(M₺)", "CMF", "MA200Ustunde",
                      "Dogrulanmis", "StochRsiSinyal", "StochRsiAciklama"):
            assert kolon in vade.columns, f"vade_taramasi şemasında eksik kolon: {kolon}"

    kirilim = ma_kirilim_taramasi(veriler)
    assert set(kirilim.keys()) == {"fiyatKiriyor", "maKiriyor"}
    assert set(kirilim["fiyatKiriyor"].keys()) == set(MA_KIRILIM_PENCERELERI)
    assert set(kirilim["maKiriyor"].keys()) == {f"{a}_{b}" for a, b in MA_KIRILIM_CIFTLERI}

    print("v21_analiz_motoru.py kendi kendine kontrol: BAŞARILI")
    print("Rejim:", rejim["durum"], rejim["puan"])
    print("hizli_puan (YUKSELEN):", hp["Puan"], hp["Karar"])
