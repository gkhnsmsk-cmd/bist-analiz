# -*- coding: utf-8 -*-
"""
sohbet_ajani.py — Yazılımın içinde çalışan AKILLI SOHBET ASİSTANI (çekirdek).
══════════════════════════════════════════════════════════════════════════════
NE YAPAR: Kullanıcı sağdaki sohbet panelinde serbest Türkçe yazar
("PGSUS analiz", "elimde EREGL var ne yapayım?", "TUPRS takas durumu ne?"),
asistan bunu ANLAR, yazılımın kendi motorlarını ÇALIŞTIRIR ve sonucu
konuşma diliyle anlatır. Gerekirse ilgili sekmeye yönlendirir.

MİMARİ — neden böyle kuruldu (ÖNEMLİ):
Bu desen, HVAC Hesap Pro yazılımındaki ajan sohbetinden uyarlandı: dil modeli
serbest metin üretmez, önce ```json_commands``` bloğu içinde ÇALIŞTIRILACAK
KOMUTLARI yazar; komutları biz çalıştırırız; sonra GERÇEK SONUÇLARI modele
geri veririz ve cevabı o sonuçlara dayanarak yazdırırız.

╔════════════════════════════════════════════════════════════════════════════╗
║  HALÜSİNASYON KORUMASI — bu yazılımın en kritik güvenlik tasarımı           ║
╠════════════════════════════════════════════════════════════════════════════╣
║  Dil modelleri sayı UYDURUR. Bir borsa yazılımında uydurma bir fiyat ya da  ║
║  puan, doğrudan para kaybı demektir. Bu yüzden akış İKİ FAZLIDIR:           ║
║                                                                            ║
║   FAZ 1 — Model SADECE hangi aracı çağıracağını söyler. Sayı üretemez.      ║
║   FAZ 2 — Araçları BİZ çalıştırırız (analiz_motoru vb.), gerçek sayıları    ║
║           modele veririz ve "yalnızca bu verilerdeki sayıları kullan"       ║
║           talimatıyla cevabı yazdırırız.                                    ║
║                                                                            ║
║  Yani ekranda görünen her rakam, yazılımın kendi motorundan gelir.          ║
╚════════════════════════════════════════════════════════════════════════════╝

YATIRIM TAVSİYESİ SINIRI: Asistan "şunu al / şunu sat" diye emir vermez.
Motorun ürettiği puanı, riski, takas durumunu ve KARŞI ARGÜMANI sunar; kararı
kullanıcıya bırakır. Bu, uygulamanın geri kalanıyla (her ekranda "yatırım
tavsiyesi değildir" uyarısı) tutarlıdır.
"""
from __future__ import annotations

import json
import re

import pandas as pd

import analiz_motoru as am
import llm_ajanlari as la
import ozet_metni as ozm

# ─────────────────────────────────────────────────────────────────────────────
# 1) ARAÇ KATALOĞU — asistanın yapabildiği her şey
# ─────────────────────────────────────────────────────────────────────────────
# Buradaki metin doğrudan sistem promptuna giriyor. Kısa ve net tutulması
# ÖNEMLİ: uzun prompt hem yavaşlatır hem de küçük modellerin komutları
# karıştırmasına yol açar.
ARAC_KATALOGU = """
1.  analiz        {"arac":"analiz","sembol":"PGSUS"}
    Hissenin tam analizi: genel puan, vade puanları, karar, stop/hedef, trend.

2.  risk          {"arac":"risk","sembol":"EREGL","alis_fiyati":42.0}
    Satış/düşüş alarmları, risk puanı, önerilen stop seviyesi.
    alis_fiyati OPSİYONELDİR — kullanıcı alış fiyatını söylediyse ekle.

3.  takas         {"arac":"takas","sembol":"TUPRS"}
    Takas/para akışı analizi + (varsa) AKD aracı kurum dağılımı sinyali.

4.  portfoy       {"arac":"portfoy"}
    Kullanıcının portföyü: pozisyonlar, kâr/zarar, sanal portföy durumu.

5.  tarama        {"arac":"tarama","adet":10,"kapsam":"BIST30"}
    ÖNE ÇIKAN hisseler: genel puana göre sıralı liste.
    kapsam OPSİYONELDİR: BIST30 / BIST100 (yazılmazsa tüm BIST).

5b. yukselecek    {"arac":"yukselecek","vade":"Kısa","adet":5,"kapsam":"BIST30"}
    YÜKSELEBİLECEK hisseler: vade bazlı (Kısa/Orta/Uzun) AL sinyali olanlar.
    Kullanıcı "yükselebilecek", "yükselir mi", "hangi hisseler yükselir",
    "kısa/orta/uzun vadede ne alınır" derse BU aracı kullan — "tarama" değil.
    vade OPSİYONEL (yazılmazsa üç vade de gelir).

6.  karsilastir   {"arac":"karsilastir","semboller":["THYAO","PGSUS"]}
    İki veya daha fazla hisseyi yan yana puanlar.

7.  favori_ekle   {"arac":"favori_ekle","sembol":"ASELS"}
8.  favori_cikar  {"arac":"favori_cikar","sembol":"ASELS"}
    Favori listesini yönetir.

9.  sayfaya_git   {"arac":"sayfaya_git","sekme":"arastir","sembol":"PGSUS"}
    Kullanıcıyı ilgili sekmeye yönlendirir. Geçerli sekmeler:
    arastir, yukselecek, tarama, takas, fon, portfoy, sanal, backtest,
    tavsiye, durum
    KURAL: Kullanıcı bir hisse analizi istediğinde ÖNCE "analiz" aracını,
    SONRA sayfaya_git'i çağır — böylece hem cevabı okur hem sayfa hazırlanır.

10. temel         {"arac":"temel","sembol":"ENKAI"}
    Temel veriler: F/K, PD/DD, piyasa değeri, temettü verimi, halka açıklık,
    yabancı oranı, şirket adı, sektör. "F/K kaç", "kaç para eder",
    "temettü veriyor mu" gibi sorular için.

11. donem_getirileri {"arac":"donem_getirileri","sembol":"PGSUS","periyot":"haftalik","son":12}
    Son N dönemin getirileri, TARİHLERİYLE birlikte.
    periyot: gunluk / haftalik / aylik
    "En son hangi hafta yükseldi", "geçen ay ne yaptı", "kaç haftadır
    düşüyor" gibi ZAMAN sorularının cevabı BURADADIR.

12. fiyat_ozet    {"arac":"fiyat_ozet","sembol":"PGSUS"}
    Son fiyat, 1h/1a/3a/6a/1y getiriler, 52 hafta zirve/dip ve bunlara
    uzaklık, volatilite, ortalama hacim.

13. gostergeler   {"arac":"gostergeler","sembol":"PGSUS"}
    Güncel teknik göstergeler: RSI, MACD, Stokastik, ATR, Bollinger,
    MA20/50/200 ve fiyatın bunlara uzaklığı, OBV/MFI/CMF.

14. haberler      {"arac":"haberler","sembol":"PGSUS"}
    Son KAP bildirimleri.

15. analist       {"arac":"analist","sembol":"PGSUS"}
    Analist hedef fiyatları ve tavsiyeleri (varsa).

16. hisse_ara     {"arac":"hisse_ara","metin":"enka"}
    Şirket adından hisse kodu bulur. Kullanıcı kod yerine ad yazdıysa
    ÖNCE bunu çağır, doğru kodu öğren, sonra asıl aracı çağır.

17. alanlar       {"arac":"alanlar"}
    Filtreleme yapılabilecek TÜM sütunları ve örnek değerleri listeler.
    Hangi alanın var olduğundan emin değilsen ÖNCE bunu çağır.

18. filtre        ★ EN GÜÇLÜ ARAÇ — serbest tarama/sıralama/filtreleme
    {"arac":"filtre",
     "kosullar":[{"alan":"1 Ay %","operator":"<","deger":0},
                 {"alan":"Puan","operator":">=","deger":50}],
     "sirala":"1 Ay %", "yon":"artan", "adet":5, "kapsam":"BIST100"}

    TÜM BIST taramasındaki hisseler üzerinde çalışır.
    operator: > >= < <= == != içerir
    yon: "artan" (küçükten büyüğe) | "azalan" (büyükten küçüğe)
    kosullar OPSİYONEL — sadece sıralama da yapabilirsin.

    ÖRNEKLER:
    • "en çok düşen 5 hisse"      → sirala:"1 Ay %", yon:"artan", adet:5
    • "en çok yükselen 10"        → sirala:"1 Ay %", yon:"azalan", adet:10
    • "en yüksek puanlı hisseler" → sirala:"Puan", yon:"azalan"
    • "puanı 70 üstü olanlar"     → kosullar:[{"alan":"Puan","operator":">=","deger":70}]
    • "hacmi yüksek ve düşenler"  → kosullar:[{"alan":"Hacim(M₺)","operator":">","deger":100},
                                              {"alan":"1 Ay %","operator":"<","deger":0}]
    • "AL sinyali olanlar"        → kosullar:[{"alan":"Karar","operator":"içerir","deger":"AL"}]
"""

