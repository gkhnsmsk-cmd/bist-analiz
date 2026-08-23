# -*- coding: utf-8 -*-
"""
sohbet_paneli.py — Sağda sürekli duran AI asistan panelinin ARAYÜZÜ.
══════════════════════════════════════════════════════════════════════════════
Çekirdek mantık sohbet_ajani.py'dedir; bu dosya yalnızca Streamlit arayüzünü
çizer. Ayrım bilinçlidir: ajan mantığı Streamlit'siz test edilebilsin diye.

YERLEŞİM KARARI — neden st.sidebar DEĞİL:
Kullanıcının açık ve tekrarlanmış isteği: "sayfada sadece 1 adet kayar çubuk
olsun, iç içe kaydırma olmasın." st.sidebar mimari olarak AYRI bir kaydırma
bölgesidir ve bu kuralı bozar. Bu yüzden panel, ana sayfa akışının içindeki
sağ kolona yerleştirilir ve `position: sticky` ile ekranda kalır — kendi
kaydırma çubuğunu OLUŞTURMAZ, sayfayla birlikte davranır.
"""
from __future__ import annotations

import streamlit as st

import sohbet_ajani as sa
import llm_ajanlari as la

_GECMIS = "_sohbet_gecmisi"

# Kullanıcı yazmak zorunda kalmadan tek tıkla sorabileceği başlangıç soruları.
HIZLI_SORULAR = [
    "Bugün öne çıkan hisseler neler?",
    "Portföyümün durumu nasıl?",
    "Riskli pozisyonum var mı?",
]


def stil():
    """Panelin CSS'i. app.py'deki ana <style> bloğundan AYRI tutuldu ki
    sohbet paneli kapatılırsa bu stiller de devreye girmesin."""
    st.markdown("""
<style>
/* ── Sağ kolon: ekranda kalır (sticky), KENDİ kaydırma çubuğu YOKTUR ──────
   ÖNEMLİ: Bu stiller `st.container(key="sohbet_paneli")` ile üretilen
   `.st-key-sohbet_paneli` sınıfına bağlanır. Daha önce burada bir sarmalayıcı
   <div> AÇILIP başka bir st.markdown çağrısında KAPATILIYORDU; Streamlit her
   markdown bloğunu kendi kapsayıcısına sardığı için o div gerçekte hiçbir şeyi
   sarmıyor, başlıkların kırpılmasına ve küçük kaydırma çubuklarının
   belirmesine yol açıyordu. Artık ham div kullanılmıyor. */
.st-key-sohbet_paneli {position: sticky; top: 3.2rem;}

/* Panelin İÇİNDEKİ hiçbir kutu kendi kaydırma çubuğunu üretmesin.
   Kullanıcının kuralı: sayfada TEK kayar çubuk olur, o da sayfanın kendisidir. */
.st-key-sohbet_paneli, .st-key-sohbet_paneli * {overflow: visible !important;}

/* Başlık satırı — flex yerine sade akış; dikey kırpılma olmaz. */
.st-key-sohbet_paneli h4 {margin: 0 0 .5rem 0; font-size: 1rem; font-weight: 700;
                          line-height: 1.6;}
.sohbet-rozet {font-size:.62rem; padding:2px 8px; border-radius:999px;
               background:rgba(56,189,248,.14); color:#7dd3fc;
               border:1px solid rgba(56,189,248,.3); font-weight:600;
               text-transform:uppercase; letter-spacing:.05em;
               white-space:nowrap; vertical-align:middle;}
.sohbet-bos {font-size:.82rem; opacity:.7; line-height:1.65;
             border:1px dashed rgba(148,163,184,.25); border-radius:12px;
             padding:12px 14px;}
/* Mesaj kutuları st.container(border=True) ile çizilir; sadece boşluk ayarı. */
.st-key-sohbet_paneli div[data-testid="stVerticalBlockBorderWrapper"] {
    margin-bottom: 6px;
}
.sohbet-rol {font-size:.62rem; opacity:.55; text-transform:uppercase;
             letter-spacing:.06em; margin-bottom:2px;}
</style>""", unsafe_allow_html=True)


def _baglam_uret(kaynaklar):
    """Modele verilecek kısa durum özeti (portföy + favoriler + rejim)."""
    portfoy_semboller, favoriler = [], []
    try:
        import portfoy_takip as pt
        portfoy_semboller = [p["sembol"] for p in pt.pozisyonlari_getir()][:20]
    except Exception:
        pass
    try:
        import favoriler as fav
        favoriler = fav.getir()[:20]
    except Exception:
        pass
    try:
        rejim = kaynaklar["rejim"]()
    except Exception:
        rejim = None
    return sa.baglam_uret(portfoy_semboller, favoriler, rejim)


