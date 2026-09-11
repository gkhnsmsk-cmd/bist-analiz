# -*- coding: utf-8 -*-
"""
ozet_metni.py — Teknik çıktıları SADE TÜRKÇE duruma çeviren özet üreticisi.
══════════════════════════════════════════════════════════════════════════════
AMAÇ: Her modül teknik ayrıntısını (puanlar, göstergeler, tablolar) korurken,
üstünde "bu ne anlama geliyor?" sorusunu jargonsuz yanıtlayan kısa bir metin
göstersin. Rakam okumak ile durumu anlamak farklı şeylerdir.

YAZIM İLKELERİ (bilinçli seçimler):
  • Jargon kullanılmaz; kullanılması zorunluysa aynı cümlede açıklanır.
  • Sayı tekrarlanmaz, YORUMLANIR. "Puan 68" demek yerine "AL bölgesinde,
    yani teknik tablo olumlu" denir.
  • ABARTILMAZ. Bu bir satış metni değil; zayıf tarafı da açıkça söylenir.
  • Belirsizlik gizlenmez. Az veriyle güçlü cümle kurulmaz.
  • Hiçbir özet "al" / "sat" emri vermez; durumu tarif eder, kararı kullanıcı verir.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Teknik boyut adlarının sade karşılıkları
_BOYUT_SADE = {
    "Kısa Vade (1-4 hafta)": "önümüzdeki birkaç haftalık görünüm",
    "Orta Vade (1-6 ay)": "önümüzdeki birkaç aylık görünüm",
    "Uzun Vade (6 ay+)": "uzun vadeli sağlamlık",
    "Takas / Para Akışı": "hisseye para girip çıkması",
    "Fon / Kurumsal": "büyük kurumsal yatırımcıların ilgisi",
}


def _sayi(x, ondalik=1):
    try:
        d = float(x)
        if not np.isfinite(d):
            return None
        return d
    except (TypeError, ValueError):
        return None


def _puan_sozu(puan) -> str:
    """0-100 puanı sade bir duruma çevirir."""
    p = _sayi(puan)
    if p is None:
        return "belirsiz"
    if p >= 72:  return "çok olumlu"
    if p >= 62:  return "olumlu"
    if p >= 52:  return "kararsız ama hafif olumlu"
    if p >= 40:  return "zayıf"
    return "olumsuz"


# ─────────────────────────────────────────────────────────────────────────────
# 1) Piyasa rejimi
# ─────────────────────────────────────────────────────────────────────────────
def rejim_ozeti(rejim: dict) -> str:
    if not rejim:
        return ""
    p = _sayi(rejim.get("puan"))
    if p is None:
        return ""
    if p >= 62:
        return ("**Piyasanın genel havası şu an olumlu.** Endeks yükseliş eğiliminde ve "
                "kur tarafı sakin. Böyle dönemlerde hisselerin çoğu birlikte yükselme "
                "eğilimindedir — yani iyi görünen bir hisse, kendi başarısından çok genel "
                "havadan da yükseliyor olabilir.")
    if p >= 45:
        return ("**Piyasanın genel havası kararsız.** Ne belirgin bir yükseliş ne de çöküş "
                "var. Bu tür dönemlerde hisseler birbirinden ayrışır; genel endekse değil, "
                "tek tek hisselerin kendi durumuna bakmak daha anlamlıdır.")
    return ("**Piyasanın genel havası olumsuz.** Endeks zayıf ve/veya kur tarafında gerginlik "
            "var. Böyle dönemlerde teknik olarak iyi görünen hisseler bile genel satış "
            "baskısıyla düşebilir — bu, en iyi seçimlerin bile zarar edebileceği anlamına gelir.")


# ─────────────────────────────────────────────────────────────────────────────
# 2) Tek hisse analizi
# ─────────────────────────────────────────────────────────────────────────────
def hisse_ozeti(analiz: dict, temel: dict = None, akd_sinyali: dict = None) -> str:
    if not analiz:
        return ""
    temel = temel or {}
    sembol = analiz.get("sembol", "Bu hisse")
    puan = _sayi(analiz.get("genel_puan"))
    karar = analiz.get("karar", "")

    s = []
    s.append(f"**{sembol} şu an ne durumda?** Genel teknik tablo {_puan_sozu(puan)} "
             f"görünüyor ve sistem bunu \"{karar}\" olarak sınıflandırıyor.")

    # En güçlü ve en zayıf boyut
    puanlar = {k: _sayi(v) for k, v in (analiz.get("puanlar") or {}).items()}
    puanlar = {k: v for k, v in puanlar.items() if v is not None}
    if len(puanlar) >= 2:
        en_iyi = max(puanlar, key=puanlar.get)
        en_kotu = min(puanlar, key=puanlar.get)
        if puanlar[en_iyi] - puanlar[en_kotu] >= 8:
            s.append(f"En güçlü tarafı **{_BOYUT_SADE.get(en_iyi, en_iyi)}**, en zayıf tarafı ise "
                     f"**{_BOYUT_SADE.get(en_kotu, en_kotu)}**.")
        else:
            s.append("Tüm boyutlar birbirine yakın — yani belirgin bir güçlü ya da zayıf "
                     "taraf öne çıkmıyor, tablo dengeli.")

    # Gerçekleşmiş getiriler (bunlar tahmin değil, olan biten)
    g1, g3 = _sayi(analiz.get("getiri_1a")), _sayi(analiz.get("getiri_3a"))
    if g1 is not None and g3 is not None:
        if g1 > 0 and g3 > 0:
            gecmis = f"Son 1 ayda %{g1:+.1f}, son 3 ayda %{g3:+.1f} ile yükselişte olmuş."
        elif g1 < 0 and g3 < 0:
            gecmis = f"Son 1 ayda %{g1:+.1f}, son 3 ayda %{g3:+.1f} ile düşüşte olmuş."
        else:
            gecmis = (f"Son 1 ayda %{g1:+.1f}, son 3 ayda %{g3:+.1f} — kısa ve orta vadeli "
                      "yön birbirinden farklı, yani hisse yön değiştiriyor olabilir.")
        s.append(gecmis + " *(Bunlar gerçekleşmiş getiriler, gelecek tahmini değil.)*")

    # Değerleme
    fk, pddd = _sayi(temel.get("fk")), _sayi(temel.get("pddd"))
    if fk is not None and fk > 0:
        if fk < 8:
            s.append(f"Değerleme tarafında F/K {fk:.1f} ile ucuz sayılır — şirket kazancına "
                     "göre hisse fiyatı düşük. *(Ucuz olması her zaman iyi demek değildir; "
                     "piyasa bir sorun görüyor da olabilir.)*")
        elif fk > 35:
            s.append(f"Değerleme tarafında F/K {fk:.1f} ile pahalı sayılır — yatırımcılar "
                     "gelecekte yüksek büyüme bekliyor demektir; beklenti tutmazsa sert "
                     "düşüş riski taşır.")

    # AKD (Aracı Kurum Dağılımı) sinyalinin görüşü — geçmiş örüntü analizinin
    # yerini aldı (bkz. OKU_BENI.txt): geçmişin istatistiksel tekrarı yerine
    # BUGÜN kimin alıp kimin sattığına dayanan somut bir veri.
    if akd_sinyali and akd_sinyali.get("puan") is not None:
        akd_karari = akd_sinyali.get("karar")
        sebep = akd_sinyali["sebepler"][0] if akd_sinyali.get("sebepler") else None
        if akd_karari:
            s.append(f"AKD (aracı kurum dağılımı) tarafı ise **{akd_karari}** diyor: "
                     "bugün hangi aracı kurumların net alıcı/satıcı olduğuna bakılıyor"
                     + (f" — {sebep}" if sebep else "") + ".")

    # Stop/hedef
    stop, hedef = _sayi(analiz.get("stop_oneri")), _sayi(analiz.get("hedef_oneri"))
    if stop and hedef:
        s.append(f"Risk yönetimi için referans seviyeler: fiyat **{stop:.2f} TL** altına "
                 f"inerse teknik tablo bozulmuş sayılır; **{hedef:.2f} TL** ise yukarı "
                 "yönde makul bir hedef bölge. *(Bunlar oynaklığa göre hesaplanmış referanslar, "
                 "kesin seviyeler değil.)*")

    s.append("\n⚠️ **Bunlar bir tahmin değil, bugünkü teknik tablonun özetidir.** Puanlar "
             "geleceği bilmez; geçmiş fiyat ve hacim hareketlerinden çıkarılan işaretlerdir. "
             "Yatırım tavsiyesi değildir.")
    return " ".join(s[:1]) + "\n\n" + "\n\n".join(s[1:])


# ─────────────────────────────────────────────────────────────────────────────
# 3) Öne Çıkan Hisseler (tarama)
# ─────────────────────────────────────────────────────────────────────────────
def tarama_ozeti(tablo: pd.DataFrame) -> str:
    if tablo is None or len(tablo) == 0:
        return ""
    n = len(tablo)
    puanlar = pd.to_numeric(tablo.get("Puan"), errors="coerce").dropna()
    if puanlar.empty:
        return ""
    guclu = int((puanlar >= 62).sum())
    zayif = int((puanlar < 40).sum())
    en_iyi = tablo.head(3)["Hisse"].tolist() if "Hisse" in tablo.columns else []

    s = [f"**Tarama sonucu:** {n} hisse incelendi. Bunlardan **{guclu} tanesi** teknik olarak "
         f"olumlu bölgede (62 puan üstü), **{zayif} tanesi** ise olumsuz bölgede (40 altı)."]

    if en_iyi:
        s.append(f"Listenin en üstünde **{', '.join(en_iyi)}** var — yani bugünkü teknik "
                 "tabloya göre en iyi görünenler bunlar.")

    oran = guclu / n if n else 0
    if oran > 0.35:
        s.append("Güçlü görünen hisse oranı yüksek. Bu genelde piyasanın genelinin iyi "
                 "gittiği anlamına gelir — böyle dönemlerde hisse seçmek kolay görünür ama "
                 "yükseliş büyük ölçüde genel havadan gelir, seçiminizin başarısından değil.")
    elif oran < 0.10:
        s.append("Güçlü görünen hisse sayısı çok az. Bu, piyasada genel bir zayıflık "
                 "olduğuna işaret eder — böyle dönemlerde 'en iyi' hisse bile aslında "
                 "'en az kötü' olabilir.")
    else:
        s.append("Güçlü ve zayıf hisseler dengeli dağılmış; piyasa ayrışıyor, yani hisse "
                 "seçimi bu dönemde gerçekten fark yaratabilir.")

    s.append("\n⚠️ **Puanlar getiri tahmini değildir.** 100 üzerinden verilen bu skorlar, "
             "teknik göstergelerin bugünkü durumunu özetler. Yüksek puanlı bir hisse düşebilir, "
             "düşük puanlı bir hisse yükselebilir.")
    return "\n\n".join(s)


# ─────────────────────────────────────────────────────────────────────────────
# 4) Yükselebilecek Hisseler (teknik vade taraması)
# ─────────────────────────────────────────────────────────────────────────────
# NOT: Bu dosyada eskiden yukselecek_ozeti() vardı — örüntü/istatistiksel
# benzerlik taramasının sade-dil özetiydi. Örüntü analizi tamamen kaldırıldığı
# için (bkz. OKU_BENI.txt) bu fonksiyon da kaldırıldı; "Yükselebilecek
# Hisseler" sekmesi artık aşağıdaki vade_taramasi_ozeti()'ni kullanır.
def vade_taramasi_ozeti(tablo) -> str:
    """Vade bazlı tarama (Kısa/Orta/Uzun) için sade dil özeti."""
    if tablo is None or len(tablo) == 0:
        return "Tarama sonucu boş — bu kapsamda değerlendirilebilecek hisse bulunamadı."

    s = [f"**{len(tablo)} hisse** üç ayrı vadede değerlendirildi. "
         "Her vade için ayrı karar verilir; bir hisse kısa vadede riskli, "
         "uzun vadede olumlu olabilir."]

    for vade, sure in (("Kısa", "~2 hafta"), ("Orta", "~3 ay"), ("Uzun", "~6 ay")):
        if vade not in tablo.columns:
            continue
        kolon = tablo[vade].astype(str)
        al = int(kolon.str.contains("🟢").sum())
        bekle = int(kolon.str.contains("ÇELİŞKİ").sum())
        uzak = int(kolon.str.contains("🔴").sum())
        veriyok = int(kolon.str.contains("Veri yok").sum())
        parca = (f"- **{vade} vade ({sure})**: {al} hissede AL, {bekle} hissede "
                 f"çelişki nedeniyle BEKLE, {uzak} hissede uzak dur")
        if veriyok:
            parca += f" ({veriyok} hissede bu vade için yeterli geçmiş yok)"
        s.append(parca + ".")

    # Örnek sayısı düşük olan vadeler için dürüst uyarı.
    az_ornekli = []
    for vade in ("Kısa", "Orta", "Uzun"):
        k = f"{vade} Örnek"
        if k in tablo.columns:
            ort = _sayi(tablo[k].mean())
            if ort is not None and ort < 8:
                az_ornekli.append(f"{vade} (ort. {ort:.0f} örnek)")
    if az_ornekli:
        s.append("⚠️ **Zayıf kanıt uyarısı:** " + ", ".join(az_ornekli) +
                 " vadesinde geçmişte çok az benzer durum bulundu. Ufuk uzadıkça "
                 "örneklem azalır; az örneğe dayanan bir 'AL' tek başına güvenilir "
                 "değildir.")

    if "Kısa" in tablo.columns and "Uzun" in tablo.columns:
        ayrisan = tablo[tablo["Kısa"].astype(str).str.contains("🔴|ÇELİŞKİ", regex=True)
                        & tablo["Uzun"].astype(str).str.contains("🟢")]
        if len(ayrisan):
            adlar = ", ".join(f"**{h}**" for h in ayrisan["Hisse"].head(5))
            s.append(f"🔎 **Kısa vadede temkinli, uzun vadede olumlu:** {adlar}. "
                     "Bu tipik bir 'şu an zamanlaması iyi değil ama hikâyesi olumlu' "
                     "görünümüdür — acele almak yerine beklemek düşünülebilir.")

    s.append("\n⚠️ Bu sayılar geçmişin ortalamasıdır, gelecek vaadi değildir.")
    return "\n\n".join(s)


# ─────────────────────────────────────────────────────────────────────────────
# 5) Sanal portföy (paper trading)
# ─────────────────────────────────────────────────────────────────────────────
def sanal_portfoy_ozeti(rapor: dict) -> str:
    if not rapor:
        return ""
    getiri = _sayi(rapor.get("gerceklesen_kumulatif_yuzde"))
    gun = rapor.get("gun_sayisi") or 0
    toplam = _sayi(rapor.get("toplam_deger"))
    baslangic = _sayi(rapor.get("baslangic_butce"))
    hedef_ayl = _sayi(rapor.get("hedef_aylik_yuzde"))
    yakaliyor = rapor.get("hedefi_yakaliyor_mu")
    dusus = _sayi(rapor.get("maksimum_dusus_yuzde"))

    if getiri is None or toplam is None or baslangic is None:
        return ""

    s = []
    if getiri >= 0:
        s.append(f"**Sanal portföy şu an kârda.** {baslangic:,.0f} TL ile başlayıp "
                 f"{toplam:,.0f} TL'ye ulaşmış — {gun} günde **%{getiri:+.2f}**.")
    else:
        s.append(f"**Sanal portföy şu an zararda.** {baslangic:,.0f} TL ile başlayıp "
                 f"{toplam:,.0f} TL'ye gerilemiş — {gun} günde **%{getiri:+.2f}**.")

    if yakaliyor is False and hedef_ayl:
        s.append(f"Aylık %{hedef_ayl:.0f} hedefinin **gerisinde**. Bu bilgi gizlenmiyor: "
                 "motor hedefi tutturmak için puanları değiştirmez, sonuç ne çıkarsa onu gösterir.")
    elif yakaliyor is True and hedef_ayl:
        s.append(f"Şu an aylık %{hedef_ayl:.0f} hedefinin **önünde**. Ancak kısa dönemli "
                 "iyi sonuç şans eseri de olabilir; asıl ölçüt aylarca süren tutarlılıktır.")

    if dusus is not None and dusus < -5:
        s.append(f"En yüksek noktasından bugüne kadar gördüğü en büyük düşüş **%{abs(dusus):.1f}**. "
                 "Bu sayı önemlidir: gerçek parayla bu düşüşe dayanabilir miydiniz sorusunun cevabıdır.")

    if gun < 60:
        s.append(f"\n⚠️ **Henüz sadece {gun} gün geçti — bu süre hiçbir şey kanıtlamaz.** "
                 "Bu kadar kısa dönemde iyi ya da kötü sonuç büyük ölçüde şanstır. Anlamlı bir "
                 "değerlendirme için en az birkaç ay gerekir.")
    else:
        s.append("\n⚠️ Bu bir simülasyondur; gerçek para kullanılmamıştır. Gerçekte alım-satım "
                 "anındaki fiyat kaymaları sonucu bir miktar kötüleştirir.")
    return "\n\n".join(s)


# ─────────────────────────────────────────────────────────────────────────────
# 6) Backtest (puanlama motoru)
# ─────────────────────────────────────────────────────────────────────────────
def backtest_ozeti(ozet: dict, ana_ufuk: int = 10) -> str:
    if not ozet or ozet.get("n_toplam", 0) == 0:
        return ""
    kor = ozet.get("korelasyonlar", {}).get(f"korelasyon_{ana_ufuk}g")
    anl = (ozet.get("anlamlilik") or {}).get(f"anlamlilik_{ana_ufuk}g")
    anlamli = anl.get("anlamli_mi") if anl else None
    n = ozet.get("n_toplam", 0)

    s = [f"**Bu test ne yaptı?** Geçmişteki {n} ayrı güne dönüldü; her gün, SADECE o güne "
         "kadar bilinen veriyle puan hesaplandı ve sonra gerçekte ne olduğuna bakıldı. "
         "Yani sistemin geçmişte gerçekten işe yarayıp yaramayacağı ölçüldü."]

    if kor is None:
        s.append("**Sonuç:** Ölçüm yapılamadı — puanlarda yeterli çeşitlilik yok.")
    elif kor > 0.05 and anlamli:
        s.append("**Sonuç: Sistem işe yarıyor gibi görünüyor.** Yüksek puan verdiği hisseler, "
                 "düşük puan verdiklerine göre gerçekten daha iyi performans göstermiş ve bu "
                 "fark rastlantıyla açıklanamayacak kadar belirgin.")
    elif kor > 0.05:
        s.append("**Sonuç: Zayıf bir olumlu işaret var ama güvenilir değil.** Yüksek puanlılar "
                 "biraz daha iyi gitmiş, ancak bu fark rastlantı da olabilir — üzerine para "
                 "koyacak kadar güçlü bir kanıt değil.")
    elif kor > -0.05:
        s.append("**Sonuç: Sistem şu an bir işe yaramıyor.** Verdiği puan ile sonrasında olan "
                 "arasında ölçülebilir bir ilişki bulunamadı. Yani yüksek puanlı hisseyi almak "
                 "ile rastgele hisse almak arasında anlamlı bir fark çıkmamış.")
    else:
        s.append("**Sonuç: Sistem ters çalışıyor olabilir.** Düşük puan verdiği hisseler, "
                 "yüksek puan verdiklerinden daha iyi performans göstermiş. Bu ilginç bir "
                 "bulgudur ama tek başına 'tersini yap' demek için yeterli değildir — "
                 "önce daha geniş veriyle doğrulanmalı.")

    mono = ozet.get("monotonluk", {}).get(f"monoton_{ana_ufuk}g")
    if mono is True:
        s.append("Ayrıca puan arttıkça getiri de düzenli olarak artmış — bu, puanlamanın "
                 "sadece 'iyi/kötü' ayırmakla kalmayıp derece de ölçebildiğini gösterir.")
    elif mono is False:
        s.append("Puan arttıkça getiri düzenli artmamış; yani mevcut eşikler (72/62/52/40) "
                 "hisseleri en doğru şekilde ayırmıyor olabilir.")

    s.append("\n⚠️ **Bu test iyimser tarafta hata yapar:** yalnızca bugün borsada olan hisseler "
             "test edilebiliyor (batmış/çıkmış şirketler veride yok) ve komisyon dahil değil. "
             "Yani gerçek sonuç buradakinden bir miktar daha kötüdür.")
    return "\n\n".join(s)


# ─────────────────────────────────────────────────────────────────────────────
# 7) Örüntü motoru backtesti
# ─────────────────────────────────────────────────────────────────────────────
# NOT: Bu dosyada eskiden oruntu_backtest_ozeti() vardı — örüntü motoru
# tamamen kaldırıldığı için (bkz. OKU_BENI.txt) bu özet üretici de kaldırıldı.


# ─────────────────────────────────────────────────────────────────────────────
# 8) Tavsiye geçmişi
# ─────────────────────────────────────────────────────────────────────────────
def tavsiye_gecmisi_ozeti(ozet: dict, ana_ufuk: int = 10) -> str:
    if not ozet or ozet.get("n_toplam", 0) == 0:
        return ""
    n = ozet["n_toplam"]
    olg = (ozet.get("olgunluk") or {}).get(f"{ana_ufuk}g", {})
    olgun = olg.get("olgun", 0)
    bekleyen = olg.get("bekleyen", 0)

    s = [f"**Bu sekme neyi gösteriyor?** Sistemin gerçek zamanda verdiği {n} tavsiye "
         "kaydedildi. Backtest geçmişi yeniden oynatır; burada ise sistem tavsiyeyi verirken "
         "sonucu KİMSE bilmiyordu — bu yüzden burası daha dürüst bir sınavdır."]

    s.append(f"Şu an {olgun} tavsiyenin sonucu belli oldu, {bekleyen} tanesi hâlâ bekliyor "
             f"({ana_ufuk} iş günü dolmadı). Bekleyenler ortalamaya katılmıyor.")

    if olgun < 20:
        s.append(f"⚠️ **{olgun} sonuç henüz bir şey söylemek için çok az.** Bu sayı en az "
                 "20-30'a ulaşmadan çıkarılacak sonuç yanıltıcı olur. Sabırla birikmesini bekleyin.")
        return "\n\n".join(s)

    kt = ozet.get("kaynak_tablo")
    if kt is not None and not kt.empty:
        kolon = f"endeks_ustu_{ana_ufuk}g"
        if kolon in kt.columns:
            gecerli = kt[kt[kolon].notna()]
            if len(gecerli):
                ortalama_eu = float(gecerli[kolon].mean())
                if ortalama_eu > 0.5:
                    s.append(f"**Asıl önemli sonuç:** Tavsiyeler ortalama olarak endeksten "
                             f"%{ortalama_eu:+.2f} daha iyi performans göstermiş. Yani sadece "
                             "piyasayla birlikte yükselmekle kalmamış, gerçekten değer katmış.")
                elif ortalama_eu < -0.5:
                    s.append(f"**Asıl önemli sonuç:** Tavsiyeler endeksin %{abs(ortalama_eu):.2f} "
                             "gerisinde kalmış. Yani bu tavsiyeleri takip etmek yerine sadece "
                             "endeks almak daha iyi sonuç verirdi.")
                else:
                    s.append("**Asıl önemli sonuç:** Tavsiyeler endeksle hemen hemen aynı "
                             "performansı vermiş. Yani ek bir değer üretmemiş — bu durumda "
                             "uğraşmak yerine endeks almak daha basit ve ucuz olurdu.")

    s.append("\n⚠️ Komisyon ve alım-satım maliyetleri bu hesaba dahil değildir; onlar da "
             "düşünce gerçek sonuç bir miktar daha düşüktür.")
    return "\n\n".join(s)


# ─────────────────────────────────────────────────────────────────────────────
# 9) Portföy & Tavsiye — "şunu sat, yerine bunu al" eylem planı
# ─────────────────────────────────────────────────────────────────────────────
def portfoy_eylem_plani(oneriler: list, durum: dict = None,
                         sektor_uyarilari: list = None) -> str:
    """Motorun ürettiği önerileri, doğrudan uygulanabilir bir eylem planına çevirir.

    Amaç: kullanıcı listeyi tek tek okuyup yorumlamak zorunda kalmasın; ne
    satılacak, yerine ne alınacak, ne dokunulmayacak — net görsün.
    """
    if not oneriler:
        return ""

    satilacak = [o for o in oneriler if o.get("eylem") == "KAYIP KES / ELDEN ÇIKAR (SAT)"]
    takaslar = [o for o in oneriler if o.get("eylem") == "TAKAS"]
    izlenecek = [o for o in oneriler if o.get("eylem") == "ZAYIF / İZLE"]
    guclu = [o for o in oneriler if o.get("eylem") == "TAŞIMAYA DEVAM ET / AĞIRLIK ARTIR (AL)"]
    tut = [o for o in oneriler if o.get("eylem") == "TUT"]
    veri_yok = [o for o in oneriler if o.get("eylem") == "VERİ YOK"]

    s = []

    # Genel durum cümlesi
    if durum:
        kz = _sayi(durum.get("toplam_kar_zarar_yuzde"))
        if kz is not None:
            durum_sozu = ("kârda" if kz > 0 else "zararda" if kz < 0 else "başabaşta")
            s.append(f"**Portföyünüz şu an {durum_sozu}** (%{kz:+.2f}). "
                     f"Aşağıda motorun önerdiği somut adımlar var.")

    # ── SATILACAKLAR ──
    if satilacak:
        satirlar = [f"- **{o['sembol']}** (puan {o['puan']:.0f}) — teknik tablo kritik "
                    "seviyenin altında" for o in satilacak]
        s.append("### 🔴 Satılması önerilenler\n" + "\n".join(satirlar) +
                 "\n\nBu hisselerin puanı kayıp-kes eşiğinin altına düşmüş. Motor, yerine "
                 "belirli bir alternatif önermiyor — nakde geçip beklemek de bir seçenektir.")

    # ── TAKASLAR: asıl istenen "şunu sat, bunu al" formatı ──
    if takaslar:
        satirlar = []
        for o in takaslar:
            aday = o.get("takas_adayi") or {}
            aday_sembol = aday.get("sembol", "—")
            aday_puan = _sayi(aday.get("puan"))
            aday_fiyat = _sayi(aday.get("fiyat"))
            fiyat_metni = f", güncel fiyat ~{aday_fiyat:.2f} TL" if aday_fiyat else ""
            satirlar.append(
                f"- **{o['sembol']} SAT** (puan {o['puan']:.0f}) → yerine "
                f"**{aday_sembol} AL** (puan {aday_puan:.0f}{fiyat_metni})"
                if aday_puan is not None else
                f"- **{o['sembol']} SAT** (puan {o['puan']:.0f}) → yerine **{aday_sembol} AL**")
        s.append("### 🔁 Takas önerileri (şunu sat, yerine bunu al)\n" + "\n".join(satirlar) +
                 "\n\nBuradaki mantık: eldeki hisse zayıflamış, izleme listenizde teknik olarak "
                 "belirgin şekilde daha güçlü bir hisse var. Her zayıf pozisyona **farklı** bir "
                 "aday atanır — hepsini tek hisseye yığmamak için.")

    # ── GÜÇLÜ / TUTULACAK ──
    if guclu:
        adlar = ", ".join(f"**{o['sembol']}** ({o['puan']:.0f})" for o in guclu)
        s.append(f"### 🟢 Güçlü duranlar\n{adlar}\n\nBunlar teknik olarak güçlü bölgede; "
                 "elde tutmak (ve isterseniz ağırlığını artırmak) değerlendirilebilir.")

    if tut:
        adlar = ", ".join(o["sembol"] for o in tut)
        s.append(f"### ⚪ Dokunulmayacaklar\n{adlar} — nötr bölgede, şu an bir aksiyon "
                 "gerektirmiyor.")

    if izlenecek:
        adlar = ", ".join(f"**{o['sembol']}** ({o['puan']:.0f})" for o in izlenecek)
        s.append(f"### 🟡 Yakın takibe alınacaklar\n{adlar}\n\nBu hisseler zayıflamış (kayıp-kes "
                 "eşiğine yakın) ama motor bunların yerine geçecek güçlü bir aday BULAMADI — "
                 "çünkü sadece yukarıdaki 'Takas aday havuzu — izleme listesi' kutusuna "
                 "yazdığınız hisseler arasında arıyor, tüm BIST'i taramıyor.\n\n"
                 "**Ne yapmalısınız — iki seçenek:**\n"
                 "1. **İzleme listesini genişletin:** Bu sayfada yukarıda, '💼 Portföyüm' "
                 "bölümünün altındaki **'Takas aday havuzu — izleme listesi'** kutusuna, "
                 "aday olabilecek hisse kodlarını virgülle ayırarak ekleyin (örn. "
                 "`ASELS, SISE, KCHOL, TUPRS, ...`), sonra **'📊 PORTFÖYÜ ANALİZ ET VE "
                 "TAVSİYE ÜRET'**e tekrar basın. Motor bu genişletilmiş listede yeniden arar.\n"
                 "2. **Aşağıdaki '🎯 Fırsatlar' bölümüne bakın** — orada, izleme listenizden "
                 "bağımsız olarak TÜM BIST taramasından (arka plan önbelleği varsa) öne çıkan "
                 "hisseler listelenir; oradan uygun bir aday görürseniz elle "
                 "değerlendirebilirsiniz.")

    if veri_yok:
        adlar = ", ".join(o["sembol"] for o in veri_yok)
        s.append(f"### ⚫ Değerlendirilemeyenler\n{adlar} — güncel veri alınamadı, bu hisseler "
                 "için öneri üretilemedi.")

    if sektor_uyarilari:
        s.append("### ⚠️ Yoğunlaşma riski\n" + "\n".join(f"- {u}" for u in sektor_uyarilari) +
                 "\n\nTek bir hisse veya sektör portföyün büyük bölümünü oluşturuyorsa, o "
                 "alandaki tek bir kötü haber portföyün tamamını sarsabilir.")

    if not (satilacak or takaslar or guclu or izlenecek):
        s.append("Motor şu an portföyünüzde acil bir aksiyon görmüyor — tüm pozisyonlar "
                 "nötr bölgede.")

    s.append("\n---\n⚠️ **Bunlar motorun mekanik çıktısıdır, yatırım tavsiyesi değildir.** "
             "Puanlar yalnızca geçmiş fiyat/hacim hareketlerine dayanır; şirket haberlerini, "
             "bilançoyu veya sizin vergi/nakit durumunuzu bilmez. Hiçbir emir otomatik "
             "gönderilmez — alım-satım kararını ve işlemini siz yaparsınız.")
    return "\n\n".join(s)


# ─────────────────────────────────────────────────────────────────────────────
# 10) GÖRSEL GÖSTERGELER — üç durum + yeşilden kırmızıya yumuşak geçiş
# ─────────────────────────────────────────────────────────────────────────────
# ÜÇ DURUM (karar_ver eşikleriyle uyumlu, sadeleştirilmiş):
#   ≥62  → OLUMLU   (karar_ver: AL / GÜÇLÜ AL)
#   52-62→ NÖTR     (karar_ver: İZLE / TUT)
#   <52  → OLUMSUZ  (karar_ver: ZAYIF/BEKLE / UZAK DUR)
# Bu eşiklerin karar metniyle aynı kalması ÖNEMLİDİR: aksi halde yeşil görünen
# bir hisse "ZAYIF" diye etiketlenir ve kullanıcı haklı olarak güvenini yitirir.
OLUMLU_ESIK = 62.0
NOTR_ESIK = 52.0

# Renk durakları: puan → RGB. Aradaki değerler doğrusal olarak karıştırılır,
# böylece 41 ile 43 puan arasında bile hafif bir ton farkı oluşur (keskin
# sıçrama yerine geçiş).
_DURAKLAR = [
    (0.0,   (185, 28, 28)),    # koyu kırmızı
    (40.0,  (220, 38, 38)),    # kırmızı
    (52.0,  (245, 158, 11)),   # turuncu
    (62.0,  (250, 204, 21)),   # sarı
    (75.0,  (34, 197, 94)),    # yeşil
    (100.0, (21, 128, 61)),    # koyu yeşil
]


def renk_kodu(puan) -> str:
    """Puanı yeşil-sarı-kırmızı ekseninde SÜREKLİ bir renge çevirir (#rrggbb)."""
    p = _sayi(puan)
    if p is None:
        return "#94a3b8"                      # gri — veri yok
    p = max(0.0, min(100.0, p))
    for i in range(len(_DURAKLAR) - 1):
        x0, c0 = _DURAKLAR[i]
        x1, c1 = _DURAKLAR[i + 1]
        if x0 <= p <= x1:
            t = 0.0 if x1 == x0 else (p - x0) / (x1 - x0)
            r, g, b = (int(round(a + (bb - a) * t)) for a, bb in zip(c0, c1))
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#15803d"


def durum_adi(puan) -> str:
    """Üç durumdan biri: Olumlu / Nötr / Olumsuz."""
    p = _sayi(puan)
    if p is None:
        return "Veri yok"
    if p >= OLUMLU_ESIK:
        return "Olumlu"
    if p >= NOTR_ESIK:
        return "Nötr"
    return "Olumsuz"


def renk_topu(puan) -> str:
    """Üç durumu tek emoji ile: 🟢 Olumlu · 🟡 Nötr · 🔴 Olumsuz."""
    ad = durum_adi(puan)
    return {"Olumlu": "🟢", "Nötr": "🟡", "Olumsuz": "🔴"}.get(ad, "⚪")


def renk_etiketi(puan) -> str:
    """'🟢 Olumlu' gibi renk + durum adı."""
    ad = durum_adi(puan)
    return f"{renk_topu(puan)} {ad}"


def renk_cubugu(puan, adet: int = 5) -> str:
    """Doluluk çubuğu. Renk körlüğüne karşı yalnızca renge değil, DOLU KARE
    SAYISINA da bakılabilsin diye hem renk hem doluluk taşır."""
    p = _sayi(puan)
    if p is None:
        return "⬜" * adet
    dolu = max(0, min(adet, int(round(max(0.0, min(100.0, p)) / 100.0 * adet))))
    kare = {"🟢": "🟩", "🟡": "🟨", "🔴": "🟥"}.get(renk_topu(p), "⬜")
    return kare * dolu + "⬜" * (adet - dolu)


def gradyan_cubugu_html(puan, genislik_px=120, yukseklik_px: int = 10) -> str:
    """Yeşilden kırmızıya geçişli, dolgu oranı puana bağlı ince bir çubuk (HTML).

    genislik_px sayı ise piksel, metin ise ("100%" gibi) doğrudan kullanılır.
    DAR KOLONLARDA SABİT PİKSEL KULLANMAYIN: kart genişliğinden taşıp sayfayı
    yatayda bozar (vade kartlarında bu hata yaşandı — 999px verilmişti).
    """
    p = _sayi(puan)
    oran = 0 if p is None else max(0.0, min(100.0, p))
    renk = renk_kodu(p)
    genislik = genislik_px if isinstance(genislik_px, str) else f"{genislik_px}px"
    # KOYU TEMA: zemin eskiden açık pastel bir degradeydi (#fee2e2…#dcfce7);
    # koyu arka planda göz alıyordu (canlı uygulamada doğrulandı — düşük puanlı
    # favori kartında çubuğun dolmayan kısmı bembeyaz parlıyordu). Artık zemin
    # sönük/şeffaf, dolu kısım ise puan rengiyle hafifçe parlıyor.
    return (f"<div style='width:{genislik};max-width:100%;box-sizing:border-box;"
            f"height:{yukseklik_px}px;border-radius:99px;"
            f"background:rgba(148,163,184,.14);position:relative;"
            f"overflow:hidden;border:1px solid rgba(148,163,184,.20)'>"
            f"<div style='position:absolute;left:0;top:0;bottom:0;width:{oran}%;"
            f"background:{renk};box-shadow:0 0 10px -2px {renk};"
            f"border-radius:99px'></div></div>")


# ─────────────────────────────────────────────────────────────────────────────
# 11) NİHAİ KARAR — iki motoru TEK bir cevapta birleştirir
# ─────────────────────────────────────────────────────────────────────────────
# NEDEN VAR (önemli):
# Uygulama iki bağımsız motor çalıştırır ve bunlar FARKLI SORULARA cevap verir:
#   • Puanlama motoru (analiz_motoru): "Hissenin BUGÜNKÜ teknik tablosu nasıl?"
#   • AKD motoru (telegram_akd)      : "BUGÜN aracı kurum bazında kim alıp kim sattı?"
# Bu ikisi pekâlâ çelişebilir (ör. teknik tablo bozuk ama AKD'de güçlü kurumsal
# alım görünüyor). Eskiden ikinci görüş GEÇMİŞ ÖRÜNTÜ (istatistiksel benzerlik)
# motorundan geliyordu; bu, kullanıcı deneyiminde yanıltıcı bulunduğu için
# (bkz. OKU_BENI.txt) tamamen kaldırıldı ve yerini AKD sinyali aldı.
#
# ÇÖZÜM: Tek bir NİHAİ KARAR üretilir. Kural bilerek TEMKİNLİDİR:
#   - İki motor da olumlu  → olumlu karar (en güvenilir durum)
#   - İki motor da olumsuz → olumsuz karar
#   - ÇELİŞKİ VARSA        → "BEKLE" — ne al ne sat. Çünkü iki bağımsız yöntem
#     zıt şey söylüyorsa kanıt gerçekten karışıktır; böyle bir anda "GÜÇLÜ AL"
#     yazmak kullanıcıyı yanıltmak olur.
#   - AKD verisi yoksa (hisse için henüz çekilmemiş) → tek başına puanlama
#     motorunun kararı kullanılır ve bu durum açıkça belirtilir.


def nihai_karar(analiz: dict, akd_sinyali: dict = None) -> dict:
    """Nihai karar: TEKNİK puan + (varsa) AKD sinyali.

    ═══════════════════════════════════════════════════════════════════════════
    ÖNEMLİ TASARIM NOTU: Bu fonksiyon eskiden teknik puanı GEÇMİŞ ÖRÜNTÜ
    sinyaliyle birleştiriyordu. Örüntü sinyali kullanıcı deneyiminde yanıltıcı
    bulunduğu (yüksek teknik puanlı hisselerde sürekli "ÇELİŞKİLİ — BEKLE"
    üretip kararı bulanıklaştırdığı) için sistemden TAMAMEN çıkarıldı. İkinci
    görüş artık AKD (Aracı Kurum Dağılımı) sinyalinden gelir: bu, geçmişin
    istatistiksel tekrarına değil, BUGÜN kimin alıp kimin sattığına dayanan
    somut bir veridir.

    akd_sinyali: telegram_akd.akd_sinyal_uret() çıktısı (ya da None).

    Dönüş: {"karar", "emoji", "renk", "puan", "celiskili_mi", "aciklama",
            "teknik_karar", "teknik_puan", "akd_karari", "akd_puani",
            "akd_var_mi"}
    """
    if not analiz:
        return {"karar": "VERİ YOK", "emoji": "⚪", "renk": "#94a3b8", "puan": None,
                "celiskili_mi": False, "akd_var_mi": False,
                "teknik_karar": None, "teknik_puan": None,
                "akd_karari": None, "akd_puani": None,
                "aciklama": "Analiz verisi yok."}

    puan = _sayi(analiz.get("genel_puan"))
    teknik_karar = analiz.get("karar")
    teknik_durum = durum_adi(puan)          # Olumlu / Nötr / Olumsuz

    akd_var = bool(akd_sinyali) and akd_sinyali.get("puan") is not None
    akd_puani = akd_sinyali.get("puan") if akd_var else None
    akd_karari = akd_sinyali.get("karar") if akd_var else None

    if not akd_var:
        return {
            "karar": teknik_karar or "—", "emoji": analiz.get("emoji", "⚪"),
            "renk": renk_kodu(puan), "puan": puan, "celiskili_mi": False,
            "akd_var_mi": False, "teknik_karar": teknik_karar,
            "teknik_puan": puan, "akd_karari": None, "akd_puani": None,
            "aciklama": ("Bu karar **bugünkü teknik tabloya** dayanıyor "
                        f"(puan {puan:.0f}). Bu hisse için AKD (aracı kurum "
                        "dağılımı) verisi çekilmemiş — çekerseniz kimin alıp "
                        "kimin sattığı da karara dahil edilir."),
        }

    akd_olumlu = akd_puani >= 30
    akd_olumsuz = akd_puani <= -30
    teknik_olumlu = teknik_durum == "Olumlu"
    teknik_olumsuz = teknik_durum == "Olumsuz"
    teknik_notr = teknik_durum == "Nötr"
    akd_sebep = ""
    if akd_sinyali.get("sebepler"):
        akd_sebep = " " + akd_sinyali["sebepler"][0]

    ortak = {"puan": puan, "teknik_karar": teknik_karar, "teknik_puan": puan,
             "akd_karari": akd_karari, "akd_puani": akd_puani, "akd_var_mi": True}

    # ── ÇELİŞKİ ─────────────────────────────────────────────────────────────
    if (akd_olumlu and teknik_olumsuz) or (akd_olumsuz and teknik_olumlu):
        if akd_olumlu:
            aciklama = (
                "⚠️ **Teknik tablo ile AKD zıt yönde, bu yüzden karar BEKLE.**\n\n"
                f"- **Teknik tablo olumsuz** (puan {puan:.0f} → *{teknik_karar}*).\n"
                f"- **AKD olumlu** (*{akd_karari}*).{akd_sebep}\n\n"
                "Fiyat henüz bozuk görünüyor ama takas tarafında toplama işareti "
                "var. Teknik tablonun düzelmesini (puanın 52'nin üstüne çıkmasını) "
                "beklemek daha savunulabilir.")
        else:
            aciklama = (
                "⚠️ **Teknik tablo ile AKD zıt yönde, bu yüzden karar BEKLE.**\n\n"
                f"- **Teknik tablo olumlu** (puan {puan:.0f} → *{teknik_karar}*).\n"
                f"- **AKD olumsuz** (*{akd_karari}*).{akd_sebep}\n\n"
                "Fiyat güçlü görünüyor ama takas tarafında dağıtım işareti var — "
                "yani yükselişi kurumlar satarak karşılıyor olabilir. Yeni alım "
                "için acele etmemek, pozisyon varsa kâr korumak makul.")
        return {**ortak, "karar": "ÇELİŞKİLİ — BEKLE", "emoji": "⚠️",
                "renk": "#f59e0b", "celiskili_mi": True, "aciklama": aciklama}

    # ── İKİSİ DE AYNI YÖNDE ─────────────────────────────────────────────────
    if akd_olumlu and teknik_olumlu:
        return {**ortak, "karar": teknik_karar, "emoji": "🟢",
                "renk": renk_kodu(puan), "celiskili_mi": False,
                "aciklama": ("✅ **Teknik tablo ve AKD aynı yönde — en güvenilir durum.**\n\n"
                            f"Teknik puan {puan:.0f} (olumlu) ve AKD *{akd_karari}*."
                            f"{akd_sebep}")}

    if akd_olumsuz and teknik_olumsuz:
        return {**ortak, "karar": teknik_karar, "emoji": "🔴",
                "renk": renk_kodu(puan), "celiskili_mi": False,
                "aciklama": ("🔴 **Teknik tablo ve AKD birlikte olumsuz.**\n\n"
                            f"Teknik puan {puan:.0f} (zayıf) ve AKD *{akd_karari}*."
                            f"{akd_sebep} Uzak durmak için tutarlı gerekçe var.")}

    # ── KISMİ UYUM ──────────────────────────────────────────────────────────
    if akd_olumlu and teknik_notr:
        return {**ortak, "karar": "KISMEN OLUMLU — İZLE", "emoji": "🟡",
                "renk": "#eab308", "celiskili_mi": False,
                "aciklama": (f"AKD olumlu (*{akd_karari}*){akd_sebep} ama teknik tablo "
                            f"kararsız (puan {puan:.0f}). Destekleyici işaret var, teyit yok "
                            "— izleme listesine alıp teknik puan 62'yi aşarsa yeniden bakın.")}

    if akd_olumsuz and teknik_notr:
        return {**ortak, "karar": "KISMEN OLUMSUZ — TEMKİNLİ", "emoji": "🟠",
                "renk": "#f97316", "celiskili_mi": False,
                "aciklama": (f"Teknik tablo nötr (puan {puan:.0f}) ama AKD olumsuz "
                            f"(*{akd_karari}*).{akd_sebep} Yeni alım için elverişli zemin yok.")}

    # ── AKD NÖTR ────────────────────────────────────────────────────────────
    return {**ortak, "karar": teknik_karar, "emoji": analiz.get("emoji", "⚪"),
            "renk": renk_kodu(puan), "celiskili_mi": False,
            "aciklama": (f"Karar bugünkü teknik tabloya dayanıyor (puan {puan:.0f}). "
                        f"AKD tarafı belirgin bir yön göstermiyor (*{akd_karari}*) — "
                        "ne teyit ediyor ne çelişiyor.")}


def nihai_karar_kisa(akd_puani, teknik_puan) -> str:
    """Tablolarda kullanılmak üzere KISA nihai karar etiketi.

    nihai_karar() ile AYNI kuralları uygular — listedeki karar ile detay
    sayfasındaki karar asla farklı şey söylemesin diye mantık tek yerde
    (burada ve nihai_karar'da aynı eşiklerle) tutulur.
    akd_puani None ise sadece teknik puana bakılır.
    """
    p = _sayi(teknik_puan)
    if p is None:
        return "⚪ Bilinmiyor"
    d = durum_adi(p)
    a = _sayi(akd_puani)
    if a is None:
        return {"Olumlu": "🟢 AL", "Nötr": "🟡 İZLE"}.get(d, "🔴 UZAK DUR")
    olumlu, olumsuz = a >= 30, a <= -30
    if (olumlu and d == "Olumsuz") or (olumsuz and d == "Olumlu"):
        return "⚠️ ÇELİŞKİ — BEKLE"
    if olumlu and d == "Olumlu":
        return "🟢 AL"
    if olumsuz and d == "Olumsuz":
        return "🔴 UZAK DUR"
    if olumlu and d == "Nötr":
        return "🟡 KISMEN OLUMLU — İZLE"
    if olumsuz and d == "Nötr":
        return "🟠 KISMEN OLUMSUZ"
    return {"Olumlu": "🟢 AL", "Nötr": "🟡 İZLE"}.get(d, "🔴 UZAK DUR")


def gorsel_tablo(tablo, puan_kolonlari: list = None, ana_kolon: str = "Puan",
                  sayilari_koru: bool = True):
    """Tabloya renkli 'Durum' sütunu ekler ve alt puanları renge çevirir."""
    if tablo is None or len(tablo) == 0:
        return tablo
    t = tablo.copy()
    if ana_kolon in t.columns:
        t.insert(min(1, len(t.columns)), "Durum", t[ana_kolon].map(renk_etiketi))
    for k in (puan_kolonlari or []):
        if k not in t.columns:
            continue
        if sayilari_koru:
            t[k] = t[k].map(lambda v: f"{renk_topu(v)} {v:.0f}"
                            if _sayi(v) is not None else "⚪")
        else:
            t[k] = t[k].map(renk_topu)
    return t
