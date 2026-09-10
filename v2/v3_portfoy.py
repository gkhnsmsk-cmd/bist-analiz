# -*- coding: utf-8 -*-
"""
v2/v3_portfoy.py — Pusula V3 portföy kurulumu + rebalans/çıkış (§5, §6).

İki bağımsız sorumluluk, iki saf fonksiyon:
  - hedef_portfoy(): REBALANS gününde (her 20 işlem günü) çağrılır. v3_skor.
    skorla() çıktısına bakıp kimin satılacağını, kimin alınacağını ve tüm
    portföyün hedef ağırlıklarını (ters-volatilite, %5-%15 bant, sektör
    başına maks 3) hesaplar.
  - gunluk_kontrol(): HER GÜN çağrılır, yalnız İKİ kontrolü uygular: felaket
    stopu (-%25) ve rejim çıkışı (R3/R4). Trailing stop / zaman stopu / kâr
    hedefi YOKTUR — V2'nin başarısız olma nedeni tam olarak buydu (bkz.
    STRATEJI_V3.md §0, §6).

Ağ çağrısı YOK, dosya okuma YOK (sektör haritası hariç — repo kökündeki
sektor_haritasi.py'den, backtest.py'deki ile AYNI opsiyonel/hataya-dayanıklı
yöntemle okunur). Girdiler: veri.gostergeler() uygulanmış DataFrame'ler ve
v3_skor.skorla() çıktısı.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_V2_DIR = Path(__file__).resolve().parent
if str(_V2_DIR) not in sys.path:
    sys.path.insert(0, str(_V2_DIR))

# Repo kökündeki sektor_haritasi.py'yi kullanmayı dene; yoksa tüm semboller
# "Diğer" sayılır — sektör yoğunlaşma kısıtı yine çalışır, yalnız daha kaba
# biçimde (backtest.py'deki AYNI hataya-dayanıklı desen).
try:
    _REPO_KOKU = _V2_DIR.parent
    if str(_REPO_KOKU) not in sys.path:
        sys.path.insert(0, str(_REPO_KOKU))
    from sektor_haritasi import SEKTOR_HARITASI as _SEKTOR_HARITASI
except Exception:
    _SEKTOR_HARITASI = {}

_DIGER_SEKTOR = "Diğer / Sınıflandırılmamış"


def _sektor_bul(sembol: str) -> str:
    return _SEKTOR_HARITASI.get(sembol.strip().upper(), _DIGER_SEKTOR)


# ─────────────────────────────────────────────────────────────────────────
# §5 sabitleri.
# ─────────────────────────────────────────────────────────────────────────
_MAKS_POZISYON = 10        # en yüksek skorlu 10 hisse
_ILK_N_TAMPON = 20         # rebalansta "ilk 20"nin dışına düşünce SAT
_AGIRLIK_TAVANI = 0.15
_AGIRLIK_TABANI = 0.05
_MAKS_SEKTOR = 3
_AGIRLIK_TOLERANSI = 0.05  # sapma bundan küçükse dokunulmaz (turnover azaltma)

# §6 sabiti.
_FELAKET_STOP_ORANI = 0.25


def _bugun_satiri(df: pd.DataFrame | None, tarih: pd.Timestamp) -> pd.Series | None:
    """`tarih`e kadarki veriyi kısıtlar, tam o güne ait satırı döner (yoksa None)."""
    if df is None or df.empty:
        return None
    gecmis = df.loc[df.index <= tarih]
    if gecmis.empty or gecmis.index[-1] != tarih:
        return None
    return gecmis.iloc[-1]


def _agirlik_kliple(ham_agirliklar: dict[str, float], taban: float, tavan: float) -> dict[str, float]:
    """Ters-volatilite ağırlıklarını [taban, tavan] bandına sıkıştırır.

    YÖNTEM — sınırlı "water-filling": toplamı 1'e normalize edilmiş ham
    ağırlıklar sırayla taban/tavana çarpanlar; sınıra takılan isim orada
    SABİTLENİR, kalan bütçe geri kalan ("serbest") isimler arasında yine
    kendi aralarındaki oranla yeniden dağıtılır; sabitlenen kalmayana kadar
    tekrarlanır.

    ÖNEMLİ — sonuç toplamı HER ZAMAN 1'e ulaşmayabilir: elde ≤10 pozisyon
    varken taban toplamı (10×%5=%50) her zaman ulaşılabilir ama tavan
    toplamı (10×%15=%150) az sayıda (<7) isimle ulaşılamayabilir
    (7×%15=%105 > %100 ama 6×%15=%90 < %100). Bu durumda kalan pay basitçe
    NAKİTTE bırakılır — §5'in "az ama kaliteli aday varsa daha fazla nakit"
    ilkesiyle tutarlı, YAPAY olarak tavanı zorlayıp riski artırmak yerine.
    """
    if not ham_agirliklar:
        return {}
    toplam = sum(ham_agirliklar.values())
    if toplam <= 0:
        return {s: 0.0 for s in ham_agirliklar}

    kalan = {s: w / toplam for s, w in ham_agirliklar.items()}
    sabit: dict[str, float] = {}
    serbest = set(kalan.keys())

    for _ in range(len(kalan) + 2):
        if not serbest:
            break
        kalan_butce = 1.0 - sum(sabit.values())
        kalan_butce = max(kalan_butce, 0.0)
        serbest_ham_toplam = sum(kalan[s] for s in serbest)
        if serbest_ham_toplam <= 0:
            for s in serbest:
                sabit[s] = 0.0
            serbest = set()
            break

        degisti = False
        for s in list(serbest):
            aday_agirlik = kalan[s] / serbest_ham_toplam * kalan_butce
            if aday_agirlik > tavan + 1e-12:
                sabit[s] = tavan
                serbest.discard(s)
                degisti = True
            elif aday_agirlik < taban - 1e-12:
                sabit[s] = taban
                serbest.discard(s)
                degisti = True

        if not degisti:
            kalan_butce = max(1.0 - sum(sabit.values()), 0.0)
            serbest_ham_toplam = sum(kalan[s] for s in serbest)
            for s in serbest:
                sabit[s] = (kalan[s] / serbest_ham_toplam * kalan_butce) if serbest_ham_toplam > 0 else 0.0
            serbest = set()
            break

    # Güvenlik ağı: döngü sınırına takılıp serbest kalan olursa (teorik
    # olarak olmamalı) 0'a çekilir — sessizce yanlış/tutarsız bir ağırlık
    # üretmektense muhafazakâr davranmak tercih edildi.
    for s in serbest:
        sabit[s] = 0.0

    return sabit


def hedef_portfoy(siralama: list[dict], veriler: dict, tarih,
                   ozsermaye: float, hedef_oran: float,
                   mevcut: list[dict]) -> dict:
    """§5-§6: rebalans gününde hedef portföyü kurar.

    siralama: v3_skor.skorla() çıktısı (skora göre azalan, 'uygun' bayraklı).
    veriler: {sembol: DataFrame} — veri.gostergeler() uygulanmış.
    tarih: karar tarihi (rebalans günü kapanışı). SONRASINA bakılmaz.
    ozsermaye: GÜNCEL (mark-to-market) toplam özsermaye — hedef ağırlıklar
               bu tabana göre TL'ye çevrilecek (çağıran taraf hesaplar).
    hedef_oran: rejimin o günkü hedef yatırım oranı (v3_backtest.py'nin
                kademeli/anında mantığıyla ürettiği EFEKTİF oran — bu
                fonksiyon kademeleme YAPMAZ, doğrudan verileni kullanır).
    mevcut: [{'sembol','giris_fiyati', ...}] — hâlihazırda açık pozisyonlar.

    Döner: {'alinacak': [sembol, ...], 'satilacak': [{'sembol','neden'}, ...],
            'hedef_agirliklar': {sembol: agirlik}} — agirlik, TOPLAM
            özsermayeye oranla ifade edilir (hedef_oran zaten çarpılmıştır);
            çağıran taraf `agirlik * ozsermaye` ile TL hedefini bulur.
    """
    tarih = pd.Timestamp(tarih)
    mevcut = mevcut or []
    siralama_sirali = sorted(siralama or [], key=lambda s: s["skor"], reverse=True)
    ilk_n = {s["sembol"] for s in siralama_sirali[:_ILK_N_TAMPON]}
    skor_haritasi = {s["sembol"]: s for s in siralama_sirali}

    # ── 1) Mevcut pozisyonlardan SATILACAKLARI belirle. ────────────────
    satilacak: list[dict] = []
    tutulanlar: list[str] = []
    for p in mevcut:
        sembol = p["sembol"]
        satir = _bugun_satiri(veriler.get(sembol), tarih)
        if satir is None:
            # Veri yoksa güvenli taraf: elde tutmaya devam (satış emri
            # veremeyiz, fiyat bilgisi yok) — bir sonraki rebalansta tekrar
            # değerlendirilir.
            tutulanlar.append(sembol)
            continue

        kapanis = satir.get("Close")
        ma200 = satir.get("MA200")
        ma200_alti = (not pd.isna(kapanis)) and (not pd.isna(ma200)) and kapanis < ma200
        disarida = sembol not in ilk_n

        if ma200_alti:
            satilacak.append({"sembol": sembol, "neden": "Kapanış < MA200 (trend kaybı)."})
        elif disarida:
            satilacak.append({"sembol": sembol,
                               "neden": f"Skor sıralamasında ilk {_ILK_N_TAMPON}'nin dışına düştü."})
        else:
            tutulanlar.append(sembol)

    # ── 2) Boşalan yerleri, uygunluk filtresini geçen en yüksek skorlulardan
    #        (sektör kısıtına uyarak) doldur. ────────────────────────────
    bos_sayisi = max(0, _MAKS_POZISYON - len(tutulanlar))
    sektor_sayaci: dict[str, int] = {}
    for sembol in tutulanlar:
        sektor = _sektor_bul(sembol)
        sektor_sayaci[sektor] = sektor_sayaci.get(sektor, 0) + 1

    alinacak: list[str] = []
    if bos_sayisi > 0:
        tutulan_kume = set(tutulanlar)
        for aday in siralama_sirali:
            if len(alinacak) >= bos_sayisi:
                break
            sembol = aday["sembol"]
            if not aday.get("uygun", False):
                continue
            if sembol in tutulan_kume:
                continue
            sektor = _sektor_bul(sembol)
            if sektor_sayaci.get(sektor, 0) >= _MAKS_SEKTOR:
                continue
            alinacak.append(sembol)
            sektor_sayaci[sektor] = sektor_sayaci.get(sektor, 0) + 1

    secili = tutulanlar + alinacak

    # ── 3) Ters-volatilite ağırlıklandırma (1/ATR%), %5-%15 bandı. ─────
    ham_agirlik: dict[str, float] = {}
    for sembol in secili:
        satir = _bugun_satiri(veriler.get(sembol), tarih)
        if satir is None:
            continue
        kapanis = satir.get("Close")
        atr = satir.get("ATR14")
        if pd.isna(kapanis) or pd.isna(atr) or kapanis is None or atr is None or kapanis <= 0 or atr <= 0:
            continue
        atr_oran = atr / kapanis
        if atr_oran <= 0:
            continue
        ham_agirlik[sembol] = 1.0 / atr_oran

    klip_agirlik = _agirlik_kliple(ham_agirlik, _AGIRLIK_TABANI, _AGIRLIK_TAVANI)

    # ── 4) §4 madde-4 likidite kontrolü — NİHAİ/OTORİTER kontrol burada,
    #        GERÇEK ağırlık ve GERÇEK özsermaye ile (v3_skor'daki yalnız
    #        YAKLAŞIK bir ön-elemeydi). Aşan pozisyon, likiditenin izin
    #        verdiği tavana KIRPILIR (tamamen reddedilmez — elde zaten
    #        tutulan bir pozisyon aniden sıfırlanırsa gereksiz turnover
    #        yaratır); açığa çıkan pay basitçe nakitte kalır. ────────────
    hedef_agirliklar_invested: dict[str, float] = {}
    for sembol, agirlik in klip_agirlik.items():
        satir = _bugun_satiri(veriler.get(sembol), tarih)
        hacim_medyan = satir.get("HACIM_TL_MEDYAN20") if satir is not None else None
        agirlik_nihai = agirlik
        if ozsermaye and ozsermaye > 0 and hacim_medyan is not None and not pd.isna(hacim_medyan) and hacim_medyan > 0:
            likidite_tavan_agirlik = (0.01 * hacim_medyan) / ozsermaye
            agirlik_nihai = min(agirlik_nihai, likidite_tavan_agirlik)
        hedef_agirliklar_invested[sembol] = max(0.0, agirlik_nihai)

    hedef_oran_guvenli = 0.0 if (hedef_oran is None or pd.isna(hedef_oran)) else float(hedef_oran)
    hedef_agirliklar = {s: w * hedef_oran_guvenli for s, w in hedef_agirliklar_invested.items()}

    return {
        "alinacak": alinacak,
        "satilacak": satilacak,
        "hedef_agirliklar": hedef_agirliklar,
    }


def gunluk_kontrol(pozisyonlar: list[dict], bugun: dict, rejim: dict) -> list[dict]:
    """§6: rebalans DIŞI günlük kontrol — YALNIZ felaket stopu + rejim çıkışı.

    pozisyonlar: [{'sembol','giris_fiyati','adet', 'skor_giriste' (ops.)}].

    bugun: {'fiyatlar': {sembol: pd.Series (o günün OHLC+gösterge satırı)},
            'ozsermaye': float}
        YORUM KARARI: şartname §11 imzası `bugun: dict` olarak sabitliyor
        ama iç şemasını tanımlamıyor. R3 rejim çıkışının "hedef orana inene
        kadar" ifadesi ölçülebilmek için TOPLAM özsermaye (nakit dahil)
        bilgisi şart — yalnızca pozisyon fiyatlarıyla bu hesaplanamaz. Bu
        yüzden dict'in {'fiyatlar':..., 'ozsermaye':...} biçiminde olduğu
        varsayılıyor; v3_backtest.py bu şemayla üretir. `ozsermaye` verilmezse
        (veya NaN/≤0), R3 dalı GÜVENLİ biçimde hiçbir şey yapmaz (aşağı bkz.).

    rejim: rejim.rejim_hesapla() çıktısı ({'rejim','hedef_oran',...}).

    Döner: [{'sembol','neden': 'felaket_stop'|'rejim_cikisi','fiyat': float}]
    — kapatılması gereken pozisyonlar. Trailing/zaman/kâr-hedefi YOKTUR.
    """
    fiyatlar = (bugun or {}).get("fiyatlar", {}) or {}
    kapatilacaklar: list[dict] = []
    kapanan: set[str] = set()

    # 1) Felaket stopu: girişe göre -%25. Trading stopu DEĞİL, tek isim
    #    riskine karşı bir sigorta (bkz. STRATEJI_V3.md §6).
    for p in pozisyonlar or []:
        sembol = p.get("sembol")
        satir = fiyatlar.get(sembol)
        if satir is None:
            continue
        kapanis = satir.get("Close") if hasattr(satir, "get") else None
        giris = p.get("giris_fiyati")
        if kapanis is None or pd.isna(kapanis) or not giris or giris <= 0:
            continue
        getiri = (kapanis / giris) - 1.0
        if getiri <= -_FELAKET_STOP_ORANI:
            kapatilacaklar.append({"sembol": sembol, "neden": "felaket_stop", "fiyat": float(kapanis)})
            kapanan.add(sembol)

    # 2) Rejim çıkışı.
    rejim = rejim or {}
    rejim_adi = rejim.get("rejim")
    hedef_oran = rejim.get("hedef_oran")

    if rejim_adi == "R4":
        # R4: hedef %0 — kalan TÜM pozisyonlar kapanır (felaket stopuyla
        # zaten kapananlar hariç, çift emir üretilmesin diye).
        for p in pozisyonlar or []:
            sembol = p.get("sembol")
            if sembol in kapanan:
                continue
            satir = fiyatlar.get(sembol)
            if satir is None:
                continue
            kapanis = satir.get("Close") if hasattr(satir, "get") else None
            if kapanis is None or pd.isna(kapanis):
                continue
            kapatilacaklar.append({"sembol": sembol, "neden": "rejim_cikisi", "fiyat": float(kapanis)})
            kapanan.add(sembol)

    elif rejim_adi == "R3":
        ozsermaye = (bugun or {}).get("ozsermaye")
        if (ozsermaye is not None and not pd.isna(ozsermaye) and ozsermaye > 0
                and hedef_oran is not None and not pd.isna(hedef_oran)):
            kalanlar = [p for p in (pozisyonlar or [])
                        if p.get("sembol") not in kapanan and p.get("sembol") in fiyatlar]
            toplam_deger = sum(
                float(fiyatlar[p["sembol"]].get("Close", 0.0) or 0.0) * p.get("adet", 0.0)
                for p in kalanlar
            )
            hedef_tl = float(hedef_oran) * float(ozsermaye)

            # En düşük skorlu (girişteki skor; yoksa 0 varsayılır -> önce o
            # kapanır) sıralı — "liderliği en zayıf olan önce çıkar" ilkesi.
            kalanlar_sirali = sorted(kalanlar, key=lambda p: p.get("skor_giriste", p.get("skor", 0.0)))
            for p in kalanlar_sirali:
                if toplam_deger <= hedef_tl:
                    break
                sembol = p["sembol"]
                kapanis = float(fiyatlar[sembol].get("Close"))
                kapatilacaklar.append({"sembol": sembol, "neden": "rejim_cikisi", "fiyat": kapanis})
                kapanan.add(sembol)
                toplam_deger -= kapanis * p.get("adet", 0.0)
        # ozsermaye bilgisi yoksa: R3 dalı GÜVENLİ biçimde atlanır (hiçbir
        # şey kapatılmaz) — yanlış/rastgele bir sayıda pozisyon kapatmaktan
        # daha güvenli; bir sonraki günde bilgi varsa tekrar denenir.

    return kapatilacaklar


if __name__ == "__main__":
    # Ağ çağrısı / dosya okuma (sektör haritası hariç) içermeyen kendi
    # kendine kontrol.
    import numpy as np
    import sys as _sys
    from pathlib import Path as _Path

    _dir = _Path(__file__).resolve().parent
    if str(_dir) not in _sys.path:
        _sys.path.insert(0, str(_dir))
    import veri  # aynı dizindeki veri.py

    tarihler = pd.date_range("2023-01-02", periods=300, freq="B")
    tarih_son = tarihler[-1]

    def _df_kur(kapanis: np.ndarray, hacim: float = 5_000_000.0) -> pd.DataFrame:
        openf = kapanis - 0.05
        high = np.maximum(kapanis, openf) + 0.1
        low = np.minimum(kapanis, openf) - 0.1
        return pd.DataFrame({
            "Open": openf, "High": high, "Low": low, "Close": kapanis,
            "Volume": np.full(len(kapanis), hacim),
        }, index=tarihler)

    # ── _agirlik_kliple testi: taban/tavan bandı ve toplam <=1 -----------
    ham = {"A": 10.0, "B": 1.0, "C": 1.0, "D": 1.0}
    klip = _agirlik_kliple(ham, 0.05, 0.15)
    assert all(0.0 <= w <= 0.15 + 1e-9 for w in klip.values()), klip
    assert sum(klip.values()) <= 1.0 + 1e-6, klip
    assert abs(klip["A"] - 0.15) < 1e-6, klip  # en yüksek ham ağırlık tavana çarpmalı

    # 3 isimle (taban%5*3=%15, tavan%15*3=%45<%100) toplam 1'e ulaşamamalı
    # -> geri kalan nakitte kalmalı.
    ham3 = {"X": 1.0, "Y": 1.0, "Z": 1.0}
    klip3 = _agirlik_kliple(ham3, 0.05, 0.15)
    assert all(abs(w - 0.15) < 1e-6 for w in klip3.values()), klip3
    assert abs(sum(klip3.values()) - 0.45) < 1e-6, klip3

    # ── hedef_portfoy testi: rejim üzerinden basit senaryo ---------------
    rng = np.random.default_rng(1)
    veriler = {}
    for i in range(15):
        egim = 0.15 if i < 10 else -0.05  # ilk 10'u yükselişte (uygun), son 5 düşüşte
        seri = 50.0 + i + np.arange(300) * egim + rng.normal(0, 0.3, 300)
        seri = np.maximum(seri, 5.0)
        veriler[f"H{i}"] = veri.gostergeler(_df_kur(seri))

    siralama = []
    for i in range(15):
        satir = veriler[f"H{i}"].iloc[-1]
        uygun = i < 10  # yükselenler uygun, düşenler değil (basit varsayım)
        siralama.append({"sembol": f"H{i}", "skor": float(15 - i), "mom6": 0.1,
                          "mom12": 0.1, "vol": 0.2, "uygun": uygun,
                          "red_nedeni": None if uygun else "test"})

    sonuc = hedef_portfoy(siralama, veriler, tarih_son, ozsermaye=1_000_000.0,
                           hedef_oran=1.0, mevcut=[])
    assert len(sonuc["alinacak"]) <= _MAKS_POZISYON
    assert all(a in [f"H{i}" for i in range(10)] for a in sonuc["alinacak"]), sonuc["alinacak"]
    assert sonuc["satilacak"] == []  # mevcut boştu
    toplam_agirlik = sum(sonuc["hedef_agirliklar"].values())
    assert toplam_agirlik <= 1.0 + 1e-6, toplam_agirlik

    # Mevcutta MA200 altına düşmüş bir pozisyon varsa SATILMALI.
    mevcut = [{"sembol": "H14", "giris_fiyati": 60.0}]  # H14 düşüş serisinde -> MA200 altı
    sonuc2 = hedef_portfoy(siralama, veriler, tarih_son, ozsermaye=1_000_000.0,
                            hedef_oran=1.0, mevcut=mevcut)
    satilan_semboller = {s["sembol"] for s in sonuc2["satilacak"]}
    assert "H14" in satilan_semboller, sonuc2["satilacak"]

    # ── gunluk_kontrol testi: felaket stopu ------------------------------
    poz = [{"sembol": "TEST", "giris_fiyati": 100.0, "adet": 10.0, "skor_giriste": 5.0}]
    bugun_felaket = {"fiyatlar": {"TEST": pd.Series({"Close": 74.0})}, "ozsermaye": 1_000_000.0}
    rejim_r1 = {"rejim": "R1", "hedef_oran": 1.0}
    sonuc_felaket = gunluk_kontrol(poz, bugun_felaket, rejim_r1)
    assert len(sonuc_felaket) == 1 and sonuc_felaket[0]["neden"] == "felaket_stop", sonuc_felaket

    # -%24 (eşik altında) -> TETİKLENMEMELİ.
    bugun_esik_alti = {"fiyatlar": {"TEST": pd.Series({"Close": 76.5})}, "ozsermaye": 1_000_000.0}
    sonuc_esik_alti = gunluk_kontrol(poz, bugun_esik_alti, rejim_r1)
    assert sonuc_esik_alti == [], sonuc_esik_alti

    # R4 -> TÜM pozisyonlar kapanmalı.
    poz2 = [{"sembol": "A", "giris_fiyati": 50.0, "adet": 10.0, "skor_giriste": 3.0},
            {"sembol": "B", "giris_fiyati": 50.0, "adet": 10.0, "skor_giriste": 1.0}]
    bugun_r4 = {"fiyatlar": {"A": pd.Series({"Close": 55.0}), "B": pd.Series({"Close": 52.0})},
                "ozsermaye": 1_000_000.0}
    rejim_r4 = {"rejim": "R4", "hedef_oran": 0.0}
    sonuc_r4 = gunluk_kontrol(poz2, bugun_r4, rejim_r4)
    assert {s["sembol"] for s in sonuc_r4} == {"A", "B"}, sonuc_r4

    # R3 -> hedef orana inene kadar EN DÜŞÜK skorlu önce kapanmalı.
    poz3 = [{"sembol": "IYI", "giris_fiyati": 50.0, "adet": 100.0, "skor_giriste": 9.0},
            {"sembol": "KOTU", "giris_fiyati": 50.0, "adet": 100.0, "skor_giriste": 1.0}]
    # Her ikisi de 50 TL'de (2*100*50=10.000 TL toplam), özsermaye 20.000 varsayımıyla
    # mevcut oran %50; hedef_oran %30 -> bir pozisyon kapanmalı (KOTU, düşük skor).
    bugun_r3 = {"fiyatlar": {"IYI": pd.Series({"Close": 50.0}), "KOTU": pd.Series({"Close": 50.0})},
                "ozsermaye": 20_000.0}
    rejim_r3 = {"rejim": "R3", "hedef_oran": 0.30}
    sonuc_r3 = gunluk_kontrol(poz3, bugun_r3, rejim_r3)
    assert len(sonuc_r3) == 1 and sonuc_r3[0]["sembol"] == "KOTU", sonuc_r3

    # ozsermaye bilgisi eksikse R3 GÜVENLİ biçimde hiçbir şey yapmamalı.
    bugun_r3_eksik = {"fiyatlar": {"IYI": pd.Series({"Close": 50.0}), "KOTU": pd.Series({"Close": 50.0})}}
    sonuc_r3_eksik = gunluk_kontrol(poz3, bugun_r3_eksik, rejim_r3)
    assert sonuc_r3_eksik == [], sonuc_r3_eksik

    print("v3_portfoy.py kendi kendine kontrol: BAŞARILI")
    print("Ters-volatilite kırpma örneği (4 isim):", klip)
    print("Hedef portföy (uygun 10 isim):", sonuc["hedef_agirliklar"])