def _mesaj_ciz(rol: str, icerik: str):
    """Bir mesajı çizer.

    NOT: Burada ham <div> AÇIP başka bir çağrıda KAPATMAK işe yaramaz —
    Streamlit her markdown bloğunu kendi kapsayıcısına sarar, bu yüzden
    etiket ile içerik farklı kutulara düşer ve görüntü kırpılır. Bunun
    yerine Streamlit'in kendi kenarlıklı kapsayıcısı kullanılıyor.
    """
    etiket = "Siz" if rol == "user" else "Asistan"
    with st.container(border=True):
        st.markdown(f"<div class='sohbet-rol'>{etiket}</div>",
                    unsafe_allow_html=True)
        st.markdown(icerik)


def _soru_isle(soru: str, kaynaklar: dict):
    """Bir soruyu ajana gönderir, geçmişe yazar, yan etkileri uygular."""
    gecmis = st.session_state.setdefault(_GECMIS, [])
    gecmis.append({"role": "user", "content": soru})

    with st.spinner("Düşünüyor..."):
        sonuc = sa.yanitla(soru, gecmis[:-1], kaynaklar,
                           baglam=_baglam_uret(kaynaklar))

    gecmis.append({"role": "assistant", "content": sonuc["yanit"]})
    st.session_state[_GECMIS] = gecmis[-20:]     # geçmişi sınırla (token/bellek)

    # ── Yan etkiler: sayfa yönlendirmesi ────────────────────────────────
    # Streamlit'te sekmeler arası PROGRAMATİK geçiş mümkün değildir; bu
    # yüzden hisse analizi önceden hesaplanıp session_state'e yazılır ve
    # kullanıcı o sekmeye tıkladığında sonucu HAZIR bulur (app.py'deki
    # _analize_gonder ile aynı yaklaşım).
    yan = sonuc.get("yan_etkiler") or {}
    hedef = yan.get("sayfaya_git")
    if hedef and hedef.get("sembol"):
        try:
            gonder = st.session_state.get("_analize_gonder_fn")
            if callable(gonder):
                gonder(hedef["sembol"])
        except Exception:
            pass
    if hedef:
        st.session_state["_sohbet_yonlendirme"] = hedef
    if yan.get("yenile"):
        st.session_state["_sohbet_yenile"] = True


def ciz(kaynaklar: dict):
    """Sohbet panelini çizer. kaynaklar: app.py'nin önbellekli veri
    fonksiyonları (bkz. sohbet_ajani.komutlari_calistir)."""
    stil()

    saglayicilar = la.sohbet_saglayicilari()
    rozet = saglayicilar[0] if saglayicilar else "kapalı"
    st.markdown(f"#### 💬 Asistan &nbsp;<span class='sohbet-rozet'>{rozet}</span>",
                unsafe_allow_html=True)

    if not saglayicilar:
        st.markdown(
            "<div class='sohbet-bos'>Asistanı kullanmak için ücretsiz bir yapay "
            "zeka anahtarı gerekiyor.<br><br>"
            "<b>.env</b> dosyasına şu satırlardan birini ekleyin:<br>"
            "<code>GROQ_API_KEY=gsk_...</code> "
            "(console.groq.com)<br>"
            "<code>NVIDIA_API_KEY=nvapi-...</code> "
            "(build.nvidia.com)<br><br>"
            "İkisi de ücretsizdir ve kredi kartı istemez.</div>",
            unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        return

    gecmis = st.session_state.get(_GECMIS, [])

    if not gecmis:
        st.markdown(
            "<div class='sohbet-bos'>Yazılımın içindeki her şeyi bana "
            "sorabilirsiniz:<br>• <i>PGSUS analiz</i><br>"
            "• <i>Elimde EREGL var, ne yapayım?</i><br>"
            "• <i>TUPRS'un takas durumu nedir?</i></div>",
            unsafe_allow_html=True)
        for i, s in enumerate(HIZLI_SORULAR):
            if st.button(s, key=f"sohbet_hizli_{i}", use_container_width=True):
                _soru_isle(s, kaynaklar)
                st.rerun()
    else:
        for m in gecmis:
            _mesaj_ciz(m["role"], m["content"])
        if st.button("🗑️ Sohbeti temizle", key="sohbet_temizle",
                     use_container_width=True):
            st.session_state[_GECMIS] = []
            st.rerun()

    soru = st.chat_input("Bir şey sorun...", key="sohbet_girdi")
    if soru:
        _soru_isle(soru, kaynaklar)
        st.rerun()

    yonlendirme = st.session_state.get("_sohbet_yonlendirme")
    if yonlendirme:
        ad = sa._GECERLI_SEKMELER.get(yonlendirme.get("sekme"), "?")
        st.caption(f"➡️ **{ad}** sekmesi hazır"
                   + (f" ({yonlendirme['sembol']})" if yonlendirme.get("sembol") else ""))

    st.markdown("</div>", unsafe_allow_html=True)
