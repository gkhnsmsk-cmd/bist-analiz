# -*- coding: utf-8 -*-
"""
sanal_yatirimci.py — Sanal Portföy (Paper Trading) Motoru
══════════════════════════════════════════════════════════════════════════════
GERÇEK PARA KULLANMAZ. Kullanıcının belirlediği sanal bir bütçeyle (örn.
1.000.000 TL), motorun kendi kararıyla otonom şekilde sanal hisse alıp sattığı
bir TEST/KANITLAMA ortamıdır. Gerçek bir aracı kuruma hiçbir emir gönderilmez.

TASARIM KARARLARI (kullanıcı tarafından onaylanmıştır):
  • Çalışma şekli : TAM OTOMATİK — GUNLUK_SANAL_YATIRIM.bat üzerinden Windows
                    Görev Zamanlayıcısı ile her gün (borsa kapanışından sonra)
                    çalıştırılması önerilir.
  • Sıklık        : HER GÜN. Takvim kısıtı YOKTUR (18.08.2026'da kaldırıldı).
                    gunluk_izle portföy değerini kaydeder; gunluk_karar ise
                    her çalıştırmada karar verir ama yalnızca GEREKÇE VARSA
                    işlem yapar. Bir hissenin ne kadar elde tutulacağına
                    takvim değil hissenin kendi durumu karar verir.
  • Pozisyon kuralı: PUAN AĞIRLIKLI, maksimum %30 tek hisse, HER ZAMAN TAM
                    YATIRIMLI (nakit tutmaz). Bu kullanıcının bilinçli olarak
                    seçtiği daha agresif bir kuraldır: piyasa zayıfken bile
                    portföy dolu tutulur. Bu riski hafifletmek için:
                      1) Puanlar piyasa rejimi düzeltmesini içerir
                         (analiz_motoru.piyasa_rejimi) — riskli ortamda
                         skorlar düşer. NOT: Bu koruma eskiden SADECE
                         belgelenmişti ama fiilen ÇALIŞMIYORDU; hizli_puan
                         rejim parametresi almıyordu. Artık rejim
                         gunluk_karar/gunluk_izle'ye geçirilip
                         puanlara gerçekten uygulanıyor.
                      2) Zayıf piyasada bu kural devreye girdiğinde durum
                         raporda açıkça "zayıf piyasa uyarısı" ile belirtilir.
                    (Eskiden ikinci bir güvenlik filtresi olarak oruntu_motoru
                    kullanılıyordu; örüntü analizi tamamen kaldırıldığı için
                    bu filtre de kaldırıldı — bkz. OKU_BENI.txt.)

DÜRÜSTLÜK İLKESİ: Bu motor %10/ay hedefini TUTTURMAK için puanları veya
sinyalleri ASLA çarpıtmaz/zorlamaz. Hedef sadece bir performans ölçütüdür;
gerçekleşen getiri (pozitif ya da negatif) olduğu gibi raporlanır. Gerçekçi
olması için her alım-satımda sanal komisyon (KOMISYON_ORANI) düşülür — aksi
halde sonuçlar gerçek hayattan olduğundan iyimser çıkar.

Bu modül, KULLANICININ KENDİ ELLE GİRDİĞİ portföyü tutan portfoy_takip.py'den
TAMAMEN BAĞIMSIZDIR — ikisi karışmaz, ayrı JSON dosyalarında saklanır.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pandas as pd

import sektor_haritasi as sh

KLASOR = os.path.dirname(os.path.abspath(__file__))
SANAL_PORTFOY_DOSYASI = os.path.join(KLASOR, "sanal_portfoy.json")
SANAL_ISLEM_GECMISI_DOSYASI = os.path.join(KLASOR, "sanal_islem_gecmisi.json")
SANAL_DEGER_GECMISI_DOSYASI = os.path.join(KLASOR, "sanal_deger_gecmisi.json")

# ── Ayarlar (kullanıcı onaylı) ────────────────────────────────────────────────
VARSAYILAN_BUTCE = 1_000_000.0
HEDEF_AYLIK_YUZDE = 10.0
KOMISYON_ORANI = 0.0015           # binde 1,5 — gerçekçi aracı kurum komisyonu tahmini
# MIN_POZISYON, MAKS_TEK_HISSE_ORANI ile tutarlı olmak zorundadır:
# "tam yatırımlı" + "maks %30 tek hisse" kurallarının aynı anda sağlanabilmesi
# için en az ceil(1 / 0.30) = 4 pozisyon gerekir. 3 ve altında iki kural
# matematiksel olarak çakışır (bkz. _hedef_agirliklari_hesapla).
MIN_POZISYON = 4
# 5 pozisyon = yoğunlaşmış portföy (kullanıcı kararı, 23.08.2026).
# Sınav setinde N=5 endeks üstü %+2,62/ay verdi (N=10'da %+0,93) ama
# kazanan ay oranı %46'dan %39'a düştü — daha yüksek getiri, daha sert
# iniş çıkış. Bilinçli bir risk tercihidir.
MAKS_POZISYON = 5
MAKS_TEK_HISSE_ORANI = 0.30
PUAN_ALIM_ESIGI = 52.0            # analiz_motoru.karar_ver ile tutarlı (İZLE/TUT ve üstü)
PUAN_SATIM_ESIGI = 45.0           # bu puanın altına düşen mevcut pozisyon SATILIR
REBALANS_GUNU = 4                 # (ARTIK KULLANILMIYOR — bkz. aşağıdaki not)

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  TAKVİM KURALI KALDIRILDI (18.08.2026 — kullanıcı kararı)                ║
# ╠══════════════════════════════════════════════════════════════════════════╣
# ║  ESKİ DAVRANIŞ: Alım-satım SADECE Cuma günü yapılırdı (REBALANS_GUNU=4). ║
# ║  Ayrıca satış kararı SIRALAMAYA dayalıydı: "hedef portföyde artık yer    ║
# ║  almıyor (puan sıralamasında geride kaldı)". Bu iki kural birlikte iki    ║
# ║  soruna yol açıyordu:                                                     ║
# ║    1) Cuma dışında kötüleşen bir pozisyon günlerce elde kalıyordu         ║
# ║    2) Sıralama tabanlı satış, motoru her koşuda listeyi baştan kurmaya    ║
# ║       zorluyordu — 21 satış denemesinin 16'sı bu yüzden oluşmuştu         ║
# ║                                                                           ║
# ║  YENİ DAVRANIŞ: Motor HER GÜN çalışır ama yalnızca GEREKÇE VARSA işlem    ║
# ║  yapar. Bir hissenin ne kadar elde tutulacağına takvim değil, hissenin    ║
# ║  kendi durumu karar verir:                                                ║
# ║                                                                           ║
# ║    SAT  → puan < 45  VEYA  takip eden stop (trailing stop) tetiklendi     ║
# ║    AL   → boş yer var + puan >= 52                                        ║
# ║    TAKAS→ portföy doluysa, yeni aday en zayıf pozisyondan MARJ kadar iyi  ║
# ║                                                                           ║
# ║  SÜRTÜNMEYİ (churn) ÖNLEYEN MEKANİZMA — HİSTEREZİS:                      ║
# ║  Alım eşiği (52) ile satım eşiği (45) FARKLIDIR. 45-52 arasında           ║
# ║  dalgalanan bir hisse ne satılır ne yeniden alınır — elde kalır. Tutma    ║
# ║  süresi böylece motorun kendi kararıyla, hissenin gücüne göre oluşur:     ║
# ║  güçlü kalan hisse aylarca durur, bozulan hisse ertesi gün satılır.       ║
# ║  Takvime dayalı bir "minimum tutma süresi" BİLEREK konmamıştır —          ║
# ║  kullanıcı "ne kadar tutacağına kendisi karar versin" dedi.               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# Takip eden stop (trailing stop): pozisyonun giriş sonrası gördüğü EN YÜKSEK
# fiyattan bu kadar ATR aşağıda kapanırsa satılır. Kazananın koşmasına izin
# verir, kaybedeni keser — "ne kadar tutulacağı" kararının ikinci ayağı budur.
STOP_ATR_KATSAYISI = 2.5
# Portföy doluyken bir pozisyonu yenisiyle değiştirmek için gereken PUAN FARKI.
# Küçük puan oynamalarının gereksiz alım-satım üretmesini engeller.
DEGISIM_MARJI = 8.0
# Seçim skoru (CMF) için takas marjı. CMF tipik olarak -0,4 ile +0,3
# arasında oynar; 0,10 fark anlamlı bir birikim farkıdır.
SECIM_DEGISIM_MARJI = 0.10
# Bu tutarın altındaki nakitle işlem açılmaz (komisyon anlamsız hale gelir).
MIN_ISLEM_TUTARI = 1000.0
# STOP ile çıkılan bir hisseye kaç gün yeniden girilmez.
# ═══════════════════════════════════════════════════════════════════════════
# NEDEN VAR: Testte üç ardışık koşu çalıştırıldığında gerçekten şu oluştu —
# AKSEN takip eden stop ile satıldı, ERTESİ KOŞUDA "puanı 56, alım eşiğini
# geçiyor" diye AYNI FİYATTAN geri alındı. Stop bir riski kesmek içindir;
# ertesi gün aynı yere geri girilirse hiçbir risk kesilmemiş, sadece iki kez
# komisyon ödenmiş olur. Puanla satılanlarda bu sorun yoktur (histerezis
# gereği puanın 45'ten 52'ye çıkması gerekir), o yüzden kural SADECE stop
# çıkışlarına uygulanır.
# Bekleme süresi dolmadan da girilebilir: puan, çıkış anındakinden
# DEGISIM_MARJI kadar YÜKSELMİŞSE hisse gerçekten değişmiş demektir.
# ═══════════════════════════════════════════════════════════════════════════
YENIDEN_GIRIS_BEKLEME_GUNU = 10


# ─────────────────────────────────────────────────────────────────────────────
# JSON depolama
# ─────────────────────────────────────────────────────────────────────────────
def _oku(dosya, varsayilan):
    if not os.path.exists(dosya):
        return varsayilan
    try:
        with open(dosya, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return varsayilan


def _yaz(dosya, veri):
    with open(dosya, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)


def baslat_veya_getir(baslangic_butce: float = VARSAYILAN_BUTCE,
                       hedef_aylik_yuzde: float = HEDEF_AYLIK_YUZDE) -> dict:
    """Sanal portföy ilk kez kuruluyorsa başlatır; zaten varsa OLDUĞU GİBİ
    döner (üzerine yazmaz)."""
    mevcut = _oku(SANAL_PORTFOY_DOSYASI, None)
    if mevcut is not None:
        return mevcut
    portfoy = {
        "baslangic_butce": baslangic_butce,
        "baslangic_tarihi": dt.date.today().isoformat(),
        "hedef_aylik_yuzde": hedef_aylik_yuzde,
        "nakit": baslangic_butce,
        "pozisyonlar": [],   # [{"sembol","adet","maliyet","eklenme_tarihi"}]
        "son_rebalans_tarihi": None,
        "aktif": True,       # False ise: otomatik script (GUNLUK_SANAL_YATIRIM.bat)
                             # HİÇBİR işlem/izleme yapmadan çıkar — motor duraklatılmış demektir.
    }
    _yaz(SANAL_PORTFOY_DOSYASI, portfoy)
    return portfoy


# ─────────────────────────────────────────────────────────────────────────────
# Kullanıcı kontrolü: aç/kapat, hedef güncelleme, manuel düzenleme
# ─────────────────────────────────────────────────────────────────────────────
def motor_aktif_mi() -> bool:
    return bool(portfoy_getir().get("aktif", True))


def motoru_ac():
    """Otomatik motoru devreye alır. GUNLUK_SANAL_YATIRIM.bat bir dahaki
    çalıştığında normal şekilde izleme/rebalans yapmaya devam eder."""
    portfoy = portfoy_getir()
    portfoy["aktif"] = True
    _yaz(SANAL_PORTFOY_DOSYASI, portfoy)
    return portfoy


def motoru_kapat():
    """Otomatik motoru DURAKLATIR. Kapalıyken GUNLUK_SANAL_YATIRIM.bat hiçbir
    izleme/alım-satım yapmaz (script hemen çıkar) — mevcut pozisyonlar ve
    geçmiş olduğu gibi kalır, siz tekrar açana kadar hiçbir şey değişmez.
    Uygulama içindeki manuel butonlar (Bugünün İzlemesi / Rebalansı Zorla
    Çalıştır) motor kapalıyken de elle kullanılabilir — bu bir kısıtlama
    değil, sadece OTOMATİK çalışmayı durdurur."""
    portfoy = portfoy_getir()
    portfoy["aktif"] = False
    _yaz(SANAL_PORTFOY_DOSYASI, portfoy)
    return portfoy


def hedefi_guncelle(yeni_hedef_aylik_yuzde: float):
    """Portföyü, pozisyonları ve işlem geçmişini SİLMEDEN sadece hedef aylık
    getiri yüzdesini günceller. Bu bir performans ölçütü değişikliğidir,
    portföyün kendisini etkilemez."""
    portfoy = portfoy_getir()
    portfoy["hedef_aylik_yuzde"] = float(yeni_hedef_aylik_yuzde)
    _yaz(SANAL_PORTFOY_DOSYASI, portfoy)
    return portfoy


def manuel_duzenle(pozisyon_satirlari: list, yeni_nakit: float | None = None):
    """Kullanıcının doğrudan müdahalesi: pozisyon tablosunu (hisse/adet/
    maliyet) ve/veya nakit miktarını elle düzenlemenizi sağlar — örn. bir
    hisseyi elle satmak/eklemek, yanlış hesaplanan bir maliyeti düzeltmek,
    veya nakdi ayarlamak için. Bu bir 'motor kararı' DEĞİLDİR; şeffaflık için
    işlem geçmişine 'MANUEL DÜZENLEME' notu düşülür.

    pozisyon_satirlari: [{"Hisse": "THYAO", "Adet": 100, "Maliyet": 285.5}, ...]
    (Streamlit st.data_editor çıktısı formatına uyumludur.)
    """
    portfoy = portfoy_getir()
    temiz = []
    mevcut_tarihler = {p["sembol"]: p.get("eklenme_tarihi") for p in portfoy["pozisyonlar"]}
    simdi = dt.datetime.now().isoformat()
    for satir in pozisyon_satirlari:
        sembol = str(satir.get("Hisse") or satir.get("sembol") or "").strip().upper().replace(".IS", "")
        try:
            adet = float(satir.get("Adet") if satir.get("Adet") is not None else satir.get("adet", 0))
            maliyet = float(satir.get("Maliyet") if satir.get("Maliyet") is not None else satir.get("maliyet", 0))
        except (TypeError, ValueError):
            continue
        if not sembol or adet <= 0 or maliyet <= 0:
            continue
        temiz.append({"sembol": sembol, "adet": adet, "maliyet": maliyet,
                      "eklenme_tarihi": mevcut_tarihler.get(sembol, simdi)})

    portfoy["pozisyonlar"] = temiz
    if yeni_nakit is not None:
        portfoy["nakit"] = float(yeni_nakit)
    _yaz(SANAL_PORTFOY_DOSYASI, portfoy)
    _islem_kaydet({
        "tarih": dt.date.today().isoformat(), "sembol": "—", "yon": "MANUEL DÜZENLEME",
        "adet": None, "fiyat": None, "tutar": None, "komisyon": None,
        "gerekce": "Kullanıcı portföyü/nakti elle düzenledi (motor kararı değil).",
        "puan": None,
    })
    return portfoy


def pozisyonu_manuel_sat(sembol: str, satis_fiyati: float):
    """Tek bir pozisyonu HEMEN, elle (motorun haftalık rebalans döngüsünü
    beklemeden) sanal olarak satar. Komisyon uygulanır, nakde eklenir."""
    sembol = sembol.strip().upper().replace(".IS", "")
    portfoy = portfoy_getir()
    hedef = next((p for p in portfoy["pozisyonlar"] if p["sembol"] == sembol), None)
    if hedef is None:
        return None
    tutar = satis_fiyati * hedef["adet"]
    komisyon = tutar * KOMISYON_ORANI
    portfoy["nakit"] += tutar - komisyon
    portfoy["pozisyonlar"] = [p for p in portfoy["pozisyonlar"] if p["sembol"] != sembol]
    _yaz(SANAL_PORTFOY_DOSYASI, portfoy)
    kayit = {
        "tarih": dt.date.today().isoformat(), "sembol": sembol, "yon": "SAT (MANUEL)",
        "adet": round(hedef["adet"], 4), "fiyat": round(satis_fiyati, 2),
        "tutar": round(tutar, 2), "komisyon": round(komisyon, 2),
        "gerekce": "Kullanıcı bu pozisyonu elle, hemen sattı (motor kararını beklemeden).",
        "puan": None,
    }
    _islem_kaydet(kayit)
    return kayit


def sifirla(baslangic_butce: float = VARSAYILAN_BUTCE,
            hedef_aylik_yuzde: float = HEDEF_AYLIK_YUZDE) -> dict:
    """Sanal portföyü ve TÜM geçmişini (işlem + değer eğrisi) SİLİP baştan
    başlatır. GERİ ALINAMAZ — arayüzde ayrı bir onay adımı gerektirmelidir."""
    for dosya in (SANAL_PORTFOY_DOSYASI, SANAL_ISLEM_GECMISI_DOSYASI, SANAL_DEGER_GECMISI_DOSYASI):
        if os.path.exists(dosya):
            os.remove(dosya)
    return baslat_veya_getir(baslangic_butce, hedef_aylik_yuzde)


def portfoy_getir() -> dict:
    return baslat_veya_getir()


def islem_gecmisi() -> list:
    return _oku(SANAL_ISLEM_GECMISI_DOSYASI, [])


def _son_kapanis(df) -> float | None:
    """Bir OHLCV DataFrame'inden GEÇERLİ son kapanış fiyatını döndürür.

    Puanlama motorundan tamamen BAĞIMSIZDIR — satış yapabilmek için puana
    değil yalnızca fiyata ihtiyaç vardır (bkz. haftalik_rebalans içindeki
    'askıda kalan satışlar' düzeltme notu). Son satır NaN ise geriye doğru
    ilk geçerli değeri arar; hiçbir geçerli değer yoksa None döner.
    """
    try:
        if df is None or len(df) == 0 or "Close" not in getattr(df, "columns", []):
            return None
        seri = pd.to_numeric(df["Close"], errors="coerce").dropna()
        seri = seri[(seri > 0) & (seri < float("inf"))]
        if len(seri) == 0:
            return None
        return float(seri.iloc[-1])
    except Exception:
        return None


def askidaki_satislari_bul() -> list:
    """Motorun BU SON KOŞUDA satmak istediği ama fiyatı bulunamadığı için
    satamadığı pozisyonlar.

    ÖNEMLİ DEĞİŞİKLİK (18.08.2026): Bu fonksiyon eskiden TÜM işlem geçmişini
    tarayıp "SAT (BAŞARISIZ)" kaydı olan her sembolü askıda sayıyordu. Kayıt
    ancak başarılı bir satışla temizlendiği için, motor bir hisseyi artık
    satmak İSTEMESE bile (örn. puanı yükseldi, tutmaya karar verdi) uyarı
    sonsuza kadar tekrarlanıyordu. Gerçek örnek: TUPRS puanı 76'ya çıkıp
    motorun bilinçli olarak TUTTUĞU bir pozisyon olmasına rağmen her koşuda
    "günlerdir elde kalmış" diye uyarı basılıyordu.

    Artık liste gunluk_karar() tarafından her koşuda sıfırdan yazılır; burada
    sadece okunur. Yanlış alarm üretmez.
    """
    portfoy = portfoy_getir()
    mevcut = {p["sembol"] for p in portfoy["pozisyonlar"]}
    askida = portfoy.get("askida_satislar")
    if askida is None:
        # Motor bu sürümle henüz hiç çalışmadı — bilinen bir şey yok.
        return []
    gecmis = islem_gecmisi()
    sonuc = []
    for sembol in askida:
        if sembol not in mevcut:
            continue                      # bu arada satılmış
        denemeler = [k for k in gecmis
                     if k.get("sembol") == sembol
                     and "BAŞARISIZ" in str(k.get("yon", ""))]
        sonuc.append({
            "sembol": sembol,
            "deneme": len(denemeler),
            "ilk_tarih": min((k["tarih"] for k in denemeler), default="—"),
            "son_tarih": max((k["tarih"] for k in denemeler), default="—"),
            "gerekce": denemeler[-1].get("gerekce", "") if denemeler else "",
        })
    return sonuc


def _islem_kaydet(kayit: dict):
    gecmis = islem_gecmisi()
    gecmis.append(kayit)
    _yaz(SANAL_ISLEM_GECMISI_DOSYASI, gecmis)


# ─────────────────────────────────────────────────────────────────────────────
# Değer/performans hesapları
# ─────────────────────────────────────────────────────────────────────────────
def portfoy_degeri(guncel_fiyatlar: dict) -> dict:
    """Nakit + pozisyon değerleri toplamı. Sahte/iyimser bir kâr hesabı
    yapmaz — sadece o anki toplam sanal serveti raporlar.

    ══════════════════════════════════════════════════════════════════════════
    KRİTİK DÜZELTME (gerçek kayıtlarda tespit edildi):
    Eskiden fiyatı çözülemeyen bir pozisyon toplama HİÇ KATILMIYORDU — yani
    sessizce "0 TL" sayılıyordu. Kullanıcının gerçek sanal portföyünde fiyatı
    çözülemeyen 5 pozisyon (KCAER, ISGYO, AEFES, TUPRS, EREGL) portföyün
    %41,5'ini oluşturuyordu ve bu yüzden performans eğrisi 1.000.000 TL'den
    737.827 TL'ye "düşmüş" görünüyordu (-%26). Bu GERÇEK bir zarar değil,
    ÖLÇÜM HATASIYDI.

    Artık fiyat şu sırayla çözülür:
        1) bugünkü güncel fiyat
        2) pozisyonda saklanan EN SON GEÇERLİ fiyat (son_fiyat)
        3) alış maliyeti (son çare — "değişmemiş varsay")
    Hangi kaynağın kullanıldığı pozisyon bazında raporlanır ve toplam değerin
    yüzde kaçının tahmini olduğu 'tahmini_deger_yuzde' ile açıkça bildirilir;
    böylece rakam gizlenmez ama uydurma bir çöküş de üretilmez.
    """
    portfoy = portfoy_getir()
    pozisyonlar_detay = []
    yatirilan_deger = 0.0
    tahmini_deger = 0.0          # fiyatı bugünden GELMEYEN pozisyonların değeri
    fiyatsiz_semboller = []
    guncellendi = False

    for p in portfoy["pozisyonlar"]:
        fiyat = guncel_fiyatlar.get(p["sembol"])
        # ÖNEMLİ: vk.canli_fiyat_cek() tüm kaynaklar başarısız olduğunda
        # float('nan') döndürür. NaN, "is not None" kontrolünü GEÇER ve
        # toplama karıştığında portföyün TAMAMINI nan yapar. Bu yüzden
        # geçersiz (NaN/sonsuz/sıfır-altı) fiyatlar burada elenir.
        if fiyat is not None and (fiyat != fiyat or fiyat <= 0 or fiyat in (float("inf"), float("-inf"))):
            fiyat = None

        if fiyat is not None:
            kaynak = "güncel"
            # En son geçerli fiyatı pozisyona yaz — bir sonraki sefer fiyat
            # alınamazsa 0 yerine bu kullanılır.
            if p.get("son_fiyat") != fiyat:
                p["son_fiyat"] = float(fiyat)
                guncellendi = True
        else:
            son = p.get("son_fiyat")
            if son is not None and son == son and son > 0:
                fiyat, kaynak = float(son), "son bilinen"
            else:
                fiyat, kaynak = float(p["maliyet"]), "maliyet"
            fiyatsiz_semboller.append(p["sembol"])

        deger = fiyat * p["adet"]
        pozisyonlar_detay.append({
            "Hisse": p["sembol"], "Adet": round(p["adet"], 4),
            "Maliyet": round(p["maliyet"], 2),
            "Güncel Fiyat": round(fiyat, 2),
            "Fiyat Kaynağı": kaynak,
            "Güncel Değer": round(deger, 2),
            "Kâr/Zarar %": round(100 * (fiyat / p["maliyet"] - 1), 2) if p["maliyet"] else None,
            "Sektör": sh.sektor_bul(p["sembol"]),
        })
        yatirilan_deger += deger
        if kaynak != "güncel":
            tahmini_deger += deger

    if guncellendi:
        try:
            _yaz(SANAL_PORTFOY_DOSYASI, portfoy)
        except Exception:
            pass                  # kayıt başarısız olsa da hesap doğru döner

    toplam = portfoy["nakit"] + yatirilan_deger
    baslangic = portfoy["baslangic_butce"]
    gun_sayisi = max((dt.date.today() - dt.date.fromisoformat(portfoy["baslangic_tarihi"])).days, 0)
    return {
        "nakit": round(portfoy["nakit"], 2),
        "yatirilan_deger": round(yatirilan_deger, 2),
        "toplam_deger": round(toplam, 2),
        "baslangic_butce": baslangic,
        "baslangic_tarihi": portfoy["baslangic_tarihi"],
        "toplam_getiri_yuzde": round(100 * (toplam / baslangic - 1), 2) if baslangic else 0.0,
        "gun_sayisi": gun_sayisi,
        "pozisyonlar": pozisyonlar_detay,
        "hedef_aylik_yuzde": portfoy["hedef_aylik_yuzde"],
        "son_rebalans_tarihi": portfoy.get("son_rebalans_tarihi"),
        # Şeffaflık alanları — arayüz bunları kullanıcıya göstermelidir.
        "fiyatsiz_semboller": fiyatsiz_semboller,
        "tahmini_deger_yuzde": round(100 * tahmini_deger / toplam, 1) if toplam else 0.0,
    }


def _endeks_seviyesi(endeks_df, tarih=None):
    """endeks_df'ten verilen tarihteki (yoksa ondan önceki son) kapanışı okur."""
    if endeks_df is None or len(endeks_df) == 0:
        return None
    try:
        seri = pd.to_numeric(endeks_df["Close"], errors="coerce").dropna()
        if len(seri) == 0:
            return None
        if tarih is None:
            return float(seri.iloc[-1])
        t = pd.Timestamp(str(tarih)[:10])
        oncesi = seri[seri.index <= t]
        return float(oncesi.iloc[-1]) if len(oncesi) else None
    except Exception:
        return None