_GECERLI_SEKMELER = {
    "arastir": "🔍 Hisse Araştır",
    "yukselecek": "📈 Yükselebilecek Hisseler",
    "tarama": "⭐ Öne Çıkan Hisseler",
    "takas": "🤝 Takas Analizi",
    "fon": "🏦 Fon & Kurumsal",
    "portfoy": "💼 Portföy & Tavsiye",
    "sanal": "🤖 Sanal Portföy (Paper)",
    "backtest": "🔬 Backtest / Doğrulama",
    "tavsiye": "📜 Tavsiye Geçmişi",
    "durum": "🩺 Sistem Durumu",
}


def _sistem_promptu_faz1(baglam: str) -> str:
    """FAZ 1: Model yalnızca hangi araçların çağrılacağını söyler."""
    return f"""Sen "BIST Analiz Platformu" yazılımının içinde çalışan asistansın.
Kullanıcının isteğini anlayıp YAZILIMIN ARAÇLARINI çağırırsın.

=== GÖREVIN (SADECE BU) ===
Kullanıcının sorusuna cevap YAZMA. Sadece hangi araçların çağrılması
gerektiğini bir JSON listesi olarak döndür:

```json_commands
[{{"arac":"analiz","sembol":"PGSUS"}}]
```

Birden fazla araç aynı listede olabilir. Sıralama önemlidir.

=== KULLANILABİLİR ARAÇLAR ==={ARAC_KATALOGU}
=== KURALLAR ===
- ASLA sayı, fiyat, puan veya tahmin üretme. Senin işin sadece araç seçmek.
- Hisse kodlarını BÜYÜK HARF yaz (pgsus → PGSUS).
- Kullanıcı "elimde X var, ne yapayım" derse: analiz + risk araçlarını çağır.
- LİSTE / SIRALAMA / FİLTRELEME sorularında ("en çok düşen", "en yüksek
  puanlı", "şu şartı sağlayanlar", "ilk 5", "hangileri") MUTLAKA "filtre"
  aracını kullan. Bu tür soruları asla "veri yok" diye geçiştirme.
- Alan adından emin değilsen önce {{"arac":"alanlar"}} çağır, sonra filtrele.
- Kullanıcı hisse KODU yerine şirket ADI yazdıysa önce "hisse_ara" çağır.
- ZAMAN soruları ("ne zaman", "hangi hafta", "kaç gündür") → donem_getirileri
- Birden fazla araç gerekiyorsa hepsini AYNI listede sırayla ver.
- Kullanıcı sadece sohbet ediyorsa/selamlıyorsa boş liste döndür: []
- Sadece JSON bloğunu döndür, başka hiçbir şey yazma.

=== MEVCUT DURUM ===
{baglam}"""


def _sistem_promptu_faz2(baglam: str, arac_sonuclari: str) -> str:
    """FAZ 2: Model, SADECE gerçek araç sonuçlarını kullanarak cevabı yazar."""
    return f"""Sen "BIST Analiz Platformu" yazılımının asistanısın. Türkçe, net,
kısa ve anlaşılır yazarsın. Jargon kullanırsan aynı cümlede açıklarsın.

=== EN ÖNEMLİ KURAL ===
Aşağıdaki ARAÇ SONUÇLARI bölümünde yer alan sayıların DIŞINDA hiçbir sayı,
fiyat, oran veya tahmin YAZMA. Bir bilgi orada yoksa "bu veri yok" de.
Kendi bilgi dağarcığından hisse fiyatı, bilanço, haber veya beklenti UYDURMA.

=== NASIL CEVAP VERİRSİN ===
- Önce tek cümlelik net durum özeti.
- Sonra 2-4 madde: hangi göstergeler olumlu, hangileri olumsuz.
- Risk varsa mutlaka söyle (stop seviyesi, alarmlar).
- KARŞI ARGÜMANI da yaz — tek yönlü konuşma.
- ARAÇ SONUCUNDA "hata" ALANI VARSA: asla sadece "veri yok" deyip bırakma.
  O hata metni kullanıcının NE YAPMASI gerektiğini söyler — bunu açıkça,
  adım adım aktar (hangi düğmeye basacak, hangi dosyayı çalıştıracak).
- "Kesinlikle al / kesinlikle sat" DEME. Sen lisanslı bir yatırım danışmanı
  değilsin ve bu yazılım da değil. Durumu tarif et, kararı kullanıcı versin.
- Kısa tut: en fazla 150 kelime.
- Sonunda tek satır: "⚠️ Yatırım tavsiyesi değildir."

=== MEVCUT DURUM ===
{baglam}

=== ARAÇ SONUÇLARI (yalnızca bunları kullan) ===
{arac_sonuclari}"""


