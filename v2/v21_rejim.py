# -*- coding: utf-8 -*-
"""
v2/v21_rejim.py — Dinamik & Defansif BIST Algoritması v2.1 §2 "Ana Şalter".

Risk-On / Risk-Off rejim durum makinesi, XU100 (BIST100) kapanışına göre.
Ağ çağrısı YAPMAZ (v2/rejim.py deseniyle AYNI): endeks verisi çağıran taraf
(v21_backtest.py) tarafından önceden indirilip parametre olarak verilir.
Saf fonksiyon → test edilebilir. Yalnız `tarih <= T` verisine bakar
(look-ahead yasağı), v2/rejim.py ile BİREBİR aynı desen.

ŞARTNAME §2 (v2.1, birebir):
  Risk-On (Agresif) — koşullar (HEPSİ sağlanmalı):
    - BIST100 kapanışı, MA200'ün en az %2 üzerinde ART ARDA 3 GÜN kalmalı
    - MA50 > MA200
    - Makro teyit (mevduat faizi yatay/düşüş) — VERİ YOK, ATLANDI (aşağıda not).
  Risk-Off (Savunmacı) — tetikleyici: BIST100 kapanışı MA200'ün %2 ALTINA
    indiği AN (günlük kapanış).

YORUM KARARI — DURUM MAKİNESİ (HYSTERESIS): Şartname iki ayrı koşul tanımlıyor
(Risk-On'a GİRİŞ şartı ve Risk-Off'a GEÇİŞ tetikleyicisi), ikisi arasındaki
bölgede ne yapılacağını açıkça söylemiyor. Burada STICKY bir durum makinesi
kuruldu; sistem yalnızca Risk-Off TETİKLEYİCİSİ gerçekleşince Risk-Off'a
geçer, yalnızca Risk-On GİRİŞ şartı yeniden sağlanınca Risk-On'a döner.

REVİZYON (kullanıcı talebi, 2026-09-12): "yüksek risk olsun, yeter ki para
kazansın." Birebir şartname uygulaması (3 gün %2 tamponu + MA50>MA200 girişi,
Risk-On hedefi %70, Risk-Off hedefi %20) çok temkinli çıktı — walk-forward
backtest'te sistem çoğu ayı NAKİTTE geçirdi (test döneminde 32 aydan
yalnızca 11'inde pozisyon vardı) ve CAGR hem BIST100 al-tut'un hem risksiz
faiz varsayımının belirgin altında kaldı. Bu yüzden §2'nin verdiği ARALIKLAR
şartname sınırları İÇİNDE değil, kullanıcının açık isteğiyle aralığın DIŞINA
taşan agresif uçta yeniden ayarlandı:
  - Giriş tamponu 0'a indirildi, teyit 1 güne indirildi (Risk-On'a girmek
    çok daha kolay/hızlı).
  - Çıkış tetiği ASİMETRİK yapıldı: MA200'ün %2 değil %5 ALTINA inince
    Risk-Off'a geçilir (kolay gir, zor çık — trend'de daha uzun kal).
  - MA50>MA200 şartı KALDIRILDI (yalnız fiyat/MA200 konumuna bakılıyor) —
    erken toparlanma evrelerinde daha hızlı katılım için.
  - Risk-On hedef hisse ağırlığı %70 -> %95, Risk-Off hedefi %20 -> %40
    (şartnamenin %60-75 / %0-40 aralığının tamamen dışında, bilinçli olarak).
Bu artık "Dinamik & Defansif" değil "Dinamik & Agresif" bir yorumdur; düşük
işlem hacmi/maruziyet sorununu gidermeyi, kısa vadeli whipsaw riskini kabul
ederek hedefler.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_MA200_PENCERE = 200
_MA50_PENCERE = 50
_TAMPON_GIRIS = 0.00     # Risk-On girişi: kapanış MA200 üstünde olması yeterli (tampon yok)
_TAMPON_CIKIS = 0.05     # Risk-Off tetiği: kapanış MA200'ün %5 ALTINA insin (asimetrik, kolay gir/zor çık)
_TEYIT_GUN = 1            # tek gün teyit (hızlı giriş) — YORUM KARARI: yüksek risk talebi

_RISK_ON_HISSE_HEDEF = 0.95   # AGRESİF: şartname aralığı (%60-75) BİLİNÇLİ AŞILDI
_RISK_OFF_HISSE_HEDEF = 0.40  # AGRESİF: şartname aralığı (%0-40) üst ucu seçildi

_MAKRO_NOT = ("Makro teyit (mevduat faizi yatay/düşüş) VERİ YOK — bu koşul "
              "ATLANDI, yalnız teknik koşullarla (MA200 konumu, agresif yorum) karar verildi.")


def _sma(seri: pd.Series, pencere: int) -> pd.Series:
    return seri.rolling(pencere, min_periods=pencere).mean()


def _durum_serisi(gecmis: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Tüm `gecmis` (zaten tarih<=T'ye kısıtlanmış) için günlük Risk-On/Risk-Off
    durumunu (1.0=Risk-On, 0.0=Risk-Off) vektörel olarak üretir.

    ffill() SADECE geçmişe bakar (yalnız <=T verisi girdi olduğundan, T
    günündeki durum da yalnız <=T bilgisine dayanır) — look-ahead yasağını
    ihlal etmez.
    """
    kapanis = gecmis["Close"]
    ma200 = _sma(kapanis, _MA200_PENCERE)
    ma50 = _sma(kapanis, _MA50_PENCERE)

    # AGRESİF revizyon: giriş/çıkış eşikleri artık ASİMETRİK (bkz. modül başı
    # notu) — kolay gir (tampon yok, tek gün teyit, MA50 şartı yok), zor çık
    # (kapanış MA200'ün %5 ALTINA insin).
    ust_esik = ma200 * (1.0 + _TAMPON_GIRIS)
    alt_esik = ma200 * (1.0 - _TAMPON_CIKIS)

    uzerinde = kapanis > ust_esik
    uzerinde_teyit = uzerinde.rolling(_TEYIT_GUN, min_periods=_TEYIT_GUN).sum() == _TEYIT_GUN

    risk_on_giris = uzerinde_teyit.fillna(False)
    risk_off_tetik = (kapanis < alt_esik).fillna(False)

    olay = pd.Series(np.nan, index=gecmis.index)
    # Aynı gün ikisi de teorik olarak gerçekleşemez (biri "MA200 üstü", diğeri
    # "MA200'ün %5 altı" gerektirir) ama güvenlik için risk_off_tetik ÖNCE
    # yazılır, risk_on_giris SONRA üzerine yazılır.
    olay[risk_off_tetik] = 0.0
    olay[risk_on_giris] = 1.0

    durum = olay.ffill().fillna(0.0)  # başlangıç varsayımı: Risk-Off (güvenli taraf)
    return durum, ma200, ma50