def deger_kaydet(guncel_fiyatlar: dict, endeks_df=None):
    """Portföy değerini VE aynı günün endeks seviyesini kaydeder.

    ═══════════════════════════════════════════════════════════════════════════
    NEDEN ENDEKS DE KAYDEDİLİYOR (22.08.2026'da eklendi):
    Rapor "%-1,59 getiri" diyordu ama NEYE GÖRE olduğu yoktu. Elle bakınca
    BIST 100'ün aynı dönemde %+5,89 yükseldiği, yani motorun endeksin %7,49
    GERİSİNDE kaldığı görüldü. Mutlak getiri tek başına anlamsızdır: piyasa
    düşerken -%2 iyi bir sonuçtur, piyasa +%6 çıkarken -%2 kötüdür.
    Karşılaştırma olmadan hiçbir iyileştirmenin işe yarayıp yaramadığı
    ölçülemez. Bu yüzden asıl başarı ölçütü ENDEKS ÜSTÜ GETİRİDİR.
    ═══════════════════════════════════════════════════════════════════════════
    """
    durum = portfoy_degeri(guncel_fiyatlar)
    gecmis = _oku(SANAL_DEGER_GECMISI_DOSYASI, [])
    bugun = dt.date.today().isoformat()
    gecmis = [g for g in gecmis if g.get("tarih") != bugun]
    kayit = {"tarih": bugun, "toplam_deger": durum["toplam_deger"],
             "nakit": durum["nakit"]}
    e = _endeks_seviyesi(endeks_df, bugun)
    if e is not None:
        kayit["endeks"] = round(e, 2)
    gecmis.append(kayit)
    gecmis = gecmis[-2000:]
    if endeks_df is not None:
        gecmis = _endeks_geriye_doldur(gecmis, endeks_df)
    _yaz(SANAL_DEGER_GECMISI_DOSYASI, gecmis)