# ─────────────────────────────────────────────────────────────────────────────
# 2) BAĞLAM — modelin her turda gördüğü kısa durum özeti
# ─────────────────────────────────────────────────────────────────────────────
def baglam_uret(portfoy_sembolleri=None, favoriler=None, rejim=None) -> str:
    """Modele verilecek KISA durum özeti.

    Kısa tutulması bilinçli: uzun bağlam hem token yakar hem de küçük
    modellerin dikkatini dağıtır. Ayrıntı gerekiyorsa model zaten aracı
    çağırıp gerçek veriyi alacak.
    """
    parcalar = []
    if rejim:
        try:
            parcalar.append(f"Piyasa rejimi: {rejim['puan']:.0f}/100 ({rejim['durum']})")
        except Exception:
            pass
    if portfoy_sembolleri:
        parcalar.append("Kullanıcının portföyündeki hisseler: "
                        + ", ".join(portfoy_sembolleri))
    if favoriler:
        parcalar.append("Favorileri: " + ", ".join(favoriler))
    return "\n".join(parcalar) if parcalar else "(ek durum bilgisi yok)"


# ─────────────────────────────────────────────────────────────────────────────
# 3) KOMUT AYRIŞTIRMA
# ─────────────────────────────────────────────────────────────────────────────
_BLOK = re.compile(r"```(?:json_commands|json)?\s*(.*?)```", re.S)


def komutlari_ayikla(metin: str) -> list:
    """Model yanıtından araç komutlarını çıkarır.

    Modeller kod bloğunu bazen ```json_commands, bazen ```json, bazen hiç
    işaretlemeden döndürür; üçü de desteklenir. Ayrıştırılamayan yanıt
    BOŞ LİSTE döndürür — asla istisna fırlatmaz (sohbet çökmesin).
    """
    if not metin:
        return []
    adaylar = _BLOK.findall(metin)
    if not adaylar:
        # Blok yoksa: metnin içindeki ilk JSON dizisini yakalamayı dene.
        i, j = metin.find("["), metin.rfind("]")
        if i != -1 and j > i:
            adaylar = [metin[i:j + 1]]
    for ham in adaylar:
        try:
            veri = json.loads(ham.strip())
        except Exception:
            continue
        if isinstance(veri, dict):
            veri = [veri]
        if isinstance(veri, list):
            return [k for k in veri if isinstance(k, dict) and k.get("arac")]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# 4) ARAÇLARIN ÇALIŞTIRILMASI
# ─────────────────────────────────────────────────────────────────────────────
def _sayi(x, ondalik=2):
    try:
        d = float(x)
        if d != d:
            return None
        return round(d, ondalik)
    except (TypeError, ValueError):
        return None


def _analiz_calistir(sembol, kaynaklar):
    """Tek hisse tam analizi — sonuç SÖZLÜK olarak döner (modele verilecek)."""
    df = kaynaklar["gecmis"](sembol)
    if df is None or len(df) == 0:
        return {"hata": f"{sembol} için fiyat verisi bulunamadı."}
    temel = kaynaklar["temel"](sembol) or {}
    analiz = am.tam_analiz(sembol, df, temel, kaynaklar["yabanci"](sembol),
                           kaynaklar["endeks"](), rejim=kaynaklar["rejim"]())
    akd = kaynaklar["akd"](sembol)
    nihai = ozm.nihai_karar(analiz, akd)
    return {
        "sembol": sembol,
        "son_fiyat_TL": _sayi(analiz.get("son_fiyat")),
        "genel_puan_100": _sayi(analiz.get("genel_puan"), 1),
        "motor_karari": analiz.get("karar"),
        "nihai_karar": nihai.get("karar"),
        "celiskili_mi": nihai.get("celiskili_mi"),
        "trend_yonu": analiz.get("trend_yonu"),
        "vade_puanlari": {k: _sayi(v, 1) for k, v in (analiz.get("puanlar") or {}).items()},
        "getiri_1ay_yuzde": _sayi(analiz.get("getiri_1a"), 1),
        "getiri_3ay_yuzde": _sayi(analiz.get("getiri_3a"), 1),
        "stop_onerisi_TL": _sayi(analiz.get("stop_oneri")),
        "hedef_onerisi_TL": _sayi(analiz.get("hedef_oneri")),
        "temel_FK": _sayi(temel.get("fk"), 1),
        "temel_PDDD": _sayi(temel.get("pddd"), 2),
    }


def _risk_calistir(sembol, alis_fiyati, kaynaklar):
    df = kaynaklar["gecmis"](sembol)
    if df is None or len(df) == 0:
        return {"hata": f"{sembol} için fiyat verisi bulunamadı."}
    r = am.risk_alarmlari(df, alis_fiyati=_sayi(alis_fiyati))
    etiket = am.SATIS_SEVIYE_METNI.get(r.get("seviye"), ("—", "#888"))[0]
    # Alarmlar sözlük listesi olarak gelir ({"baslik","mesaj","agirlik"}).
    # Modele düz metin vermek hem token tasarrufu sağlar hem de modelin
    # yanlış alana atıfta bulunmasını engeller.
    alarmlar = []
    for a in (r.get("alarmlar") or []):
        if isinstance(a, dict):
            alarmlar.append(f"{a.get('baslik')}: {a.get('mesaj')}")
        else:
            alarmlar.append(str(a))
    return {
        "sembol": sembol,
        "risk_seviyesi": etiket,
        "risk_puani_100": r.get("risk_puani"),
        "aktif_alarmlar": alarmlar or ["(alarm yok)"],
        "onerilen_stop_TL": _sayi(r.get("stop_seviyesi")),
        "mevcut_zarar_yuzde": _sayi(r.get("zarar_yuzde"), 1),
    }