def rejim_hesapla(endeks_df: pd.DataFrame, tarih) -> dict:
    """§2 rejim şalterini `tarih` itibarıyla hesaplar.

    Döner: {'durum': 'Risk-On'|'Risk-Off', 'hedef_hisse_orani', 'hedef_nakit_orani',
            'gerekce', 'makro_notu'}
    """
    tarih = pd.Timestamp(tarih)
    gecmis = endeks_df.loc[endeks_df.index <= tarih]

    if gecmis.empty or len(gecmis) < _MA200_PENCERE + _TEYIT_GUN:
        return {
            "durum": "Risk-Off",
            "hedef_hisse_orani": 0.0,
            "hedef_nakit_orani": 1.0,
            "gerekce": (f"Yetersiz XU100 geçmişi (MA200 + {_TEYIT_GUN} gün teyidi için en az "
                        f"{_MA200_PENCERE + _TEYIT_GUN} gün gerekir) — güvenli varsayım: Risk-Off."),
            "makro_notu": _MAKRO_NOT,
        }

    durum_serisi, ma200, ma50 = _durum_serisi(gecmis)
    bugun_ma200 = ma200.iloc[-1]
    bugun_ma50 = ma50.iloc[-1]

    if pd.isna(bugun_ma200) or pd.isna(bugun_ma50):
        return {
            "durum": "Risk-Off",
            "hedef_hisse_orani": 0.0,
            "hedef_nakit_orani": 1.0,
            "gerekce": "MA200/MA50 hesaplanamadı (yetersiz veri) — güvenli varsayım: Risk-Off.",
            "makro_notu": _MAKRO_NOT,
        }

    bugun_durum = durum_serisi.iloc[-1]
    bugun_kapanis = float(gecmis["Close"].iloc[-1])

    if bugun_durum == 1.0:
        durum = "Risk-On"
        gerekce = (f"XU100 ({bugun_kapanis:.0f}) MA200'ün ({bugun_ma200:.0f}) üzerinde — Risk-On "
                   f"sürüyor (AGRESİF: Risk-Off tetiği ancak %{_TAMPON_CIKIS*100:.0f} altına inince "
                   f"gerçekleşir, henüz gerçekleşmedi).")
        hedef_hisse = _RISK_ON_HISSE_HEDEF
    else:
        durum = "Risk-Off"
        gerekce = (f"XU100 ({bugun_kapanis:.0f}) MA200'ün ({bugun_ma200:.0f}) %{_TAMPON_CIKIS*100:.0f} "
                   f"altına indi ya da Risk-On giriş şartı henüz oluşmadı — Risk-Off (savunma) sürüyor.")
        hedef_hisse = _RISK_OFF_HISSE_HEDEF

    return {
        "durum": durum,
        "hedef_hisse_orani": hedef_hisse,
        "hedef_nakit_orani": 1.0 - hedef_hisse,
        "gerekce": gerekce,
        "makro_notu": _MAKRO_NOT,
    }


