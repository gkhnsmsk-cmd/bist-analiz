# -*- coding: utf-8 -*-
"""
akd_model.py — AKD_Model_Egitim_Rehberi.md'deki tarife göre, akd_veri_toplama.py
ile biriktirilen akd_egitim_verisi.csv üzerinde bir XGBoost sınıflandırıcı
eğitir ve canlı tahmin için kullanılabilir hâle getirir.
══════════════════════════════════════════════════════════════════════════════
ÖNEMLİ — VERİ YETERLİLİĞİ: Bu modelin anlamlı bir şey öğrenebilmesi için
GERÇEKTEN ETİKETLENMİŞ (yani T+1 getirisi bilinen) onlarca-yüzlerce satırlık
geçmiş veri gerekir. akd_veri_toplama.py'yi kurduğun ilk gün bu script
"yeterli veri yok" hatası verecektir — bu BEKLENEN bir durumdur, hata değil.
Veri toplama scriptini her gün (borsa kapanışından sonra) çalıştırıp birkaç
hafta biriktirdikten sonra tekrar deneyin.

KULLANIM:
  python akd_model.py            → mevcut veriyle modeli eğitir, raporu basar
  python akd_model.py --tahmin TERA → (varsa) TERA için bugünkü AKD verisiyle
                                       eğitilmiş modelden tahmin üretir
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")

KLASOR = Path(__file__).parent
CSV_DOSYA = KLASOR / "akd_egitim_verisi.csv"
MODEL_DOSYASI = KLASOR / "akd_model.pkl"

# maliyet_fiyat_farki şu an OCR ile hesaplanamıyor (bkz. telegram_akd.py) —
# bu yüzden eğitim özelliklerinden ÇIKARILDI; ileride eklenirse buraya
# eklenmesi yeterli.
FEATURES = [
    "ilk5_alici_yuzde", "ilk5_satici_yuzde", "akd_spread",
    "diger_alici_yuzde", "diger_satici_yuzde", "en_buyuk_alici_yuzde",
    "kurumsal_alim_gucu", "akd_hacim_rasyosu", "kural_puani",
]
VARSAYILAN_MIN_EGITIM_SATIRI = 30
YUKSELIS_ESIGI_PCT = 1.0  # rehberdeki gibi: T+1 getiri > %1 ise "yükseldi" (1)


def veri_yukle() -> pd.DataFrame:
    """Etiketlenmiş (target_t1_return dolu) ve özellik sütunlarının HİÇBİRİ
    eksik olmayan satırları döndürür — eksik satırlar modeli bozmasın diye
    sessizce atlanır (kaç satırın atlandığı çağıran tarafından loglanabilir)."""
    if not CSV_DOSYA.exists():
        return pd.DataFrame(columns=["target_t1_return"] + FEATURES)
    df = pd.read_csv(CSV_DOSYA)
    if "target_t1_return" not in df.columns:
        return pd.DataFrame(columns=["target_t1_return"] + FEATURES)
    df = df[df["target_t1_return"].notna() & (df["target_t1_return"] != "")]
    for kol in FEATURES + ["target_t1_return"]:
        if kol in df.columns:
            df[kol] = pd.to_numeric(df[kol], errors="coerce")
    df = df.dropna(subset=FEATURES + ["target_t1_return"])
    return df


def model_egit(min_satir: int = VARSAYILAN_MIN_EGITIM_SATIRI) -> dict:
    try:
        import xgboost as xgb
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, classification_report
        import joblib
    except ImportError as e:
        raise ImportError(
            "xgboost/scikit-learn kurulu değil. Kur: "
            "pip install xgboost scikit-learn --break-system-packages"
        ) from e

    df = veri_yukle()
    if len(df) < min_satir:
        raise ValueError(
            f"Yeterli etiketlenmiş veri yok: {len(df)} satır var, en az {min_satir} "
            f"gerekli. akd_veri_toplama.py'yi her gün (borsa kapanışından sonra) "
            f"çalıştırıp birkaç hafta biriktirdikten sonra tekrar deneyin. "
            f"Bu bir hata değil — model henüz öğrenecek yeterli örnek görmedi."
        )

    X = df[FEATURES]
    y = (df["target_t1_return"] > YUKSELIS_ESIGI_PCT).astype(int)

    if y.nunique() < 2:
        raise ValueError(
            "Tüm etiketlenmiş kayıtlar aynı sınıfta (hepsi yükseliş ya da hepsi "
            "değil) — model iki sınıfı da görmeden anlamlı eğitilemez. Daha "
            "fazla/çeşitli veri birikmesini bekleyin."
        )

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, shuffle=False)  # zaman serisi -> shuffle yok

    model = xgb.XGBClassifier(
        n_estimators=100, learning_rate=0.05, max_depth=4, random_state=42,
        eval_metric="logloss",
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test) if len(X_test) else []
    dogruluk = accuracy_score(y_test, y_pred) if len(X_test) else None
    rapor = classification_report(y_test, y_pred, zero_division=0) if len(X_test) else "(test seti boş)"

    onem = pd.DataFrame({"Ozellik": FEATURES, "Onem": model.feature_importances_}) \
        .sort_values("Onem", ascending=False).reset_index(drop=True)

    joblib.dump(model, MODEL_DOSYASI)

    return {
        "egitim_satiri": len(df), "dogruluk": dogruluk, "rapor": rapor,
        "onem": onem, "model_dosyasi": str(MODEL_DOSYASI),
    }


def model_yukle():
    try:
        import joblib
    except ImportError:
        return None
    if not MODEL_DOSYASI.exists():
        return None
    return joblib.load(MODEL_DOSYASI)


def tahmin_et(ozellikler: dict) -> dict:
    """ozellikler: akd_ozellik_cikar()'ın döndürdüğü sözlük (ya da aynı
    anahtarlara sahip herhangi bir sözlük). Model henüz eğitilmemişse veya
    özellikler eksikse net bir açıklama ile None tahmin döner — asla sessizce
    yanlış/rastgele bir sayı üretmez."""
    model = model_yukle()
    if model is None:
        return {"tahmin": None, "not": "Model henüz eğitilmedi (python akd_model.py çalıştırın)."}

    satir = {f: ozellikler.get(f) for f in FEATURES}
    eksikler = [f for f, v in satir.items() if v is None]
    if eksikler:
        return {"tahmin": None, "not": f"Eksik özellik(ler): {eksikler} — tahmin güvenilir olmaz."}

    X = pd.DataFrame([satir])
    olasilik = float(model.predict_proba(X)[0][1])
    return {
        "tahmin": int(olasilik > 0.5),
        "yukselis_olasiligi": round(olasilik, 3),
        "not": f"Model %{YUKSELIS_ESIGI_PCT:.0f}'den fazla T+1 getiri olasılığını tahmin ediyor.",
    }


if __name__ == "__main__":
    if "--tahmin" in sys.argv:
        idx = sys.argv.index("--tahmin")
        sembol = sys.argv[idx + 1].upper() if len(sys.argv) > idx + 1 else None
        if not sembol:
            print("Kullanım: python akd_model.py --tahmin SEMBOL")
            sys.exit(1)
        import telegram_akd as takd
        veri = takd.oku(sembol)
        if not veri or not veri.get("tablo"):
            print(f"{sembol} için önce 'python telegram_akd.py {sembol}' ile güncel AKD verisi çekilmeli.")
            sys.exit(1)
        ozellikler = takd.akd_ozellik_cikar(veri["tablo"], kapanis_fiyati=veri.get("kapanis_fiyati"))
        sonuc = tahmin_et(ozellikler)
        print(f"{sembol}: {sonuc}")
        sys.exit(0)

    try:
        sonuc = model_egit()
    except (ValueError, ImportError) as e:
        print(f"Model eğitilemedi: {e}")
        sys.exit(1)

    print(f"Eğitim satırı: {sonuc['egitim_satiri']}")
    if sonuc["dogruluk"] is not None:
        print(f"Test doğruluğu: {sonuc['dogruluk']:.2f}")
    print("\nSınıflandırma raporu:\n", sonuc["rapor"])
    print("Özellik önem düzeyleri:\n", sonuc["onem"].to_string(index=False))
    print(f"\nModel kaydedildi: {sonuc['model_dosyasi']}")