def _takas_calistir(sembol, kaynaklar):
    df = kaynaklar["gecmis"](sembol)
    if df is None or len(df) == 0:
        return {"hata": f"{sembol} için fiyat verisi bulunamadı."}
    puan, sinyaller = am.takas_analizi(df, kaynaklar["temel"](sembol) or {},
                                       kaynaklar["yabanci"](sembol))
    sonuc = {
        "sembol": sembol,
        "takas_puani_100": _sayi(puan, 1),
        "aciklama": "50 üzeri = hisseye para girişi ağır basıyor",
        "sinyaller": [f"{s.get('etiket')}: {s.get('aciklama')}"
                      for s in (sinyaller or [])][:6],
    }
    akd = kaynaklar["akd"](sembol)
    if akd and akd.get("puan") is not None:
        sonuc["akd_karari"] = akd.get("karar")
        sonuc["akd_puani"] = akd.get("puan")
        sonuc["akd_sebepleri"] = (akd.get("sebepler") or [])[:3]
    else:
        sonuc["akd_durumu"] = "Bu hisse için AKD verisi henüz çekilmemiş."
    return sonuc


def _portfoy_calistir(kaynaklar):
    sonuc = {}
    try:
        import portfoy_takip as pt
        pozlar = pt.pozisyonlari_getir()
        if pozlar:
            fiyatlar = {}
            for p in pozlar:
                df = kaynaklar["gecmis"](p["sembol"])
                if df is not None and len(df):
                    fiyatlar[p["sembol"]] = float(df["Close"].iloc[-1])
            durum = pt.portfoy_durumu(fiyatlar)
            sonuc["gercek_portfoy"] = {
                "toplam_deger_TL": _sayi(durum.get("toplam_deger"), 0),
                "toplam_kar_zarar_yuzde": _sayi(durum.get("toplam_kar_zarar_yuzde"), 2),
                "pozisyonlar": durum.get("pozisyonlar"),
            }
        else:
            sonuc["gercek_portfoy"] = "Portföyünüze henüz hisse eklenmemiş."
    except Exception as e:
        sonuc["gercek_portfoy"] = f"(okunamadı: {e})"

    try:
        import sanal_yatirimci as sv
        pozlar = sv.portfoy_getir().get("pozisyonlar", [])
        fiyatlar = {}
        for p in pozlar:
            df = kaynaklar["gecmis"](p["sembol"])
            if df is not None and len(df):
                fiyatlar[p["sembol"]] = float(df["Close"].iloc[-1])
        d = sv.portfoy_degeri(fiyatlar)
        sonuc["sanal_portfoy"] = {
            "toplam_deger_TL": _sayi(d.get("toplam_deger"), 0),
            "getiri_yuzde": _sayi(d.get("toplam_getiri_yuzde"), 2),
            "gun_sayisi": d.get("gun_sayisi"),
            "fiyati_alinamayan": d.get("fiyatsiz_semboller"),
        }
    except Exception as e:
        sonuc["sanal_portfoy"] = f"(okunamadı: {e})"
    return sonuc


_TARAMA_YOK_MESAJI = (
    "Tarama önbelleği BOŞ — henüz hiç tam tarama çalışmamış. "
    "Kullanıcıya şunu söyle: ya 'Öne Çıkan Hisseler' sekmesinden "
    "'CANLI TARA' düğmesine bassın, ya da ARKA_PLAN_TARAMA.bat dosyasını "
    "bir kez çalıştırsın. Tarama bittikten sonra bu liste anında gelir.")


def _kapsam_filtrele(df, kapsam):
    """Tabloyu BIST30/BIST100 gibi bir endeks kapsamına indirger.

    Kapsam listesi veri katmanından gelir; alınamazsa filtre UYGULANMAZ ve
    tablo olduğu gibi döner (yanlışlıkla boş liste göstermemek için).
    """
    if not kapsam or df is None or "Hisse" not in getattr(df, "columns", []):
        return df, None
    anahtar = str(kapsam).upper().replace(" ", "").replace("BIST", "")
    harita = {"30": "BIST30", "100": "BIST100", "TUM": "TUM", "TÜM": "TUM"}
    hedef = harita.get(anahtar)
    if not hedef or hedef == "TUM":
        return df, None
    try:
        import veri_katmani as vk
        liste = set(vk.sembol_listesi(hedef) or [])
    except Exception:
        return df, None
    if not liste:
        return df, None
    return df[df["Hisse"].isin(liste)], hedef


def _tarama_calistir(adet, kapsam=None):
    try:
        import tarama_onbellek as tob
        tarama_df, _vade, _x, zaman, taze = tob.oku()
    except Exception as e:
        return {"hata": f"Tarama önbelleği okunamadı: {e}"}
    if tarama_df is None or len(tarama_df) == 0:
        return {"hata": _TARAMA_YOK_MESAJI}
    tarama_df, uygulanan = _kapsam_filtrele(tarama_df, kapsam)
    if len(tarama_df) == 0:
        return {"hata": f"{kapsam} kapsamında puanlanmış hisse bulunamadı."}
    n = max(1, min(int(adet or 10), 25))
    kolonlar = [k for k in ("Hisse", "Puan", "Karar", "Fiyat", "1 Ay %")
                if k in tarama_df.columns]
    return {
        "tarama_zamani": zaman,
        "veri_taze_mi": taze,
        "kapsam": uygulanan or "TÜM BIST",
        "en_iyi_hisseler": tarama_df.head(n)[kolonlar].to_dict("records"),
    }


