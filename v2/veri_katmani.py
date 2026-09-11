# -*- coding: utf-8 -*-
"""
veri_katmani.py — BIST Analiz Platformu veri katmanı
Canlı fiyat için birincil kaynak: Mynet Finans (finans.mynet.com) — API anahtarı
gerektirmez, yfinance/borsapy'den daha hızlı ve güncel canlı fiyat verir.
Derinlemesine geçmiş (çok yıllı OHLCV, MA200 vb. göstergeler için) hâlâ
Yahoo Finance / borsapy / İş Yatırım zincirinden gelir; Mynet'in tarihsel
verileri sitede yalnızca kısa bir pencere (~son birkaç hafta) olarak açık
şekilde sunulduğundan, çok yıllı analiz için TEK BAŞINA yeterli değildir —
bu yüzden son çare (4.) kaynak olarak zincire eklenmiştir. Bu, gerçek veri
davranışına dayanan bilinçli bir mühendislik kararıdır (bkz. OKU_BENI.txt).
"""

import json
import re
import time
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import requests

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import borsapy as bp
except ImportError:
    bp = None

CACHE_DIR = Path(__file__).parent / ".veri_cache"
CACHE_DIR.mkdir(exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# ─────────────────────────────────────────────────────────────────────────────
# Yedek sembol listesi — çevrimiçi kaynakların HİÇBİRİ çalışmazsa kullanılır.
# ─────────────────────────────────────────────────────────────────────────────
# ÖNEMLİ GEÇMİŞ: Bu liste eskiden yalnızca ~106 likit hisse içeriyordu ve
# borsapy çalışmadığında "Tüm BIST" taraması sessizce 106 hisseye düşüyordu —
# kullanıcı 600 hisse taradığını sanırken küçük/orta ölçekli hisselerin tamamı
# kapsam dışı kalıyordu. Artık liste TÜM pazarları kapsayacak şekilde
# genişletildi ve çevrimiçi kaynaklarla BİRLEŞTİRİLİYOR (bkz. sembol_listesi),
# böylece kapsam asla bu listenin altına düşemez.
# NOT: Bu liste elle derlendiği için yeni halka arzları içermeyebilir; asıl
# kaynak her zaman önce çevrimiçi listelerdir. Listede olup artık işlem
# görmeyen bir kod zararsızdır — veri gelmeyince tarama onu atlar.
YEDEK_SEMBOLLER = [
    "A1CAP","ACSEL","ADEL","ADESE","ADGYO","AEFES","AFYON","AGESA","AGHOL","AGROT",
    "AGYO","AHGAZ","AHSGY","AKBNK","AKCNS","AKENR","AKFGY","AKFYE","AKGRT","AKMGY",
    "AKSA","AKSEN","AKSGY","AKSUE","AKYHO","ALARK","ALBRK","ALCAR","ALCTL","ALFAS",
    "ALGYO","ALKA","ALKIM","ALKLC","ALMAD","ALTINS1","ALVES","ANELE","ANGEN","ANHYT",
    "ANSGR","ARASE","ARCLK","ARDYZ","ARENA","ARSAN","ARTMS","ARZUM","ASELS","ASGYO",
    "ASTOR","ASUZU","ATAGY","ATAKP","ATATP","ATEKS","ATLAS","ATSYH","AVGYO","AVHOL",
    "AVOD","AVPGY","AVTUR","AYCES","AYDEM","AYEN","AYES","AYGAZ","AZTEK","BAGFS",
    "BAHKM","BAKAB","BALAT","BANVT","BARMA","BASCM","BASGZ","BAYRK","BEGYO","BERA",
    "BEYAZ","BFREN","BIENY","BIGCH","BIMAS","BINHO","BIOEN","BIZIM","BJKAS","BLCYT",
    "BMSCH","BMSTL","BNTAS","BOBET","BORLS","BORSK","BOSSA","BRISA","BRKO","BRKSN",
    "BRKVY","BRLSM","BRMEN","BRSAN","BRYAT","BSOKE","BTCIM","BUCIM","BURCE","BURVA",
    "BVSAN","BYDNR","CANTE","CASA","CATES","CCOLA","CELHA","CEMAS","CEMTS","CEOEM",
    "CIMSA","CLEBI","CMBTN","CMENT","CONSE","COSMO","CRDFA","CRFSA","CUSAN","CVKMD",
    "CWENE","DAGHL","DAGI","DAPGM","DARDL","DENGE","DERHL","DERIM","DESA","DESPC",
    "DEVA","DGATE","DGGYO","DGNMO","DIRIT","DITAS","DMSAS","DNISI","DOAS","DOBUR",
    "DOCO","DOFER","DOGUB","DOHOL","DOKTA","DURDO","DYOBY","DZGYO","EBEBK","ECILC",
    "ECZYT","EDATA","EDIP","EFORC","EGEEN","EGEPO","EGGUB","EGPRO","EGSER","EKGYO",
    "EKIZ","EKOS","EKSUN","ELITE","EMKEL","EMNIS","ENERY","ENJSA","ENKAI","ENSRI",
    "ENTRA","EPLAS","ERBOS","ERCB","EREGL","ERSU","ESCAR","ESCOM","ESEN","ETILR",
    "ETYAT","EUHOL","EUKYO","EUPWR","EUREN","EUYO","EYGYO","FADE","FENER","FLAP",
    "FMIZP","FONET","FORMT","FORTE","FRIGO","FROTO","FZLGY","GARAN","GARFA","GEDIK",
    "GEDZA","GENIL","GENTS","GEREL","GESAN","GIPTA","GLBMD","GLCVY","GLRYH","GLYHO",
    "GMTAS","GOKNR","GOLTS","GOODY","GOZDE","GRNYO","GRSEL","GRTRK","GSDDE","GSDHO",
    "GSRAY","GUBRF","GWIND","GZNMI","HALKB","HATEK","HATSN","HDFGS","HEDEF","HEKTS",
    "HKTM","HLGYO","HOROZ","HRKET","HTTBT","HUBVC","HUNER","HURGZ","ICBCT","ICUGS",
    "IDGYO","IEYHO","IHAAS","IHEVA","IHGZT","IHLAS","IHLGM","IHYAY","IMASM","INDES",
    "INFO","INGRM","INTEM","INVEO","INVES","IPEKE","ISATR","ISBIR","ISBTR","ISCTR",
    "ISDMR","ISFIN","ISGSY","ISGYO","ISKPL","ISMEN","ISSEN","ISYAT","IZENR","IZFAS",
    "IZINV","IZMDC","JANTS","KAPLM","KAREL","KARSN","KARTN","KARYE","KATMR","KAYSE",
    "KBORU","KCAER","KCHOL","KENT","KERVN","KERVT","KFEIN","KGYO","KIMMR","KLGYO",
    "KLKIM","KLMSN","KLNMA","KLRHO","KLSER","KLSYN","KMPUR","KNFRT","KOCMT","KONKA",
    "KONTR","KONYA","KOPOL","KORDS","KOTON","KOZAA","KOZAL","KRDMA","KRDMB","KRDMD",
    "KRGYO","KRONT","KRPLS","KRSTL","KRTEK","KRVGD","KSTUR","KTLEV","KTSKR","KUTPO",
    "KUYAS","KZBGY","KZGYO","LIDER","LIDFA","LILAK","LINK","LKMNH","LMKDC","LOGO",
    "LRSHO","LUKSK","MAALT","MACKO","MAGEN","MAKIM","MAKTK","MANAS","MARBL","MARKA",
    "MARTI","MAVI","MEDTR","MEGAP","MEGMT","MEKAG","MENDR","MEPET","MERCN","MERIT",
    "MERKO","METRO","METUR","MGROS","MHRGY","MIATK","MIPAZ","MMCAS","MNDRS","MNDTR",
    "MOBTL","MOGAN","MPARK","MRGYO","MRSHL","MSGYO","MTRKS","MTRYO","MZHLD","NATEN",
    "NETAS","NIBAS","NTGAZ","NTHOL","NUGYO","NUHCM","OBAMS","OBASE","ODAS","ODINE",
    "OFSYM","ONCSM","ORCAY","ORGE","ORMA","OSMEN","OSTIM","OTKAR","OTTO","OYAKC",
    "OYAYO","OYLUM","OZGYO","OZKGY","OZRDN","OZSUB","OZYSR","PAGYO","PAMEL","PAPIL",
    "PARSN","PASEU","PATEK","PCILT","PEGYO","PEKGY","PENGD","PENTA","PETKM","PETUN",
    "PGSUS","PINSU","PKART","PKENT","PLTUR","PNLSN","PNSUT","POLHO","POLTK","PRDGS",
    "PRKAB","PRKME","PRZMA","PSDTC","PSGYO","QUAGR","RALYH","RAYSG","REEDR","RGYAS",
    "RNPOL","RODRG","ROYAL","RTALB","RUBNS","RYGYO","RYSAS","SAFKR","SAHOL","SAMAT",
    "SANEL","SANFM","SANKO","SARKY","SASA","SAYAS","SDTTR","SEGMN","SEGYO","SEKFK",
    "SEKUR","SELEC","SELGD","SELVA","SEYKM","SILVR","SISE","SKBNK","SKTAS","SKYLP",
    "SKYMD","SMART","SMRTG","SNGYO","SNICA","SNKRN","SNPAM","SODSN","SOKE","SOKM",
    "SONME","SRVGY","SUMAS","SUNTK","SURGY","SUWEN","TABGD","TARKM","TATEN","TATGD",
    "TAVHL","TBORG","TCELL","TDGYO","TEKTU","TERA","TETMT","TEZOL","TGSAS","THYAO",
    "TKFEN","TKNSA","TLMAN","TMPOL","TMSN","TNZTP","TOASO","TRCAS","TRGYO","TRILC",
    "TSGYO","TSKB","TSPOR","TTKOM","TTRAK","TUCLK","TUKAS","TUPRS","TUREX","TURGG",
    "TURSG","UFUK","ULAS","ULKER","ULUFA","ULUSE","ULUUN","UNLU","USAK","UZERB",
    "VAKBN","VAKFN","VAKKO","VANGD","VBTYZ","VERTU","VERUS","VESBE","VESTL","VKGYO",
    "VKING","VRGYO","YAPRK","YATAS","YAYLA","YBTAS","YEOTK","YESIL","YGGYO","YGYO",
    "YIGIT","YKBNK","YKSLN","YONGA","YUNSA","YYAPI","YYLGD","ZEDUR","ZOREN","ZRGYO",
]


# Endeks bazlı kapsamlar için yedek listeler. TÜM listesi bunlar için
# KULLANILAMAZ — "BIST 30" seçen kullanıcıya 560 hisse döndürmek yanlış olur.
YEDEK_XU030 = [
    "AKBNK","ALARK","ARCLK","ASELS","ASTOR","BIMAS","BRSAN","CIMSA","EKGYO","ENKAI",
    "EREGL","FROTO","GARAN","GUBRF","HEKTS","ISCTR","KCHOL","KOZAL","KRDMD","MGROS",
    "ODAS","OYAKC","PETKM","PGSUS","SAHOL","SASA","SISE","TCELL","THYAO","TOASO",
    "TUPRS","YKBNK",
]

YEDEK_XU100 = sorted(set(YEDEK_XU030 + [
    "AEFES","AGHOL","AHGAZ","AKCNS","AKFGY","AKSA","AKSEN","ALBRK","ALFAS","ANSGR",
    "AYDEM","BAGFS","BERA","BIENY","BIOEN","BOBET","BRYAT","BUCIM","CANTE","CCOLA",
    "CVKMD","CWENE","DOAS","DOHOL","ECILC","ECZYT","EGEEN","ENERY","ENJSA","EUPWR",
    "FENER","GENIL","GESAN","GLYHO","GSDHO","GWIND","HALKB","IPEKE","ISDMR","ISGYO",
    "ISMEN","IZENR","KARSN","KAYSE","KCAER","KMPUR","KONTR","KONYA","KORDS","KOZAA",
    "KZBGY","MAVI","MIATK","MPARK","OTKAR","PENTA","QUAGR","SAYAS","SDTTR","SELEC",
    "SKBNK","SMRTG","SOKM","TABGD","TAVHL","TKFEN","TSKB","TTKOM","TTRAK","TUKAS",
    "TURSG","ULKER","VAKBN","VESBE","VESTL","YEOTK","YYLGD","ZOREN",
]))


def _disk_cache_oku(ad: str, max_yas_saat: float):
    f = CACHE_DIR / f"{ad}.json"
    if f.exists():
        yas = time.time() - f.stat().st_mtime
        if yas < max_yas_saat * 3600:
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


def _disk_cache_yaz(ad: str, veri):
    try:
        (CACHE_DIR / f"{ad}.json").write_text(
            json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Sembol listesi
# ─────────────────────────────────────────────────────────────────────────────
def _temizle_semboller(ham) -> list:
    """Ham sembol dizisini BIST hisse koduna indirger (geçersizleri atar)."""
    cikti = set()
    for s in ham or []:
        k = str(s).strip().upper().replace(".IS", "").replace(".E", "")
        if k.isalnum() and 3 <= len(k) <= 6 and not k.isdigit():
            cikti.add(k)
    return sorted(cikti)


def _semboller_borsapy(endeks: str) -> list:
    if bp is None:
        return []
    try:
        comps = bp.Index(endeks).components
        if comps is None:
            return []
        if isinstance(comps, pd.DataFrame):
            for kolon in ("symbol", "Symbol", "code", "Kod", "kod", "ticker"):
                if kolon in comps.columns:
                    return _temizle_semboller(comps[kolon].dropna())
            return _temizle_semboller(comps.iloc[:, 0].dropna())
        return _temizle_semboller(comps)
    except Exception:
        return []


def _semboller_isyatirim() -> list:
    """İş Yatırım'ın açık 'tüm hisseler' tablosu — TÜM pazarları kapsar."""
    url = ("https://www.isyatirim.com.tr/_layouts/15/IsYatirim.Website/Common/"
           "Data.aspx/HisseYuzeysel?hisse=&endeks=09")
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        veri = r.json().get("value") or []
        return _temizle_semboller(k.get("SENETADI") or k.get("HISSEKODU") for k in veri)
    except Exception:
        return []


def _semboller_kap() -> list:
    """KAP'ta işlem gören tüm şirketler (BIST'in resmî kaynağı)."""
    try:
        r = requests.get("https://www.kap.org.tr/tr/api/kap-company-list",
                         headers=UA, timeout=20)
        r.raise_for_status()
        veri = r.json() or []
        kodlar = []
        for k in veri:
            kod = k.get("stockCode") or k.get("ticker") or ""
            # KAP çok kodlu şirketlerde "AAA, BBB" biçiminde verebiliyor.
            kodlar.extend(str(kod).replace(";", ",").split(","))
        return _temizle_semboller(kodlar)
    except Exception:
        return []


def sembol_listesi(kapsam: str = "TUM", ayrinti: bool = False):
    """kapsam: 'TUM' | 'XU100' | 'XU030'.

    KAPSAM GARANTİSİ (önemli): 'TUM' için birden fazla kaynak denenir ve
    sonuçlar YEDEK LİSTEYLE BİRLEŞTİRİLİR. Böylece tek bir kaynak çökse bile
    tarama sessizce 100 hisseye düşemez — eskiden borsapy başarısız olunca
    tam olarak bu oluyordu ve kullanıcı küçük/orta ölçekli hisseleri hiç
    göremiyordu.

    ayrinti=True ise (liste, kaynak_metni) döndürür — arayüzde kaç hissenin
    nereden geldiğini göstermek için.
    """
    cache_adi = f"semboller_{kapsam}"
    endeks = {"TUM": "XUTUM", "XU100": "XU100", "XU030": "XU030"}[kapsam]

    kaynaklar = []
    birlesik = set()

    bp_liste = _semboller_borsapy(endeks)
    if len(bp_liste) >= 25:
        birlesik |= set(bp_liste)
        kaynaklar.append(f"borsapy:{len(bp_liste)}")

    # Endeks bazlı kapsamlarda (XU100/XU030) ek kaynak KULLANILMAZ; o listeler
    # tanımı gereği sabit bileşenlerdir, genişletmek yanlış olur.
    if kapsam == "TUM":
        for ad, fn in (("isyatirim", _semboller_isyatirim), ("kap", _semboller_kap)):
            try:
                ek = fn()
            except Exception:
                ek = []
            if len(ek) >= 100:
                birlesik |= set(ek)
                kaynaklar.append(f"{ad}:{len(ek)}")

        onceki = _disk_cache_oku(cache_adi, max_yas_saat=24 * 30) or []
        if len(onceki) >= 100:
            birlesik |= set(onceki)
            kaynaklar.append(f"önbellek:{len(onceki)}")

        birlesik |= set(YEDEK_SEMBOLLER)
        kaynaklar.append(f"yerleşik:{len(YEDEK_SEMBOLLER)}")

    if not birlesik:
        onceki = _disk_cache_oku(cache_adi, max_yas_saat=24 * 30)
        if onceki:
            birlesik = set(onceki)
            kaynaklar.append(f"önbellek:{len(onceki)}")
        else:
            # Kapsama UYGUN yedek: BIST 30 seçildiyse 30'luk liste kullanılır,
            # tüm BIST listesi DEĞİL (aksi halde "BIST 30" 560 hisse tarardı).
            yedek = {"XU030": YEDEK_XU030, "XU100": YEDEK_XU100}.get(
                kapsam, YEDEK_SEMBOLLER)
            birlesik = set(yedek)
            kaynaklar.append(f"yerleşik-{kapsam}:{len(yedek)}")

    liste = _temizle_semboller(birlesik)
    if len(liste) >= 25:
        _disk_cache_yaz(cache_adi, liste)
    if ayrinti:
        return liste, " + ".join(kaynaklar)
    return liste


# ─────────────────────────────────────────────────────────────────────────────
# Mynet Finans — canlı fiyat ve tarihsel veri
# ─────────────────────────────────────────────────────────────────────────────
_MYNET_AYLAR = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
    "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
}


def _mynet_sayi(s: str):
    """Mynet sayfalarında hem '133.7' (nokta ondalık) hem '2.674.908.118,00'
    (nokta binlik + virgül ondalık) formatı görülüyor; ikisini de doğru çözer."""
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except ValueError:
        return None


def _mynet_url(sembol: str) -> str:
    """Mynet, '{ticker}-{herhangi-bir-ek}/' biçimindeki URL'yi otomatik olarak
    doğru şirket sayfasına yönlendirir (sunucu tarafı ticker-önekli eşleşme);
    bu sayede tam URL slug'ını (şirket adını) önceden bilmeye gerek kalmaz."""
    return f"https://finans.mynet.com/borsa/hisseler/{sembol.strip().lower()}-x/"


def mynet_canli_ozet(sembol: str) -> dict:
    """Mynet hisse sayfasından canlı fiyat + günlük/yıllık istatistikleri +
    F/K, PD/DD, sektör bilgisini metin ayrıştırmasıyla çıkarır.
    Sayfa yapısı değişirse ilgili alan sessizce None döner (uygulama çökmez)."""
    sembol = sembol.strip().upper().replace(".IS", "")
    sonuc = {}
    try:
        r = requests.get(_mynet_url(sembol), headers=UA, timeout=15)
        r.raise_for_status()
        metin = r.text

        def bul(desen, gruptan=1):
            m = re.search(desen, metin, re.IGNORECASE)
            return _mynet_sayi(m.group(gruptan)) if m else None

        sonuc["son_fiyat"] = bul(rf"{re.escape(sembol)}\s+Son Değer:\s*([\d.,]+)")
        sonuc["acilis"] = bul(r"Açılış Fiyatı\s*([\d.,]+)")
        sonuc["gun_ici_dusuk"] = bul(r"Gün İçi En Düşük\s*([\d.,]+)")
        sonuc["gun_ici_yuksek"] = bul(r"Gün İçi En Yüksek\s*([\d.,]+)")
        sonuc["onceki_kapanis"] = bul(r"Önceki Kapanış Fiyatı\s*([\d.,]+)")
        sonuc["hacim_tl"] = bul(r"Günlük Hacim \(TL\)\s*([\d.,]+)")
        sonuc["yillik_dusuk"] = bul(r"Yıllık En Düşük\s*([\d.,]+)")
        sonuc["yillik_yuksek"] = bul(r"Yıllık En Yüksek\s*([\d.,]+)")
        sonuc["fk"] = bul(r"\(F/K\)\s*oran[ıi]\s*(?:ise\s*)?([\d.,]+)")
        sonuc["pddd"] = bul(r"\(PD/DD\)\s*oran[ıi]\s*(?:ise\s*)?([\d.,]+)")

        sektor_m = re.search(r"sektöründe faaliyet gösteren", metin)
        if sektor_m:
            on_metin = metin[max(0, sektor_m.start() - 60):sektor_m.start()]
            parca_m = re.search(r"([A-ZÇĞİÖŞÜa-zçğıöşü /]+)$", on_metin)
            if parca_m:
                sektor_metni = parca_m.group(1).strip(" ,.")
                sektor_metni = re.sub(r"^(de|da)\s+", "", sektor_metni, flags=re.IGNORECASE)
                sonuc["sektor"] = sektor_metni

        sonuc = {k: v for k, v in sonuc.items() if v is not None}
        if sonuc.get("son_fiyat") is None:
            m2 = re.search(r"şu anda\s*([\d.,]+)\s*TL seviyesinden işlem görmektedir", metin)
            if m2:
                sonuc["son_fiyat"] = _mynet_sayi(m2.group(1))
    except Exception:
        pass
    return sonuc


def canli_fiyat_cek(sembol: str) -> float:
    """Anlık/son fiyat. Birincil kaynak: Mynet Finans (hızlı, tek istekle güncel
    fiyat verir). Mynet başarısız olursa yfinance'e (gecikmeli olabilir) düşer."""
    sembol = sembol.strip().upper().replace(".IS", "")
    ozet = mynet_canli_ozet(sembol)
    if ozet.get("son_fiyat") is not None:
        return float(ozet["son_fiyat"])
    if yf is not None:
        try:
            t = yf.Ticker(f"{sembol}.IS")
            fi = t.fast_info
            fiyat = getattr(fi, "last_price", None) if fi is not None else None
            if fiyat:
                return float(fiyat)
        except Exception:
            pass
        try:
            df = yf.Ticker(f"{sembol}.IS").history(period="5d", interval="1d")
            if len(df) > 0:
                return float(df["Close"].iloc[-1])
        except Exception:
            pass
    return float("nan")


def fiyat_gecmisi_mynet(sembol: str, periyot: str = "1Y") -> pd.DataFrame:
    """Mynet 'Tarihsel Veriler' tablosundan günlük OHLCV üretir.

    ÖNEMLİ SINIRLAMA: Mynet bu tabloyu sayfasında yalnızca kısa bir pencere
    (tipik olarak son birkaç hafta) olarak sunar; ileri sayfalama uç noktası
    dokümante edilmediğinden çok yıllı geçmiş bu fonksiyonla ELDE EDİLEMEZ.
    'periyot' parametresi yalnızca ileriye dönük uyumluluk için tutulmuştur —
    sayfanın sunduğundan daha fazla veri talep edilemez. Çok yıllı/derin
    geçmiş için fiyat_gecmisi() fonksiyonunu kullanın (Mynet, son çare olarak
    o zincire de dahildir).

    Sütunlar: Open (bir önceki günün kapanışından yaklaşık), High, Low, Close,
    Volume (TL cinsinden hacmin kapanış fiyatına bölünmesiyle yaklaşık lot
    sayısına çevrilmiştir — Mynet'in tabloda verdiği hacim TL bazlıdır).
    """
    sembol = sembol.strip().upper().replace(".IS", "")
    try:
        url = f"https://finans.mynet.com/borsa/hisseler/{sembol.lower()}-x/tarihselveriler/"
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        try:
            tablolar = pd.read_html(r.text)
        except ImportError:
            return pd.DataFrame()
        hedef = None
        for t in tablolar:
            kolonlar = [str(c) for c in t.columns]
            if any("Tarih" in c for c in kolonlar) and any("Son Fiyat" in c for c in kolonlar):
                hedef = t
                break
        if hedef is None or hedef.empty:
            return pd.DataFrame()

        satirlar = []
        for _, satir in hedef.iterrows():
            try:
                tarih_metni = str(satir.get("Tarih", "")).strip()
                tarih_metni = re.sub(r"\[|\]|\(#\)", "", tarih_metni).strip()
                parcalar = tarih_metni.split()
                if len(parcalar) != 3:
                    continue
                gun, ay_adi, yil_str = parcalar
                ay = _MYNET_AYLAR.get(ay_adi.lower())
                if ay is None:
                    continue
                tarih = dt.date(int(yil_str), ay, int(gun))

                kapanis = _mynet_sayi(str(satir.get("Son Fiyat", "")))
                dusuk = _mynet_sayi(str(satir.get("En Düşük", "")))
                yuksek = _mynet_sayi(str(satir.get("En Yüksek", "")))
                hacim_tl = _mynet_sayi(str(satir.get("Hacim", "")))
                if kapanis is None:
                    continue
                hacim_lot = (hacim_tl / kapanis) if hacim_tl and kapanis else None
                satirlar.append({
                    "Tarih": pd.Timestamp(tarih), "Close": kapanis,
                    "Low": dusuk if dusuk is not None else kapanis,
                    "High": yuksek if yuksek is not None else kapanis,
                    "Volume": hacim_lot if hacim_lot is not None else 0.0,
                })
            except Exception:
                continue

        if not satirlar:
            return pd.DataFrame()

        df = pd.DataFrame(satirlar).drop_duplicates(subset="Tarih").set_index("Tarih").sort_index()
        # Açılışı yaklaşık olarak bir önceki günün kapanışından türet
        df["Open"] = df["Close"].shift(1)
        df["Open"] = df["Open"].fillna(df["Close"])
        return df[["Open", "High", "Low", "Close", "Volume"]]
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Fiyat geçmişi (derin/çok yıllı — Mynet son çare olarak dahildir)
# ─────────────────────────────────────────────────────────────────────────────
def _yf_duzelt(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.title)
    gerekli = ["Open", "High", "Low", "Close", "Volume"]
    df = df[[c for c in gerekli if c in df.columns]].dropna(how="all")
    # ÖNEMLİ: Toplu (çoklu-hisse) indirmede, henüz seansı açılmamış/o gün işlem
    # görmemiş bir hissenin son satırında Hacim dolu ama Kapanış (Close) boş
    # gelebiliyor — bu satır "tüm sütunlar boş" (dropna how='all') kriterine
    # uymadığı için silinmiyor ve c.iloc[-1] (Fiyat, 1 Ay %, 3 Ay %, MA200
    # tabanlı Uzun puanı) NaN'a bulaşıyordu. Kapanışı boş olan HERHANGİ bir
    # satırı ayrıca eliyoruz — Close, tüm hesaplamaların temel dayanağıdır.
    if "Close" in df.columns:
        df = df[df["Close"].notna()]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def fiyat_gecmisi(sembol: str, yil: float = 2.0) -> pd.DataFrame:
    """Günlük OHLCV. Sıra: yfinance → borsapy → İş Yatırım → Mynet (son çare).
    Mynet ilk sıraya alınmadı çünkü sitedeki tarihsel tablo yalnızca kısa bir
    pencere sunuyor; çok yıllı göstergeler (MA200, 1 yıllık getiri vb.) için
    yeterli değil. Canlı/anlık fiyat için ayrıca canli_fiyat_cek() kullanın —
    o fonksiyon Mynet'i BİRİNCİL kaynak olarak kullanır."""
    # 1) yfinance
    if yf is not None:
        try:
            df = yf.Ticker(f"{sembol}.IS").history(period=f"{int(yil*12)}mo",
                                                   interval="1d", auto_adjust=True)
            df = _yf_duzelt(df)
            if len(df) > 30:
                return df
        except Exception:
            pass
    # 2) borsapy (TradingView)
    if bp is not None:
        try:
            df = bp.Ticker(sembol).history(period="max" if yil > 3 else f"{int(yil)}y")
            if df is not None and len(df) > 30:
                df = df.rename(columns=str.title)
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df[["Open", "High", "Low", "Close", "Volume"]].dropna(how="all")
        except Exception:
            pass
    # 3) İş Yatırım
    try:
        bit = dt.date.today()
        bas = bit - dt.timedelta(days=int(yil * 365))
        url = ("https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/"
               f"Data.aspx/HisseTekil?hisse={sembol}"
               f"&startdate={bas:%d-%m-%Y}&enddate={bit:%d-%m-%Y}.json")
        r = requests.get(url, headers=UA, timeout=15)
        rows = r.json().get("value", [])
        if rows:
            df = pd.DataFrame(rows)
            df["Tarih"] = pd.to_datetime(df["HGDG_TARIH"], dayfirst=True, errors="coerce")
            df = df.set_index("Tarih").sort_index()
            out = pd.DataFrame({
                "Open":  pd.to_numeric(df.get("HGDG_ACILIS", df["HGDG_KAPANIS"]), errors="coerce"),
                "High":  pd.to_numeric(df.get("HGDG_MAX", df["HGDG_KAPANIS"]), errors="coerce"),
                "Low":   pd.to_numeric(df.get("HGDG_MIN", df["HGDG_KAPANIS"]), errors="coerce"),
                "Close": pd.to_numeric(df["HGDG_KAPANIS"], errors="coerce"),
                "Volume": pd.to_numeric(df.get("HGDG_HACIM", 0), errors="coerce"),
            }).dropna(subset=["Close"])
            if len(out) > 30:
                return out
    except Exception:
        pass
    # 4) Mynet (son çare — kısa pencere ama hiç veri yoktan iyidir)
    try:
        df = fiyat_gecmisi_mynet(sembol)
        if len(df) > 5:
            return df
    except Exception:
        pass
    return pd.DataFrame()


def toplu_fiyat(semboller: list, yil: float = 1.0, ilerleme=None) -> dict:
    """Tarama için toplu OHLCV. yfinance ile 50'şerli gruplar halinde indirir."""
    sonuc = {}
    if yf is None:
        return sonuc
    grup_boyu = 50
    gruplar = [semboller[i:i + grup_boyu] for i in range(0, len(semboller), grup_boyu)]
    for gi, grup in enumerate(gruplar):
        try:
            tickers = " ".join(f"{s}.IS" for s in grup)
            df = yf.download(tickers, period=f"{int(yil*12)}mo", interval="1d",
                             auto_adjust=True, progress=False, threads=True,
                             group_by="ticker")
            for s in grup:
                try:
                    alt = df[f"{s}.IS"] if isinstance(df.columns, pd.MultiIndex) else df
                    alt = _yf_duzelt(alt.copy())
                    if len(alt) > 60:
                        sonuc[s] = alt
                except Exception:
                    continue
        except Exception:
            continue
        if ilerleme:
            ilerleme((gi + 1) / len(gruplar))
    return sonuc


def endeks_gecmisi(yil: float = 2.0) -> pd.DataFrame:
    """XU100 (BIST100) endeksi — göreceli güç hesabı için."""
    if yf is not None:
        try:
            df = _yf_duzelt(yf.Ticker("XU100.IS").history(period=f"{int(yil*12)}mo",
                                                          interval="1d", auto_adjust=True))
            if len(df) > 30:
                return df
        except Exception:
            pass
    if bp is not None:
        try:
            df = bp.Index("XU100").history(period=f"{int(yil)}y")
            if df is not None and len(df) > 30:
                df = df.rename(columns=str.title)
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df
        except Exception:
            pass
    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Temel veriler + takas (yabancı oranı) + haberler
# ─────────────────────────────────────────────────────────────────────────────
def temel_veriler(sembol: str) -> dict:
    """F/K, PD/DD, piyasa değeri, halka açıklık, yabancı oranı, temettü...
    Mynet canlı özeti (F/K, PD/DD, sektör) öncelikli tamamlayıcı olarak kullanılır."""
    sonuc = {}
    if bp is not None:
        try:
            t = bp.Ticker(sembol)
            fi = {}
            try:
                fi = dict(t.fast_info or {})
            except Exception:
                pass
            info = {}
            try:
                info = dict(t.info or {})
            except Exception:
                pass
            sonuc.update({
                "son_fiyat":      fi.get("last_price") or info.get("last"),
                "piyasa_degeri":  fi.get("market_cap") or info.get("marketCap"),
                "fk":             fi.get("pe_ratio") or info.get("trailingPE"),
                "pddd":           info.get("priceToBook") or fi.get("pb_ratio"),
                "halka_aciklik":  fi.get("free_float"),
                "yabanci_orani":  fi.get("foreign_ratio"),
                "temettu_verimi": info.get("dividendYield"),
                "sirket_adi":     info.get("name") or info.get("shortName") or info.get("longName"),
                "sektor":         info.get("sector") or info.get("industry"),
            })
        except Exception:
            pass
    # yfinance ile tamamla (F/K, piyasa değeri VEYA şirket adı eksikse — adı
    # eksik diye borsapy'nin dolu bıraktığı diğer alanları görmezden gelip
    # bu adımı ATLAMAK, "hisse kartlarında hala tam ad yok" şikayetinin asıl
    # nedeniydi: borsapy F/K'yı bulunca yfinance hiç denenmiyordu, oysa isim
    # çoğu zaman sadece yfinance'ta vardı.)
    if yf is not None and (not sonuc.get("fk") or not sonuc.get("piyasa_degeri") or not sonuc.get("sirket_adi")):
        try:
            info = yf.Ticker(f"{sembol}.IS").info or {}
            sonuc.setdefault("son_fiyat", info.get("currentPrice"))
            for anahtar, yf_anahtar in [("piyasa_degeri", "marketCap"), ("fk", "trailingPE"),
                                        ("pddd", "priceToBook"), ("temettu_verimi", "dividendYield"),
                                        ("sirket_adi", "longName"), ("sektor", "sector")]:
                if not sonuc.get(anahtar):
                    sonuc[anahtar] = info.get(yf_anahtar)
        except Exception:
            pass
    # Mynet ile tamamla (son fiyat, F/K, PD/DD, sektör)
    if not sonuc.get("fk") or not sonuc.get("pddd") or not sonuc.get("son_fiyat"):
        try:
            mynet = mynet_canli_ozet(sembol)
            sonuc.setdefault("son_fiyat", mynet.get("son_fiyat"))
            sonuc.setdefault("fk", mynet.get("fk"))
            sonuc.setdefault("pddd", mynet.get("pddd"))
            sonuc.setdefault("sektor", mynet.get("sektor"))
        except Exception:
            pass
    return {k: v for k, v in sonuc.items() if v is not None}


def toplu_temel_veriler(semboller: list, ilerleme=None, max_worker: int = 20) -> dict:
    """Birden fazla hissenin temel verilerini (F/K, PD/DD, temettü vb.) PARALEL
    iş parçacıklarıyla çeker. temel_veriler() ağ I/O baskın (borsapy/yfinance/
    Mynet zinciri) olduğundan, threading burada GIL'e rağmen gerçek bir
    hızlanma sağlar — 100+ hisseyi sıralı çekmek yerine aynı anda ~20'şer
    istek göndererek toplam süreyi kabaca max_worker kat kısaltır."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    sonuc = {}
    tamamlanan = 0
    toplam = len(semboller)
    with ThreadPoolExecutor(max_workers=max_worker) as havuz:
        gelecekler = {havuz.submit(temel_veriler, s): s for s in semboller}
        for gelecek in as_completed(gelecekler):
            s = gelecekler[gelecek]
            try:
                sonuc[s] = gelecek.result()
            except Exception:
                sonuc[s] = {}
            tamamlanan += 1
            if ilerleme:
                ilerleme(tamamlanan / max(toplam, 1))
    return sonuc


def toplu_yabanci_orani(semboller: list, yil: float = 1.0, ilerleme=None,
                        max_worker: int = 20) -> dict:
    """toplu_temel_veriler ile aynı mantık — yabancı takas oranı geçmişini
    (İş Yatırım) paralel çeker."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    sonuc = {}
    tamamlanan = 0
    toplam = len(semboller)
    with ThreadPoolExecutor(max_workers=max_worker) as havuz:
        gelecekler = {havuz.submit(yabanci_orani_gecmisi, s, yil): s for s in semboller}
        for gelecek in as_completed(gelecekler):
            s = gelecekler[gelecek]
            try:
                sonuc[s] = gelecek.result()
            except Exception:
                sonuc[s] = pd.Series(dtype=float)
            tamamlanan += 1
            if ilerleme:
                ilerleme(tamamlanan / max(toplam, 1))
    return sonuc


def yabanci_orani_gecmisi(sembol: str, yil: float = 1.0) -> pd.Series:
    """Yabancı takas oranı geçmişi — İş Yatırım HisseTekil'deki yabancı kolonu
    dinamik aranır. Bulunamazsa boş seri döner."""
    try:
        bit = dt.date.today()
        bas = bit - dt.timedelta(days=int(yil * 365))
        url = ("https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/"
               f"Data.aspx/HisseTekil?hisse={sembol}"
               f"&startdate={bas:%d-%m-%Y}&enddate={bit:%d-%m-%Y}.json")
        r = requests.get(url, headers=UA, timeout=15)
        rows = r.json().get("value", [])
        if rows:
            df = pd.DataFrame(rows)
            yab_kolon = next((c for c in df.columns if "YABANCI" in c.upper()), None)
            if yab_kolon:
                df["Tarih"] = pd.to_datetime(df["HGDG_TARIH"], dayfirst=True, errors="coerce")
                s = pd.to_numeric(df.set_index("Tarih")[yab_kolon], errors="coerce").dropna()
                return s.sort_index()
    except Exception:
        pass
    return pd.Series(dtype=float)


def kap_haberleri(sembol: str, adet: int = 10) -> list:
    if bp is None:
        return []
    try:
        haberler = bp.Ticker(sembol).news
        if isinstance(haberler, pd.DataFrame):
            haberler = haberler.head(adet).to_dict("records")
        return list(haberler)[:adet] if haberler else []
    except Exception:
        return []


def analist_verileri(sembol: str) -> dict:
    sonuc = {}
    if bp is None:
        return sonuc
    t = None
    try:
        t = bp.Ticker(sembol)
        hedef = t.analyst_price_targets
        if hedef is not None:
            sonuc["hedef_fiyat"] = hedef
    except Exception:
        pass
    try:
        if t is not None:
            ozet = t.recommendations_summary
            if ozet is not None:
                sonuc["tavsiye_ozeti"] = ozet
    except Exception:
        pass
    return sonuc


# ─────────────────────────────────────────────────────────────────────────────
# Fon & kurumsal sahiplik
# ─────────────────────────────────────────────────────────────────────────────
def etf_sahipligi(sembol: str) -> pd.DataFrame:
    """Uluslararası ETF'lerin bu hissedeki pozisyonları (BlackRock, Vanguard...).
    Yabancı kurumsal ilginin somut göstergesi."""
    if bp is None:
        return pd.DataFrame()
    try:
        df = bp.Ticker(sembol).etf_holders
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


def ana_ortaklar(sembol: str):
    if bp is None:
        return None
    try:
        return bp.Ticker(sembol).major_holders
    except Exception:
        return None


def tefas_hisse_trendi(ay_sayisi: int = 6) -> pd.Series:
    """TEFAS: Yatırım fonlarının portföylerindeki ortalama HİSSE ağırlığı (%).
    Artıyorsa yerli fonlar borsaya para sokuyor demektir. Aylık örneklem alır."""
    cache = _disk_cache_oku("tefas_hisse_trendi", max_yas_saat=24)
    if cache:
        try:
            s = pd.Series({pd.Timestamp(k): v for k, v in cache.items()})
            if len(s) >= 3:
                return s.sort_index()
        except Exception:
            pass
    url = "https://www.tefas.gov.tr/api/DB/BindHistoryAllocation"
    headers = dict(UA)
    headers.update({"X-Requested-With": "XMLHttpRequest",
                    "Origin": "https://www.tefas.gov.tr",
                    "Referer": "https://www.tefas.gov.tr/TarihselVeriler.aspx"})
    sonuc = {}
    bugun = dt.date.today()
    for i in range(ay_sayisi, -1, -1):
        tarih = bugun - dt.timedelta(days=30 * i + 3)
        # hafta sonuna denk gelmesin
        while tarih.weekday() >= 5:
            tarih -= dt.timedelta(days=1)
        t_str = tarih.strftime("%d.%m.%Y")
        try:
            r = requests.post(url, headers=headers, timeout=20, data={
                "fontip": "YAT", "sfontur": "", "fonkod": "", "fongrup": "",
                "bastarih": t_str, "bittarih": t_str,
                "fonturkod": "", "fonunvantip": "", "kurucukod": ""})
            veri = r.json()
            rows = veri.get("data", veri) if isinstance(veri, dict) else veri
            if rows:
                df = pd.DataFrame(rows)
                hs_kolon = next((c for c in df.columns if c.upper() in ("HS", "HISSESENEDI")
                                 or "HISSE" in c.upper()), None)
                if hs_kolon is not None:
                    vals = pd.to_numeric(df[hs_kolon], errors="coerce").dropna()
                    vals = vals[vals > 0]
                    if len(vals) > 10:
                        sonuc[str(pd.Timestamp(tarih))] = float(vals.mean())
        except Exception:
            continue
        time.sleep(0.4)
    if sonuc:
        _disk_cache_yaz("tefas_hisse_trendi", sonuc)
        return pd.Series({pd.Timestamp(k): v for k, v in sonuc.items()}).sort_index()
    return pd.Series(dtype=float)


def usdtry_gecmisi(yil: float = 1.0) -> pd.DataFrame:
    """Piyasa rejimi için USDTRY kuru."""
    if yf is not None:
        try:
            df = _yf_duzelt(yf.Ticker("USDTRY=X").history(period=f"{int(yil*12)}mo",
                                                          interval="1d"))
            if len(df) > 30:
                return df
        except Exception:
            pass
    if bp is not None:
        try:
            df = bp.FX("USDTRY").history(period=f"{int(yil)}y")
            if df is not None and len(df) > 30:
                df = df.rename(columns=str.title)
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df
        except Exception:
            pass
    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Kaynak testi
# ─────────────────────────────────────────────────────────────────────────────
def kaynak_testi() -> dict:
    """Her veri kaynağını canlı test eder. Uygulamadaki 'Durum' sekmesi kullanır."""
    rapor = {}
    # Mynet canlı fiyat
    try:
        fiyat = canli_fiyat_cek("THYAO")
        rapor["Mynet canlı fiyat"] = "ÇALIŞIYOR" if fiyat == fiyat and fiyat > 0 else "SORUNLU"
    except Exception as e:
        rapor["Mynet canlı fiyat"] = f"HATA: {e}"
    # Yahoo / borsapy / İş Yatırım / Mynet zinciri
    try:
        df = fiyat_gecmisi("THYAO", yil=0.3) if yf else pd.DataFrame()
        rapor["Fiyat verisi (Yahoo/borsapy/İş Yatırım/Mynet)"] = (
            "ÇALIŞIYOR" if len(df) > 10 else "SORUNLU")
    except Exception as e:
        rapor["Fiyat verisi (Yahoo/borsapy/İş Yatırım/Mynet)"] = f"HATA: {e}"
    # borsapy temel
    try:
        tv = temel_veriler("THYAO")
        rapor["Temel veriler (F/K, yabancı oranı...)"] = (
            "ÇALIŞIYOR" if tv else "SORUNLU")
        rapor["Yabancı takas oranı (anlık)"] = (
            "ÇALIŞIYOR" if tv.get("yabanci_orani") is not None else "ALINAMADI")
    except Exception as e:
        rapor["Temel veriler (F/K, yabancı oranı...)"] = f"HATA: {e}"
    # İş Yatırım yabancı geçmişi
    try:
        s = yabanci_orani_gecmisi("THYAO", yil=0.3)
        rapor["Yabancı takas oranı (geçmiş, İş Yatırım)"] = (
            "ÇALIŞIYOR" if len(s) > 5 else "ALINAMADI (anlık değer kullanılacak)")
    except Exception as e:
        rapor["Yabancı takas oranı (geçmiş, İş Yatırım)"] = f"HATA: {e}"
    # ETF sahipliği
    try:
        e = etf_sahipligi("ASELS")
        rapor["ETF sahipliği (yabancı kurumsal)"] = (
            "ÇALIŞIYOR" if len(e) > 0 else "ALINAMADI")
    except Exception as ex:
        rapor["ETF sahipliği (yabancı kurumsal)"] = f"HATA: {ex}"
    # TEFAS
    try:
        t = tefas_hisse_trendi(2)
        rapor["TEFAS fon verileri"] = "ÇALIŞIYOR" if len(t) >= 2 else "ALINAMADI"
    except Exception as ex:
        rapor["TEFAS fon verileri"] = f"HATA: {ex}"
    # USDTRY
    try:
        u = usdtry_gecmisi(0.3)
        rapor["USDTRY kuru (piyasa rejimi)"] = "ÇALIŞIYOR" if len(u) > 10 else "ALINAMADI"
    except Exception as ex:
        rapor["USDTRY kuru (piyasa rejimi)"] = f"HATA: {ex}"
    # Sembol listesi
    try:
        lst = sembol_listesi("TUM")
        rapor[f"Sembol listesi ({len(lst)} hisse)"] = (
            "DİNAMİK" if len(lst) > 150 else
            "YEDEK LİSTE (en likit ~106 hisse)")
    except Exception as e:
        rapor["Sembol listesi"] = f"HATA: {e}"
    return rapor