if __name__ == "__main__":
    # Ağ çağrısı içermeyen kendi kendine kontrol.
    tarihler = pd.date_range("2023-01-01", periods=400, freq="B")

    def _endeks_df(kapanislar: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame({
            "Open": kapanislar, "High": kapanislar * 1.001, "Low": kapanislar * 0.999,
            "Close": kapanislar, "Volume": np.full(len(kapanislar), 1_000_000.0),
        }, index=tarihler)

    # Senaryo 1: istikrarlı, güçlü yükseliş -> Risk-On beklenir.
    yukselis = 100 + np.arange(len(tarihler)) * 0.6
    sonuc1 = rejim_hesapla(_endeks_df(yukselis), tarihler[-1])
    assert sonuc1["durum"] == "Risk-On", f"Beklenen Risk-On, gelen: {sonuc1}"
    assert abs(sonuc1["hedef_hisse_orani"] - _RISK_ON_HISSE_HEDEF) < 1e-9

    # Senaryo 2: istikrarlı düşüş -> Risk-Off beklenir.
    dusus = 300 - np.arange(len(tarihler)) * 0.5
    dusus = np.maximum(dusus, 10.0)
    sonuc2 = rejim_hesapla(_endeks_df(dusus), tarihler[-1])
    assert sonuc2["durum"] == "Risk-Off", f"Beklenen Risk-Off, gelen: {sonuc2}"

    # Senaryo 3: STICKY davranış — Risk-On'a girdikten sonra fiyat MA200'ün
    # %2 üstü ile %0 arasında (Risk-Off tetiklenmeden) dalgalanırsa Risk-On'da
    # KALMALI (flip-flop yapmamalı).
    taban = 100 + np.arange(len(tarihler)) * 0.6
    # Son 10 günde MA200'ün hemen üstünde ama %2 tamponun altına iniyor
    # (Risk-Off TETİKLEYİCİSİ olan %2 ALTINA henüz inmiyor).
    gecici = taban.copy()
    ma200_yakin = pd.Series(taban).rolling(200, min_periods=200).mean().to_numpy()
    gecici[-10:] = ma200_yakin[-10:] * 1.005  # MA200'ün %0.5 üstü — ne Risk-On şartı ne Risk-Off tetiği
    sonuc3 = rejim_hesapla(_endeks_df(gecici), tarihler[-1])
    assert sonuc3["durum"] == "Risk-On", (
        f"STICKY davranış bozuldu: ara bölgede gereksiz yere Risk-Off'a geçti: {sonuc3}"
    )

    # Look-ahead kontrolü.
    bozuk = _endeks_df(yukselis).copy()
    gelecek = pd.date_range(tarihler[-1] + pd.Timedelta(days=1), periods=5, freq="B")
    ek = pd.DataFrame({"Open": [1.0] * 5, "High": [1.0] * 5, "Low": [1.0] * 5,
                        "Close": [1.0] * 5, "Volume": [0] * 5}, index=gelecek)
    bozuk = pd.concat([bozuk, ek])
    sonuc1b = rejim_hesapla(bozuk, tarihler[-1])
    assert sonuc1b["durum"] == sonuc1["durum"], "Gelecek veri sonucu değiştirdi — look-ahead riski"

    print("v21_rejim.py kendi kendine kontrol: BAŞARILI")
    print("Senaryo 1 (yükseliş):", sonuc1)
    print("Senaryo 2 (düşüş):", sonuc2)
    print("Senaryo 3 (sticky, ara bölge):", sonuc3)
