# -*- coding: utf-8 -*-
"""
v2/pozisyon.py — Pusula V2 çıkış hiyerarşisi ve portföy kısıtları (§5, §6).

Tek sorumluluk: açık bir pozisyonun bugün kapanmasını gerektirip
gerektirmediğine karar vermek (§5, sırayla / ilk tetikleyen kazanır) ve
trailing (chandelier) stop'u güncellemek. Ayrıca §6 portföy kısıtlarını
kontrol eden bağımsız bir yardımcı fonksiyon içerir. Ağ çağrısı YOK, dosya
okuma YOK — tüm fonksiyonlar saf; yalnız aldıkları parametrelere bakar.

─────────────────────────────────────────────────────────────────────────
POZİSYON SÖZLÜĞÜ ŞEMASI (bu modülün beklediği alanlar)
─────────────────────────────────────────────────────────────────────────
§11'de `pozisyon: dict` biçimi tam olarak tanımlanmamış; bu modülün ihtiyaç
duyduğu alanlar aşağıda net biçimde belgelenmiştir (motor.py bu şemayla
üretip güncel tutmalıdır):

    sembol              : str
    giris_tarihi        : pd.Timestamp
    giris_fiyati        : float
    ilk_stop            : float   # giriş − 2.5×ATR14(giriş günü). SABİT,
                                   # bu modül tarafından ASLA değiştirilmez.
    guncel_stop         : float   # trailing (chandelier) ile güncellenen,
                                   # yalnız YUKARI hareket eden asıl stop.
                                   # Başlangıçta ilk_stop'a eşit olmalı.
    en_yuksek_kapanis   : float   # girişten bugüne en yüksek KAPANIŞ.
                                   # Başlangıçta giriş_fiyatına eşit olmalı.
    gun_sayisi          : int     # girişten bu yana geçen işlem günü sayısı.
                                   # trailing_guncelle() her çağrıda +1 eder.
    ust_uste_ema50_alti : int     # kapanışın EMA50 altında kapandığı
                                   # ardışık gün sayacı. trailing_guncelle()
                                   # günceller (Close>=EMA50 ise sıfırlanır).
    sektor              : str     # opsiyonel; verilmezse portfoy_kisit_kontrol
                                   # sektor_haritasi üzerinden sembolden bulur.

`giris_adaylari()` (sinyal.py) çıktısındaki minimal alanlara ek olarak,
`portfoy_kisit_kontrol`'ün "bugün" bilgisine ihtiyacı olduğundan (30 gün
yeniden-giriş yasağı için), YORUM KARARI: `aday` sözlüğünün ayrıca bir
'tarih' anahtarı taşıdığı varsayılıyor — bunu ekleyen motor.py'dir (zaten
giris_adaylari()'ı hangi tarih için çağırdığını biliyor). Bu, §11'deki
sabit alan kümesine (sembol/kurulum/skor/kapanis/atr/uzama/goreli_guc) YENİ
BİR alan eklemekten ibarettir, mevcut alanların hiçbiri değişmez/kaldırılmaz.
"""

from __future__ import annotations

import pandas as pd

# §6 sabitleri.
_MAKS_ESZAMANLI_POZISYON = 6
_MAKS_SEKTOR_POZISYON = 2
_MAKS_GUNLUK_YENI_POZISYON = 2
_STOP_SONRASI_BEKLEME_GUN = 30

# §5 sabitleri.
_ZAMAN_STOPU_GUN = 15
_ZAMAN_STOPU_GETIRI_ESIGI = 0.02  # +%2
_CHANDELIER_ATR_KATSAYI = 3.0
_TRAILING_AKTIVASYON_R = 1.0  # trailing yalnız +1R sonrası devreye girer

_DIGER_SEKTOR = "Diğer / Sınıflandırılmamış"