def _endeks_geriye_doldur(gecmis: list, endeks_df) -> list:
    """Endeks alanı olmayan ESKİ kayıtları doldurur.

    Endeks kaydı bu özellik eklendikten sonra başladığı için geçmiş günlerde
    boştur; o günlerin endeks seviyesi geçmiş veriden okunabilir, uydurmaya
    gerek yoktur."""
    for g in gecmis:
        if g.get("endeks") is None:
            e = _endeks_seviyesi(endeks_df, g.get("tarih"))
            if e is not None:
                g["endeks"] = round(e, 2)
    return gecmis


def deger_egrisi() -> pd.DataFrame:
    gecmis = _oku(SANAL_DEGER_GECMISI_DOSYASI, [])
    if not gecmis:
        return pd.DataFrame(columns=["tarih", "toplam_deger"])
    df = pd.DataFrame(gecmis)
    df["tarih"] = pd.to_datetime(df["tarih"])
    return df.sort_values("tarih")


def endeks_karsilastirmasi(endeks_df=None) -> dict:
    """Portföyün BAŞLANGIÇTAN BUGÜNE endekse göre nasıl gittiği.

    Dönüş: {"portfoy_yuzde", "endeks_yuzde", "endeks_ustu_yuzde",
            "endeks_bas", "endeks_son", "yeniyor_mu", "veri_var"}
    Endeks verisi yoksa veri_var=False döner — uydurma sayı üretmez.
    """
    bos = {"portfoy_yuzde": None, "endeks_yuzde": None, "endeks_ustu_yuzde": None,
           "endeks_bas": None, "endeks_son": None, "yeniyor_mu": None,
           "veri_var": False}
    portfoy = portfoy_getir()
    gecmis = _oku(SANAL_DEGER_GECMISI_DOSYASI, [])
    if endeks_df is not None and gecmis:
        gecmis = _endeks_geriye_doldur(gecmis, endeks_df)
        _yaz(SANAL_DEGER_GECMISI_DOSYASI, gecmis)
    if not gecmis:
        return bos

    gecmis = sorted(gecmis, key=lambda g: g.get("tarih", ""))
    son = gecmis[-1]
    bas_tarih = portfoy.get("baslangic_tarihi")

    # Endeksin BAŞLANGIÇ seviyesi: önce doğrudan endeks_df'ten (en doğrusu),
    # olmazsa kayıtlardaki ilk endeks değerinden.
    e_bas = _endeks_seviyesi(endeks_df, bas_tarih) if endeks_df is not None else None
    if e_bas is None:
        ilk = next((g for g in gecmis if g.get("endeks") is not None), None)
        e_bas = ilk.get("endeks") if ilk else None
    e_son = son.get("endeks")
    if e_son is None and endeks_df is not None:
        e_son = _endeks_seviyesi(endeks_df, son.get("tarih"))

    p_yuzde = round(100 * (son["toplam_deger"] / portfoy["baslangic_butce"] - 1), 2) \
        if portfoy.get("baslangic_butce") else None
    if e_bas is None or e_son is None or e_bas <= 0:
        return {**bos, "portfoy_yuzde": p_yuzde}

    e_yuzde = round(100 * (e_son / e_bas - 1), 2)
    fark = round((p_yuzde or 0.0) - e_yuzde, 2)
    return {"portfoy_yuzde": p_yuzde, "endeks_yuzde": e_yuzde,
            "endeks_ustu_yuzde": fark, "endeks_bas": round(e_bas, 2),
            "endeks_son": round(e_son, 2), "yeniyor_mu": fark > 0,
            "veri_var": True}