def _yukselecek_calistir(vade=None, adet=None, kapsam=None):
    """'Yükselebilecek Hisseler' sekmesinin verisi — vade bazlı AL sinyalleri.

    NEDEN AYRI ARAÇ: Kullanıcı "yükselebilecek hisseler" dediğinde kastettiği
    tablo budur; 'Öne Çıkan' tablosundan FARKLIDIR (o, genel puana göre
    sıralar). Bu araç eklenmeden önce asistan bu soruya "veri yok" diyordu.
    """
    try:
        import tarama_onbellek as tob
        _tarama, vade_df, _x, zaman, taze = tob.oku()
    except Exception as e:
        return {"hata": f"Tarama önbelleği okunamadı: {e}"}
    if vade_df is None or len(vade_df) == 0:
        return {"hata": _TARAMA_YOK_MESAJI}

    vade_df, uygulanan = _kapsam_filtrele(vade_df, kapsam)
    if len(vade_df) == 0:
        return {"hata": f"{kapsam} kapsamında değerlendirilmiş hisse bulunamadı."}

    n = max(1, min(int(adet or 5), 20))
    istenen = None
    if vade:
        v = str(vade).strip().lower()
        for aday in ("kısa", "kisa", "orta", "uzun"):
            if aday in v:
                istenen = {"kisa": "Kısa", "kısa": "Kısa",
                           "orta": "Orta", "uzun": "Uzun"}[aday]
                break

    sonuc = {"tarama_zamani": zaman, "veri_taze_mi": taze,
             "kapsam": uygulanan or "TÜM BIST"}
    for vade_adi in (["Kısa", "Orta", "Uzun"] if not istenen else [istenen]):
        if vade_adi not in vade_df.columns:
            continue
        # 🟢 = o vadede AL sinyali (bkz. analiz_motoru.vade_taramasi)
        secim = vade_df[vade_df[vade_adi].astype(str).str.contains("🟢")]
        puan_kolonu = f"{vade_adi} Puan"
        if puan_kolonu in secim.columns:
            secim = secim.sort_values(puan_kolonu, ascending=False)
        kolonlar = [k for k in ("Hisse", vade_adi, puan_kolonu, "Genel Puan",
                                "Fiyat", "1 Ay %") if k in secim.columns]
        sonuc[f"{vade_adi}_vade_AL_sinyalleri"] = (
            secim.head(n)[kolonlar].to_dict("records") if len(secim)
            else "Bu vadede AL sinyali veren hisse yok.")
    return sonuc


def _karsilastir_calistir(semboller, kaynaklar):
    cikti = []
    for s in (semboller or [])[:5]:
        cikti.append(_analiz_calistir(str(s).upper().strip(), kaynaklar))
    return {"karsilastirma": cikti}


# ── Genişletilmiş veri araçları ──────────────────────────────────────────────
# Bu araçlar "her soruya cevap verebilme" için eklendi. Fikir şudur: motorun
# ÖZETİNİ vermek yerine HAM VERİYİ tarih/sayı olarak sunmak. Böylece model
# "en son hangi hafta yükseldi", "kaç haftadır düşüyor", "F/K'sı kaç" gibi
# önceden düşünülmemiş soruları da GERÇEK sayılarla cevaplayabilir.

def _temel_calistir(sembol, kaynaklar):
    t = kaynaklar["temel"](sembol) or {}
    if not t:
        return {"hata": f"{sembol} için temel veri alınamadı."}
    pd_deger = _sayi(t.get("piyasa_degeri"), 0)
    tem = _sayi(t.get("temettu_verimi"), 4)
    if tem is not None and tem < 1:
        tem = round(tem * 100, 2)          # 0.043 → %4,3
    return {
        "sembol": sembol,
        "sirket_adi": t.get("sirket_adi"),
        "sektor": t.get("sektor"),
        "son_fiyat_TL": _sayi(t.get("son_fiyat")),
        "FK_fiyat_kazanc": _sayi(t.get("fk"), 2),
        "PDDD_piyasa_defter": _sayi(t.get("pddd"), 2),
        "piyasa_degeri_TL": pd_deger,
        "piyasa_degeri_milyar_TL": round(pd_deger / 1e9, 2) if pd_deger else None,
        "temettu_verimi_yuzde": tem,
        "halka_aciklik_yuzde": _sayi(t.get("halka_aciklik"), 1),
        "yabanci_orani_yuzde": _sayi(t.get("yabanci_orani"), 1),
    }


def _donem_getirileri_calistir(sembol, periyot, son, kaynaklar):
    """Son N dönemin getirisi — TARİHLERİYLE.

    "En son hangi hafta yükseldi?" gibi sorular ancak tarihli ham seri
    verilirse doğru cevaplanabilir; özet puanlarla cevaplanamaz.
    """
    df = kaynaklar["gecmis"](sembol)
    if df is None or len(df) == 0:
        return {"hata": f"{sembol} için fiyat verisi bulunamadı."}
    p = str(periyot or "haftalik").lower()
    kural, ad = ("W", "hafta")
    if p.startswith("gun"):
        kural, ad = ("D", "gün")
    elif p.startswith("ay"):
        kural, ad = ("ME", "ay")

    kapanis = df["Close"].resample(kural).last().dropna()
    if kural == "D":
        kapanis = df["Close"].dropna()
    getiri = kapanis.pct_change().dropna() * 100
    n = max(1, min(int(son or 12), 60))
    dilim = getiri.tail(n)

    satirlar = [{"donem_bitis": t.strftime("%d.%m.%Y"),
                 "getiri_yuzde": round(float(v), 2),
                 "yon": "yükseliş" if v > 0 else ("düşüş" if v < 0 else "yatay")}
                for t, v in dilim.items()]

    # "En son ne zaman yükseldi/düştü" sorusunu doğrudan cevaplayalım
    son_artis = next((s for s in reversed(satirlar) if s["getiri_yuzde"] > 0), None)
    son_dusus = next((s for s in reversed(satirlar) if s["getiri_yuzde"] < 0), None)
    # Kaç dönemdir aynı yönde
    ardisik, yon0 = 0, None
    for s in reversed(satirlar):
        y = s["yon"]
        if yon0 is None:
            yon0 = y
        if y == yon0 and y != "yatay":
            ardisik += 1
        else:
            break

    return {
        "sembol": sembol, "periyot": ad, "donem_sayisi": len(satirlar),
        "donemler_eskiden_yeniye": satirlar,
        f"en_son_yukselen_{ad}": son_artis,
        f"en_son_dusen_{ad}": son_dusus,
        "son_ardisik_seri": f"{ardisik} {ad}dır {yon0}" if yon0 else None,
        "en_iyi_donem": max(satirlar, key=lambda s: s["getiri_yuzde"]) if satirlar else None,
        "en_kotu_donem": min(satirlar, key=lambda s: s["getiri_yuzde"]) if satirlar else None,
    }