def _sektor_bul(sembol: str, sektor_haritasi) -> str:
    """sektor_haritasi ister dict (sembol->sektor) ister çağrılabilir olsun,
    her iki biçimi de kabul eder — repodaki sektor_haritasi.py'nin
    sektor_bul() işlevindeki normalize mantığıyla (boşluk/BÜYÜK harf, ".IS"
    soneki temizliği) tutarlı çalışır. Haritada yoksa 'Diğer' döner; bu,
    sektörel yoğunlaşma hesabını sessizce atlamak yerine ayrı bir grup
    olarak izlemeye devam eder.
    """
    if sektor_haritasi is None:
        return _DIGER_SEKTOR
    if callable(sektor_haritasi):
        try:
            return sektor_haritasi(sembol) or _DIGER_SEKTOR
        except Exception:
            return _DIGER_SEKTOR
    anahtar = sembol.strip().upper().replace(".IS", "")
    return sektor_haritasi.get(anahtar, _DIGER_SEKTOR)


def cikis_kontrol(pozisyon: dict, bugun: pd.Series, rejim: dict) -> dict | None:
    """§5 çıkış hiyerarşisini SIRAYLA kontrol eder; ilk tetiklenen kazanır.

    Sıra (şartnameyle birebir):
      1) İlk stop     — bugünün en düşüğü (Low) ilk_stop'a değdi mi?
      2) Trailing     — trailing aktifse (kâr +1R'yi geçtiyse VE guncel_stop
                        ilk_stop'un üzerine çıktıysa) bugünün Low'u guncel_stop'a
                        değdi mi?
      3) Zaman stopu  — 15. işlem gününde getiri hâlâ +%2'nin altında mı?
      4) Trend kırılımı — 2 gün üst üste kapanış EMA50 altında mı?
      5) Rejim çıkışı — R4 ise HER pozisyon kapanır; R3 için portföy
                        seviyesinde "en zayıf" karşılaştırması bu fonksiyonun
                        bilgi kapsamı DIŞINDADIR (bkz. modül altındaki not).

    YORUM KARARI — Low mu Close mu? Şartname "her gün kapanışta kontrol"
    diyor; bu, kontrolün NE ZAMAN çalıştığını (günde bir kez, kapanıştan
    sonra) belirtir, hangi FİYATLA karşılaştırılacağını değil. Stop
    seviyeleri (1 ve 2) intraday bir eşik olduğundan günün Low'u ile,
    trend/zaman kuralları (3 ve 4) ise doğrudan kapanışa dayalı olduğundan
    Close ile kontrol edilir — EOD veriyle en gerçekçi/tutarlı yorum budur.
    Gap-down durumunda gerçekleşme fiyatı min(Open, stop_seviyesi) alınır
    (açılış stopun altındaysa emir stopta değil açılışta gerçekleşir).

    Döner: {'neden': 'stop'|'trailing'|'zaman'|'trend'|'rejim', 'fiyat': float}
    veya çıkış yoksa None.
    """
    low = bugun.get("Low")
    close = bugun.get("Close")
    openf = bugun.get("Open")
    if low is None or close is None or pd.isna(low) or pd.isna(close):
        return None  # günün verisi eksikse karar verilemez, güvenli taraf: bekle

    ilk_stop = pozisyon["ilk_stop"]
    giris_fiyati = pozisyon["giris_fiyati"]

    # 1) İlk stop — ASLA aşağı çekilmeyen sabit seviye.
    if low <= ilk_stop:
        fiyat = min(openf, ilk_stop) if (openf is not None and not pd.isna(openf) and openf < ilk_stop) else ilk_stop
        return {"neden": "stop", "fiyat": float(fiyat)}

    # 2) Trailing (Chandelier) — yalnız aktifse VE gerçekten ilk_stop'un
    #    üzerine taşınmışsa kontrol edilir (aksi halde madde 1 ile aynı
    #    seviyeyi iki kez kontrol etmiş oluruz).
    guncel_stop = pozisyon.get("guncel_stop", ilk_stop)
    if guncel_stop > ilk_stop and low <= guncel_stop:
        fiyat = min(openf, guncel_stop) if (openf is not None and not pd.isna(openf) and openf < guncel_stop) else guncel_stop
        return {"neden": "trailing", "fiyat": float(fiyat)}

    # 3) Zaman stopu — 15 işlem günü sonunda getiri hâlâ cılızsa "ölü para".
    gun_sayisi = pozisyon.get("gun_sayisi", 0)
    if gun_sayisi >= _ZAMAN_STOPU_GUN and giris_fiyati:
        getiri = (close - giris_fiyati) / giris_fiyati
        if getiri < _ZAMAN_STOPU_GETIRI_ESIGI:
            return {"neden": "zaman", "fiyat": float(close)}

    # 4) Trend kırılımı — 2 gün üst üste EMA50 altında kapanış.
    if pozisyon.get("ust_uste_ema50_alti", 0) >= 2:
        return {"neden": "trend", "fiyat": float(close)}

    # 5) Rejim çıkışı.
    if rejim and rejim.get("rejim") == "R4":
        return {"neden": "rejim", "fiyat": float(close)}
    if rejim and rejim.get("rejim") == "R3":
        # "En zayıf (en düşük R) pozisyonlar hedef orana inene dek kapanır"
        # kuralı, TÜM açık pozisyonların R'sinin karşılaştırılmasını
        # gerektiren PORTFÖY SEVİYESİNDE bir karardır — bu fonksiyon tek bir
        # pozisyonun bilgisiyle çağrıldığından (§11 imzası: pozisyon, bugun,
        # rejim) bunu tek başına belirleyemez. YORUM KARARI: motor.py, R3
        # altında hangi pozisyonların kapatılması gerektiğine portföy
        # genelinde karar verip, o pozisyonlar için `rejim` sözlüğüne
        # (rejim.py'nin ürettiği sabit {'rejim','hedef_oran','genislik',
        # 'gerekce'} şemasını BOZMADAN, ek/opsiyonel bir anahtar olarak)
        # 'r3_bu_pozisyonu_kapat': True ekleyip cikis_kontrol'ü öyle
        # çağırabilir. Bu anahtar yoksa (varsayılan) hiçbir şey tetiklenmez
        # — böylece portföy bağlamı olmadan yanlışlıkla TÜM R3 pozisyonları
        # kapatılmaz.
        if rejim.get("r3_bu_pozisyonu_kapat", False):
            return {"neden": "rejim", "fiyat": float(close)}

    return None