def performans_raporu(guncel_fiyatlar: dict, endeks_df=None) -> dict:
    """DÜRÜST performans karşılaştırması: hedefin gerektirdiği kümülatif
    getiri ile gerçekleşen kümülatif getiriyi kıyaslar. Hedef tutturulamamışsa
    bunu açıkça 'hedefi_yakaliyor_mu': False olarak bildirir — gizlemez."""
    durum = portfoy_degeri(guncel_fiyatlar)
    ay_sayisi = durum["gun_sayisi"] / 30.44 if durum["gun_sayisi"] else 0.0
    hedef_yuzde = durum["hedef_aylik_yuzde"]
    beklenen_kumulatif = ((1 + hedef_yuzde / 100) ** ay_sayisi - 1) * 100 if ay_sayisi > 0 else 0.0
    gerceklesen = durum["toplam_getiri_yuzde"]

    egri = deger_egrisi()
    maks_dusus_yuzde = None
    if len(egri) > 1:
        kumulatif_maks = egri["toplam_deger"].cummax()
        dusus = (egri["toplam_deger"] - kumulatif_maks) / kumulatif_maks * 100
        maks_dusus_yuzde = round(float(dusus.min()), 2)

    return {
        **durum,
        "ay_sayisi": round(ay_sayisi, 2),
        "hedefe_gore_beklenen_kumulatif_yuzde": round(beklenen_kumulatif, 2),
        "gerceklesen_kumulatif_yuzde": gerceklesen,
        "hedefi_yakaliyor_mu": (gerceklesen >= beklenen_kumulatif) if ay_sayisi > 0 else None,
        "maksimum_dusus_yuzde": maks_dusus_yuzde,
        "toplam_islem_sayisi": len(islem_gecmisi()),
        # ASIL BAŞARI ÖLÇÜTÜ: mutlak getiri değil, endeksi yenip yenmediği.
        "endeks": endeks_karsilastirmasi(endeks_df),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Günlük izleme (SADECE gözlem — hiçbir alım-satım yapmaz)
# ─────────────────────────────────────────────────────────────────────────────
def gunluk_izle(am, fiyat_getirici, endeks_df, guncel_fiyatlar: dict,
                 rejim: dict = None) -> dict:
    """Her iş günü çalıştırılabilir; portföy değerini değer eğrisine kaydeder
    ve mevcut pozisyonların güncel motor puanlarını hesaplar. HİÇBİR ALIM-SATIM
    YAPMAZ — sadece izler ve loglar. Gerçek alım-satım kararı yalnızca
    gunluk_karar() içinde verilir."""
    deger_kaydet(guncel_fiyatlar, endeks_df)
    portfoy = portfoy_getir()
    puanlar = {}
    for p in portfoy["pozisyonlar"]:
        sembol = p["sembol"]
        try:
            df = fiyat_getirici(sembol)
            if df is None or df.empty:
                puanlar[sembol] = None
                continue
            hp = am.hizli_puan(df, endeks_df, rejim=rejim)
            puanlar[sembol] = hp["Puan"]
        except Exception:
            puanlar[sembol] = None
    return {"tarih": dt.date.today().isoformat(), "puanlar": puanlar,
            "durum": portfoy_degeri(guncel_fiyatlar)}


# ─────────────────────────────────────────────────────────────────────────────
# Haftalık rebalans (ALIM-SATIM SADECE burada gerçekleşir)
# ─────────────────────────────────────────────────────────────────────────────
def _hedef_agirliklari_hesapla(adaylar: list) -> dict:
    """adaylar: [{'sembol','puan'}, ...], en az 1 eleman. Puan ağırlıklı hedef
    ağırlıkları hesaplar; hiçbir hisse MAKS_TEK_HISSE_ORANI'nı geçemez (aşan
    kısım diğerlerine orantılı olarak iteratif biçimde yeniden dağıtılır).

    MATEMATİKSEL SINIR: "her zaman tam yatırımlı" (ağırlık toplamı = 1.0) ve
    "maks %30 tek hisse" kuralları, hisse sayısı 1/0.30 = 3.33'ten (yani 4'ten)
    AZ olduğunda aynı anda sağlanamaz. Örneğin 3 hisseyle en iyi ihtimalle her
    biri %33,3 olur. Bu durumda tam yatırımlı kalma kuralı önceliklidir ve
    ağırlıklar EŞİT dağıtılır (üst sınır zorunlu olarak aşılır) — sessizce
    yanlış sonuç üretmek yerine kural çakışması bu şekilde çözülür.
    Not: MIN_POZISYON >= 4 olduğu sürece bu yola normalde hiç girilmez.
    """
    if not adaylar:
        return {}

    n = len(adaylar)
    if n * MAKS_TEK_HISSE_ORANI < 1.0 - 1e-9:
        # Üst sınır matematiksel olarak sağlanamıyor → eşit ağırlık, tam yatırım.
        return {a["sembol"]: 1.0 / n for a in adaylar}

    agirlik_ham = {a["sembol"]: max(a["puan"] - 40.0, 1.0) for a in adaylar}
    toplam = sum(agirlik_ham.values())
    agirlik = {s: v / toplam for s, v in agirlik_ham.items()}

    for _ in range(50):
        asan = {s: w for s, w in agirlik.items() if w > MAKS_TEK_HISSE_ORANI + 1e-9}
        if not asan:
            break
        fazla = sum(w - MAKS_TEK_HISSE_ORANI for w in asan.values())
        for s in asan:
            agirlik[s] = MAKS_TEK_HISSE_ORANI
        serbest = {s: w for s, w in agirlik.items() if s not in asan}
        serbest_toplam = sum(serbest.values())
        if serbest_toplam <= 0:
            break
        for s in serbest:
            agirlik[s] += fazla * (serbest[s] / serbest_toplam)

    # Yuvarlama/iterasyon artıklarına karşı son normalizasyon: toplam tam 1.0 olsun.
    toplam_son = sum(agirlik.values())
    if toplam_son > 0:
        agirlik = {s: w / toplam_son for s, w in agirlik.items()}
    return agirlik


def _atr_son(df) -> float | None:
    """Bir OHLCV DataFrame'inden son ATR(14) değerini döndürür (stop hesabı için).
    Hesaplanamazsa None döner — bu durumda stop kuralı UYGULANMAZ (sessizce
    yanlış bir stop üretip pozisyonu haksız yere satmaktansa kuralı atlarız)."""
    try:
        import analiz_motoru as _am
        a = _am.atr(df)
        v = float(a.iloc[-1])
        return v if (v == v and v > 0) else None
    except Exception:
        return None


def gunluk_karar(am, fiyat_getirici, endeks_df, tarama_evreni: list,
                 rejim: dict = None, zorla: bool = False) -> dict:
    """HER GÜN çalıştırılır; yalnızca GEREKÇE VARSA alım-satım yapar.

    Takvim kuralı YOKTUR (eski `haftalik_rebalans` sadece Cuma çalışırdı).
    Bir pozisyonun ne kadar elde tutulacağına takvim değil, hissenin kendi
    durumu karar verir — bkz. dosya başındaki büyük açıklama kutusu.

    KARAR KURALLARI
    ───────────────
    SAT   (biri yeterli):
          • Motor puanı PUAN_SATIM_ESIGI'nin (45) altına düştü
          • Takip eden stop tetiklendi: fiyat, giriş sonrası görülen EN YÜKSEK
            seviyeden STOP_ATR_KATSAYISI x ATR kadar aşağı indi
    AL:   Boş pozisyon yeri var + aday puanı PUAN_ALIM_ESIGI (52) ve üstü
    TAKAS: Portföy doluysa, yeni aday en zayıf pozisyondan DEGISIM_MARJI (8)
           puan daha iyiyse yer değiştirir

    NE YAPMAZ: Sıralamaya dayalı satış. Eski motor "puan sıralamasında geride
    kaldı" diye satıyordu; gerçek kayıtlarda bu, puanı 76 olan TUPRS'ı bile
    satmaya çalışmasına yol açmıştı. Güçlü bir hisse, daha güçlü bir hisse
    ortaya çıktı diye kötü hisse olmaz.

    Dönüş: {'calisti', 'islemler', 'tutulanlar', 'neden', 'zayif_piyasa_uyarisi'}
    """
    bugun = dt.date.today()
    portfoy = portfoy_getir()

    # ── 1) Tarama evrenini puanla ────────────────────────────────────────────
    puanlanan = []
    for sembol in tarama_evreni:
        try:
            df = fiyat_getirici(sembol)
            if df is None or df.empty:
                continue
            hp = am.hizli_puan(df, endeks_df, rejim=rejim)
            puan, fiyat_ham = hp["Puan"], hp["Fiyat"]
            if puan is None or fiyat_ham is None:
                continue
            if puan != puan or fiyat_ham != fiyat_ham or fiyat_ham <= 0:
                continue
            # SEÇİM SKORU (CMF + MA200) — alım sıralaması artık buna göre.
            # Genel puan SATIŞ kuralında kullanılmaya devam eder.
            try:
                sec = am.secim_skoru(df)
            except Exception:
                sec = {"skor": None, "uygun": False, "cmf": None}
            puanlanan.append({"sembol": sembol, "puan": float(puan),
                              "fiyat": float(fiyat_ham),
                              "secim_skoru": sec.get("skor"),
                              "cmf": sec.get("cmf"),
                              "secim_uygun": bool(sec.get("uygun"))})
        except Exception:
            continue

    if not puanlanan:
        return {"calisti": False, "islemler": [], "tutulanlar": [],
                "zayif_piyasa_uyarisi": False,
                "neden": "Tarama evreninden hiçbir hisse puanlanamadı "
                         "(veri kaynağı sorunlu olabilir)."}

    fiyat_haritasi = {a["sembol"]: a["fiyat"] for a in puanlanan}
    puan_haritasi = {a["sembol"]: a["puan"] for a in puanlanan}

    # ── 2) Portföydeki HER pozisyon için fiyat/puan/ATR'yi ayrıca çöz ────────
    # Pozisyon tarama evreninde olmayabilir (endeksten çıkmış, kapsam değişmiş).
    # Bu çözülmezse satış "fiyat yok" diye ertelenir ve pozisyon askıda kalır.
    atr_haritasi = {}
    for p in portfoy["pozisyonlar"]:
        sembol = p["sembol"]
        try:
            df = fiyat_getirici(sembol)
        except Exception:
            df = None
        if df is None or df.empty:
            continue
        if sembol not in fiyat_haritasi:
            f = _son_kapanis(df)
            if f is not None:
                fiyat_haritasi[sembol] = f
            try:
                hp = am.hizli_puan(df, endeks_df, rejim=rejim)
                if hp["Puan"] is not None and hp["Puan"] == hp["Puan"]:
                    puan_haritasi[sembol] = float(hp["Puan"])
            except Exception:
                pass          # puan yoksa da satış engellenmez
        a = _atr_son(df)
        if a is not None:
            atr_haritasi[sembol] = a

    islemler = []
    tutulanlar = []

    # ── 3) SAT: pozisyon bazlı kurallar ──────────────────────────────────────
    for p in list(portfoy["pozisyonlar"]):
        sembol = p["sembol"]
        fiyat = fiyat_haritasi.get(sembol)
        puan = puan_haritasi.get(sembol)

        # Takip eden stop için "giriş sonrası görülen en yüksek fiyat"ı güncelle.
        #
        # İLK KOŞU KORUMASI (grandfathering): Bu alan, takip eden stop
        # özelliğinden ÖNCE açılmış pozisyonlarda YOKTUR. Değeri maliyetten
        # başlatıp stop'u aynı koşuda değerlendirirsek, zarardaki TÜM eski
        # pozisyonlar TEK SEFERDE satılır — bu yeni bir piyasa sinyali değil,
        # sadece özelliğin devreye girme yan etkisidir. Testte gerçekten oluştu:
        # 13 pozisyonun 8'i ilk koşuda birden satıldı. Bu yüzden alan ilk kez
        # yazıldığında stop kuralı O KOŞUDA atlanır; bir sonraki çalıştırmadan
        # itibaren normal işler. Puan kuralı (< 45) bundan etkilenmez.
        stop_degerlendirilebilir = p.get("en_yuksek") is not None
        if fiyat is not None:
            onceki_zirve = p.get("en_yuksek") or p.get("maliyet") or fiyat
            p["en_yuksek"] = float(max(float(onceki_zirve), float(fiyat)))

        sat_gerekce = None
        if puan is not None and puan < PUAN_SATIM_ESIGI:
            # Puanı 1 ondalıkla yaz: 44,6 puan ":.0f" ile "45" olarak
            # yuvarlanıyordu ve log'a "(Puan: 45 < 45)" gibi kendisiyle
            # çelişen bir gerekçe düşüyordu. Karar doğruydu, gerekçe okunaksızdı.
            sat_gerekce = (f"motor puanı satım eşiğinin altına düştü "
                           f"(Puan: {puan:.1f} < {PUAN_SATIM_ESIGI:.0f})")
        elif (stop_degerlendirilebilir and fiyat is not None
              and sembol in atr_haritasi and p.get("en_yuksek")):
            stop = float(p["en_yuksek"]) - STOP_ATR_KATSAYISI * atr_haritasi[sembol]
            if fiyat < stop:
                sat_gerekce = (f"takip eden stop tetiklendi (fiyat {fiyat:.2f} < "
                               f"stop {stop:.2f}; zirve {p['en_yuksek']:.2f})")

        if not sat_gerekce:
            if puan is not None:
                tutulanlar.append({"sembol": sembol, "puan": puan})
            continue

        # SON ÇARE: satılacak ama fiyatı yoksa bir kez daha doğrudan dene
        if fiyat is None:
            try:
                fiyat = _son_kapanis(fiyat_getirici(sembol))
                if fiyat is not None:
                    fiyat_haritasi[sembol] = fiyat
            except Exception:
                fiyat = None

        if fiyat is None:
            islemler.append({
                "tarih": bugun.isoformat(), "sembol": sembol, "yon": "SAT (BAŞARISIZ)",
                "adet": round(p["adet"], 4), "fiyat": None, "tutar": None,
                "komisyon": None, "puan": puan,
                "gerekce": f"{sat_gerekce}, ancak güncel fiyat alınamadığı için satış ertelendi.",
            })
            continue

        tutar = fiyat * p["adet"]
        komisyon = tutar * KOMISYON_ORANI
        portfoy["nakit"] += tutar - komisyon
        islemler.append({
            "tarih": bugun.isoformat(), "sembol": sembol, "yon": "SAT",
            "adet": round(p["adet"], 4), "fiyat": round(fiyat, 2),
            "tutar": round(tutar, 2), "komisyon": round(komisyon, 2),
            "gerekce": sat_gerekce, "puan": puan,
            # Motorun bu pozisyonu KAÇ GÜN tuttuğu — tutma süresini takvim
            # değil motor belirlediği için bu sayı sonradan ölçülebilir olmalı.
            "tutma_gunu": _tutma_gunu(p),
            "stop_cikisi": sat_gerekce.startswith("takip eden stop"),
            "getiri_yuzde": round(100 * (fiyat / p["maliyet"] - 1), 2) if p.get("maliyet") else None,
        })
        if sat_gerekce.startswith("takip eden stop"):
            portfoy.setdefault("stop_cikislari", {})[sembol] = {
                "tarih": bugun.isoformat(),
                "puan": puan,
            }
        portfoy["pozisyonlar"] = [x for x in portfoy["pozisyonlar"] if x["sembol"] != sembol]

    # ── 4) AL / TAKAS ────────────────────────────────────────────────────────
    elde = {p["sembol"] for p in portfoy["pozisyonlar"]}
    # AYNI KOŞUDA SATILANI GERİ ALMA. Testte gerçekten oluşan hata: AKSEN stop
    # ile satıldı, birkaç satır sonra "puanı 56, alım eşiğini geçiyor" diye
    # yeniden alındı. Sonuç: portföy değişmedi ama iki kez komisyon ödendi.
    # Stop veya puan kuralıyla çıkılan bir hisseye aynı gün geri girmek o
    # kuralları anlamsız kılar.
    bugun_satilanlar = {i["sembol"] for i in islemler if i["yon"].startswith("SAT")}
    # ═══════════════════════════════════════════════════════════════════════
    # ALIM SEÇİMİ ARTIK CMF'YE GÖRE (23.08.2026)
    # ═══════════════════════════════════════════════════════════════════════
    # ESKİ: genel motor puanına göre sıralanıyordu. O puanın ileri getiriyle
    # korelasyonu 94.144 noktalık backtestte +0,012 — yani yön öngörmüyor.
    # YENİ: sıralama CMF (birikim) skoruna göre, sadece MA200 üstündeki
    # hisseler arasında. Ayrıntılı gerekçe: analiz_motoru.secim_skoru.
    #
    # PUAN EŞİĞİ NEDEN HÂLÂ VAR (ama düşürüldü): Alım eşiği olarak artık
    # PUAN_ALIM_ESIGI (52) değil PUAN_SATIM_ESIGI (45) kullanılıyor.
    # Sebebi mantıksal tutarlılık: 52 eşiği bizi öngörü gücü olmayan bir
    # ölçüte göre eleme yapmaya zorluyordu. Ama 45'in ALTINDAKİ bir hisseyi
    # almak da saçmadır — satış kuralı onu ertesi gün hemen satardı ve iki
    # kez komisyon ödenirdi. Yani 45, seçim ölçütü değil TUTARLILIK TABANIDIR.
    # ═══════════════════════════════════════════════════════════════════════
    adaylar = sorted((a for a in puanlanan
                      if a.get("secim_uygun")
                      and a.get("secim_skoru") is not None
                      and a["puan"] >= PUAN_SATIM_ESIGI
                      and a["sembol"] not in elde
                      and a["sembol"] not in bugun_satilanlar
                      and _giris_serbest_mi(portfoy, a["sembol"], a["puan"], bugun)),
                     key=lambda x: -x["secim_skoru"])
    zayif_piyasa = len(adaylar) == 0 and len(portfoy["pozisyonlar"]) < MIN_POZISYON

    # 4a-0) KAPASİTE AŞIMINI KOŞULSUZ DÜZELT (27.08.2026'da eklendi)
    # ═══════════════════════════════════════════════════════════════════════
    # NEDEN: MAKS_POZISYON 23.08.2026'da ~10'dan 5'e düşürüldü (daha
    # yoğunlaşmış strateji) ama o anda portföyde zaten MAKS_POZISYON'dan
    # fazla pozisyon vardı. Aşağıdaki fırsatçı TAKAS bloğu (4a) SADECE "daha
    # iyi bir aday var mı" sorusuna bakar (SECIM_DEGISIM_MARJI şartı) — bu
    # koşul bir gün sağlanmazsa fazlalık pozisyon o gün HİÇ satılmaz ve
    # gözlemlenen gerçek sonuç bu oldu: nakit haftalarca ~500.000 ₺'de
    # askıda kaldı, çünkü 4b'deki "boş yer" hesap (MAKS_POZISYON - mevcut
    # pozisyon sayısı) cap'in ÜZERİNDEYKEN hep negatif/sıfır çıkıyordu.
    # Kapasite aşımı, "daha iyi aday var mı" sorusundan BAĞIMSIZ, koşulsuz
    # olarak düzeltilmeli: cap'in üstündeyken en zayıf puanlı pozisyon(lar)
    # satılır (aday şartı aranmaz) — böylece portföy TEK koşuda cap'e iner
    # ve boşalan nakit hemen altındaki 4b bloğunda yeniden yatırılabilir.
    while len(portfoy["pozisyonlar"]) > MAKS_POZISYON:
        elde_puanli = [(p, puan_haritasi.get(p["sembol"]))
                       for p in portfoy["pozisyonlar"]]
        elde_puanli = [(p, s) for p, s in elde_puanli if s is not None]
        if not elde_puanli:
            break                    # puanı çözülemeyen pozisyon(lar) var — zorla satma
        zayif_p, zayif_puan = min(elde_puanli, key=lambda t: t[1])
        f = fiyat_haritasi.get(zayif_p["sembol"])
        if f is None:
            break
        tutar = f * zayif_p["adet"]
        komisyon = tutar * KOMISYON_ORANI
        portfoy["nakit"] += tutar - komisyon
        islemler.append({
            "tarih": bugun.isoformat(), "sembol": zayif_p["sembol"], "yon": "SAT",
            "adet": round(zayif_p["adet"], 4), "fiyat": round(f, 2),
            "tutar": round(tutar, 2), "komisyon": round(komisyon, 2),
            "puan": zayif_puan, "tutma_gunu": _tutma_gunu(zayif_p),
            "gerekce": (f"kapasite aşımı düzeltmesi: portföy MAKS_POZISYON "
                        f"({MAKS_POZISYON}) sınırının üzerindeydi, en zayıf "
                        f"puanlı pozisyon (Puan {zayif_puan:.0f}) satıldı"),
            "getiri_yuzde": round(100 * (f / zayif_p["maliyet"] - 1), 2) if zayif_p.get("maliyet") else None,
        })
        portfoy["pozisyonlar"] = [x for x in portfoy["pozisyonlar"]
                                  if x["sembol"] != zayif_p["sembol"]]

    # 4a) TAKAS — portföy doluyken belirgin şekilde daha iyi aday varsa
    while adaylar and len(portfoy["pozisyonlar"]) >= MAKS_POZISYON:
        elde_puanli = [(p, puan_haritasi.get(p["sembol"]))
                       for p in portfoy["pozisyonlar"]]
        elde_puanli = [(p, s) for p, s in elde_puanli if s is not None]
        if not elde_puanli:
            break
        zayif_p, zayif_puan = min(elde_puanli, key=lambda t: t[1])
        en_iyi = adaylar[0]
        # Takas kararı da SEÇİM SKORUNA göre olmalı — aksi halde alımı CMF
        # ile yapıp değişimi genel puanla yapardık, iki farklı ölçüt çakışırdı.
        _zayif_secim = next((a.get("secim_skoru") for a in puanlanan
                             if a["sembol"] == zayif_p["sembol"]), None)
        if _zayif_secim is None:
            break                    # mevcut pozisyonun skoru yok — takas etme
        if en_iyi["secim_skoru"] < _zayif_secim + SECIM_DEGISIM_MARJI:
            break                                  # fark yeterince büyük değil
        f = fiyat_haritasi.get(zayif_p["sembol"])
        if f is None:
            break
        tutar = f * zayif_p["adet"]
        komisyon = tutar * KOMISYON_ORANI
        portfoy["nakit"] += tutar - komisyon
        islemler.append({
            "tarih": bugun.isoformat(), "sembol": zayif_p["sembol"], "yon": "SAT",
            "adet": round(zayif_p["adet"], 4), "fiyat": round(f, 2),
            "tutar": round(tutar, 2), "komisyon": round(komisyon, 2),
            "puan": zayif_puan, "tutma_gunu": _tutma_gunu(zayif_p),
            "gerekce": (f"takas: {en_iyi['sembol']} birikim skoru "
                        f"{en_iyi['secim_skoru']:+.3f}, bu pozisyonunki "
                        f"{_zayif_secim:+.3f} (marj: {SECIM_DEGISIM_MARJI:.2f})"),
            "getiri_yuzde": round(100 * (f / zayif_p["maliyet"] - 1), 2) if zayif_p.get("maliyet") else None,
        })
        portfoy["pozisyonlar"] = [x for x in portfoy["pozisyonlar"]
                                  if x["sembol"] != zayif_p["sembol"]]
        break        # koşu başına en fazla BİR takas — aşırı işlem üretmemek için

    # 4b) AL — boş yerleri doldur
    bos_yer = MAKS_POZISYON - len(portfoy["pozisyonlar"])
    elde = {p["sembol"] for p in portfoy["pozisyonlar"]}
    bugun_satilanlar = {i["sembol"] for i in islemler if i["yon"].startswith("SAT")}
    alinacaklar = [a for a in adaylar if a["sembol"] not in elde
                   and a["sembol"] not in bugun_satilanlar][:max(bos_yer, 0)]

    if alinacaklar and portfoy["nakit"] > MIN_ISLEM_TUTARI:
        kalan_deger = sum(_gecerli_fiyat(fiyat_haritasi.get(p["sembol"])) * p["adet"]
                          for p in portfoy["pozisyonlar"])
        toplam_deger = portfoy["nakit"] + kalan_deger
        # Puan ağırlıklı dağıtım; tek hisse üst sınırı toplam değere göre uygulanır
        # AĞIRLIKLANDIRMA: EŞİT. Eskiden puan ağırlıklıydı ama seçim artık
        # CMF'ye göre ve CMF NEGATİF olabilir — negatif sayıyla ağırlık
        # hesaplamak anlamsız/tehlikelidir. Ayrıca CMF'nin büyüklüğü ile
        # beklenen getiri arasında doğrusal bir ilişki ölçmedik; sadece
        # SIRALAMASININ işe yaradığını biliyoruz. Sıralama bilgisini
        # ağırlığa çevirmek kanıtın ötesine geçmek olurdu.
        agirlik_ham = {a["sembol"]: 1.0 for a in alinacaklar}
        agirlik_top = sum(agirlik_ham.values())
        nakit_baslangic = portfoy["nakit"]
        for a in alinacaklar:
            sembol, fiyat = a["sembol"], a["fiyat"]
            if fiyat is None or fiyat != fiyat or fiyat <= 0:
                continue
            pay = agirlik_ham[sembol] / agirlik_top
            hedef_tutar = min(nakit_baslangic * pay, toplam_deger * MAKS_TEK_HISSE_ORANI)
            harcanacak = min(hedef_tutar, portfoy["nakit"])
            if harcanacak < MIN_ISLEM_TUTARI:
                continue
            komisyon = harcanacak * KOMISYON_ORANI
            adet_alinan = (harcanacak - komisyon) / fiyat
            if adet_alinan <= 0:
                continue
            portfoy["nakit"] -= harcanacak
            portfoy["pozisyonlar"].append({
                "sembol": sembol, "adet": adet_alinan, "maliyet": fiyat,
                "eklenme_tarihi": dt.datetime.now().isoformat(),
                "son_fiyat": fiyat, "en_yuksek": fiyat,
            })
            islemler.append({
                "tarih": bugun.isoformat(), "sembol": sembol, "yon": "AL",
                "adet": round(adet_alinan, 4), "fiyat": round(fiyat, 2),
                "tutar": round(harcanacak, 2), "komisyon": round(komisyon, 2),
                "puan": a["puan"],
                "gerekce": (f"birikim skoru en yüksek adaylardan "
                            f"(CMF {a.get('cmf'):+.3f}, MA200 üstünde, Puan {a['puan']:.0f})"),
            })

    # ASKIDA SATIŞ LİSTESİNİ BU KOŞUYA GÖRE YENİLE.
    # ═══════════════════════════════════════════════════════════════════════
    # ESKİ YÖNTEM YANLIŞ ALARM ÜRETİYORDU: askidaki_satislari_bul() işlem
    # geçmişini tarayıp "SAT (BAŞARISIZ)" kaydı olan sembolleri listeliyordu
    # ve bu kayıt ancak BAŞARILI bir satışla temizleniyordu. Yeni motor güçlü
    # hisseleri (TUPRS 76, KCAER 68, ISGYO 63) BİLEREK TUTUYOR — hiç satmıyor,
    # dolayısıyla eski kayıt hiç temizlenmiyor ve her koşuda "günlerdir elde
    # kalmışlar" uyarısı basılıyordu. Oysa o pozisyonlar sorun değil, motorun
    # kararı. Artık liste her koşuda SIFIRDAN yazılır: yalnızca BU KOŞUDA
    # satılmak istenip fiyatı bulunamayan semboller askıdadır.
    # ═══════════════════════════════════════════════════════════════════════
    portfoy["askida_satislar"] = sorted(
        {i["sembol"] for i in islemler if i["yon"] == "SAT (BAŞARISIZ)"})

    portfoy["son_rebalans_tarihi"] = bugun.isoformat()
    _yaz(SANAL_PORTFOY_DOSYASI, portfoy)
    for islem in islemler:
        _islem_kaydet(islem)
    deger_kaydet(fiyat_haritasi, endeks_df)

    if islemler:
        neden = f"{len(islemler)} işlem yapıldı (kural tabanlı, takvim kısıtı yok)."
    else:
        neden = ("Hiçbir işlem gerekmedi: elde tutulan pozisyonların hepsi satım "
                 "eşiğinin üzerinde ve stop tetiklenmedi; yeni aday da yok.")
    return {"calisti": True, "islemler": islemler, "tutulanlar": tutulanlar,
            "zayif_piyasa_uyarisi": zayif_piyasa, "neden": neden,
            # Geriye dönük uyumluluk (eski arayüz kodu bu alanı okuyor olabilir)
            "hedef_agirlik": {}}


def _giris_serbest_mi(portfoy: dict, sembol: str, puan: float, bugun) -> bool:
    """Stop ile çıkılmış bir hisseye yeniden girilebilir mi?

    İki koşuldan biri sağlanmalıdır:
      1) Çıkıştan bu yana YENIDEN_GIRIS_BEKLEME_GUNU kadar gün geçmiş, VEYA
      2) Puan, çıkış anındakinden DEGISIM_MARJI kadar yükselmiş (hisse gerçekten
         toparlanmış — bekleme süresini beklemeye gerek yok)
    Kayıt yoksa veya bozuksa serbesttir (kural asla alımı haksız yere bloke
    etmemeli; şüphede kalırsa izin verir)."""
    kayit = (portfoy.get("stop_cikislari") or {}).get(sembol)
    if not kayit:
        return True
    try:
        gecen = (bugun - dt.date.fromisoformat(str(kayit["tarih"])[:10])).days
    except Exception:
        return True
    if gecen >= YENIDEN_GIRIS_BEKLEME_GUNU:
        return True
    cikis_puani = kayit.get("puan")
    if cikis_puani is None:
        return False
    return float(puan) >= float(cikis_puani) + DEGISIM_MARJI


def _tutma_gunu(pozisyon: dict):
    """Pozisyonun kaç gündür elde tutulduğu. Tutma süresine motor karar
    verdiği için bu sayı ölçülebilir olmalıdır — sonradan 'kazançlı işlemleri
    ne kadar tuttuk, zararlıları ne kadar' diye analiz edilebilir."""
    try:
        t = pozisyon.get("eklenme_tarihi")
        if not t:
            return None
        return (dt.date.today() - dt.date.fromisoformat(str(t)[:10])).days
    except Exception:
        return None


def _gecerli_fiyat(deger) -> float:
    """NaN/None/negatif fiyatları 0'a çevirir.
    NOT: "x or 0" kalıbı NaN'ı YAKALAMAZ (NaN doğruluk değeri True'dur) ve tek
    bir NaN toplamın tamamını NaN yapardı; bu yüzden açıkça kontrol edilir."""
    if deger is None:
        return 0.0
    try:
        f = float(deger)
    except (TypeError, ValueError):
        return 0.0
    return f if (f == f and f > 0) else 0.0


def haftalik_rebalans(am, fiyat_getirici, endeks_df, tarama_evreni: list,
                      zorla: bool = False, rejim: dict = None) -> dict:
    """ESKİ AD — artık gunluk_karar()'a yönlendirir.

    Bu fonksiyon eskiden SADECE Cuma günü çalışan, sıralama tabanlı bir tam
    rebalans yapıyordu. Kullanıcı kararıyla takvim kısıtı kaldırıldı
    (18.08.2026). Adı, mevcut arayüz kodunu bozmamak için korunuyor;
    `zorla` parametresi de kabul edilir ama artık bir etkisi yoktur —
    motor zaten her çağrıldığında karar verir.
    """
    return gunluk_karar(am, fiyat_getirici, endeks_df, tarama_evreni,
                        rejim=rejim, zorla=zorla)