def _fiyat_ozet_calistir(sembol, kaynaklar):
    df = kaynaklar["gecmis"](sembol)
    if df is None or len(df) == 0:
        return {"hata": f"{sembol} için fiyat verisi bulunamadı."}
    c = df["Close"].dropna()
    son = float(c.iloc[-1])

    def getiri(gun):
        if len(c) <= gun:
            return None
        return round(100 * (son / float(c.iloc[-gun - 1]) - 1), 2)

    pencere = c.tail(252)
    zirve, dip = float(pencere.max()), float(pencere.min())
    vol = float(c.pct_change().tail(252).std() * (252 ** 0.5) * 100)
    return {
        "sembol": sembol,
        "son_fiyat_TL": round(son, 2),
        "son_veri_tarihi": c.index[-1].strftime("%d.%m.%Y"),
        "getiri_1_hafta_yuzde": getiri(5),
        "getiri_1_ay_yuzde": getiri(21),
        "getiri_3_ay_yuzde": getiri(63),
        "getiri_6_ay_yuzde": getiri(126),
        "getiri_1_yil_yuzde": getiri(252),
        "zirve_52hafta_TL": round(zirve, 2),
        "dip_52hafta_TL": round(dip, 2),
        "zirveden_uzaklik_yuzde": round(100 * (son / zirve - 1), 2) if zirve else None,
        "dipten_yukseklik_yuzde": round(100 * (son / dip - 1), 2) if dip else None,
        "yillik_volatilite_yuzde": round(vol, 1),
        "ortalama_gunluk_hacim_20g": int(df["Volume"].tail(20).mean()),
    }


def _gostergeler_calistir(sembol, kaynaklar):
    df = kaynaklar["gecmis"](sembol)
    if df is None or len(df) < 60:
        return {"hata": f"{sembol} için yeterli fiyat verisi yok."}
    c = df["Close"]
    son = float(c.iloc[-1])
    macd_h, macd_s, macd_hist = am.macd(c)
    ust, orta, alt = am.bollinger(c)
    k, d = am.stochastic(df)

    def uzaklik(n):
        m = am.sma(c, n).iloc[-1]
        if m != m:
            return None
        return {"deger_TL": round(float(m), 2),
                "fiyat_uzakligi_yuzde": round(100 * (son / float(m) - 1), 2)}

    baglam = am.trend_baglami(df)
    return {
        "sembol": sembol, "son_fiyat_TL": round(son, 2),
        "trend_yonu": baglam["yon"],
        "RSI_14": _sayi(am.rsi(c).iloc[-1], 1),
        "MACD": _sayi(macd_h.iloc[-1], 3),
        "MACD_sinyal": _sayi(macd_s.iloc[-1], 3),
        "MACD_histogram": _sayi(macd_hist.iloc[-1], 3),
        "Stokastik_K": _sayi(k.iloc[-1], 1),
        "ATR_14_TL": _sayi(am.atr(df).iloc[-1], 2),
        "Bollinger_ust_TL": _sayi(ust.iloc[-1]),
        "Bollinger_alt_TL": _sayi(alt.iloc[-1]),
        "MA20": uzaklik(20), "MA50": uzaklik(50), "MA200": uzaklik(200),
        "MFI_14": _sayi(am.mfi(df).iloc[-1], 1),
        "CMF_20": _sayi(am.cmf(df).iloc[-1], 3),
    }


def _haberler_calistir(sembol):
    try:
        import veri_katmani as vk
        haberler = vk.kap_haberleri(sembol) or []
    except Exception as e:
        return {"hata": f"KAP bildirimleri alınamadı: {e}"}
    if not haberler:
        return {"bilgi": f"{sembol} için KAP bildirimi bulunamadı."}
    cikti = []
    for h in haberler[:8]:
        if isinstance(h, dict):
            cikti.append({"tarih": h.get("date") or h.get("tarih") or "",
                          "baslik": h.get("title") or h.get("baslik") or str(h)})
        else:
            cikti.append({"baslik": str(h)})
    return {"sembol": sembol, "kap_bildirimleri": cikti}


def _analist_calistir(sembol):
    try:
        import veri_katmani as vk
        a = vk.analist_verileri(sembol) or {}
    except Exception as e:
        return {"hata": f"Analist verisi alınamadı: {e}"}
    if not a or all(v is None for v in a.values()):
        return {"bilgi": f"{sembol} için analist verisi bulunamadı."}
    return {"sembol": sembol, "analist_verileri": a}


def _hisse_ara_calistir(metin):
    """Şirket adından hisse kodu bulur (ör. 'enka' → ENKAI)."""
    try:
        import hisse_adlari as ha
        import veri_katmani as vk
        adlar = ha.adlari_getir()
        semboller = vk.sembol_listesi("TUM")
        bulunan = ha.ara(str(metin), semboller, adlar, ust_sinir=8)
    except Exception as e:
        return {"hata": f"Arama yapılamadı: {e}"}
    if not bulunan:
        return {"bilgi": f"'{metin}' ile eşleşen hisse bulunamadı."}
    return {"arama": metin,
            "bulunanlar": [{"kod": s, "ad": adlar.get(s, "")} for s in bulunan]}


# ═════════════════════════════════════════════════════════════════════════════
# SERBEST FİLTRELEME MOTORU — "her soruya cevap" yeteneğinin çekirdeği
# ═════════════════════════════════════════════════════════════════════════════
# NEDEN BÖYLE TASARLANDI:
# Kullanıcının istediği esneklik ("en çok düşen 5 hisse", "F/K'sı 10 altı olup
# RSI'ı düşük olanlar") sabit araçlarla karşılanamaz — sonsuz sayıda soru var.
# İki seçenek vardı:
#   (a) Dil modeline Python kodu yazdırıp çalıştırmak → SINIRSIZ ama TEHLİKELİ.
#       Model, kullanıcının diskindeki dosyaları silen bir kod da yazabilir.
#   (b) Bildirimsel (declarative) bir filtre dili → neredeyse aynı esneklik,
#       KOD ÇALIŞTIRMA RİSKİ YOK.
# (b) seçildi. Model yalnızca {alan, operatör, değer} üçlüleri gönderir; hangi
# alanların ve operatörlerin geçerli olduğuna BİZ karar veririz. Model uydurma
# bir alan adı gönderirse istek reddedilir ve geçerli alanlar kendisine
# bildirilir (kendini düzeltebilsin diye).

_OPERATORLER = {
    ">":  lambda s, d: pd.to_numeric(s, errors="coerce") > d,
    ">=": lambda s, d: pd.to_numeric(s, errors="coerce") >= d,
    "<":  lambda s, d: pd.to_numeric(s, errors="coerce") < d,
    "<=": lambda s, d: pd.to_numeric(s, errors="coerce") <= d,
    "==": lambda s, d: s.astype(str).str.strip().str.upper() == str(d).strip().upper(),
    "!=": lambda s, d: s.astype(str).str.strip().str.upper() != str(d).strip().upper(),
    "içerir": lambda s, d: s.astype(str).str.upper().str.contains(str(d).upper(), na=False),
    "icerir": lambda s, d: s.astype(str).str.upper().str.contains(str(d).upper(), na=False),
}