def trailing_guncelle(pozisyon: dict, bugun: pd.Series) -> dict:
    """Chandelier stop'u YALNIZ yukarı günceller; pozisyonun güncel halini döner.

    Bu fonksiyon aynı zamanda günlük "bookkeeping" tek noktasıdır: motor.py
    her gün bunu bir kez (cikis_kontrol'den ÖNCE) çağırmalı — gun_sayisi ve
    ust_uste_ema50_alti sayaçları da burada güncellenir, çünkü bunlar
    "bugünün verisiyle dünün durumunu ilerletme" işidir ve cikis_kontrol
    saf bir OKUMA fonksiyonu olarak kalmalıdır (state değiştirmez).

    Kural: trailing yalnız kâr +1R'yi (R = giriş_fiyati - ilk_stop) geçtikten
    SONRA devreye girer; öncesinde guncel_stop, ilk_stop'ta sabit kalır.
    Devreye girdikten sonra da max(...) ile hesaplandığından ASLA aşağı
    çekilmez — ne kâr geri çekilse ne de ATR küçülse.
    """
    yeni = dict(pozisyon)  # kopya — çağıranın elindeki orijinali mutasyona uğratma

    giris_fiyati = pozisyon["giris_fiyati"]
    ilk_stop = pozisyon["ilk_stop"]
    kapanis_bugun = bugun.get("Close")

    en_yuksek_onceki = pozisyon.get("en_yuksek_kapanis", giris_fiyati)
    en_yuksek_yeni = en_yuksek_onceki
    if kapanis_bugun is not None and not pd.isna(kapanis_bugun):
        en_yuksek_yeni = max(en_yuksek_onceki, float(kapanis_bugun))
    yeni["en_yuksek_kapanis"] = en_yuksek_yeni

    guncel_stop_onceki = pozisyon.get("guncel_stop", ilk_stop)
    r_birimi = giris_fiyati - ilk_stop  # tanım gereği pozitif olmalı (stop girişin altında)

    yeni_stop = max(guncel_stop_onceki, ilk_stop)  # "asla aşağı çekilmez" güvencesi
    if r_birimi > 0:
        kar_mevcut = en_yuksek_yeni - giris_fiyati
        if kar_mevcut >= _TRAILING_AKTIVASYON_R * r_birimi:
            atr_bugun = bugun.get("ATR14")
            if atr_bugun is not None and not pd.isna(atr_bugun) and atr_bugun > 0:
                chandelier_aday = en_yuksek_yeni - _CHANDELIER_ATR_KATSAYI * atr_bugun
                yeni_stop = max(yeni_stop, chandelier_aday)
    yeni["guncel_stop"] = yeni_stop

    yeni["gun_sayisi"] = pozisyon.get("gun_sayisi", 0) + 1

    ema50_bugun = bugun.get("EMA50")
    if (kapanis_bugun is not None and not pd.isna(kapanis_bugun)
            and ema50_bugun is not None and not pd.isna(ema50_bugun)
            and kapanis_bugun < ema50_bugun):
        yeni["ust_uste_ema50_alti"] = pozisyon.get("ust_uste_ema50_alti", 0) + 1
    else:
        yeni["ust_uste_ema50_alti"] = 0

    return yeni


def portfoy_kisit_kontrol(aday: dict, acik_pozisyonlar: list[dict],
                           bugun_acilan_sayisi: int, son_stop_tarihleri: dict,
                           sektor_haritasi) -> str | None:
    """§6 portföy kısıtlarını kontrol eder. Uygunsa None, değilse Türkçe red nedeni.

    Kontrol sırası (ilk ihlal edilen döner):
      1) Maks 6 eşzamanlı pozisyon
      2) Günde maks 2 yeni pozisyon
      3) Aynı sektörden maks 2
      4) Zarardaki pozisyona ekleme / ortalama düşürme yok
      5) Stop olan hisseye 30 gün yeniden giriş yok

    aday: en azından {'sembol','kapanis'} içermeli; 30 gün kuralı için
          ayrıca 'tarih' anahtarı beklenir (bkz. modül başındaki YORUM
          KARARI notu) — yoksa o kontrol güvenli biçimde atlanır (ne
          reddeder ne de sessizce riskli izin verir gibi davranmaz; sadece
          değerlendirilemeyen bir kontrolü atlar, diğer dört kontrol
          çalışmaya devam eder).
    son_stop_tarihleri: {sembol: pd.Timestamp} — son stop tarihi.
    sektor_haritasi: {sembol: sektor} sözlüğü VEYA sembol->sektor çağrılabilir.
    """
    acik_pozisyonlar = acik_pozisyonlar or []

    # 1) Maks eşzamanlı pozisyon.
    if len(acik_pozisyonlar) >= _MAKS_ESZAMANLI_POZISYON:
        return (f"Maksimum {_MAKS_ESZAMANLI_POZISYON} eşzamanlı pozisyon "
                f"sınırına ulaşıldı.")

    # 2) Günde maks yeni pozisyon.
    if (bugun_acilan_sayisi or 0) >= _MAKS_GUNLUK_YENI_POZISYON:
        return (f"Bugün için maksimum {_MAKS_GUNLUK_YENI_POZISYON} yeni "
                f"pozisyon sınırına ulaşıldı.")

    # 3) Aynı sektörden maks 2.
    aday_sektor = _sektor_bul(aday["sembol"], sektor_haritasi)
    ayni_sektor_sayisi = sum(
        1 for p in acik_pozisyonlar
        if _sektor_bul(p.get("sembol", ""), sektor_haritasi) == aday_sektor
    )
    if ayni_sektor_sayisi >= _MAKS_SEKTOR_POZISYON:
        return (f"Aynı sektörden ({aday_sektor}) zaten "
                f"{_MAKS_SEKTOR_POZISYON} pozisyon açık.")

    # 4) Zarardaki pozisyona ekleme / ortalama düşürme yok.
    aday_kapanis = aday.get("kapanis")
    for p in acik_pozisyonlar:
        if p.get("sembol") != aday["sembol"]:
            continue
        giris_fiyati = p.get("giris_fiyati")
        if (aday_kapanis is not None and giris_fiyati is not None
                and not pd.isna(aday_kapanis) and aday_kapanis < giris_fiyati):
            return (f"{aday['sembol']} zaten zararda açık bir pozisyon — "
                    f"zarardaki pozisyona ekleme/ortalama düşürme yapılamaz.")

    # 5) Stop olan hisseye 30 gün yeniden giriş yok.
    son_tarih = (son_stop_tarihleri or {}).get(aday["sembol"])
    bugun_tarih = aday.get("tarih")
    if son_tarih is not None and bugun_tarih is not None:
        fark_gun = (pd.Timestamp(bugun_tarih) - pd.Timestamp(son_tarih)).days
        if fark_gun < _STOP_SONRASI_BEKLEME_GUN:
            kalan = _STOP_SONRASI_BEKLEME_GUN - fark_gun
            return (f"{aday['sembol']} {fark_gun} gün önce stop oldu — "
                     f"{_STOP_SONRASI_BEKLEME_GUN} gün yeniden giriş yasağı "
                     f"sürüyor (kalan {kalan} gün).")

    return None