def _tablo_getir(kaynak):
    """Filtrelenecek tabloyu önbellekten okur."""
    try:
        import tarama_onbellek as tob
        tarama_df, vade_df, _x, zaman, taze = tob.oku()
    except Exception as e:
        return None, None, None, f"Tarama önbelleği okunamadı: {e}"
    df = vade_df if str(kaynak or "").lower().startswith("vade") else tarama_df
    if df is None or len(df) == 0:
        return None, None, None, _TARAMA_YOK_MESAJI
    return df, zaman, taze, None


def _alan_coz(df, istenen):
    """Model'in yazdığı alan adını gerçek sütuna eşler (büyük/küçük harf ve
    kısmi eşleşme toleranslı — 'puan' → 'Puan', '1 ay' → '1 Ay %')."""
    if not istenen:
        return None
    hedef = str(istenen).strip().lower()
    for k in df.columns:
        if str(k).strip().lower() == hedef:
            return k
    for k in df.columns:
        if hedef in str(k).strip().lower():
            return k
    return None


def _alanlar_calistir(kaynak=None):
    df, zaman, taze, hata = _tablo_getir(kaynak)
    if hata:
        return {"hata": hata}
    ornek = {}
    for k in df.columns:
        try:
            deger = df[k].dropna().iloc[0]
            ornek[str(k)] = str(deger)[:30]
        except Exception:
            ornek[str(k)] = "—"
    return {"tarama_zamani": zaman, "hisse_sayisi": len(df),
            "filtrelenebilir_alanlar": ornek,
            "kullanilabilir_operatorler": [">", ">=", "<", "<=", "==", "!=", "içerir"]}


def _filtre_calistir(kosullar=None, sirala=None, yon=None, adet=None,
                      kaynak=None, kapsam=None):
    df, zaman, taze, hata = _tablo_getir(kaynak)
    if hata:
        return {"hata": hata}

    df, uygulanan_kapsam = _kapsam_filtrele(df, kapsam)
    if len(df) == 0:
        return {"hata": f"{kapsam} kapsamında hisse bulunamadı."}

    uygulanan, reddedilen = [], []
    for kosul in (kosullar or [])[:6]:
        if not isinstance(kosul, dict):
            continue
        alan = _alan_coz(df, kosul.get("alan"))
        op = str(kosul.get("operator", "")).strip()
        deger = kosul.get("deger")
        if alan is None:
            reddedilen.append(f"bilinmeyen alan: {kosul.get('alan')}")
            continue
        if op not in _OPERATORLER:
            reddedilen.append(f"bilinmeyen operatör: {op}")
            continue
        try:
            maske = _OPERATORLER[op](df[alan], deger)
            df = df[maske.fillna(False)]
            uygulanan.append(f"{alan} {op} {deger}")
        except Exception as e:
            reddedilen.append(f"{alan} {op} {deger} → {e}")

    sirala_alan = _alan_coz(df, sirala) if sirala else None
    if sirala_alan is not None and len(df):
        artan = str(yon or "azalan").lower().startswith("art")
        try:
            df = df.assign(_s=pd.to_numeric(df[sirala_alan], errors="coerce")) \
                   .sort_values("_s", ascending=artan, na_position="last") \
                   .drop(columns="_s")
        except Exception:
            df = df.sort_values(sirala_alan, ascending=artan, na_position="last")

    n = max(1, min(int(adet or 10), 30))
    gosterilecek = [k for k in df.columns
                    if not str(k).endswith("Puan") or str(k) == "Puan"][:9]
    return {
        "tarama_zamani": zaman, "veri_taze_mi": taze,
        "kapsam": uygulanan_kapsam or "TÜM BIST",
        "uygulanan_kosullar": uygulanan or "(koşul yok — tüm hisseler)",
        "gecersiz_kosullar": reddedilen or None,
        "siralama": f"{sirala_alan} ({'artan' if str(yon or 'azalan').lower().startswith('art') else 'azalan'})"
                    if sirala_alan is not None else "(sıralama yok)",
        "eslesen_hisse_sayisi": int(len(df)),
        "sonuclar": df.head(n)[gosterilecek].to_dict("records"),
    }