if __name__ == "__main__":
    # Ağ çağrısı / dosya okuma içermeyen kendi kendine kontrol.

    # ── (b) Trailing stop ASLA aşağı inmiyor mu? ───────────────────────────
    giris_fiyati = 100.0
    ilk_stop = 90.0  # 2.5*ATR ile geldiğini varsayalım (ATR_giris=4.0)
    poz = {
        "sembol": "TEST", "giris_tarihi": pd.Timestamp("2024-01-02"),
        "giris_fiyati": giris_fiyati, "ilk_stop": ilk_stop,
        "guncel_stop": ilk_stop, "en_yuksek_kapanis": giris_fiyati,
        "gun_sayisi": 0, "ust_uste_ema50_alti": 0,
    }
    # Fiyat önce yükselip +1R'yi geçiyor, trailing aktifleşiyor, sonra
    # SERT biçimde geri çekiliyor (ama stop'a değmeden) — guncel_stop bu
    # geri çekilme sırasında ASLA düşmemeli.
    kapanis_yolu = [105, 112, 120, 130, 122, 115, 118, 125]  # 122->115 geri çekilme
    atr_yolu = [4.0] * len(kapanis_yolu)
    stop_gecmisi = [poz["guncel_stop"]]
    for k, a in zip(kapanis_yolu, atr_yolu):
        bugun = pd.Series({"Close": k, "EMA50": 80.0, "ATR14": a})
        poz = trailing_guncelle(poz, bugun)
        stop_gecmisi.append(poz["guncel_stop"])

    for i in range(1, len(stop_gecmisi)):
        assert stop_gecmisi[i] >= stop_gecmisi[i - 1] - 1e-9, (
            f"Trailing stop aşağı indi! {stop_gecmisi}"
        )
    assert poz["guncel_stop"] > ilk_stop, "Kâr +1R'yi geçtikten sonra trailing hiç devreye girmedi"
    assert poz["guncel_stop"] >= ilk_stop

    # ── (c) Zaman stopu tam 15. günde tetikleniyor mu? ─────────────────────
    poz2 = {
        "sembol": "DURGUN", "giris_tarihi": pd.Timestamp("2024-01-02"),
        "giris_fiyati": 100.0, "ilk_stop": 90.0,
        "guncel_stop": 90.0, "en_yuksek_kapanis": 100.0,
        "gun_sayisi": 0, "ust_uste_ema50_alti": 0,
    }
    rejim_notr = {"rejim": "R1", "hedef_oran": 1.0}
    tetiklenen_gun = None
    for gun in range(1, 20):
        # Fiyat durgun (%1 getiri) — hem stop'a hem trend kırılımına
        # değmeyecek, yalnız zaman stopunun görünmesini istiyoruz.
        bugun = pd.Series({"Open": 100.5, "High": 101.5, "Low": 99.5,
                            "Close": 101.0, "EMA50": 95.0, "ATR14": 4.0})
        poz2 = trailing_guncelle(poz2, bugun)
        sonuc = cikis_kontrol(poz2, bugun, rejim_notr)
        if sonuc is not None:
            tetiklenen_gun = gun
            assert sonuc["neden"] == "zaman", f"Beklenmeyen çıkış nedeni: {sonuc}"
            break
    assert tetiklenen_gun == _ZAMAN_STOPU_GUN, (
        f"Zaman stopu {_ZAMAN_STOPU_GUN}. günde değil {tetiklenen_gun}. günde tetiklendi"
    )

    # ── İlk stop asla aşağı çekilmiyor (statik alan, modül tarafından hiç
    # değiştirilmiyor) — dolaylı kanıt: tüm senaryolarda ilk_stop sabit kaldı.
    assert poz["ilk_stop"] == ilk_stop
    assert poz2["ilk_stop"] == 90.0

    # ── İlk stop tetiklenmesi: Low ilk_stop'un altına inince 'stop' dönmeli.
    poz3 = {
        "sembol": "DUSUS", "giris_tarihi": pd.Timestamp("2024-01-02"),
        "giris_fiyati": 100.0, "ilk_stop": 90.0, "guncel_stop": 90.0,
        "en_yuksek_kapanis": 100.0, "gun_sayisi": 3, "ust_uste_ema50_alti": 0,
    }
    bugun_dusus = pd.Series({"Open": 91.0, "High": 92.0, "Low": 88.0, "Close": 89.0,
                              "EMA50": 95.0, "ATR14": 4.0})
    sonuc_stop = cikis_kontrol(poz3, bugun_dusus, rejim_notr)
    assert sonuc_stop is not None and sonuc_stop["neden"] == "stop", sonuc_stop
    assert sonuc_stop["fiyat"] == 90.0  # açılış (91) stop üstünde, gerçekleşme=stop seviyesi

    # Gap-down: açılış stop'un ALTINDA ise gerçekleşme açılıştan olmalı.
    bugun_gap = pd.Series({"Open": 85.0, "High": 86.0, "Low": 83.0, "Close": 84.0,
                            "EMA50": 95.0, "ATR14": 4.0})
    sonuc_gap = cikis_kontrol(poz3, bugun_gap, rejim_notr)
    assert sonuc_gap["neden"] == "stop" and sonuc_gap["fiyat"] == 85.0, sonuc_gap

    # ── Rejim R4 → her pozisyon kapanmalı.
    bugun_notr = pd.Series({"Open": 101.0, "High": 102.0, "Low": 100.5, "Close": 101.5,
                             "EMA50": 95.0, "ATR14": 4.0})
    sonuc_r4 = cikis_kontrol(poz3, bugun_notr, {"rejim": "R4", "hedef_oran": 0.0})
    assert sonuc_r4 is not None and sonuc_r4["neden"] == "rejim", sonuc_r4

    # R3 tek başına (bayrak olmadan) kapatmamalı — portföy bağlamı gerektirir.
    sonuc_r3_bayraksiz = cikis_kontrol(poz3, bugun_notr, {"rejim": "R3", "hedef_oran": 0.25})
    assert sonuc_r3_bayraksiz is None, sonuc_r3_bayraksiz
    sonuc_r3_bayrakli = cikis_kontrol(
        poz3, bugun_notr,
        {"rejim": "R3", "hedef_oran": 0.25, "r3_bu_pozisyonu_kapat": True},
    )
    assert sonuc_r3_bayrakli is not None and sonuc_r3_bayrakli["neden"] == "rejim"

    # ── portfoy_kisit_kontrol testleri ──────────────────────────────────
    sektor_map = {"AKBNK": "Bankacılık", "GARAN": "Bankacılık", "VAKBN": "Bankacılık",
                  "THYAO": "Havacılık/Ulaştırma"}

    acik_6 = [{"sembol": f"H{i}", "giris_fiyati": 10.0} for i in range(6)]
    red_maks = portfoy_kisit_kontrol({"sembol": "YENI", "kapanis": 10.0}, acik_6, 0, {}, sektor_map)
    assert red_maks is not None and "6" in red_maks

    red_gunluk = portfoy_kisit_kontrol({"sembol": "YENI", "kapanis": 10.0}, [], 2, {}, sektor_map)
    assert red_gunluk is not None

    acik_sektor = [{"sembol": "AKBNK", "giris_fiyati": 10.0}, {"sembol": "GARAN", "giris_fiyati": 10.0}]
    red_sektor = portfoy_kisit_kontrol({"sembol": "VAKBN", "kapanis": 10.0}, acik_sektor, 0, {}, sektor_map)
    assert red_sektor is not None and "Bankacılık" in red_sektor

    acik_zararda = [{"sembol": "THYAO", "giris_fiyati": 100.0}]
    red_zarar = portfoy_kisit_kontrol({"sembol": "THYAO", "kapanis": 90.0}, acik_zararda, 0, {}, sektor_map)
    assert red_zarar is not None

    kabul_kar = portfoy_kisit_kontrol({"sembol": "THYAO", "kapanis": 110.0}, acik_zararda, 0, {}, sektor_map)
    assert kabul_kar is None  # kârdaki pozisyona ekleme yasağı YOK (şart yalnız zarar için)

    son_stoplar = {"ASELS": pd.Timestamp("2024-01-01")}
    aday_erken = {"sembol": "ASELS", "kapanis": 50.0, "tarih": pd.Timestamp("2024-01-10")}
    red_cooldown = portfoy_kisit_kontrol(aday_erken, [], 0, son_stoplar, sektor_map)
    assert red_cooldown is not None and "30" in red_cooldown

    aday_gec = {"sembol": "ASELS", "kapanis": 50.0, "tarih": pd.Timestamp("2024-02-15")}
    kabul_cooldown = portfoy_kisit_kontrol(aday_gec, [], 0, son_stoplar, sektor_map)
    assert kabul_cooldown is None

    # Hiçbir kısıt ihlal edilmiyorsa None dönmeli.
    kabul_normal = portfoy_kisit_kontrol({"sembol": "SASA", "kapanis": 10.0, "tarih": pd.Timestamp("2024-01-10")},
                                          [], 0, {}, sektor_map)
    assert kabul_normal is None

    print("pozisyon.py kendi kendine kontrol: BAŞARILI")
    print("Trailing stop geçmişi (hiç düşmedi):", stop_gecmisi)
    print(f"Zaman stopu {tetiklenen_gun}. günde tetiklendi (beklenen {_ZAMAN_STOPU_GUN})")