def komutlari_calistir(komutlar: list, kaynaklar: dict) -> tuple:
    """Komutları sırayla çalıştırır.

    kaynaklar: app.py'nin sağladığı önbellekli veri fonksiyonları sözlüğü —
      gechmis/temel/yabanci/endeks/rejim/akd. Böylece bu modül Streamlit'e
      HİÇ bağımlı değildir ve ayrıca test edilebilir.

    Dönüş: (sonuclar_listesi, yan_etkiler)
      yan_etkiler: arayüzün uygulaması gereken işlemler
                   {"sayfaya_git": {...}, "yenile": bool}
    """
    sonuclar = []
    yan_etkiler = {}
    for k in komutlar[:10]:                 # üst sınır: kaçak döngüye karşı
        arac = str(k.get("arac", "")).strip()
        sembol = str(k.get("sembol", "")).upper().strip()
        try:
            if arac == "analiz" and sembol:
                sonuclar.append({arac: _analiz_calistir(sembol, kaynaklar)})
            elif arac == "risk" and sembol:
                sonuclar.append({arac: _risk_calistir(sembol, k.get("alis_fiyati"),
                                                      kaynaklar)})
            elif arac == "takas" and sembol:
                sonuclar.append({arac: _takas_calistir(sembol, kaynaklar)})
            elif arac == "portfoy":
                sonuclar.append({arac: _portfoy_calistir(kaynaklar)})
            elif arac == "tarama":
                sonuclar.append({arac: _tarama_calistir(k.get("adet"),
                                                        k.get("kapsam"))})
            elif arac == "yukselecek":
                sonuclar.append({arac: _yukselecek_calistir(
                    k.get("vade"), k.get("adet"), k.get("kapsam"))})
            elif arac == "karsilastir":
                sonuclar.append({arac: _karsilastir_calistir(k.get("semboller"),
                                                            kaynaklar)})
            elif arac == "temel" and sembol:
                sonuclar.append({arac: _temel_calistir(sembol, kaynaklar)})
            elif arac == "donem_getirileri" and sembol:
                sonuclar.append({arac: _donem_getirileri_calistir(
                    sembol, k.get("periyot"), k.get("son"), kaynaklar)})
            elif arac == "fiyat_ozet" and sembol:
                sonuclar.append({arac: _fiyat_ozet_calistir(sembol, kaynaklar)})
            elif arac == "gostergeler" and sembol:
                sonuclar.append({arac: _gostergeler_calistir(sembol, kaynaklar)})
            elif arac == "haberler" and sembol:
                sonuclar.append({arac: _haberler_calistir(sembol)})
            elif arac == "analist" and sembol:
                sonuclar.append({arac: _analist_calistir(sembol)})
            elif arac == "alanlar":
                sonuclar.append({arac: _alanlar_calistir(k.get("kaynak"))})
            elif arac == "filtre":
                sonuclar.append({arac: _filtre_calistir(
                    k.get("kosullar"), k.get("sirala"), k.get("yon"),
                    k.get("adet"), k.get("kaynak"), k.get("kapsam"))})
            elif arac == "hisse_ara":
                sonuclar.append({arac: _hisse_ara_calistir(
                    k.get("metin") or k.get("sorgu") or sembol)})
            elif arac in ("favori_ekle", "favori_cikar") and sembol:
                import favoriler as fav
                if arac == "favori_ekle":
                    fav.ekle(sembol)
                    sonuclar.append({arac: f"{sembol} favorilere eklendi."})
                else:
                    fav.cikar(sembol)
                    sonuclar.append({arac: f"{sembol} favorilerden çıkarıldı."})
                yan_etkiler["yenile"] = True
            elif arac == "sayfaya_git":
                sekme = str(k.get("sekme", "")).strip().lower()
                if sekme in _GECERLI_SEKMELER:
                    yan_etkiler["sayfaya_git"] = {"sekme": sekme, "sembol": sembol}
                    sonuclar.append({arac: f"'{_GECERLI_SEKMELER[sekme]}' sekmesi hazırlandı."})
                else:
                    sonuclar.append({arac: f"Bilinmeyen sekme: {sekme}"})
            else:
                sonuclar.append({"bilinmeyen_komut": k})
        except Exception as e:
            sonuclar.append({arac or "hata": f"Çalıştırılamadı: {e}"})
    return sonuclar, yan_etkiler


# ─────────────────────────────────────────────────────────────────────────────
# 5) ANA AKIŞ — iki fazlı yanıt üretimi
# ─────────────────────────────────────────────────────────────────────────────
def yanitla(kullanici_mesaji: str, gecmis: list, kaynaklar: dict,
             baglam: str = "") -> dict:
    """Kullanıcı mesajına cevap üretir.

    gecmis: [{"role":"user"/"assistant","content":...}] — son birkaç tur.
    Dönüş: {"yanit": str, "saglayici": str|None, "komutlar": [...],
            "yan_etkiler": {...}, "arac_sonuclari": [...]}
    """
    if not la.sohbet_hazir_mi():
        return {"yanit": ("Sohbet asistanı için bir yapay zeka anahtarı gerekiyor. "
                         "`.env` dosyasına `GROQ_API_KEY` (console.groq.com — ücretsiz) "
                         "veya `NVIDIA_API_KEY` (build.nvidia.com — ücretsiz) ekleyin."),
                "saglayici": None, "komutlar": [], "yan_etkiler": {},
                "arac_sonuclari": []}

    son_gecmis = [m for m in (gecmis or []) if m.get("role") in ("user", "assistant")][-6:]

    # ── FAZ 1: hangi araçlar çağrılacak? ─────────────────────────────────
    faz1_mesajlar = ([{"role": "system", "content": _sistem_promptu_faz1(baglam)}]
                     + son_gecmis
                     + [{"role": "user", "content": kullanici_mesaji}])
    plan_metni, saglayici = la.sohbet_tamamla(faz1_mesajlar, max_tokens=400,
                                              sicaklik=0.0)
    if plan_metni is None:
        return {"yanit": f"Yapay zekaya ulaşılamadı — {saglayici}",
                "saglayici": None, "komutlar": [], "yan_etkiler": {},
                "arac_sonuclari": []}

    komutlar = komutlari_ayikla(plan_metni)

    # ── Araçları ÇALIŞTIR (gerçek sayılar burada üretilir) ───────────────
    arac_sonuclari, yan_etkiler = komutlari_calistir(komutlar, kaynaklar)

    if arac_sonuclari:
        sonuc_metni = json.dumps(arac_sonuclari, ensure_ascii=False, indent=1,
                                 default=str)
    else:
        sonuc_metni = ("(Araç çağrılmadı — kullanıcı sohbet ediyor ya da genel "
                       "bir soru sordu. Yazılımın ne yapabildiğini kısaca anlat, "
                       "sayı uydurma.)")

    # ── FAZ 2: cevabı SADECE gerçek sonuçlarla yaz ───────────────────────
    faz2_mesajlar = ([{"role": "system",
                       "content": _sistem_promptu_faz2(baglam, sonuc_metni)}]
                     + son_gecmis
                     + [{"role": "user", "content": kullanici_mesaji}])
    yanit, saglayici2 = la.sohbet_tamamla(faz2_mesajlar, max_tokens=900,
                                          sicaklik=0.3)
    if yanit is None:
        # Model cevabı yazamadıysa bile araç sonuçlarını KAYBETMEYELİM —
        # kullanıcı en azından ham veriyi görsün.
        yanit = ("Yapay zeka cevabı üretemedi ama işlem yapıldı. Ham sonuç:\n\n"
                 + "```json\n" + sonuc_metni[:1500] + "\n```")
        saglayici2 = None

    # ── ÖĞRENME MOTORU: her sorguyu kaydet ───────────────────────────────
    # NEDEN: Hangi soruların sorulduğu ve hangilerinde ARAÇ SEÇİLEMEDİĞİ,
    # yazılımın eksik yeteneklerini bulmanın en doğrudan yoludur. Kayıt
    # başarısız olsa bile sohbet ASLA bozulmamalıdır — bu yüzden sessizce
    # yutulur.
    try:
        import ogrenme_motoru as om
        om.sorgu_kaydet(kullanici_mesaji, komutlar,
                        saglayici=saglayici2 or saglayici,
                        basarili=bool(yanit))
    except Exception:
        pass

    return {"yanit": yanit, "saglayici": saglayici2 or saglayici,
            "komutlar": komutlar, "yan_etkiler": yan_etkiler,
            "arac_sonuclari": arac_sonuclari}
