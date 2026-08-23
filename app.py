# -*- coding: utf-8 -*-
"""
app.py — BIST Analiz Platformu (Streamlit web paneli)
Çalıştırmak için: BASLAT.bat'a çift tıklayın.
"""

import datetime as dt
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


# ═════════════════════════════════════════════════════════════════════════════
# DEĞİŞEN YEREL MODÜLLERİ TAZELE (import'lardan ÖNCE çalışmalı)
# ═════════════════════════════════════════════════════════════════════════════
# NEDEN GEREKLİ: Streamlit, app.py değiştiğinde onu yeniden çalıştırır AMA
# app.py'nin import ettiği yerel modülleri (veri_katmani, analiz_motoru, ...)
# bellekte (sys.modules) tutmaya devam eder — onları YENİDEN YÜKLEMEZ.
# Sonuç: bir modüle yeni fonksiyon eklendiğinde uygulama açıkken
# "module 'analiz_motoru' has no attribute 'vade_taramasi'" gibi hatalar alınır
# ve kullanıcı uygulamayı elle kapatıp açmak zorunda kalır.
#
# ÇÖZÜM: Dosyaların değişiklik zamanını izle; değişen varsa İLGİLİ TÜM yerel
# modülleri sys.modules'tan sil. Aşağıdaki `import` satırları o modülleri
# sıfırdan yükler. Hepsini birden silmek önemlidir: modüller birbirini import
# ettiği için (ör. analiz_motoru → ozet_metni) sadece birini yenilemek
# tutarsız duruma yol açardı.
#
# NOT (AKD geçişi): Geçmiş örüntü (istatistiksel benzerlik) tabanlı sinyal
# sistemi kullanıcı geri bildirimiyle YANILTICI bulunduğu için komple
# kaldırıldı (bkz. OKU_BENI.txt). İkinci görüş artık AKD (Aracı Kurum
# Dağılımı, Telegram botu üzerinden) sinyalinden geliyor — telegram_akd.py.
_KLASOR = os.path.dirname(os.path.abspath(__file__))
_ZAMAN_ANAHTARI = "_yerel_modul_zamanlari"


def _yerel_modul_dosyalari():
    return {ad[:-3]: os.path.join(_KLASOR, ad)
            for ad in os.listdir(_KLASOR)
            if ad.endswith(".py") and ad != "app.py"}


def _degisen_modulleri_temizle():
    try:
        dosyalar = _yerel_modul_dosyalari()
    except OSError:
        return []
    simdiki = {}
    for ad, yol in dosyalar.items():
        try:
            simdiki[ad] = os.path.getmtime(yol)
        except OSError:
            continue
    onceki = st.session_state.get(_ZAMAN_ANAHTARI)
    st.session_state[_ZAMAN_ANAHTARI] = simdiki
    if not onceki:
        return []                       # ilk çalıştırma — karşılaştıracak şey yok
    degisenler = [ad for ad, t in simdiki.items() if onceki.get(ad) != t]
    if degisenler:
        for ad in dosyalar:             # HEPSİNİ at, tek tek değil (bkz. yukarısı)
            sys.modules.pop(ad, None)
    return degisenler


_TAZELENENLER = _degisen_modulleri_temizle()

import veri_katmani as vk
import analiz_motoru as am
import portfoy_takip as pt
import llm_ajanlari as la
import sanal_yatirimci as sv
import backtest_motoru as bt
import tavsiye_kaydi as tkd
import ozet_metni as ozm
import hisse_adlari as ha
import tarama_onbellek as tob
import favoriler as fav
import telegram_akd as takd

st.set_page_config(page_title="BIST Analiz Platformu", page_icon="📈",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
/* ═════════════════════════════════════════════════════════════════════════
   FÜTÜRİSTİK KOYU TEMA — cam yüzeyler (glassmorphism) + camgöbeği parıltı.
   Referans: kullanıcının onayladığı Seadance moodboard'u (koyu lacivert zemin,
   ince camgöbeği kenarlıklı camsı kartlar, yuvarlak/parlayan rozetler).
   NOT: Tüm kaydırma kuralları (tek kaydırma = sayfanın kendisi) korunuyor;
   bu güncelleme SADECE görsel yüzey/renk/parıltı katmanını değiştiriyor. ═══ */

:root {
    --cam-bg: rgba(20,27,41,.55);
    --cam-bg-2: rgba(20,27,41,.35);
    --cam-kenar: rgba(56,189,248,.22);
    --cam-kenar-guclu: rgba(56,189,248,.45);
    --parilti: 0 0 0 1px rgba(56,189,248,.10), 0 8px 28px rgba(0,0,0,.35);
    --parilti-hover: 0 0 0 1px rgba(56,189,248,.35), 0 0 26px rgba(14,165,233,.22),
                      0 10px 30px rgba(0,0,0,.4);
}

/* ── Sayfa zemini: derin lacivert + çok hafif ambiyans parıltısı ─────── */
.stApp {
    background:
        radial-gradient(ellipse 900px 480px at 12% -8%, rgba(14,165,233,.10), transparent 60%),
        radial-gradient(ellipse 900px 480px at 100% 0%, rgba(56,189,248,.06), transparent 55%),
        #0a0e17;
}

/* ── Genel yerleşim: TAM GENİŞLİK ────────────────────────────────────
   ÖNCEDEN max-width:1500px vardı ve geniş ekranlarda sayfanın iki yanında
   kocaman boş şeritler kalıyordu (kullanıcı: "sayfayı daraltmayı iptal et,
   yatay serbest olsun, ekrana sığdır"). Artık içerik pencerenin TAMAMINI
   kullanır; kenar boşluğu sadece nefes payı kadardır. ─────────────────── */
.block-container {padding-top: 1.1rem; max-width: 100% !important;
                  padding-left: 1.6rem; padding-right: 1.6rem;}
/* Hiçbir bileşen sayfayı yatayda taşırmasın (yatay kaydırma çubuğu çıkmasın) */
.block-container, .stMarkdown {overflow-x: hidden;}
.stMarkdown img, .stMarkdown div {max-width: 100%;}
/* Grafikler/tablolar kolon genişliğini tam doldursun — sağda boşluk kalmasın */
div[data-testid="stPlotlyChart"], div[data-testid="stPlotlyChart"] > div {width: 100% !important;}
div[data-testid="stDataFrame"] {width: 100% !important;}

/* ── Metrikler: camsı kart, hover'da camgöbeği parıltı ───────────── */
div[data-testid="stMetric"] {
    background: linear-gradient(160deg, var(--cam-bg), var(--cam-bg-2));
    backdrop-filter: blur(10px);
    border: 1px solid var(--cam-kenar);
    border-radius: 14px; padding: 12px 14px;
    box-shadow: var(--parilti);
    transition: box-shadow .18s ease, border-color .18s ease, transform .12s ease;
}
div[data-testid="stMetric"]:hover {
    border-color: var(--cam-kenar-guclu); box-shadow: var(--parilti-hover);
    transform: translateY(-1px);
}
div[data-testid="stMetricValue"] {font-size: 1.45rem; font-weight: 650;
                                  text-shadow: 0 0 18px rgba(56,189,248,.18);}
div[data-testid="stMetricLabel"] {opacity: .78; font-size: .82rem;
                                  text-transform: uppercase; letter-spacing: .05em;}

/* ── Sekmeler: camsı bir "şerit" içinde, parlayan alt çizgi ─────────── */
div[data-baseweb="tab-list"] {
    background: var(--cam-bg-2); backdrop-filter: blur(10px);
    border: 1px solid var(--cam-kenar); border-radius: 14px;
    padding: 4px 6px; gap: 2px; box-shadow: var(--parilti);
}
button[data-baseweb="tab"] {font-size: .95rem; font-weight: 600; padding: 8px 14px;
                            border-radius: 10px;
                            transition: color .15s ease, background .15s ease;}
button[data-baseweb="tab"]:hover {background: rgba(56,189,248,.08); color: #38bdf8;}
button[data-baseweb="tab"][aria-selected="true"] {
    background: rgba(56,189,248,.12); color: #7dd3fc;
    text-shadow: 0 0 14px rgba(56,189,248,.45);
}
div[data-baseweb="tab-highlight"] {background-color: #38bdf8;
                                   box-shadow: 0 0 10px rgba(56,189,248,.7);
                                   transition: left .25s cubic-bezier(.22,.9,.35,1),
                                               width .25s cubic-bezier(.22,.9,.35,1);}
div[data-baseweb="tab-border"] {background-color: transparent;}

/* ── Butonlar: camgöbeği parıltılı hover/aktif geçişi ────────────── */
.stButton > button, .stDownloadButton > button {
    background: rgba(148,163,184,.05); backdrop-filter: blur(6px);
    border: 1px solid rgba(148,163,184,.22); border-radius: 10px;
    transition: transform .08s ease, box-shadow .15s ease, border-color .15s ease,
                background .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    border-color: rgba(56,189,248,.6); background: rgba(56,189,248,.08);
    box-shadow: 0 0 0 1px rgba(56,189,248,.25), 0 0 16px rgba(14,165,233,.25);
}
.stButton > button:active { transform: scale(0.98); }
/* Birincil (type="primary") butonlar: camgöbeği dolgulu, belirgin çağrı */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, rgba(14,165,233,.85), rgba(56,189,248,.65));
    border-color: rgba(125,211,252,.7); color: #041926; font-weight: 700;
    box-shadow: 0 0 20px -4px rgba(56,189,248,.6);
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 0 26px -2px rgba(56,189,248,.85);
}

/* ── Başlık ──────────────────────────────────────────────────────────
   NOT: Burada önce degrade (background-clip:text) bir başlık vardı; ancak
   -webkit-text-fill-color:transparent EMOJİYİ de şeffaf yapıyor ve
   "📈 BIST Analiz Platformu" başlığındaki emoji boş kutu olarak görünüyordu
   (canlı uygulamada doğrulandı). Bu yüzden düz renk kullanılıyor. ────── */
h1 {color: #e6edf6; letter-spacing: -.02em; font-weight: 750;
    text-shadow: 0 0 26px rgba(56,189,248,.18);}
h2, h3 {letter-spacing: -.01em;}

/* ── Streamlit'in kırmızı-turuncu üst dekorasyon şeridi ──────────────
   Varsayılan tema şeridi bu fütüristik paletle uyuşmuyor ve canlı
   uygulamada sayfanın kenarında alakasız turuncu bir ışıma bırakıyordu. */
#stDecoration {display: none !important;}

/* ── Dikey alan tasarrufu ────────────────────────────────────────────
   Canlı testte üstteki Favoriler + Piyasa Rejimi blokları o kadar yer
   kaplıyordu ki SEKMELER ekranın en altına düşüyordu; kullanıcı uygulamayı
   açtığında asıl içeriği göremiyordu. Boşluklar sıkılaştırıldı. ────── */
h3 {margin-top: .9rem; margin-bottom: .2rem;}
hr {margin: .9rem 0;}
div[data-testid="stVerticalBlock"] {gap: .55rem;}

/* ── Bilgi/uyarı kutuları da camsı olsun ─────────────────────────── */
div[data-testid="stAlert"] {border-radius: 12px; backdrop-filter: blur(8px);
                            border: 1px solid rgba(148,163,184,.22);}

/* ── Form alanları: camsı zemin, odakta camgöbeği halka ──────────── */
div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {
    background: rgba(148,163,184,.06) !important;
    border-color: rgba(148,163,184,.22) !important; border-radius: 10px !important;
    transition: border-color .15s ease, box-shadow .15s ease;
}
div[data-baseweb="select"] > div:focus-within, .stTextInput input:focus,
.stNumberInput input:focus {
    border-color: rgba(56,189,248,.6) !important;
    box-shadow: 0 0 0 2px rgba(56,189,248,.18) !important;
}

/* ── Genel tipografi: biraz daha ferah satır aralığı ─────────────── */
.stMarkdown p, .stMarkdown li {line-height: 1.55;}

/* ── AKICI HTML TABLOLAR (_html_tablo ile üretilir) ──────────────────
   NEDEN VAR: st.dataframe, satır sayısına göre yükseklik hesaplansa bile
   kendi İÇ görüntüleme motoruna (canvas tabanlı ızgara) sahiptir ve bazı
   pencere/ekran koşullarında yine de küçük bir kaydırma çubuğu gösterebilir.
   Salt-GÖSTERİM amaçlı (tıklanabilir olmayan) tablolarda bunun yerine düz
   bir HTML <table> kullanılır — bu, TARAYICI SAYFA AKIŞININ doğal bir
   parçasıdır, kendi görüntüleme alanı/kaydırması OLAMAZ. Sayfa ne kadar
   uzarsa uzasın, kaydıran TEK ŞEY sayfanın kendisidir. ────────────────── */
.akici-tablo-sarici {overflow-x: auto; max-width: 100%; border-radius: 14px;
                      background: var(--cam-bg-2); backdrop-filter: blur(8px);
                      border: 1px solid var(--cam-kenar); margin: .3rem 0 .8rem;
                      box-shadow: var(--parilti);}
.akici-tablo {width: 100%; border-collapse: collapse; font-size: .89rem;}
.akici-tablo thead th {text-align: left; padding: 9px 12px; font-weight: 650;
                        font-size: .78rem; text-transform: uppercase; letter-spacing: .04em;
                        color: rgba(226,232,240,.65);
                        background: rgba(56,189,248,.06);
                        border-bottom: 1px solid var(--cam-kenar);
                        white-space: nowrap;}
.akici-tablo tbody td {padding: 8px 12px; border-bottom: 1px solid rgba(148,163,184,.10);
                        white-space: nowrap;}
.akici-tablo tbody tr:last-child td {border-bottom: none;}
.akici-tablo tbody tr:nth-child(even) {background: rgba(148,163,184,.035);}
.akici-tablo tbody tr {transition: background .12s ease;}
.akici-tablo tbody tr:hover {background: rgba(14,165,233,.10);}
.akici-tablo td.sayi {text-align: right; font-variant-numeric: tabular-nums;}
.akici-pill {display:inline-block; padding: 3px 10px; border-radius: 999px;
             font-weight: 650; font-size: .82rem; white-space: nowrap;
             box-shadow: 0 0 10px -2px currentColor; border: 1px solid currentColor;}

/* ── SATIR KAYDIRAN METİN BLOĞU ──────────────────────────────────────
   NEDEN: st.text() içeriği bir <pre> etiketine koyar; uzun satırlar
   sığmayınca o bloğa KENDİ YATAY KAYDIRMA ÇUBUĞU eklenir. Bu, sayfadaki
   "iç içe kayar çubuk" şikayetinin kalan kaynaklarındandı. Aşağıdaki blok
   aynı sabit-genişlikli görünümü korur ama satırları SARAR — kaydırma
   çubuğu oluşmaz. ─────────────────────────────────────────────────── */
.metin-blogu {white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere;
              font-family: ui-monospace, "Cascadia Code", "Consolas", monospace;
              font-size: .82rem; line-height: 1.5; margin: 0;
              background: var(--cam-bg-2); backdrop-filter: blur(6px);
              border: 1px solid var(--cam-kenar);
              border-radius: 12px; padding: 12px 14px;}

/* ── WEB SİTESİ HİSSİ ─────────────────────────────────────────────────
   Yumuşak kaydırma + bölümler arası ferah boşluk + tıklanabilir görünen
   açılır başlıklar (accordion). Standart bir web sitesinde olduğu gibi:
   TEK dikey kaydırma, başlıklara tıklayınca ayrıntı açılır. ────────── */
html {scroll-behavior: smooth;}
details summary, div[data-testid="stExpander"] summary {cursor: pointer;}
div[data-testid="stExpander"] {border-radius: 14px; border-color: var(--cam-kenar);
                                background: var(--cam-bg-2); backdrop-filter: blur(8px);
                                margin-bottom: .5rem; transition: box-shadow .18s ease;}
div[data-testid="stExpander"]:hover {box-shadow: var(--parilti);}
div[data-testid="stExpander"] summary:hover {color: #38bdf8;}
div[data-testid="stExpander"] summary p {font-weight: 600;}
hr {margin: 1.4rem 0; border-color: rgba(148,163,184,.16);}
h3 {margin-top: 1.6rem;}

/* ── Karar kutusu: camsı + parayla ilişkili renk parıltısı ───────── */
.puan-kutu {border-radius: 16px; padding: 18px 20px; text-align:center;
            background: linear-gradient(135deg, rgba(20,27,41,.85), rgba(10,14,23,.9));
            backdrop-filter: blur(10px); color:#fff;
            box-shadow: 0 0 24px -6px var(--kkrenk, rgba(56,189,248,.5)),
                        0 8px 26px rgba(0,0,0,.4);
            transition: box-shadow .2s ease;}

/* ── Renkli durum rozetleri (renkler ozm.renk_kodu ile satır içi belirlenir) ── */
.rozet {display:inline-block; padding: 5px 13px; border-radius: 999px;
        font-weight: 700; font-size: .95rem; letter-spacing:.2px;
        border: 1px solid transparent;
        box-shadow: 0 0 14px -3px currentColor;}

/* ── Üst özet şerit / ticker ─────────────────────────────────────── */
/* NEDEN wrap (KAYDIRMA YOK): eskiden overflow-x:auto ile kendi yatay
   kaydırma çubuğu vardı — kullanıcı "her yerde kayar sekme var, hepsi sabit
   olsun" dedi. Artık öğeler sığmadığında YENİ SATIRA GEÇER (flex-wrap),
   hiçbir öğe gizlenmez/kaydırma gerekmez; tek kaydırma sayfanın kendisidir. */
.ust-serit {display:flex; gap:10px; flex-wrap:wrap; padding:10px 14px;
            border-radius: 14px; margin-bottom: .6rem; align-items:center;
            background: linear-gradient(160deg, var(--cam-bg), var(--cam-bg-2));
            backdrop-filter: blur(10px);
            border: 1px solid var(--cam-kenar); box-shadow: var(--parilti);}
/* Her öğe kendi mini cam "çipi" — moodboard'daki ticker şeridi gibi */
.ust-oge {white-space:nowrap; font-size:.86rem; display:flex; align-items:center; gap:7px;
          padding:5px 12px; border-radius:999px;
          background: rgba(148,163,184,.06); border:1px solid rgba(148,163,184,.14);
          transition: border-color .15s ease, background .15s ease;}
.ust-oge:hover {border-color: rgba(56,189,248,.35); background: rgba(56,189,248,.07);}
.ust-oge b {font-size:.95rem; font-variant-numeric: tabular-nums;
            text-shadow: 0 0 14px rgba(56,189,248,.2);}
/* Canlı nabız noktası — üst şeritteki güncel değerlerin yanına eklenebilir */
.canli-nokta {display:inline-block; width:7px; height:7px; border-radius:50%;
              background:#22c55e; box-shadow:0 0 8px 1px #22c55e;
              animation: nabiz 1.8s ease-in-out infinite;}
@keyframes nabiz {0%,100%{opacity:1; transform:scale(1);} 50%{opacity:.45; transform:scale(1.35);}}

/* ── Kart konteynerleri: camsı, ince parıltılı kenar ─────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px; background: var(--cam-bg-2); backdrop-filter: blur(8px);
    transition: box-shadow .18s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {box-shadow: var(--parilti);}

/* ── Vade puanı mini kartları ───────────────────────────────────── */
/* overflow:hidden + box-sizing ŞART: içerideki gradyan çubuk kart genişliğini
   aşarsa (dar analiz panelinde olduğu gibi) tüm sayfa yatayda bozuluyor. */
.vade-kart {border-radius: 14px; padding: 10px 8px; text-align:center;
            border:1px solid rgba(148,163,184,.28); background: var(--cam-bg-2);
            backdrop-filter: blur(6px);
            overflow:hidden; box-sizing:border-box; max-width:100%;
            transition: box-shadow .18s ease, transform .12s ease;}
.vade-kart:hover {box-shadow: 0 0 16px -4px currentColor; transform: translateY(-1px);}
.vade-kart .ad  {font-size:.72rem; opacity:.75; display:block; margin-bottom:3px;
                 line-height:1.15; min-height:2.1em; overflow-wrap:anywhere;}
.vade-kart .deg {font-size:1.3rem; font-weight:700; display:block; line-height:1.1;
                 text-shadow: 0 0 14px currentColor;}
.vade-kart .bar {font-size:.78rem; letter-spacing:-1px;}

/* ── Sade özet kutusu: sol kenar vurgulu ────────────────────────── */
.ozet-basligi {font-weight:700; font-size:1.02rem; margin-bottom:.3rem;}

/* ── Tablolarda satır yüksekliği biraz artsın (emoji okunsun) ───── */
div[data-testid="stDataFrame"] {border-radius: 12px; border: 1px solid var(--cam-kenar);}

/* ── Dairesel puan göstergesi (radyal gauge) ─────────────────────────
   AKIŞKAN BOYUT: sabit px yerine kolon genişliğine göre ölçeklenir (min 130px,
   max 210px). Böylece hem dar analiz kolonunda hem de tam ekranda düzgün
   oturur; dar kolonda taşıp sayfayı yatayda bozmaz. ───────────────────── */
.radyal-gosterge {position:relative; width:clamp(130px, 12vw, 210px); aspect-ratio:1/1;
                   margin:0 auto; border-radius:50%;
                   display:flex; align-items:center; justify-content:center;
                   animation: rg-gir .5s cubic-bezier(.22,.9,.35,1);}
@keyframes rg-gir {from {opacity:0; transform:scale(.9);} to {opacity:1; transform:scale(1);}}
.radyal-gosterge::before {content:""; position:absolute; inset:0; border-radius:50%;
                          padding:4px;
                          background: conic-gradient(from -90deg,
                                      var(--rg-renk, #38bdf8) calc(var(--rg-oran,0) * 1%),
                                      rgba(148,163,184,.10) 0);
                          -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
                          -webkit-mask-composite: xor; mask-composite: exclude;
                          box-shadow: 0 0 30px -6px var(--rg-renk, #38bdf8);
                          transition: background 1s cubic-bezier(.22,.9,.35,1);}
/* İnce dış halka — "cihaz" hissi veren ikinci kontur */
.radyal-gosterge::after {content:""; position:absolute; inset:-6px; border-radius:50%;
                         border:1px solid rgba(56,189,248,.14); pointer-events:none;}
.radyal-gosterge .rg-ic {position:relative; width:82%; height:82%; border-radius:50%;
                         background: radial-gradient(circle at 35% 28%, rgba(30,41,59,.95), #0a0e17 70%);
                         display:flex; flex-direction:column; align-items:center; justify-content:center;
                         box-shadow: inset 0 0 26px rgba(0,0,0,.55),
                                     inset 0 1px 0 rgba(255,255,255,.05);}
.radyal-gosterge .rg-sayi {font-size:clamp(1.5rem, 2.6vw, 2.3rem); font-weight:750; line-height:1;
                           color:var(--rg-renk, #38bdf8); text-shadow:0 0 20px currentColor;
                           font-variant-numeric: tabular-nums;}
.radyal-gosterge .rg-etiket {font-size:.68rem; opacity:.65; margin-top:5px;
                             text-transform:uppercase; letter-spacing:.09em;
                             text-align:center; padding:0 8px; line-height:1.2;}
/* Küçük boy — üstteki rejim şeridi gibi dikeyde yer kaplamaması gereken yerler */
.radyal-gosterge.kucuk {width:clamp(88px, 7vw, 118px); margin:0;}
.radyal-gosterge.kucuk::before {padding:3px;}
.radyal-gosterge.kucuk .rg-sayi {font-size:clamp(1.05rem, 1.6vw, 1.35rem);}
.radyal-gosterge.kucuk .rg-etiket {font-size:.55rem; margin-top:2px; letter-spacing:.06em;}

/* ── Yumuşak açılış animasyonu ────────────────────────────────────────
   Sekme değiştirince içerik "hop" diye belirmek yerine yumuşakça girer —
   moodboard'daki geçiş hissi. Sadece opaklık/konum animasyonu; yerleşimi
   veya kaydırmayı ETKİLEMEZ. ─────────────────────────────────────────── */
div[data-baseweb="tab-panel"] {animation: icerik-gir .28s cubic-bezier(.22,.9,.35,1);}
@keyframes icerik-gir {from {opacity:0; transform: translateY(6px);}
                       to   {opacity:1; transform: none;}}

/* Hareket azaltma tercihi olan kullanıcılarda animasyonlar kapanır */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {animation: none !important; transition: none !important;}
}

/* NOT: Burada eskiden TÜM elemanlara ("*") kalın bir kaydırma çubuğu
   zorlayan genel bir CSS kuralı vardı. Streamlit hemen her widget'ı iç içe
   div'lere sardığından bu kural, taşması olmayan onlarca küçük kutuda bile
   gereksiz kaydırma çubuğu/ok simgesi belirmesine yol açtı ("her yerde kayar
   sekme var" şikayeti). Kaldırıldı — kaydırma çubukları artık SADECE gerçekten
   taşan yerlerde (ör. çok uzun bir sayfa) tarayıcının kendi varsayılan
   çubuğuyla görünür. */

/* ═════════════════════════════════════════════════════════════════════════
   MOBİL (iOS Safari, ~375-430px genişlik) — SADECE dar ekranda devreye
   girer. Masaüstü görünümü yukarıdaki kurallarla değişmeden kalır; bu blok
   ekleme/düzeltme niteliğindedir. Amaç: dokunma hedeflerini iOS İnsan
   Arayüzü Kılavuzu'nun ~44px asgari ölçüsüne çıkarmak, çok küçük yazı
   tiplerini okunur kılmak ve dar ekranda kenar boşluklarını azaltmak.
   Kolonların alt alta dizilmesi zaten Streamlit'in kendi davranışı —
   buna dokunulmuyor. ═════════════════════════════════════════════════════ */
@media (max-width: 480px) {
    /* Kenar boşlukları daralt — dar ekranda her piksel değerli */
    .block-container {padding-left: .7rem; padding-right: .7rem; padding-top: .7rem;}

    /* Butonlar: asgari 44px dokunma yüksekliği (iOS HIG) */
    .stButton > button, .stDownloadButton > button {
        min-height: 44px; padding-top: 10px; padding-bottom: 10px;
        font-size: 1rem;
    }

    /* Sekmeler: dokunması kolay, taşmayan şerit */
    div[data-baseweb="tab-list"] {overflow-x: auto; flex-wrap: nowrap;}
    button[data-baseweb="tab"] {min-height: 44px; padding: 10px 12px; font-size: .9rem;}

    /* Form alanları: metin girişi, sayı girişi, seçim kutuları */
    .stTextInput input, .stNumberInput input, div[data-baseweb="select"] > div {
        min-height: 44px; font-size: 1rem;
    }
    div[data-baseweb="select"] {min-height: 44px;}

    /* iOS Safari, bir input'un hesaplanmış yazı boyutu 16px'in altındaysa
       kullanıcı dokununca sayfayı otomatik yakınlaştırır (odak kaybolunca da
       geri açmaz, kullanıcı elle uzaklaştırmak zorunda kalır). Yukarıdaki
       1rem kuralı çoğu durumda yeterli ama emin olmak için tüm gerçek form
       elemanlarına açık 16px atanıyor — SADECE bu dar-ekran bloğunda,
       masaüstü görünümü etkilenmiyor. */
    input, select, textarea {font-size: 16px !important;}

    /* Checkbox/radio dokunma alanı büyütülsün */
    .stCheckbox, .stRadio {min-height: 44px;}
    .stCheckbox label, .stRadio label {min-height: 44px; display: flex; align-items: center;}

    /* Expander başlıkları da rahat dokunulabilir olsun */
    div[data-testid="stExpander"] summary {min-height: 44px; display: flex; align-items: center;}

    /* Metrik kartları: dar ekranda biraz daha kompakt ama okunur */
    div[data-testid="stMetricValue"] {font-size: 1.25rem;}
    div[data-testid="stMetricLabel"] {font-size: .76rem;}
    div[data-testid="stMetric"] {padding: 10px 10px;}

    /* Çok küçük yazı tipleri (.68rem / .55rem / .7rem) dar ekranda göz
       yormasın diye büyütülüyor */
    .radyal-gosterge .rg-etiket {font-size: .72rem;}
    .radyal-gosterge.kucuk .rg-etiket {font-size: .62rem;}
    .vade-kart .ad {font-size: .76rem;}
    .ust-oge {font-size: .82rem; padding: 6px 11px;}

    /* Akıcı HTML tablolar: dar ekranda biraz daha küçük hücre dolgusu,
       yatay kaydırma zaten .akici-tablo-sarici içinde mevcut */
    .akici-tablo thead th, .akici-tablo tbody td {padding: 8px 9px;}
    .akici-tablo {font-size: .84rem;}

    /* Yerel st.dataframe/st.table zaten kendi iç yatay kaydırmasını
       yapıyor; dar ekranda taşmayı önlemek için genişliği sınırla */
    div[data-testid="stDataFrame"], div[data-testid="stTable"] {
        max-width: 100%; overflow-x: auto;
    }

    /* Radyal gösterge dar ekranda gereğinden büyük olmasın */
    .radyal-gosterge {width: clamp(110px, 30vw, 160px);}
    .radyal-gosterge.kucuk {width: clamp(76px, 20vw, 100px);}

    /* Başlık dar ekranda taşmasın */
    h1 {font-size: 1.5rem;}
}
</style>
""", unsafe_allow_html=True)


def radyal_gosterge_html(puan, etiket: str = "PUAN", kucuk: bool = False) -> str:
    """Dairesel (radyal) puan göstergesi — Seadance moodboard'undaki dairesel
    skor göstergesinin HTML/CSS karşılığı. conic-gradient ile dolgu oranı
    puana göre çizilir; canvas/JS gerekmez, sayfa akışını bozmaz.

    kucuk=True: üstteki piyasa rejimi şeridi gibi, dikeyde yer kaplamaması
    gereken yerler için küçük boy (canlı testte büyük gösterge sekmeleri
    ekranın dibine itiyordu).
    """
    p = ozm._sayi(puan)
    oran = 0 if p is None else max(0.0, min(100.0, p))
    renk = ozm.renk_kodu(p)
    deger = f"{p:.0f}" if p is not None else "—"
    sinif = "radyal-gosterge kucuk" if kucuk else "radyal-gosterge"
    return (f"<div class='{sinif}' style='--rg-oran:{oran};--rg-renk:{renk}'>"
            f"<div class='rg-ic'><span class='rg-sayi'>{deger}</span>"
            f"<span class='rg-etiket'>{etiket}</span></div></div>")


def rozet(puan, metin: str = None) -> str:
    """Puana göre GRADYANLI renkli HTML rozet (yeşil → sarı → kırmızı).

    Renk, ozet_metni.renk_kodu() ile sürekli bir eksende hesaplanır; böylece
    41 ile 48 puan arasında bile ton farkı görülür. Durum adı üç kategoriye
    indirgenir (Olumlu / Nötr / Olumsuz) — çünkü kullanıcı için asıl soru
    "yaklaşayım mı, uzak mı durayım?" sorusudur.
    """
    renk = ozm.renk_kodu(puan)
    ad = ozm.durum_adi(puan)
    return (f"<span class='rozet' style='background:{renk}1f;color:{renk};"
            f"border-color:{renk}66'>{metin or ad.upper()}</span>")


def durum_serit(puan, etiket: str = None) -> str:
    """Gradyan çubuk + durum adı içeren kompakt görsel şerit."""
    renk = ozm.renk_kodu(puan)
    ad = etiket or ozm.durum_adi(puan)
    deger = f"{puan:.0f}" if isinstance(puan, (int, float)) and puan == puan else "—"
    return (f"<div style='display:flex;align-items:center;gap:10px'>"
            f"<span style='font-weight:700;color:{renk};min-width:34px'>{deger}</span>"
            f"{ozm.gradyan_cubugu_html(puan, 110, 9)}"
            f"<span style='font-size:.86rem;opacity:.85'>{ad}</span></div>")


def vade_kartlari(puanlar: dict, sutun_sayisi: int = None):
    """Vade puanlarını gradyan renkli mini kartlar halinde gösterir."""
    if not puanlar:
        return
    ogeler = list(puanlar.items())
    kolonlar = st.columns(sutun_sayisi or len(ogeler))
    for kolon, (ad, puan) in zip(kolonlar, ogeler):
        renk = ozm.renk_kodu(puan)
        with kolon:
            st.markdown(
                f"<div class='vade-kart' style='border-color:{renk}55;"
                f"background:linear-gradient(180deg,{renk}14,{renk}05)'>"
                f"<span class='ad'>{ad}</span>"
                f"<span class='deg' style='color:{renk}'>"
                f"{('%.0f' % puan) if puan is not None else '—'}</span>"
                # ÖNEMLİ: yüzde kullanılır, sabit piksel DEĞİL. Sabit 999px
                # verildiğinde çubuk dar kolonlardan (ör. sağdaki analiz paneli)
                # taşıp sayfayı yatayda bozuyordu.
                f"{ozm.gradyan_cubugu_html(puan, '100%', 7)}"
                f"<span style='font-size:.7rem;opacity:.7'>{ozm.durum_adi(puan)}</span></div>",
                unsafe_allow_html=True)

st.title("📈 BIST Analiz Platformu")
st.caption("Gerçek verilerle kısa · orta · uzun vade sinyal, takas analizi ve hisse puanlama. "
           "⚠️ Bu yazılım bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.")

if _TAZELENENLER:
    st.info("🔄 Güncellenen modüller belleğe yeniden yüklendi: "
            + ", ".join(sorted(_TAZELENENLER))
            + ". (Uygulamayı kapatıp açmanıza gerek yok.)")


# ─── Önbellekli veri fonksiyonları ───────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _gecmis(sembol, yil=2.0):
    return vk.fiyat_gecmisi(sembol, yil)

@st.cache_data(ttl=3600, show_spinner=False)
def _endeks():
    return vk.endeks_gecmisi(2.0)

@st.cache_data(ttl=3600, show_spinner=False)
def _temel(sembol):
    return vk.temel_veriler(sembol)

@st.cache_data(ttl=3600, show_spinner=False)
def _yabanci(sembol):
    return vk.yabanci_orani_gecmisi(sembol, 1.0)

@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _semboller(kapsam):
    return vk.sembol_listesi(kapsam)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _semboller_ayrintili(kapsam):
    """(liste, kaynak_metni) — kaç hissenin nereden geldiğini arayüzde
    gösterebilmek için. Kullanıcı 600 hisse taradığını sanıp 100 taramasın."""
    try:
        return vk.sembol_listesi(kapsam, ayrinti=True)
    except TypeError:
        return vk.sembol_listesi(kapsam), "?"


@st.cache_data(ttl=3600, show_spinner=False, max_entries=6)
def _toplu_fiyat(semboller_demeti: tuple, yil: float):
    """Toplu OHLCV indirme — ÖNBELLEKLİ.

    HIZ GEREKÇESİ: Bu çağrı önceden hiç önbelleğe alınmıyordu; "Öne Çıkan
    Hisseler", "Yükselebilecek Hisseler" ve sanal portföy panelinde her buton
    basışında ~600 hissenin 1,5-2 yıllık verisi YENİDEN indiriliyordu. Uygulamanın
    en yavaş adımı buydu (dakikalarca sürebiliyor). Artık aynı kapsam+süre için
    ilk indirmeden sonraki çağrılar anında döner; veri 1 saat sonra tazelenir.
    Liste yerine demet (tuple) alınmasının sebebi, Streamlit önbelleğinin
    argümanların değişmez/hashlenebilir olmasını gerektirmesidir.
    """
    return vk.toplu_fiyat(list(semboller_demeti), yil=yil)

@st.cache_data(ttl=3600, show_spinner=False)
def _etf(sembol):
    return vk.etf_sahipligi(sembol)

@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _tefas():
    return vk.tefas_hisse_trendi(6)

@st.cache_data(ttl=3600, show_spinner=False)
def _usdtry():
    return vk.usdtry_gecmisi(1.5)

@st.cache_data(ttl=3600, show_spinner=False)
def _rejim():
    try:
        return am.piyasa_rejimi(vk.endeks_gecmisi(2.0), vk.usdtry_gecmisi(1.5),
                                vk.tefas_hisse_trendi(6))
    except Exception:
        return None


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _hisse_adlari():
    return ha.adlari_getir()


def hisse_secici(etiket_metni: str, anahtar: str, varsayilan: str = "",
                  yardim: str = None):
    """Hisse kodu YERİNE ŞİRKET ADIYLA da arama yapılabilen seçici.

    BIST'te ~600 hisse var ve kodların çoğu akılda kalmıyor. Streamlit'in
    selectbox'ı yazdıkça listeyi filtrelediği için, kullanıcı "ereğli" yazınca
    "EREGL — Ereğli Demir ve Çelik" seçeneğini bulabilir. Adı bilinmeyen
    hisselerde sadece kod gösterilir (uydurma ad yazılmaz).
    Dönüş: seçilen hisse kodu (str) veya "".
    """
    adlar = _hisse_adlari()
    try:
        semboller = _semboller("TUM")
    except Exception:
        semboller = []
    if not semboller:
        semboller = sorted(adlar.keys())
    # Adı bilinenler önce gelsin — arama yaparken daha kullanışlı.
    semboller = sorted(set(semboller), key=lambda s: (s not in adlar, s))
    secenekler = [""] + [ha.etiket(s, adlar) for s in semboller]
    baslangic = 0
    if varsayilan:
        hedef = ha.etiket(varsayilan, adlar)
        if hedef in secenekler:
            baslangic = secenekler.index(hedef)
    secim = st.selectbox(etiket_metni, secenekler, index=baslangic, key=anahtar,
                         help=yardim or "Hisse kodunu VEYA şirket adını yazarak arayabilirsiniz "
                                        "(örn. 'ereğli' yazınca EREGL çıkar).",
                         placeholder="Kod veya şirket adı yazın…")
    return ha.etiketten_sembol(secim)


def _uyum_filtresi(tablo, sadece_uyumlu: bool):
    """Çelişkili satırları gizleyip yalnızca NİHAİ KARARI olumlu olanları bırakır."""
    if tablo is None or len(tablo) == 0 or not sadece_uyumlu:
        return tablo
    if "Nihai" in tablo.columns:
        return tablo[tablo["Nihai"].astype(str).str.contains("🟢")]
    if "Uyum" in tablo.columns:
        return tablo[tablo["Uyum"].astype(str).str.startswith("✅")]
    return tablo


def _vade_kolon_ayari():
    """Vade bazlı tarama tablosu: Kısa/Orta/Uzun kararlar + destekleyici sayılar.

    NOT (AKD geçişi): Bu tablo artık analiz_motoru.vade_taramasi()'nden gelir
    (saf TEKNİK — geçmiş örüntü karşılaştırması yok). Eski 'Benzerlik %',
    'Bek.%', 'Poz.%', 'Örnek' sütunları örüntü motoruna özgüydü, kaldırıldı.
    """
    ayar = {
        "Genel Puan": st.column_config.ProgressColumn(
            "Genel Puan", help="Puanlama motorunun bileşik 0-100 skoru",
            format="%.0f", min_value=0, max_value=100),
        "Fiyat": st.column_config.NumberColumn("Fiyat", format="%.2f ₺"),
        "1 Ay %": st.column_config.NumberColumn("1 Ay", format="%+.1f%%"),
        "3 Ay %": st.column_config.NumberColumn("3 Ay", format="%+.1f%%"),
        "Hacim(M₺)": st.column_config.NumberColumn("Hacim (M₺)", format="%.0f"),
        "Trend": st.column_config.LineChartColumn(
            "Trend", help="Son 15 kapanış fiyatı", width="small"),
    }
    for vade, sure in (("Kısa", "~2 hafta"), ("Orta", "~3 ay"), ("Uzun", "~6 ay")):
        ayar[vade] = st.column_config.TextColumn(
            f"{vade.upper()} ({sure})",
            help=f"{vade} vadedeki TEKNİK KARAR — o vadeye ait puanlama motoru "
                 f"bileşeninden (fiyat/hacim/trend) türetilir.")
        # Ham puan sütunları ana tabloyu şişirmesin diye gizlenir; ayrıntı
        # isteyen alttaki 'Vade ayrıntıları' bölümüne bakar.
        ayar[f"{vade} Puan"] = None
    return ayar


def _tarama_kolon_ayari():
    """Öne Çıkan Hisseler tablosu için renkli/görsel sütun ayarları."""
    ayar = {
        "Puan": st.column_config.ProgressColumn(
            "Puan", help="0-100 bileşik teknik skor", format="%.0f",
            min_value=0, max_value=100),
        "Fiyat": st.column_config.NumberColumn("Fiyat", format="%.2f ₺"),
        "1 Ay %": st.column_config.NumberColumn("1 Ay", format="%+.1f%%"),
        "3 Ay %": st.column_config.NumberColumn("3 Ay", format="%+.1f%%"),
        "Hacim(M₺)": st.column_config.NumberColumn("Hacim (M₺)", format="%.0f"),
        "Trend": st.column_config.LineChartColumn(
            "Trend (son 15 gün)", help="Son 15 kapanış fiyatı — mini grafik", width="small"),
    }
    for k in ("Kısa", "Orta", "Uzun", "Takas"):
        ayar[k] = st.column_config.ProgressColumn(k, format="%.0f",
                                                  min_value=0, max_value=100)
    # "Güçlü hisse" ile "iyi giriş noktası" ayrımı (bkz. analiz_motoru:
    # asiri_uzama_skoru / erken_giris_skoru). Bu iki sütun bilinçli olarak
    # Puan'dan AYRI gösterilir — tek skora ezilirse ayrım kaybolur.
    ayar["Şişkinlik"] = st.column_config.ProgressColumn(
        "Şişkinlik", help="0=sakin, 100=parabolik/aşırı uzamış. Yüksekse "
                          "fiyat ortalamalarından çok uzaklaşmış demektir — "
                          "geri çekilme riski yüksektir.",
        format="%.0f", min_value=0, max_value=100)
    ayar["Giriş"] = st.column_config.ProgressColumn(
        "Giriş", help="0=geç kalınmış, 100=hareketin başında. Puanı yüksek "
                      "ama Giriş'i düşük bir hisse 'güçlü ama şu an almak için "
                      "uygun değil' demektir.",
        format="%.0f", min_value=0, max_value=100)
    return ayar


# ═════════════════════════════════════════════════════════════════════════════
# HIZLI TIKLAMA AKIŞI — listeyi hisse hisse gezerken anında önizleme
# ═════════════════════════════════════════════════════════════════════════════
# NEDEN AYRI BİR "HIZLI" YOL VAR:
# Tam analiz her hisse için 4 AYRI AĞ İSTEĞİ yapar (fiyat geçmişi, temel oranlar,
# yabancı takas oranı, ETF sahipliği). Listeyi tarayıp 20 hisseye tıklayan bir
# kullanıcı için bu 80 istek demektir — her tıklamada saniyelerce bekleme.
# Oysa taramayı çalıştırdığımızda TÜM hisselerin fiyat verisi zaten toplu olarak
# indirilmişti. Hızlı önizleme yalnızca o veriyi kullanır: sıfır ağ isteği,
# ~30 ms hesap. Temel oranlar/takas gibi ağ gerektiren kısımlar, kullanıcı
# açıkça "Tam analiz" derse yüklenir.

def _toplu_veri_kaydet(veriler: dict):
    """Tarama sırasında indirilen fiyat verisini, tıklama önizlemesi de
    kullanabilsin diye oturumda saklar (yeni indirme yapılmasın diye)."""
    mevcut = st.session_state.get("_toplu_veri") or {}
    mevcut.update(veriler or {})
    st.session_state["_toplu_veri"] = mevcut


def _panel_df(sembol: str):
    """Önizleme için fiyat verisi: ÖNCE taramada inen toplu veriden, yoksa tekil."""
    toplu = st.session_state.get("_toplu_veri") or {}
    df = toplu.get(sembol)
    if df is not None and len(df):
        return df
    return _gecmis(sembol)


def _panel_analiz(sembol: str):
    """Hisse başına BİR KEZ hesaplanan hızlı önizleme (ağ isteği yok).

    Sonuç oturumda saklanır; aynı hisseye tekrar tıklanırsa anında gelir.
    """
    anahtar = "_panel_" + sembol
    if anahtar in st.session_state:
        return st.session_state[anahtar]
    try:
        df_p = _panel_df(sembol)
        if df_p is None or len(df_p) == 0:
            sonuc = {"hata": f"'{sembol}' için fiyat verisi bulunamadı."}
        else:
            analiz_p = am.tam_analiz(sembol, df_p, {}, None, _endeks(), rejim=rejim)
            akd_sinyal_p = _akd_sinyal_getir(sembol)
            sonuc = {"analiz": analiz_p, "akd_sinyal": akd_sinyal_p, "df": df_p,
                     "nihai": ozm.nihai_karar(analiz_p, akd_sinyal_p)}
    except Exception as e:
        sonuc = {"hata": str(e)}
    st.session_state[anahtar] = sonuc
    return sonuc


def _akd_sinyal_getir(sembol: str):
    """AKD (Aracı Kurum Dağılımı) sinyalini önbellekten okur (ağ isteği yapmaz).

    Eskiden burada geçmiş örüntü analizi hesaplanıyordu; kullanıcı geri
    bildirimiyle yanıltıcı bulunduğu için tamamen kaldırıldı (bkz. OKU_BENI.txt).
    İkinci görüş artık telegram_akd.oku()'nün döndürdüğü, daha önce Telegram'dan
    çekilip diske yazılmış AKD verisinin içindeki 'sinyal' alanından gelir
    (telegram_akd.akd_sinyal_uret() çıktısı). Veri hiç çekilmemişse None
    döner ve nihai_karar() teknik-tek-motor moduna düşer.
    """
    try:
        akd_veri = takd.oku(sembol)
    except Exception:
        return None
    if not akd_veri:
        return None
    return akd_veri.get("sinyal")


def _analize_gonder(sembol: str):
    """Bir listeden seçilen hisseyi 'Hisse Araştır' sekmesinde analiz eder.

    Streamlit'te sekmeler arası programatik geçiş mümkün olmadığı için,
    analiz burada HEMEN hesaplanıp session_state'e yazılır; kullanıcı
    'Hisse Araştır' sekmesine tıkladığında sonucu hazır bulur.
    """
    try:
        df_a = _gecmis(sembol)
        if df_a is None or df_a.empty:
            return False, f"'{sembol}' için veri bulunamadı."
        temel_a = _temel(sembol)
        etf_a = _etf(sembol)
        analiz_a = am.tam_analiz(sembol, df_a, temel_a, _yabanci(sembol), _endeks(),
                                 etf_df=etf_a if (etf_a is not None and len(etf_a)) else None,
                                 tefas_s=_tefas(), rejim=rejim)
        st.session_state["analiz"] = analiz_a
        st.session_state["df"] = df_a
        st.session_state["temel"] = temel_a
        st.session_state["yabanci"] = _yabanci(sembol)
        st.session_state["etf"] = etf_a
        return True, None
    except Exception as e:
        return False, str(e)


def _panel_mini_grafik(df, sembol):
    """Panelde gösterilen hafif fiyat grafiği (son ~120 gün, çizgi)."""
    d = df.tail(120)
    kapanis = d["Close"].astype(float)
    yukseldi = float(kapanis.iloc[-1]) >= float(kapanis.iloc[0])
    renk = "#26a69a" if yukseldi else "#ef5350"
    dolgu = "rgba(38,166,154,0.12)" if yukseldi else "rgba(239,83,80,0.12)"
    fig = go.Figure(go.Scatter(x=d.index, y=kapanis, mode="lines",
                               line=dict(color=renk, width=1.8),
                               fill="tozeroy", fillcolor=dolgu, name=sembol,
                               hovertemplate="%{x|%d.%m.%Y}<br>%{y:.2f} ₺<extra></extra>"))
    # Y ekseni fiyat aralığına göre daraltılır. Aksi halde fill='tozeroy'
    # ekseni 0'a kadar açıyor ve fiyat hareketi tepede düz çizgi gibi
    # görünüyordu (ör. 30-35 TL bandındaki hisse 0-35 ekseninde eziliyordu).
    alt, ust = float(kapanis.min()), float(kapanis.max())
    pay = max((ust - alt) * 0.12, ust * 0.01, 0.01)
    fig.update_layout(height=170, margin=dict(l=0, r=0, t=6, b=0),
                      template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", showlegend=False,
                      yaxis=dict(gridcolor="rgba(148,163,184,.12)",
                                 range=[alt - pay, ust + pay]),
                      xaxis=dict(gridcolor="rgba(148,163,184,.12)"))
    return fig


def _analiz_paneli(sembol: str, anahtar: str = "panel"):
    """Listeden tıklanan hissenin analizini gösteren panel (sağ tarafta).

    Hızlı önizleme verisiyle çalışır — ağ isteği yapmaz, bu yüzden hisseden
    hisseye anında geçilebilir. Temel oranlar gibi ağ gerektiren veriler için
    alttaki 'Tam analiz' butonu kullanılır.
    """
    if not sembol:
        st.info("👈 Soldaki listeden bir hisseye tıklayın — analizi burada anında açılır.")
        return
    p = _panel_analiz(sembol)
    if p.get("hata"):
        st.error(f"{sembol}: {p['hata']}")
        return

    analiz, nihai, df_p = p["analiz"], p["nihai"], p["df"]
    ad = _hisse_adlari().get(sembol) or ""
    if ad.strip().upper() == sembol.upper():
        ad = ""

    with st.container(border=True):
        _bt1, _bt2 = st.columns([4, 1])
        with _bt1:
            st.markdown(f"## {nihai['emoji']} {sembol}")
            if ad:
                st.caption(ad)
        with _bt2:
            st.write("")
            if sembol in fav.getir():
                if st.button("★", key=f"fav_kaldir_{anahtar}_{sembol}", use_container_width=True,
                            help="Favorilerden çıkar"):
                    fav.cikar(sembol); st.rerun()
            else:
                if st.button("☆", key=f"fav_ekle_{anahtar}_{sembol}", use_container_width=True,
                            help="Favorilere ekle"):
                    fav.ekle(sembol); st.rerun()
        st.markdown(
            f"<div style='padding:8px 12px;border-radius:10px;margin-bottom:6px;"
            f"border-left:5px solid {nihai['renk']};background:{nihai['renk']}14'>"
            f"<b style='color:{nihai['renk']}'>{nihai['karar']}</b> "
            f"<span style='opacity:.75'>· {analiz['genel_puan']:.0f}/100</span></div>",
            unsafe_allow_html=True)

        p1, p2, p3 = st.columns(3)
        p1.metric("Fiyat", f"{analiz['son_fiyat']:.2f} ₺")
        p2.metric("1 Ay", f"%{analiz['getiri_1a']:+.1f}"
                  if analiz.get("getiri_1a") is not None else "—")
        p3.metric("3 Ay", f"%{analiz['getiri_3a']:+.1f}"
                  if analiz.get("getiri_3a") is not None else "—")

        st.plotly_chart(_panel_mini_grafik(df_p, sembol), use_container_width=True,
                        key=f"pgraf_{anahtar}_{sembol}")

        vade_kartlari(analiz.get("puanlar") or {})

        if nihai["celiskili_mi"]:
            st.warning(f"⚠️ Teknik tablo (**{nihai['teknik_karar']}**) ile AKD sinyali "
                      f"(**{nihai['akd_karari']}**) çelişiyor → karar **BEKLE**.")
        elif nihai["akd_var_mi"]:
            st.caption(f"Teknik: **{nihai['teknik_karar']}** · "
                      f"AKD: **{nihai['akd_karari']}**")

        if analiz.get("stop_oneri") and analiz.get("hedef_oneri"):
            st.caption(f"📌 Stop: **{analiz['stop_oneri']} ₺** · "
                      f"Hedef: **{analiz['hedef_oneri']} ₺** (ATR tabanlı)")

        akd_verisi = takd.oku(sembol)
        if akd_verisi and akd_verisi.get("gorsel_dosya") and os.path.exists(akd_verisi["gorsel_dosya"]):
            tazelik = "🟢 taze" if akd_verisi.get("taze_mi") else "🟡 bayat, yeniden çekmek isteyebilirsiniz"
            with st.expander(f"📡 Telegram AKD (BOPT) — {tazelik}", expanded=False):
                st.caption(f"Kaynak: {akd_verisi.get('kaynak', '?')} · "
                          f"Çekilme zamanı: {akd_verisi.get('zaman', '?')[:16].replace('T', ' ')}")
                st.image(akd_verisi["gorsel_dosya"], use_container_width=True)
                st.caption("Bu görsel üçüncü taraf bir Telegram botundan (@b0pt_bot) elle/"
                          "komutla çekilir (`python telegram_akd.py SEMBOL`); uygulama içinden "
                          "otomatik/canlı çekilmez. Doğruluğu teyit edilmemiştir, bilgi amaçlıdır.")

        st.caption("⚡ Hızlı önizleme — fiyat verisine dayanır, ağ isteği yapmaz. "
                  "Temel oranlar (F/K, PD/DD) ve takas verisi için:")
        if st.button("🔍 Tam analizi yükle", key=f"tam_{anahtar}_{sembol}",
                     use_container_width=True):
            with st.spinner(f"{sembol} — temel veriler ve takas çekiliyor..."):
                ok, hata = _analize_gonder(sembol)
            if ok:
                st.success("Tam analiz hazır → **🔍 Hisse Araştır** sekmesine geçin.")
            else:
                st.error(f"Tam analiz yapılamadı: {hata}")


def _mini_analiz_karti(sembol: str):
    """Yan panelin dar alanlar için sadeleştirilmiş hâli (alt alta gösterim)."""
    _analiz_paneli(sembol, anahtar="mini")


def _tablo_kaydet(anahtar: str, semboller):
    """Bir tablonun satır→hisse eşlemesini kaydeder.

    Böylece bir SONRAKİ çalıştırmada, sekmeler daha çizilmeden seçimi çözüp
    analizi hazırlayabiliriz (bkz. _bekleyen_secimleri_isle)."""
    kayit = st.session_state.get("_tablo_kayit") or {}
    kayit[anahtar] = [str(s) for s in semboller]
    st.session_state["_tablo_kayit"] = kayit


def _secili_satirlar(anahtar: str) -> list:
    """st.dataframe(on_select=...) widget durumundan seçili satır indekslerini
    okur. Streamlit sürümüne göre sözlük ya da nesne olabilir; ikisi de desteklenir."""
    durum = st.session_state.get(anahtar)
    if durum is None:
        return []
    sec = durum.get("selection") if isinstance(durum, dict) else getattr(durum, "selection", None)
    if sec is None:
        return []
    satirlar = sec.get("rows") if isinstance(sec, dict) else getattr(sec, "rows", None)
    return list(satirlar or [])


def _bekleyen_secimleri_isle():
    """Tablolardaki tıklamaları, SEKMELER ÇİZİLMEDEN ÖNCE işler.

    HIZ GEREKÇESİ: Eskiden seçim, tablo çizilirken (yani sayfanın ortasında)
    yakalanıyordu; 'Hisse Araştır' sekmesi ondan ÖNCE çizildiği için analizin
    oraya da yansıması ancak st.rerun() ile mümkün oluyordu. Yani her tıklama
    scripti İKİ KEZ baştan çalıştırıyordu. Seçimi en başta çözünce tek çalıştırma
    yetiyor — tıklama tepkisi iki katına çıkıyor.
    """
    kayit = st.session_state.get("_tablo_kayit") or {}
    for anahtar, semboller in list(kayit.items()):
        satirlar = _secili_satirlar(anahtar)
        if not satirlar:
            continue
        i = satirlar[0]
        if i < 0 or i >= len(semboller):
            continue
        sembol = (semboller[i] or "").strip().upper()
        if not sembol or sembol in ("—", "NAN", "NONE"):
            continue
        if st.session_state.get("_son_analiz_" + anahtar) == sembol:
            continue                      # aynı hisse zaten seçili — yeniden hesaplama
        st.session_state["_son_analiz_" + anahtar] = sembol
        # Aynı paneli paylaşan tablolar için (ör. günlük/haftalık listeler)
        # "en son tıklanan" hisseyi grup bazında da sakla.
        st.session_state["_son_secim_" + anahtar.split("_")[0]] = sembol
        _panel_analiz(sembol)             # hızlı önizleme (ağ isteği yok)


def _hisseye_git(sembol: str, anahtar: str):
    """Tekil hisse butonları (ör. Fırsatlar) için hızlı önizleme akışı."""
    st.session_state["_son_analiz_" + anahtar] = sembol
    _panel_analiz(sembol)


def _tam_yukseklik(satir_sayisi: int, baslik_var: bool = True) -> int:
    """Bir st.dataframe'in TÜM satırları kendi İÇ kaydırması olmadan
    göstermesi için gereken piksel yüksekliğini hesaplar.

    NEDEN VAR: st.dataframe yükseklik verilmezse kendi içinde SABİT/kısa bir
    kutuya sığdırıp fazla satırı KENDİ minik kaydırma çubuğuna gönderiyordu —
    kullanıcı "her yerde kayar sekme var, hepsi sabit olsun" diye şikayet etti.
    Bu fonksiyon satır sayısına göre tam yüksekliği hesaplar; öyle bir kutuda
    iç kaydırmaya HİÇ gerek kalmaz, sayfanın TEK kaydırma çubuğu yeterli olur.
    """
    satir_yuksekligi = 35
    baslik_yuksekligi = 38 if baslik_var else 0
    # +40px GENİŞ güvenlik payı: az miktar fazla boşluk, istenmeyen bir iç
    # kaydırma çubuğundan çok daha iyidir — kullanıcı kesinlikle iç kaydırma
    # istemiyor. (Salt-gösterim tablolarının çoğu artık _html_tablo() ile
    # basılıyor ve bu sorunu kökten ortadan kaldırıyor; bu fonksiyon sadece
    # TIKLANABİLİR — st.dataframe gerektiren — tablolar için kullanılıyor.)
    return baslik_yuksekligi + satir_yuksekligi * max(satir_sayisi, 1) + 40


_KARAR_RENK = {
    "GÜÇLÜ AL": "#22c55e", "AL": "#22c55e", "GÜÇLÜ ALIŞ": "#22c55e",
    "İZLE": "#eab308", "İZLE / TUT": "#eab308", "NÖTR": "#eab308",
    "ZAYIF": "#f97316", "ZAYIF / BEKLE": "#f97316", "BEKLE": "#f97316",
    "UZAK DUR": "#ef4444", "UZAK DUR / SAT": "#ef4444", "SAT": "#ef4444",
    "GÜÇLÜ SAT": "#ef4444", "ÇELİŞKİ": "#f97316", "ÇELİŞKİLİ": "#f97316",
}


def _hucre_render(deger) -> str:
    """Bir hücre değerini HTML'e çevirir; emoji+karar metni içeriyorsa
    renkli bir 'pill' rozete sarar (mevcut renk şemasıyla tutarlı).

    Sayılar OKUNAKLI biçimlendirilir: st.dataframe bunu kendiliğinden
    yapıyordu; düz HTML'e geçince 78.30000000000001 gibi ham float
    gösterimleri ekrana düşerdi. Burada en fazla 2 ondalık basamağa
    yuvarlanır ve gereksiz sondaki sıfırlar atılır.
    """
    import html as _html
    if deger is None:
        return "—"
    try:
        if isinstance(deger, float) and np.isnan(deger):
            return "—"
    except Exception:
        pass
    # Sayısal biçimlendirme (bool hariç — True/False metin olarak kalsın)
    if isinstance(deger, (int, np.integer)) and not isinstance(deger, bool):
        return f"{int(deger):,}".replace(",", ".")
    if isinstance(deger, (float, np.floating)):
        d = float(deger)
        if not np.isfinite(d):
            return "—"
        if abs(d) >= 1000:
            return f"{d:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
        s = f"{d:.2f}".rstrip("0").rstrip(".")
        return (s if s not in ("", "-") else "0").replace(".", ",")
    if isinstance(deger, pd.Timestamp):
        return deger.strftime("%d.%m.%Y")
    s = str(deger)
    if s.strip() in ("", "nan", "None", "NaT"):
        return "—"
    metin_govde = s
    for e in ("🟢", "🔴", "🟡", "🟠", "⚪", "⚫", "⚠️"):
        metin_govde = metin_govde.replace(e, "").strip()
    renk = None
    for anahtar, r in _KARAR_RENK.items():
        if anahtar in metin_govde.upper():
            renk = r
            break
    if renk and any(e in s for e in ("🟢", "🔴", "🟡", "🟠", "⚪", "⚫", "⚠️")):
        return (f"<span class='akici-pill' style='background:{renk}22;"
                f"color:{renk};border:1px solid {renk}55'>{_html.escape(s)}</span>")
    return _html.escape(s)


def _metin_blogu(metin: str):
    """Uzun teknik raporları KENDİ KAYDIRMA ÇUBUĞU OLMADAN basar.

    st.text() bunu bir <pre> içine koyar ve uzun satırlarda o bloğa yatay
    kaydırma çubuğu ekler. Burada satırlar sarılır (pre-wrap), böylece
    sayfada tek kaydırma çubuğu kalır.
    """
    import html as _html
    if not metin:
        return
    st.markdown(f"<pre class='metin-blogu'>{_html.escape(str(metin))}</pre>",
                unsafe_allow_html=True)


def _html_tablo(df: pd.DataFrame, sayisal_kolonlar: tuple = None,
                 indeks_goster: bool = False):
    """DataFrame'i, İÇ KAYDIRMASI OLMAYAN düz bir HTML tablo olarak basar.

    Sadece GÖSTERİM amaçlı (tıklanabilir/seçilebilir olmayan) tablolar için
    kullanılır — satır tıklayınca analiz açma özelliği gereken tablolar hâlâ
    st.dataframe(on_select=...) kullanır (bkz. _tablo_ciz). Bu fonksiyonun
    ürettiği tablo TARAYICI SAYFA AKIŞININ doğal bir parçasıdır; ne kadar
    satır olursa olsun kendi kaydırma çubuğu OLUŞMAZ.

    indeks_goster=True ise DataFrame'in indeksi ilk sütun olarak basılır
    (sıralı listelerde "1., 2., 3." sıra numarasını korumak için).
    """
    import html as _html
    if df is None or len(df) == 0:
        st.caption("Gösterilecek veri yok.")
        return
    if sayisal_kolonlar is None:
        sayisal_kolonlar = tuple(c for c in df.columns
                                 if pd.api.types.is_numeric_dtype(df[c]))
    basliklar = ("<th></th>" if indeks_goster else "")
    basliklar += "".join(f"<th>{_html.escape(str(c))}</th>" for c in df.columns)
    satirlar_html = []
    for idx, satir in df.iterrows():
        hucreler = []
        if indeks_goster:
            hucreler.append(f"<td class='sayi' style='opacity:.55'>"
                            f"{_html.escape(str(idx))}</td>")
        for c in df.columns:
            sinif = " class='sayi'" if c in sayisal_kolonlar else ""
            hucreler.append(f"<td{sinif}>{_hucre_render(satir[c])}</td>")
        satirlar_html.append(f"<tr>{''.join(hucreler)}</tr>")
    html = (f"<div class='akici-tablo-sarici'><table class='akici-tablo'>"
           f"<thead><tr>{basliklar}</tr></thead><tbody>{''.join(satirlar_html)}"
           f"</tbody></table></div>")
    st.markdown(html, unsafe_allow_html=True)


def _tablo_ciz(tablo, anahtar: str, sembol_kolonu: str, column_config, hide_index,
               yukseklik):
    """Tabloyu tıklanabilir olarak çizer ve satır→hisse eşlemesini kaydeder.
    Seçimin İŞLENMESİ burada değil, sayfanın en başında yapılır
    (bkz. _bekleyen_secimleri_isle) — böylece tek çalıştırmada sonuç çıkar.

    yukseklik verilmezse TÜM satırları gösterecek tam yükseklik otomatik
    hesaplanır (bkz. _tam_yukseklik) — tablo kendi içinde kaymaz."""
    _tablo_kaydet(anahtar, tablo[sembol_kolonu].tolist())
    hesaplanan = yukseklik if yukseklik is not None else _tam_yukseklik(len(tablo))
    st.dataframe(tablo, use_container_width=True, hide_index=hide_index,
                 column_config=column_config, on_select="rerun",
                 selection_mode="single-row", key=anahtar, height=hesaplanan)


def tiklanabilir_tablo(tablo, anahtar: str, sembol_kolonu: str = "Hisse",
                       column_config: dict = None, hide_index: bool = True,
                       ipucu: bool = True, yukseklik: int = None,
                       yan_panel: bool = False, oran=(3, 2)):
    """Tıklanabilir sonuç tablosu.

    yan_panel=True ise tablo SOLDA, analiz paneli SAĞDA gösterilir; kullanıcı
    listeyi yukarıdan aşağı tıklayarak hızlıca tarayabilir (panel yerinde
    güncellenir, sayfa kaymaz). yan_panel=False ise analiz tablonun altında
    çıkar (dar/ikincil tablolar için).
    """
    if tablo is None or len(tablo) == 0 or sembol_kolonu not in getattr(tablo, "columns", []):
        if tablo is not None:
            # hide_index=False ise sıra numarası korunmalı (sıralı listeler).
            _html_tablo(tablo, indeks_goster=not hide_index)
        return

    if yan_panel:
        sol, sag = st.columns(oran, gap="medium")
        with sol:
            if ipucu:
                st.caption("💡 Bir satıra tıklayın — analiz **sağda** anında açılır. "
                          "Sıradaki hisseye tıklayarak listeyi hızlıca tarayabilirsiniz.")
            _tablo_ciz(tablo, anahtar, sembol_kolonu, column_config, hide_index, yukseklik)
        with sag:
            _analiz_paneli(st.session_state.get("_son_analiz_" + anahtar), anahtar)
        return

    if ipucu:
        st.caption("💡 Bir satıra tıklayınca o hissenin analizi hemen altında açılır.")
    _tablo_ciz(tablo, anahtar, sembol_kolonu, column_config, hide_index, yukseklik)
    gosterilecek = st.session_state.get("_son_analiz_" + anahtar)
    if gosterilecek:
        _analiz_paneli(gosterilecek, anahtar)


def hisse_linki(sembol: str, anahtar: str, etiket: str = None):
    """Tek bir hisse kodunu TIKLANABİLİR bir buton olarak gösterir (metin
    içinde geçen 'AL: THYAO' gibi tekil bahsedişler için — tam tablo yerine)."""
    if st.button(etiket or f"🔗 {sembol}", key=f"link_{anahtar}_{sembol}"):
        _hisseye_git(sembol, anahtar)


def puan_grafigi(puan):
    _renk = ozm.renk_kodu(puan)
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=puan,
        number={"suffix": " / 100", "font": {"size": 34, "color": _renk}},
        gauge={"axis": {"range": [0, 100], "tickcolor": "#475569"},
               "bar": {"color": _renk, "thickness": 0.3},
               "bgcolor": "rgba(148,163,184,.05)",
               "borderwidth": 1, "bordercolor": "rgba(56,189,248,.25)",
               "steps": [{"range": [0, 40], "color": "rgba(239,68,68,.14)"},
                         {"range": [40, 52], "color": "rgba(249,115,22,.14)"},
                         {"range": [52, 62], "color": "rgba(234,179,8,.14)"},
                         {"range": [62, 72], "color": "rgba(34,197,94,.12)"},
                         {"range": [72, 100], "color": "rgba(34,197,94,.20)"}]}))
    fig.update_layout(height=240, margin=dict(l=20, r=20, t=20, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#cbd5e1"))
    return fig


def fiyat_grafigi(df, sembol, gosterge="Yok", bollinger=True):
    """TradingView tarzı çok panelli grafik: fiyat+MA(+Bollinger), hacim,
    ve isteğe bağlı alt panel (RSI veya MACD)."""
    alt_panel_var = gosterge in ("RSI", "MACD")
    if alt_panel_var:
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            row_heights=[0.60, 0.18, 0.22], vertical_spacing=0.03)
    else:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25],
                            vertical_spacing=0.03)

    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"],
                                 low=df["Low"], close=df["Close"], name=sembol,
                                 increasing_line_color="#26a69a",
                                 decreasing_line_color="#ef5350",
                                 increasing_fillcolor="#26a69a",
                                 decreasing_fillcolor="#ef5350"), row=1, col=1)
    for n, renk in [(20, "#f59e0b"), (50, "#3b82f6"), (200, "#8b5cf6")]:
        fig.add_trace(go.Scatter(x=df.index, y=am.sma(df["Close"], n),
                                 line=dict(width=1.1, color=renk),
                                 name=f"MA{n}"), row=1, col=1)
    if bollinger:
        try:
            ust, orta, alt = am.bollinger(df["Close"])
            fig.add_trace(go.Scatter(x=df.index, y=ust, line=dict(width=0.8, color="rgba(148,163,184,0.55)"),
                                     name="Boll. Üst", showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=alt, line=dict(width=0.8, color="rgba(148,163,184,0.55)"),
                                     name="Boll. Alt", fill="tonexty",
                                     fillcolor="rgba(148,163,184,0.08)", showlegend=False), row=1, col=1)
        except Exception:
            pass

    renkler = np.where(df["Close"] >= df["Open"], "rgba(38,166,154,0.7)", "rgba(239,83,80,0.7)")
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], marker_color=renkler,
                         name="Hacim"), row=2, col=1)

    if gosterge == "RSI":
        r = am.rsi(df["Close"])
        fig.add_trace(go.Scatter(x=df.index, y=r, line=dict(width=1.3, color="#a855f7"),
                                 name="RSI"), row=3, col=1)
        fig.add_hline(y=70, line=dict(width=1, dash="dot", color="#ef5350"), row=3, col=1)
        fig.add_hline(y=30, line=dict(width=1, dash="dot", color="#26a69a"), row=3, col=1)
        fig.update_yaxes(range=[0, 100], row=3, col=1)
    elif gosterge == "MACD":
        macd_hat, sinyal_hat, hist = am.macd(df["Close"])
        hist_renk = np.where(hist >= 0, "rgba(38,166,154,0.7)", "rgba(239,83,80,0.7)")
        fig.add_trace(go.Bar(x=df.index, y=hist, marker_color=hist_renk, name="MACD Hist"), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=macd_hat, line=dict(width=1.2, color="#3b82f6"),
                                 name="MACD"), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=sinyal_hat, line=dict(width=1.2, color="#f59e0b"),
                                 name="Sinyal"), row=3, col=1)

    fig.update_layout(height=560 if alt_panel_var else 520, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.06),
                      template="plotly_dark",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#cbd5e1"))
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.12)")
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.12)")
    return fig


def sinyal_tablosu(sinyaller):
    ikon = {"AL": "🟢 AL", "SAT": "🔴 SAT", "NÖTR": "🟡 NÖTR"}
    satirlar = [{"Gösterge": s["etiket"], "Sinyal": ikon.get(s["yon"], s["yon"]),
                 "Açıklama": s["aciklama"]} for s in sinyaller]
    if satirlar:
        _html_tablo(pd.DataFrame(satirlar))
    else:
        st.info("Bu vade için belirgin sinyal yok.")


# ─── Üst özet şerit (her zaman üstte, TradingView tarzı ticker) ─────────────
def _ust_serit():
    """Endeks ve dolar kuru durumunu tek bakışta gösteren kompakt şerit."""
    ogeler = []
    try:
        e = _endeks()
        if e is not None and len(e) > 1:
            son, onceki = float(e["Close"].iloc[-1]), float(e["Close"].iloc[-2])
            degisim = (son / onceki - 1) * 100 if onceki else 0.0
            renk = "#26a69a" if degisim >= 0 else "#ef5350"
            ok = "▲" if degisim >= 0 else "▼"
            ogeler.append(f"<span class='ust-oge'><span class='canli-nokta'></span>BIST100 "
                          f"<b>{son:,.0f}</b> "
                          f"<span style='color:{renk}'>{ok} %{abs(degisim):.2f}</span></span>")
    except Exception:
        pass
    try:
        usd = _usdtry()
        if usd is not None and len(usd) > 1:
            son, onceki = float(usd["Close"].iloc[-1]), float(usd["Close"].iloc[-2])
            degisim = (son / onceki - 1) * 100 if onceki else 0.0
            renk = "#ef5350" if degisim >= 0 else "#26a69a"  # dolar yükselişi TL için olumsuz
            ok = "▲" if degisim >= 0 else "▼"
            ogeler.append(f"<span class='ust-oge'>USD/TRY <b>{son:,.2f}</b> "
                          f"<span style='color:{renk}'>{ok} %{abs(degisim):.2f}</span></span>")
    except Exception:
        pass
    _c_tarama0, _, _, _c_zaman0, _c_taze0 = tob.oku()
    if _c_zaman0:
        durum = "⚡ taze" if _c_taze0 else "⏳ eski"
        ogeler.append(f"<span class='ust-oge'>📒 Tarama önbelleği: {_c_zaman0} ({durum})</span>")
    ogeler.append(f"<span class='ust-oge'>🕒 {dt.datetime.now().strftime('%d.%m.%Y %H:%M')}</span>")
    if ogeler:
        st.markdown(f"<div class='ust-serit'>{''.join(ogeler)}</div>", unsafe_allow_html=True)

_ust_serit()


# ─── Favoriler / İzleme Listesi ──────────────────────────────────────────────
# TASARIM KARARLARI (kullanıcı geri bildirimiyle):
#  1) st.sidebar KULLANILMIYOR — kenar çubuğu sayfadan BAĞIMSIZ kendi kaydırma
#     alanına sahiptir; sayfada tek bir kaydırma çubuğu olması isteniyor.
#  2) st.expander KULLANILMIYOR — "kapalı bir alt sekme olmasın, her şey açıkta
#     olsun" istendi. Bölüm daima görünür.
#  3) SABİT PİKSEL GENİŞLİKLİ öğe YOK — önceki sürümde puan şeridi 110px sabit
#     genişlikteydi; dar bir ızgara sütununda taşıp kırpılıyordu (kart yarım
#     görünüyordu). Artık tüm görsel öğeler yüzde tabanlıdır.
def _favoriler_paneli():
    st.markdown("### ⭐ Favoriler")
    liste = fav.getir()
    fc_ekle, fc_ac = st.columns([2, 3])
    with fc_ekle:
        yeni = hisse_secici("Favorilere hisse ekle:", anahtar="fav_ekle_secici")
        if yeni and st.button("➕ Favorilere ekle", key="fav_ekle_buton",
                              use_container_width=True):
            fav.ekle(yeni)
            st.rerun()
    with fc_ac:
        st.caption("Sık baktığınız hisseleri burada sabitleyin. Karta tıklayınca "
                   "analiz açılır; ✕ ile listeden çıkarırsınız.")

    if not liste:
        st.caption("Henüz favori eklenmedi.")
        st.divider()
        return

    endeks_f = _endeks()
    # Izgara: çok favori olsa bile dikeyde az yer kaplar, hepsi AYNI ANDA
    # görünür — hiçbir iç kaydırma kutusu yoktur.
    # Sayfa artık TAM GENİŞLİK kullandığı için 6 kart yan yana sığar; 4 kolonda
    # kartlar gereksiz yere devasa görünüyordu.
    _sutun_sayisi = 6
    for _bas in range(0, len(liste), _sutun_sayisi):
        _kolonlar = st.columns(_sutun_sayisi)
        for _k, s in enumerate(liste[_bas:_bas + _sutun_sayisi]):
            try:
                df_f = _gecmis(s)
                puan = am.hizli_puan(df_f, endeks_f)["Puan"] if len(df_f) else None
            except Exception:
                puan = None
            with _kolonlar[_k]:
                with st.container(border=True):
                    # Puan rozeti + yüzde genişlikli çubuk (sabit piksel YOK).
                    if puan is not None:
                        _renk = ozm.renk_kodu(puan)
                        st.markdown(
                            f"<div style='display:flex;align-items:center;"
                            f"justify-content:space-between;gap:6px;margin-bottom:4px'>"
                            f"<span style='font-weight:700;font-size:1.05rem'>{s}</span>"
                            f"<span style='font-weight:700;color:{_renk}'>{puan:.0f}</span>"
                            f"</div>"
                            f"{ozm.gradyan_cubugu_html(puan, '100%', 6)}"
                            f"<div style='font-size:.72rem;opacity:.75;margin-top:3px'>"
                            f"{ozm.durum_adi(puan)}</div>",
                            unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='font-weight:700;font-size:1.05rem'>{s}</div>"
                                    f"<div style='font-size:.72rem;opacity:.6'>veri yok</div>",
                                    unsafe_allow_html=True)
                    _b1, _b2 = st.columns([3, 1])
                    with _b1:
                        if st.button("Analiz", key=f"fav_git_{s}",
                                     use_container_width=True):
                            _analize_gonder(s)
                            st.session_state["_son_analiz_fav"] = s
                            st.rerun()
                    with _b2:
                        if st.button("✕", key=f"fav_sil_{s}",
                                     help="Favorilerden çıkar",
                                     use_container_width=True):
                            fav.cikar(s)
                            st.rerun()
    gosterilecek_fav = st.session_state.get("_son_analiz_fav")
    if gosterilecek_fav:
        st.caption(f"'{gosterilecek_fav}' analizi 'Hisse Araştır' sekmesinde hazır.")
    st.divider()


_favoriler_paneli()

# ─── Piyasa rejimi şeridi (her zaman üstte) ─────────────────────────────────
rejim = _rejim()
if rejim:
    # Kompakt şerit: gösterge KÜÇÜK boy, gerekçeler varsayılan KAPALI.
    # Gerekçe (canlı testte görüldü): büyük gösterge + açık gerekçe listesi
    # üstte ~400px yer kaplayınca SEKMELER ekranın en altına düşüyor ve
    # kullanıcı uygulamayı açtığında asıl içeriği hiç göremiyordu.
    rc1, rc2 = st.columns([1, 6])
    with rc1:
        st.markdown(radyal_gosterge_html(rejim["puan"], "REJİM", kucuk=True),
                   unsafe_allow_html=True)
    rc2.markdown(f"**Piyasa Rejimi: {rejim['emoji']} {rejim['durum']}** — BIST100 trendi, "
                 "dolar bazlı BIST, USDTRY ve fon akımlarından hesaplanır; hisse puanlarına "
                 "otomatik yansıtılır.")
    _rejim_ozet = ozm.rejim_ozeti(rejim)
    if _rejim_ozet:
        rc2.caption(_rejim_ozet)
    with st.expander("Rejim gerekçeleri", expanded=False):
        for s in rejim["sinyaller"]:
            st.write(f"- **{s['etiket']}** ({s['yon']}): {s['aciklama']}")
    st.divider()

# ─── Tablo tıklamalarını SEKMELER ÇİZİLMEDEN ÖNCE çöz ───────────────────────
# Hız için kritik: seçim burada işlenince tek çalıştırmada sonuç çıkar
# (eskiden st.rerun() ile iki tam çalıştırma gerekiyordu).
_bekleyen_secimleri_isle()

# ═════════════════════════════════════════════════════════════════════════════
# YERLEŞİM: ana içerik (sol) + AI sohbet asistanı (sağ, yapışkan)
# ─────────────────────────────────────────────────────────────────────────────
# NEDEN BÖYLE: Asistanın sağda SÜREKLİ durması istendi. st.sidebar bunun için
# uygun DEĞİL — sidebar mimari olarak AYRI bir kaydırma bölgesidir ve
# kullanıcının "sayfada tek kayar çubuk olsun" kuralını bozar. Bunun yerine
# ana sayfa akışı iki kolona bölünür; sağ kolon CSS'te `position: sticky`
# olduğu için ekranda kalır ama KENDİ kaydırma çubuğunu oluşturmaz.
#
# ÖNEMLİ TEKNİK AYRINTI: st.tabs() çağrısı `_ana_kolon` içinde yapılır, ama
# aşağıdaki `with sekme_xxx:` blokları dosya boyunca kolonun DIŞINDA kalabilir.
# Bu sorun değildir — Streamlit'te sekme nesneleri birer KAPSAYICIDIR; içeriğe
# nerede yazıldığından bağımsız olarak kendi (kolonun içindeki) yerlerine
# çizilirler. Böylece 1000+ satırlık sekme kodunu yeniden girintilemeye gerek
# kalmaz.
_SOHBET_ACIK = True          # sohbet panelini kapatmak için False yapın

if _SOHBET_ACIK:
    _ana_kolon, _sohbet_kolonu = st.columns([4, 1], gap="large")
else:
    _ana_kolon, _sohbet_kolonu = st.container(), None

with _ana_kolon:
    (sekme_arastir, sekme_yukselecek, sekme_tarama, sekme_takas, sekme_fon,
     sekme_oto, sekme_sanal, sekme_backtest, sekme_tavsiye_gecmisi, sekme_durum) = st.tabs(
        ["🔍 Hisse Araştır", "📈 Yükselebilecek Hisseler", "🚀 Öne Çıkan Hisseler",
         "🤝 Takas Analizi", "🏦 Fon & Kurumsal", "💼 Portföy & Tavsiye",
         "🧪 Sanal Portföy (Paper)", "📐 Backtest / Doğrulama",
         "📒 Tavsiye Geçmişi", "ℹ️ Sistem Durumu"])

# ─────────────────────────────────────────────────────────────────────────────
# 1) HİSSE ARAŞTIR
# ─────────────────────────────────────────────────────────────────────────────
with sekme_arastir:
    col1, col2 = st.columns([3, 1])
    with col1:
        sembol = hisse_secici("Hisse seçin — kod ya da şirket adı yazabilirsiniz:",
                              anahtar="arastir_sembol")
    with col2:
        st.write(""); st.write("")
        arastir = st.button("🔎 ARAŞTIR", type="primary", use_container_width=True)

    if arastir and sembol:
        with st.spinner(f"{sembol} araştırılıyor — fiyat, temel veriler, takas, haberler..."):
            df = _gecmis(sembol)
            if df.empty:
                st.error(f"'{sembol}' için veri bulunamadı. Kodu kontrol edin (örn. THYAO). "
                         "İnternet bağlantınızı da kontrol edin.")
            else:
                temel = _temel(sembol)
                yabanci = _yabanci(sembol)
                endeks = _endeks()
                etf = _etf(sembol)
                tefas = _tefas()
                # ETF kaynağı normalde BOŞ DataFrame döndürür; ancak kaynak
                # değişir de None dönerse len(None) tüm sekmeyi çökertirdi.
                analiz = am.tam_analiz(sembol, df, temel, yabanci, endeks,
                                       etf_df=etf if (etf is not None and len(etf)) else None,
                                       tefas_s=tefas, rejim=rejim)
                st.session_state["analiz"] = analiz
                st.session_state["df"] = df
                st.session_state["temel"] = temel
                st.session_state["yabanci"] = yabanci
                st.session_state["etf"] = etf

    if "analiz" in st.session_state:
        analiz = st.session_state["analiz"]
        df = st.session_state["df"]
        temel = st.session_state["temel"]
        yabanci = st.session_state["yabanci"]

        ad = temel.get("sirket_adi") or analiz["sembol"]
        _sh1, _sh2 = st.columns([5, 1])
        _sh1.subheader(f"{analiz['emoji']} {analiz['sembol']} — {ad}")
        with _sh2:
            st.write("")
            if analiz["sembol"] in fav.getir():
                if st.button("★ Favoride", key="fav_kaldir_arastir", use_container_width=True,
                            help="Favorilerden çıkar"):
                    fav.cikar(analiz["sembol"]); st.rerun()
            else:
                if st.button("☆ Favorile", key="fav_ekle_arastir", use_container_width=True,
                            help="Favorilere ekle"):
                    fav.ekle(analiz["sembol"]); st.rerun()

        # ÖNEMLİ: Nihai karar ESKİDEN sayfanın en altında hesaplanan geçmiş
        # örüntü sinyaliyle birleştiriliyordu; bu yüzden üstteki karar kutusu
        # onu göremiyor ve ekranda "KARAR: UZAK DUR" ile "Örüntü Sinyali:
        # GÜÇLÜ AL" yan yana, birbiriyle çelişerek duruyordu. Örüntü sinyali
        # kaldırıldı; ikinci görüş artık AKD (Aracı Kurum Dağılımı) sinyalinden
        # gelir — ÖNCE hesaplanır, tek bir NİHAİ KARAR üretilir.
        _akd_sinyal = _akd_sinyal_getir(analiz["sembol"])
        _nihai = ozm.nihai_karar(analiz, _akd_sinyal)

        _hisse_ozet = ozm.hisse_ozeti(analiz, temel, _akd_sinyal)
        if _hisse_ozet:
            with st.container(border=True):
                st.markdown("#### 📝 Sade Özet — bu ne anlama geliyor?")
                st.markdown(_hisse_ozet)

        # Nihai kararın GEREKÇESİ — özellikle çelişki varsa kullanıcı neden
        # "bekle" dendiğini burada okur.
        with st.container(border=True):
            st.markdown(f"### {_nihai['emoji']} Nihai Karar: "
                        f"<span style='color:{_nihai['renk']}'>{_nihai['karar']}</span>",
                        unsafe_allow_html=True)
            st.markdown(_nihai["aciklama"])
            if _nihai["akd_var_mi"]:
                st.caption(f"Bileşenler → Teknik tablo: **{_nihai['teknik_karar']}** "
                          f"(puan {_nihai['teknik_puan']:.0f}) · "
                          f"AKD: **{_nihai['akd_karari']}**")

        # ─────────────────────────────────────────────────────────────
        # 🚨 SATIŞ / RİSK ALARMLARI — "bu hisseden çıkmalı mıyım?"
        # NEDEN AYRI BİR BÖLÜM: Puan "almaya değer mi?" sorusunu yanıtlar.
        # Ama ELDE TUTULAN bir hissede asıl soru "çıkmalı mıyım?"dır ve bu,
        # puanın yavaşça düşmesini beklemekten çok daha HIZLI bir uyarı
        # gerektirir (bir hisse 70'ten 55'e inene kadar %20 kaybettirebilir).
        # Buradaki alarmlar klasik risk yönetimi kurallarını doğrudan kontrol
        # eder: trend kırılımı, death cross, ATR zarar-kes, yeni dip, yüksek
        # hacimli satış, sessiz dağıtım ve (girerseniz) kendi alış fiyatınıza
        # göre zarar seviyesi.
        _risk = analiz.get("risk")
        if _risk:
            _rs_metin, _rs_renk = am.SATIS_SEVIYE_METNI.get(
                _risk["seviye"], ("—", "#94a3b8"))
            with st.container(border=True):
                st.markdown(f"### 🚨 Satış / Risk Uyarıları: "
                            f"<span style='color:{_rs_renk}'>{_rs_metin}</span>",
                            unsafe_allow_html=True)
                _ra1, _ra2 = st.columns([3, 2])
                with _ra2:
                    _alis = st.number_input(
                        "Alış fiyatınız (isteğe bağlı)", min_value=0.0, value=0.0,
                        step=0.01, key="risk_alis_fiyati",
                        help="Girerseniz zarar yüzdeniz hesaplanır ve zarar-kes "
                             "uyarısı üretilir. 0 bırakırsanız dikkate alınmaz.")
                    if _risk.get("stop_seviyesi"):
                        st.metric("Önerilen zarar-kes (ATR)",
                                  f"{_risk['stop_seviyesi']:.2f} ₺",
                                  help="Son 20 günün zirvesinden 2.5×ATR aşağısı. "
                                       "Fiyat bunun altına inerse trend bozulmuş "
                                       "sayılır.")
                # Kullanıcı alış fiyatı girdiyse alarmları ONA GÖRE yeniden üret.
                if _alis and _alis > 0:
                    _risk = am.risk_alarmlari(df, alis_fiyati=_alis)
                    _rs_metin, _rs_renk = am.SATIS_SEVIYE_METNI.get(
                        _risk["seviye"], ("—", "#94a3b8"))
                with _ra1:
                    st.markdown(f"**Risk puanı: {_risk['risk_puani']}/100** "
                                f"· Ana trend: **{analiz.get('trend_yonu','—')}**")
                    if _risk["alarmlar"]:
                        for _a in _risk["alarmlar"]:
                            st.markdown(f"- **{_a['baslik']}** — {_a['mesaj']}")
                    else:
                        st.success("Bu hissede şu an belirgin bir satış/çıkış "
                                   "sinyali görünmüyor.")
                    if _risk.get("zarar_yuzde") is not None:
                        st.caption(f"Alış fiyatınıza göre durum: "
                                   f"**%{_risk['zarar_yuzde']:+.1f}**")
                st.caption("⚠️ Bu uyarılar mekanik kurallardır, kesin sonuç değildir. "
                          "Amaç, kaybı büyümeden fark etmenizi sağlamaktır — nihai "
                          "kararı siz verirsiniz.")

        # ─────────────────────────────────────────────────────────────
        # 🤝 AKD ANALİZİ (Telegram/BOPT) — kullanıcı isteği üzerine Hisse
        # Araştır'da İSTİSNASIZ görünmesi gereken bölüm. Önce önbelleği
        # okur; yoksa/bayatsa canlı çekmeyi TEKLİF eder (otomatik arka
        # planda toplu taramaya çıkarılmaz — bkz. telegram_akd.py'deki
        # hız sınırı notu; ama tek bir hisseyi araştırırken elle/butonla
        # çekmek güvenlidir).
        with st.container(border=True):
            st.markdown("### 🤝 AKD Analizi (Telegram/BOPT)")
            _akd_veri = takd.oku(analiz["sembol"])

            # ÖNEMLİ: Eskiden bu kutu SADECE hem `tablo` hem `sinyal` varsa
            # içerik gösteriyordu. Tesseract-OCR kurulu olmayan bir bilgisayarda
            # görsel başarıyla indirilse bile `tablo` üretilemediği için kutu
            # "henüz çekilmemiş" diyor, kullanıcı butona bassa da ekranda hiçbir
            # şey değişmiyordu. Artık ELDE NE VARSA o gösterilir: sinyal varsa
            # sinyal, yoksa en azından indirilen GÖRSEL ve ham metin.
            if _akd_veri:
                _tazelik = "🟢 taze" if _akd_veri.get("taze_mi") else "🟡 bayat"
                st.caption(f"Kaynak: Telegram @b0pt_bot · Çekilme zamanı: "
                          f"{_akd_veri.get('zaman', '?')[:16].replace('T',' ')} · {_tazelik}")

                _s = _akd_veri.get("sinyal")
                if _s:
                    st.markdown(f"**{_s['karar']}** (puan {_s['puan']:+d})")
                    for _sebep in _s["sebepler"]:
                        st.caption(f"• {_sebep}")

                _tablo = _akd_veri.get("tablo")
                if _tablo:
                    _ac, _sc = st.columns(2)
                    with _ac:
                        st.markdown("**🟢 Net Alıcılar**")
                        _alici_satirlar = [
                            {"Kurum": k["kurum"] if k.get("guven", 0) >= 0.6 else "❓ okunamadı",
                             "Pay %": k["oran"], "Net Lot ~": k.get("net_lot_tahmini")}
                            for k in _tablo["net_alicilar"]["kurumlar"]]
                        _html_tablo(pd.DataFrame(_alici_satirlar))
                    with _sc:
                        st.markdown("**🔴 Net Satıcılar**")
                        _satici_satirlar = [
                            {"Kurum": k["kurum"] if k.get("guven", 0) >= 0.6 else "❓ okunamadı",
                             "Pay %": k["oran"], "Net Lot ~": k.get("net_lot_tahmini")}
                            for k in _tablo["net_saticilar"]["kurumlar"]]
                        _html_tablo(pd.DataFrame(_satici_satirlar))
                    if _tablo.get("guven") != "yuksek":
                        st.caption(f"⚠️ Okuma güveni: {_tablo.get('guven')} — {_tablo.get('guven_notu','')}")
                elif _akd_veri.get("tablo_hatasi"):
                    st.warning(
                        f"Görsel indirildi ama sayısal tabloya çevrilemedi: "
                        f"{_akd_veri['tablo_hatasi']}\n\n"
                        "Kurum isimlerini ve oranları otomatik okuyabilmek için "
                        "**Tesseract-OCR** programının kurulu olması gerekir: "
                        "https://github.com/UB-Mannheim/tesseract/wiki "
                        "(kurduktan sonra uygulamayı yeniden başlatın). "
                        "Aşağıdaki görselden bilgileri yine de okuyabilirsiniz.")

                if _akd_veri.get("gorsel_dosya") and os.path.exists(_akd_veri["gorsel_dosya"]):
                    with st.expander("📊 AKD tablo görseli", expanded=not _tablo):
                        st.image(_akd_veri["gorsel_dosya"], use_container_width=True)
                elif not _tablo:
                    st.caption(f"Ham cevap: {_akd_veri.get('ham', '—')}")

                st.caption("Bu veri üçüncü taraf bir Telegram botundan (@b0pt_bot) gelir ve "
                          "görselden OCR ile okunur; doğruluğu teyit edilmemiştir, bilgi "
                          "amaçlıdır, tek başına yatırım kararı vermeyin.")
                _btn_etiket, _btn_key = "🔄 AKD verisini yeniden çek", "akd_yenile_arastir"
            else:
                st.caption("Bu hisse için henüz AKD verisi çekilmemiş.")
                _btn_etiket, _btn_key = "📡 AKD verisini şimdi çek (Telegram)", "akd_getir_arastir"

            if st.button(_btn_etiket, key=_btn_key, use_container_width=True):
                with st.spinner(f"{analiz['sembol']} için Telegram'dan AKD verisi çekiliyor "
                                f"(ilk seferde biraz sürebilir)..."):
                    try:
                        takd.akd_getir(analiz["sembol"])
                    except ImportError as e:
                        st.error(f"Gerekli kütüphane kurulu değil: {e}")
                    except FileNotFoundError as e:
                        st.error(f"Telegram ayarları eksik: {e}")
                    except Exception as e:
                        st.error(f"AKD verisi çekilemedi: {e}")
                    else:
                        st.rerun()

        gc1, gc2, gc3 = st.columns([2, 2, 4])
        _gosterge = gc1.selectbox("Alt panel", ["Yok", "RSI", "MACD"], key="fg_gosterge")
        _bant = gc2.checkbox("Bollinger bandı", value=True, key="fg_bant")

        cg, ck = st.columns([1, 2])
        with cg:
            # ÖNEMLİ (kullanıcı geri bildirimi): Gösterge SADECE teknik puanı
            # gösterir; nihai karar ise teknik puan + AKD sinyalinin
            # BİRLEŞİMİDİR. Bu ikisi çeliştiğinde ekranda "62.4/100" ile
            # "ÇELİŞKİLİ — BEKLE" yan yana durup kafa karıştırıyordu. Artık
            # göstergenin ne olduğu açıkça yazılıyor ve çelişki varsa nedeni
            # tam burada, göstergenin altında açıklanıyor.
            st.caption("Aşağıdaki gösterge **yalnızca TEKNİK puanı** gösterir "
                      "— nihai karar bununla AKD sinyalinin birleşimidir (varsa).")
            st.markdown(radyal_gosterge_html(analiz["genel_puan"], "GENEL PUAN"),
                       unsafe_allow_html=True)
            with st.expander("📉 Klasik gösterge (ibre)", expanded=False):
                st.plotly_chart(puan_grafigi(analiz["genel_puan"]), use_container_width=True)
            st.markdown(
                f"<div class='puan-kutu' style='border-left:6px solid {_nihai['renk']};"
                f"--kkrenk:{_nihai['renk']}77'>"
                f"<b>{_nihai['emoji']} NİHAİ KARAR: {_nihai['karar']}</b><br>"
                f"<small>İki motorun BİRLEŞTİRİLMİŞ sonucu</small></div>",
                unsafe_allow_html=True)
            if _nihai.get("celiskili_mi"):
                st.info(f"ℹ️ Teknik puan **{analiz['genel_puan']:.1f}/100** "
                       f"ama AKD sinyali **{_nihai['akd_karari']}** — "
                       f"ikisi birbiriyle çeliştiği için sistem temkinli davranıp "
                       f"**BEKLE** diyor. Yüksek puan tek başına 'al' demek değildir.")
            st.markdown(f"<div style='text-align:center;margin-top:8px'>"
                        f"{rozet(analiz['genel_puan'])}</div>", unsafe_allow_html=True)
        with ck:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Son Fiyat", f"{analiz['son_fiyat']:.2f} ₺")
            m2.metric("1 Ay", f"%{analiz['getiri_1a']}" if analiz['getiri_1a'] is not None else "—")
            m3.metric("3 Ay", f"%{analiz['getiri_3a']}" if analiz['getiri_3a'] is not None else "—")
            m4.metric("1 Yıl", f"%{analiz['getiri_1y']}" if analiz['getiri_1y'] is not None else "—")

            vade_kartlari(analiz["puanlar"])
            if analiz.get("rejim_duzeltmesi"):
                st.caption(f"⚖️ Piyasa rejimi düzeltmesi genel puana dahil: "
                           f"{analiz['rejim_duzeltmesi']:+.1f} puan")

            m5, m6, m7, m8 = st.columns(4)
            fk = temel.get("fk"); pddd = temel.get("pddd")
            yab = temel.get("yabanci_orani")
            pd_ = temel.get("piyasa_degeri")
            m5.metric("F/K", f"{float(fk):.1f}" if fk else "—")
            m6.metric("PD/DD", f"{float(pddd):.2f}" if pddd else "—")
            m7.metric("Yabancı Oranı", f"%{float(yab):.1f}" if yab is not None else "—")
            m8.metric("Piyasa Değeri", f"{float(pd_)/1e9:.1f} mlr ₺" if pd_ else "—")

            if analiz["stop_oneri"] and analiz["hedef_oneri"]:
                st.info(f"📌 Teknik seviye önerisi → Stop-loss: **{analiz['stop_oneri']} ₺** · "
                        f"Hedef bölge: **{analiz['hedef_oneri']} ₺** (ATR tabanlı)")

        st.plotly_chart(fiyat_grafigi(df.tail(380), analiz["sembol"],
                                      gosterge=_gosterge, bollinger=_bant),
                        use_container_width=True)

        st.subheader("📋 Vade Vade Sinyaller")
        basliklar = {"Kısa Vade": "⚡ Kısa Vade (1-4 hafta)",
                     "Orta Vade": "📅 Orta Vade (1-6 ay)",
                     "Uzun Vade": "🏛️ Uzun Vade (6 ay+)",
                     "Takas / Para Akışı": "🤝 Takas / Para Akışı",
                     "Fon / Kurumsal": "🏦 Fon / Kurumsal"}
        anahtarlar = [k for k in basliklar if k in analiz["sinyaller"]]
        vade_tablari = st.tabs([basliklar[k] for k in anahtarlar])
        for tab, k in zip(vade_tablari, anahtarlar):
            with tab:
                sinyal_tablosu(analiz["sinyaller"][k])
                if k == "Takas / Para Akışı" and yabanci is not None and len(yabanci) > 10:
                    figy = go.Figure(go.Scatter(x=yabanci.index, y=yabanci.values,
                                                fill="tozeroy", line=dict(color="#0ea5e9")))
                    figy.update_layout(title="Yabancı Takas Oranı (%) — son 1 yıl",
                                       height=300, margin=dict(l=10, r=10, t=40, b=10))
                    figy.update_yaxes(range=[max(0, yabanci.min() - 2), yabanci.max() + 2])
                    st.plotly_chart(figy, use_container_width=True)
                if k == "Fon / Kurumsal":
                    etf = st.session_state.get("etf")
                    if etf is not None and len(etf) > 0:
                        st.markdown("**Bu hisseyi taşıyan uluslararası ETF'ler:**")
                        _html_tablo(etf)

        # Haberler ve analist verileri
        ch, ca = st.columns(2)
        with ch:
            st.subheader("📰 Son KAP Bildirimleri")
            haberler = vk.kap_haberleri(analiz["sembol"])
            if haberler:
                for h in haberler[:8]:
                    if isinstance(h, dict):
                        baslik = h.get("title") or h.get("baslik") or h.get("subject") or str(h)
                        tarih = h.get("date") or h.get("tarih") or h.get("publishDate") or ""
                        st.markdown(f"- **{tarih}** — {baslik}")
                    else:
                        st.markdown(f"- {h}")
            else:
                st.caption("KAP bildirimi alınamadı.")
        with ca:
            st.subheader("🎯 Analist Beklentileri")
            av = vk.analist_verileri(analiz["sembol"])
            if av.get("hedef_fiyat") is not None:
                st.write(av["hedef_fiyat"])
            if av.get("tavsiye_ozeti") is not None:
                st.write(av["tavsiye_ozeti"])
            if not av:
                st.caption("Analist verisi alınamadı.")



# ─────────────────────────────────────────────────────────────────────────────
# 1B) YÜKSELEBİLECEK HİSSELER (Günlük / Haftalık TEKNİK vade taraması)
# ─────────────────────────────────────────────────────────────────────────────
# NOT (AKD geçişi): Bu sekme eskiden oruntu_motoru.vade_taramasi() (geçmiş
# örüntü/istatistiksel benzerlik) kullanıyordu; kullanıcı geri bildirimiyle
# yanıltıcı bulunduğu için kaldırıldı. Artık analiz_motoru.vade_taramasi()
# çağrılır — saf TEKNİK (fiyat/hacim/trend) puanlamaya dayanır.
with sekme_yukselecek:
    st.markdown("Tarama evrenindeki hisseleri **teknik puanlama motorundan** geçirip, "
                "Kısa/Orta/Uzun vadede en güçlü görünenleri sıralar. Amaç: doğru hisseyi "
                "erken bulmak.")
    kapsam_y = st.selectbox("Tarama kapsamı", ["TUM", "XU100", "XU030"],
                            format_func=lambda x: {"TUM": "Tüm BIST (~560 hisse)",
                                                   "XU100": "BIST 100",
                                                   "XU030": "BIST 30 (hızlı)"}[x],
                            key="kapsam_yukselecek")
    tara_y = st.button("📈 KISA / ORTA / UZUN VADE ADAYLARINI BUL (canlı tara)", type="primary",
                       use_container_width=True)

    # HIZ: canlı tıklama beklemeden, ARKA_PLAN_TARAMA.bat tarafından önceden
    # hesaplanmış önbellek varsa otomatik yükle — sekme açılır açılmaz sonuç
    # görünür. Önbellek yoksa/bayatsa kullanıcı yine de yukarıdaki butonla
    # anlık tarama yapabilir.
    if "yukselecek_vade" not in st.session_state and not tara_y:
        _c_tarama, _c_vade, _c_eski, _c_zaman, _c_taze = tob.oku()
        if _c_vade is not None and len(_c_vade):
            st.session_state["yukselecek_vade"] = _c_vade
            st.session_state["yukselecek_zamani"] = _c_zaman
            st.session_state["yukselecek_kaynak"] = "onbellek_taze" if _c_taze else "onbellek_bayat"

    if tara_y:
        st.session_state["yukselecek_kaynak"] = "canli"
        semboller_y, _kaynak_sem = _semboller_ayrintili(kapsam_y)
        st.caption(f"Kapsam: **{len(semboller_y)} hisse** · sembol kaynağı: {_kaynak_sem}")
        with st.spinner(f"{len(semboller_y)} hisse için veri toplu olarak indiriliyor..."):
            bar_y = st.progress(0.0, text="Fiyat verileri indiriliyor (toplu)...")
            # Uzun vade (120 iş günü ileri) için daha fazla geçmiş gerekir;
            # 2 yıl yerine 3 yıl indirilir, aksi halde uzun vade sütunu
            # çoğu hissede "Veri yok" çıkardı.
            bar_y.progress(0.15, text="Fiyat verileri hazırlanıyor (önbellekten/indiriliyor)...")
            veriler_y = _toplu_fiyat(tuple(semboller_y), 3.0)
            bar_y.progress(0.45, text="Kısa/Orta/Uzun vade teknik puanları hesaplanıyor...")
            vade_tablo = am.vade_taramasi(
                veriler_y, ust_sinir=40, endeks_df=_endeks(),
                ilerleme=lambda x: bar_y.progress(min(0.45 + x * 0.5, 0.95),
                text=f"Teknik puanlar hesaplanıyor... %{x*100:.0f}"))
            vade_tablo = tob.trend_ekle(vade_tablo, veriler_y)
            # Tıklama önizlemesi bu veriyi kullansın — yeniden indirme olmasın.
            _toplu_veri_kaydet(veriler_y)
            bar_y.progress(1.0, text="Tamamlandı ✅")
        st.session_state["yukselecek_vade"] = vade_tablo
        st.session_state["yukselecek_zamani"] = dt.datetime.now().strftime("%d.%m.%Y %H:%M")

        # Tavsiyeleri KALICI olarak kaydet — her VADE ayrı kaynak olarak.
        try:
            for vade, kaynak_k in (("Kısa", tkd.KAYNAK_VADE_KISA),
                                   ("Orta", tkd.KAYNAK_VADE_ORTA),
                                   ("Uzun", tkd.KAYNAK_VADE_UZUN)):
                if vade not in vade_tablo.columns:
                    continue
                # Yalnızca o vadede OLUMLU karar verilenler tavsiye sayılır.
                secim = vade_tablo[vade_tablo[vade].astype(str).str.contains("🟢")]
                if len(secim):
                    tkd.kaydet(kaynak_k, [
                        {"sembol": r["Hisse"], "sinyal": r.get(vade),
                         "puan": r.get(f"{vade} Puan"), "fiyat": r.get("Fiyat"),
                         "ek": {"genel_puan": r.get("Genel Puan"),
                                "1_ay_yuzde": r.get("1 Ay %"),
                                "3_ay_yuzde": r.get("3 Ay %")}}
                        for _, r in secim.iterrows()])
        except Exception as e:
            st.caption(f"(Tavsiye kaydı yapılamadı: {e})")

    if "yukselecek_vade" in st.session_state:
        _kaynak_y = st.session_state.get("yukselecek_kaynak")
        if _kaynak_y == "onbellek_taze":
            st.success(f"⚡ Önbellekten anında yüklendi — arka plan taraması: "
                       f"{st.session_state['yukselecek_zamani']}")
        elif _kaynak_y == "onbellek_bayat":
            st.warning(f"⏳ Önbellek {st.session_state['yukselecek_zamani']} tarihli — biraz eski. "
                      "Güncel görmek için yukarıdan canlı tarayın veya ARKA_PLAN_TARAMA.bat'ı çalıştırın.")
        else:
            st.success(f"Son tarama: {st.session_state['yukselecek_zamani']}")

        st.info("ℹ️ **Sinyal üç vadeye bölünür.** Bir hisse kısa vadede riskli, "
               "uzun vadede olumlu olabilir — bu bir çelişki değil, farklı vadelerdir.\n\n"
               "- **Kısa** ≈ 2 hafta · **Orta** ≈ 3 ay · **Uzun** ≈ 6 ay\n"
               "- Her vadedeki karar, o vadeye ait TEKNİK puandan (hizli_puan'ın "
               "Kısa/Orta/Uzun bileşenlerinden) türetilir; geçmiş örüntü/istatistiksel "
               "benzerlik kullanılmaz.")

        vade_tablo = st.session_state["yukselecek_vade"]
        f1, f2 = st.columns([2, 3])
        with f1:
            hedef_vade = st.selectbox(
                "Hangi vadeye göre sıralansın / filtrelensin?",
                ["Hepsi", "Kısa", "Orta", "Uzun"], key="yuk_hedef_vade")
        with f2:
            st.write("")
            sadece_al = st.checkbox(
                "🟢 Sadece seçilen vadede 'AL' olanları göster",
                value=False, key="yuk_sadece_uyumlu",
                disabled=(hedef_vade == "Hepsi"),
                help="Seçilen vadede iki motorun da olumlu olduğu hisseleri bırakır.")

        gosterilen = vade_tablo
        if hedef_vade != "Hepsi" and hedef_vade in gosterilen.columns:
            if sadece_al:
                gosterilen = gosterilen[gosterilen[hedef_vade].astype(str).str.contains("🟢")]
            gosterilen = gosterilen.sort_values(
                f"{hedef_vade} Puan", ascending=False, na_position="last")

        _yuk_ozet = ozm.vade_taramasi_ozeti(vade_tablo)
        if _yuk_ozet:
            with st.container(border=True):
                st.markdown("#### 📝 Sade Özet — bu ne anlama geliyor?")
                st.markdown(_yuk_ozet)

        y_sol, y_sag = st.columns([3, 2], gap="medium")
        with y_sol:
            st.caption("💡 Bir satıra tıklayın — analiz **sağda** anında açılır. "
                      "Sıradaki hisseye tıklayarak listeyi hızlıca tarayabilirsiniz.")
            if len(gosterilen):
                _tablo_ciz(gosterilen, "yuk_vade", "Hisse",
                           _vade_kolon_ayari(), True, None)
                with st.expander("🔬 Vade ayrıntıları (ham teknik puanlar)", expanded=True):
                    _ayrinti_kolonlari = ["Hisse", "Genel Puan", "Kısa Puan", "Orta Puan",
                                          "Uzun Puan", "Takas Puan", "1 Ay %", "3 Ay %",
                                          "Hacim(M₺)"]
                    _ayrinti_df = gosterilen[[k for k in _ayrinti_kolonlari if k in gosterilen.columns]]
                    _html_tablo(_ayrinti_df)
            else:
                st.caption("Bu filtreye uyan hisse bulunamadı.")
        with y_sag:
            _analiz_paneli(st.session_state.get("_son_analiz_yuk_vade"), "yuk_vade")
        st.caption("⚠️ Bu liste bugünkü teknik göstergelere dayanır, gelecek getiri "
                   "vaadi/yatırım tavsiyesi değildir. Ayrıntılı gerekçe için hisseyi "
                   "'Hisse Araştır' sekmesinde araştırın.")


# ─────────────────────────────────────────────────────────────────────────────
# 2) ÖNE ÇIKAN HİSSELER (TARAMA)
# ─────────────────────────────────────────────────────────────────────────────
with sekme_tarama:
    st.markdown("Tüm borsayı tarar, **kısa ve orta vadede potansiyeli en yüksek görünen** "
                "hisseleri puana göre sıralar.")
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        kapsam = st.selectbox("Tarama kapsamı", ["TUM", "XU100", "XU030"],
                              format_func=lambda x: {"TUM": "Tüm BIST (~560 hisse)",
                                                     "XU100": "BIST 100",
                                                     "XU030": "BIST 30"}[x])
    with c2:
        min_hacim = st.number_input("Min. günlük ortalama hacim (milyon ₺)",
                                    value=20.0, min_value=0.0, step=10.0)
    with c3:
        st.write(""); st.write("")
        tara = st.button("🚀 TARAMAYI BAŞLAT (canlı tara)", type="primary", use_container_width=True)

    temel_dahil_et = st.checkbox(
        "🔬 Temel oranları (F/K, PD/DD) ve gerçek yabancı takas oranını dahil et",
        value=False,
        help="Varsayılan taramada 'Uzun' sadece MA200/2 yıllık trende, 'Takas' sadece "
             "hacim tabanlı akış göstergelerine dayanır (ek ağ isteği olmadığı için hızlıdır). "
             "Bu kutuyu işaretlerseniz her hisse için F/K, PD/DD ve gerçek yabancı takas "
             "oranı geçmişi de PARALEL olarak çekilir — 'Uzun' ve 'Takas' puanları daha "
             "ayrıştırıcı/doğru olur ama tarama BELİRGİN ŞEKİLDE YAVAŞLAR (ek ağ istekleri "
             "nedeniyle).")

    # HIZ: canlı tıklama beklemeden, arka planda önceden hesaplanmış önbellek
    # varsa otomatik yükle. Önbellek "temel_dahil_et=Hayır" ile üretildiği için,
    # o seçeneği açan kullanıcı yine canlı taramaya yönlendirilir.
    if "tarama" not in st.session_state and not tara:
        _c_tarama, _, _, _c_zaman, _c_taze = tob.oku()
        if _c_tarama is not None:
            st.session_state["tarama"] = _c_tarama
            st.session_state["tarama_zamani"] = _c_zaman
            st.session_state["tarama_kaynak"] = "onbellek_taze" if _c_taze else "onbellek_bayat"

    if tara:
        st.session_state["tarama_kaynak"] = "canli"
        semboller = _semboller(kapsam)
        st.write(f"**{len(semboller)} hisse** taranacak. Veriler indiriliyor...")
        ust_pay = 0.55 if temel_dahil_et else 0.7
        bar = st.progress(0.0, text="Fiyat verileri indiriliyor (toplu)...")
        bar.progress(0.2, text="Fiyat verileri hazırlanıyor (önbellekten/indiriliyor)...")
        veriler = _toplu_fiyat(tuple(semboller), 1.5)
        # Tıklama önizlemesi bu veriyi kullansın — yeniden indirme olmasın.
        _toplu_veri_kaydet(veriler)
        bar.progress(ust_pay, text="Fiyat verileri hazır.")

        temel_haritasi, yabanci_haritasi = {}, {}
        if temel_dahil_et:
            adlar_indirilen = list(veriler.keys())
            temel_haritasi = vk.toplu_temel_veriler(
                adlar_indirilen,
                ilerleme=lambda x: bar.progress(ust_pay + x * 0.20,
                text=f"Temel oranlar çekiliyor (paralel)... %{x*100:.0f}"))
            yabanci_haritasi = vk.toplu_yabanci_orani(
                adlar_indirilen, yil=1.0,
                ilerleme=lambda x: bar.progress(ust_pay + 0.20 + x * 0.10,
                text=f"Yabancı takas oranı çekiliyor (paralel)... %{x*100:.0f}"))

        endeks = _endeks()
        sonuclar = []
        adlar = list(veriler.keys())
        for i, s in enumerate(adlar):
            try:
                df = veriler[s]
                ort_hacim_tl = float((df["Close"] * df["Volume"]).tail(20).mean()) / 1e6
                if ort_hacim_tl < min_hacim:
                    continue
                # rejim=_rejim(): riskli piyasada puanlar otomatik kısılır —
                # 'Hisse Araştır' sekmesiyle AYNI puanı vermesi için şart.
                satir = am.hizli_puan(df, endeks,
                                      temel=temel_haritasi.get(s),
                                      yabanci_s=yabanci_haritasi.get(s),
                                      rejim=_rejim())
                # Yetersiz/bozuk veri gelen hisseler (Puan=None) tabloya
                # alınmaz — boş satırlarla listeyi kirletmemek için.
                if satir["Puan"] is None:
                    continue
                satir["Hisse"] = s
                sonuclar.append(satir)
            except Exception:
                continue
            if i % 25 == 0:
                bar.progress(min(0.9 + 0.1 * (i + 1) / max(len(adlar), 1), 1.0),
                             text=f"Analiz ediliyor... {s} ({i+1}/{len(adlar)})")
        bar.progress(1.0, text="Tamamlandı ✅")

        if not sonuclar:
            st.error("Sonuç üretilemedi. İnternet bağlantısını kontrol edin ve tekrar deneyin.")
        else:
            tablo = pd.DataFrame(sonuclar)
            kolonlar = ["Hisse", "Puan", "Karar", "Kısa", "Orta", "Uzun", "Takas",
                        "Fiyat", "1 Ay %", "3 Ay %", "Hacim(M₺)"]
            tablo = tablo[kolonlar].sort_values("Puan", ascending=False).reset_index(drop=True)
            tablo.index += 1
            tablo = tob.trend_ekle(tablo, veriler)
            st.session_state["tarama"] = tablo
            st.session_state["tarama_zamani"] = dt.datetime.now().strftime("%d.%m.%Y %H:%M")

            # Tavsiyeleri KALICI kaydet. Sadece ilk 20 (kullanıcıya "En Yüksek
            # Puanlı 20 Hisse" olarak gösterilen liste) kaydedilir — tüm ~600
            # hisseyi kaydetmek "tavsiye" değil, ham tarama çıktısı olurdu ve
            # performans istatistiğini anlamsızlaştırırdı.
            try:
                tkd.kaydet(tkd.KAYNAK_TARAMA, [
                    {"sembol": r["Hisse"], "sinyal": r.get("Karar"),
                     "puan": r.get("Puan"), "fiyat": r.get("Fiyat"),
                     "ek": {"kisa": r.get("Kısa"), "orta": r.get("Orta"),
                            "uzun": r.get("Uzun"), "takas": r.get("Takas")}}
                    for _, r in tablo.head(20).iterrows()])
            except Exception as e:
                st.caption(f"(Tavsiye kaydı yapılamadı: {e})")

    if "tarama" in st.session_state:
        tablo = st.session_state["tarama"]
        _kaynak_t = st.session_state.get("tarama_kaynak")
        if _kaynak_t == "onbellek_taze":
            st.success(f"⚡ Önbellekten anında yüklendi — arka plan taraması: "
                      f"{st.session_state['tarama_zamani']} — {len(tablo)} hisse.")
        elif _kaynak_t == "onbellek_bayat":
            st.warning(f"⏳ Önbellek {st.session_state['tarama_zamani']} tarihli — biraz eski. "
                      "Güncel görmek için yukarıdan canlı tarayın veya ARKA_PLAN_TARAMA.bat'ı çalıştırın.")
        else:
            st.success(f"Tarama: {st.session_state['tarama_zamani']} — {len(tablo)} hisse listelendi. "
                       "Detay için hisseyi 'Hisse Araştır' sekmesinde araştırın.")
        _tar_ozet = ozm.tarama_ozeti(tablo)
        if _tar_ozet:
            with st.container(border=True):
                st.markdown("#### 📝 Sade Özet — bu ne anlama geliyor?")
                st.markdown(_tar_ozet)
        st.markdown("### 🏆 En Yüksek Puanlı 20 Hisse")
        # NOT: .style.background_gradient() matplotlib'e ihtiyaç duyar VE hatayı
        # oluşturma anında değil, st.dataframe() onu render ederken (tembel/lazy
        # hesaplama) fırlatır. Bu yüzden hatayı yakalamak için st.dataframe()
        # çağrısının kendisini de try/except içine almak gerekir — sadece
        # .style.background_gradient() satırını sarmak yeterli değildir.
        # Renkli ilerleme çubukları st.column_config ile çizilir — matplotlib
        # gerektirmez, bu yüzden eski background_gradient yaklaşımındaki
        # "matplotlib yok" çökmesi de ortadan kalkar.
        tiklanabilir_tablo(tablo.head(20), "tarama_ust20",
                          column_config=_tarama_kolon_ayari(), hide_index=False,
                          yan_panel=True)
        with st.expander("📜 Tüm sonuçları gör"):
            tiklanabilir_tablo(tablo, "tarama_tumu",
                              column_config=_tarama_kolon_ayari(), hide_index=False,
                              yan_panel=True)
        st.download_button("⬇️ Sonuçları Excel (CSV) olarak indir",
                           tablo.to_csv(index=True).encode("utf-8-sig"),
                           file_name=f"tarama_{dt.date.today()}.csv")


# ─────────────────────────────────────────────────────────────────────────────
# 3) TAKAS ANALİZİ
# ─────────────────────────────────────────────────────────────────────────────
with sekme_takas:
    st.markdown("**Takas analizi** — hisseye kimin para soktuğunu izler: MKK kaynaklı "
                "*yabancı takas oranı* + hacim tabanlı *para akışı / toplama-dağıtım* göstergeleri.")
    ts = hisse_secici("Hisse seçin — kod ya da şirket adı:", anahtar="takas_sembol")
    if st.button("🤝 TAKAS ANALİZİ YAP", type="primary") and ts:
        with st.spinner("Takas verileri çekiliyor..."):
            df = _gecmis(ts)
            if df.empty:
                st.error(f"'{ts}' için veri bulunamadı.")
            else:
                temel = _temel(ts)
                yabanci = _yabanci(ts)
                puan, sinyaller = am.takas_analizi(df, temel, yabanci)

                c1, c2 = st.columns([1, 2])
                with c1:
                    st.markdown(radyal_gosterge_html(puan, "TAKAS PUANI"), unsafe_allow_html=True)
                    _tk_renk = ozm.renk_kodu(puan)
                    st.markdown(f"<div class='puan-kutu' style='--kkrenk:{_tk_renk}77'>"
                                f"<b>TAKAS PUANI: {puan:.0f}/100</b><br>"
                                "<small>50 üzeri = para girişi ağır basıyor</small></div>",
                                unsafe_allow_html=True)
                with c2:
                    sinyal_tablosu(sinyaller)

                g1, g2 = st.columns(2)
                with g1:
                    if yabanci is not None and len(yabanci) > 10:
                        figy = go.Figure(go.Scatter(x=yabanci.index, y=yabanci.values,
                                                    fill="tozeroy", line=dict(color="#0ea5e9")))
                        figy.update_layout(title="Yabancı Takas Oranı (%)", height=320,
                                           margin=dict(l=10, r=10, t=40, b=10))
                        st.plotly_chart(figy, use_container_width=True)
                    else:
                        yab = temel.get("yabanci_orani")
                        if yab is not None:
                            st.metric("Güncel Yabancı Takas Oranı", f"%{float(yab):.1f}")
                        st.caption("Yabancı oranı geçmiş serisi şu an alınamadı; "
                                   "anlık değer ve hacim tabanlı analiz gösteriliyor.")
                with g2:
                    son = df.tail(252)
                    figc = make_subplots(rows=2, cols=1, shared_xaxes=True,
                                         subplot_titles=("Para Akışı (CMF)", "Toplama/Dağıtım (A/D)"))
                    cmf_s = am.cmf(son)
                    figc.add_trace(go.Bar(x=son.index, y=cmf_s,
                                          marker_color=np.where(cmf_s >= 0, "#16a34a", "#dc2626")),
                                   row=1, col=1)
                    figc.add_trace(go.Scatter(x=son.index, y=am.ad_cizgisi(son),
                                              line=dict(color="#8b5cf6")), row=2, col=1)
                    figc.update_layout(height=320, showlegend=False,
                                       margin=dict(l=10, r=10, t=40, b=10))
                    st.plotly_chart(figc, use_container_width=True)

    with st.expander("ℹ️ Takas analizi nedir, bu veriler nereden geliyor?"):
        st.markdown("""
- **Yabancı takas oranı**: Hissenin MKK'daki saklama bakiyesinin ne kadarının yabancı
  yatırımcıda olduğunu gösterir. Yabancı girişi genellikle orta vadeli güçlü bir sinyaldir.
  Kaynak: İş Yatırım (ücretsiz, halka açık veri).
- **CMF / A-D / OBV / MFI**: Fiyat ve hacimden hesaplanan para akışı göstergeleri;
  "sessiz toplama" (fiyat yatayken birilerinin mal toplaması) ve "dağıtım" desenlerini yakalar.
- Aracı kurum bazlı (üye dağılımı) takas verisi Türkiye'de yalnızca ücretli servislerde
  (Matriks, Fintables Pro, Finnet) sunulur; bu yazılım %100 ücretsiz kaynak kullanır.
        """)


# ─────────────────────────────────────────────────────────────────────────────
# 4) FON & KURUMSAL
# ─────────────────────────────────────────────────────────────────────────────
with sekme_fon:
    st.markdown("**Kurumsal para nerede?** Yerli fonların borsaya genel yaklaşımı (TEFAS) ve "
                "hisse bazında uluslararası ETF sahipliği (BlackRock, Vanguard...).")

    st.subheader("🇹🇷 Yerli Fonlar — Hisse Ağırlığı Trendi (TEFAS)")
    tefas = _tefas()
    if tefas is not None and len(tefas) >= 3:
        d = tefas.iloc[-1] - tefas.iloc[0]
        yorum = ("📈 Yerli fonlar hisse ağırlığını ARTIRIYOR — kurumsal para borsaya giriyor."
                 if d > 1 else
                 "📉 Yerli fonlar hisse ağırlığını AZALTIYOR — kurumsal para borsadan çekiliyor."
                 if d < -1 else "➡️ Yerli fonların hisse ağırlığı yatay.")
        st.markdown(f"**{yorum}** (6 aylık değişim: {d:+.1f} puan)")
        figt = go.Figure(go.Scatter(x=tefas.index, y=tefas.values, mode="lines+markers",
                                    line=dict(color="#16a34a", width=3)))
        figt.update_layout(title="Yatırım fonlarının ortalama hisse senedi ağırlığı (%)",
                           height=320, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(figt, use_container_width=True)
    else:
        st.warning("TEFAS verisi şu an alınamadı. 'Sistem Durumu' sekmesinden test edebilirsiniz.")

    st.divider()
    st.subheader("🌍 Hisse Bazında ETF Sahipliği")
    fs = hisse_secici("Hisse seçin — kod ya da şirket adı:", anahtar="fon_sembol")
    if st.button("🏦 KURUMSAL SAHİPLİĞİ GÖSTER", type="primary") and fs:
        with st.spinner("ETF ve ortaklık verileri çekiliyor..."):
            etf = _etf(fs)
            if etf is not None and len(etf) > 0:
                try:
                    toplam = pd.to_numeric(etf["market_cap_usd"], errors="coerce").sum()
                    c1, c2 = st.columns(2)
                    c1.metric("ETF Sayısı", len(etf))
                    c2.metric("Toplam ETF Pozisyonu", f"{toplam/1e6:,.0f} M$")
                except Exception:
                    pass
                _html_tablo(etf)
                st.caption("Çok sayıda büyük ETF'in pozisyon taşıması, hissenin uluslararası "
                           "endekslerde yer aldığını ve pasif yabancı alımına açık olduğunu gösterir.")
            else:
                st.warning(f"{fs} için ETF sahiplik verisi bulunamadı — hisse uluslararası "
                           "endekslerde olmayabilir.")
            ortaklar = vk.ana_ortaklar(fs)
            if ortaklar is not None:
                st.markdown("**Ana ortaklar:**")
                st.write(ortaklar)

    with st.expander("ℹ️ Aracı kurum (BofA vb.) takas verisi neden yok?"):
        st.markdown("""
Aracı kurum bazlı takas/alım-satım dağılımı **1 Ocak 2025'ten itibaren Borsa İstanbul
tarafından ücretli veri yayın lisansına bağlandı**. Bu yüzden Matriks, Fintables Pro, Finnet
gibi servisler bu veriyi yalnızca abonelik/müşterilik karşılığı sunuyor; ücretsiz ve yasal bir
API'si kalmadı. Bu yazılım onun yerine **ücretsiz** kaynaklardan şunları izler:
yabancı takas oranı (MKK), uluslararası ETF pozisyonları, TEFAS fon akımları ve
hacim tabanlı toplama/dağıtım analizi. Matriks aboneliğiniz olursa söyleyin, entegre edilebilir.
        """)


# ─────────────────────────────────────────────────────────────────────────────
# 5) PORTFÖY & TAVSİYE
# ─────────────────────────────────────────────────────────────────────────────
with sekme_oto:
    import tavsiye_paneli
    tavsiye_paneli.render(st, pd, np, go, dt, vk, am, pt, la, _gecmis, _endeks, ozm, tob,
                          tiklanabilir_tablo, hisse_linki, _mini_analiz_karti)


# ─────────────────────────────────────────────────────────────────────────────
# 6) SANAL PORTFÖY (PAPER TRADING)
# ─────────────────────────────────────────────────────────────────────────────
with sekme_sanal:
    import sanal_portfoy_paneli
    sanal_portfoy_paneli.render(st, pd, np, go, dt, vk, am, sv, _gecmis, _endeks,
                                _semboller, ozm, _toplu_fiyat,
                                tiklanabilir_tablo=tiklanabilir_tablo, hisse_linki=hisse_linki)


# ─────────────────────────────────────────────────────────────────────────────
# 7) BACKTEST / DOĞRULAMA
# ─────────────────────────────────────────────────────────────────────────────
with sekme_backtest:
    st.markdown("Motorların **geçmiş veride gerçekten işe yarayıp yaramadığını** ölçer. "
                "Her tarihsel gün için, SADECE o güne kadar bilinebilecek veriyle hesap "
                "yapılır (gelecek bilgisi sızdırılmaz) ve üretilen sinyalin gerçekten "
                "ileriki getiriyi öngörüp öngörmediği ölçülür.")

    bc1, bc2, bc3 = st.columns([1.3, 1, 1])
    with bc1:
        bt_modu = st.radio("Kapsam", ["Tek hisse (hızlı)", "Çoklu hisse (yavaş)"],
                           horizontal=False)
    with bc2:
        bt_yil = st.number_input("Kaç yıllık geçmiş?", value=5.0, min_value=2.0,
                                 max_value=10.0, step=1.0)
    with bc3:
        bt_adim = st.number_input("Adım (iş günü)", value=5, min_value=1, max_value=20, step=1,
                                  help="Her kaç iş gününde bir yeniden puanlama yapılsın. "
                                       "Küçük değer = daha çok örnek ama daha yavaş.")

    st.info("⚠️ Bu doğrulama yalnızca **varsayılan teknik puanlamayı** test eder — "
            "F/K, PD/DD ve gerçek yabancı takas oranının tarihsel (geçmişteki) değerlerine "
            "erişimimiz olmadığı için, '🔬 Temel oranları dahil et' ile zenginleştirilmiş "
            "puanlama bu testin kapsamı dışındadır.")

    # NOT (AKD geçişi): Bu sekmede eskiden 'Örüntü motoru' testi de vardı
    # (bkz. git geçmişi); geçmiş örüntü/istatistiksel benzerlik sinyali
    # kullanıcı geri bildirimiyle yanıltıcı bulunduğu için uygulamadan tamamen
    # kaldırıldı — bu doğrulama sekmesinden de çıkarıldı. AKD sinyali için
    # ayrı bir backtest motoru henüz yok; bu sekme yalnızca teknik puanlama
    # motorunu ('Öne Çıkan Hisseler' / 'Yükselebilecek Hisseler') test eder.

    # Pencere uzunluğu puanı GERÇEKTEN değiştirir (uzun_vade'deki 2 yıllık getiri
    # bonusu len(veri) > 400 koşuluna bağlıdır). Bu yüzden hangi canlı kullanımın
    # taklit edileceği kullanıcıya açıkça sorulur.
    bt_taklit = st.radio(
        "Hangi kullanımı taklit etsin?",
        ["Sanal portföy motoru / Hisse Araştır (2 yıllık veri)",
         "Öne Çıkan Hisseler taraması (1,5 yıllık veri)"],
        horizontal=True,
        help="Uygulamanın farklı sekmeleri farklı uzunlukta geçmiş veri kullanır ve bu, "
             "aynı hisseye aynı gün FARKLI puan verilmesine yol açar (uzun vade puanındaki "
             "2 yıllık getiri bonusu ancak ~400 günden uzun veride devreye girer). "
             "Backtest'in gerçekçi olması için burada, sonucunu merak ettiğiniz sekmeyi seçin.")
    bt_pencere = (bt.PENCERE_VARSAYILAN if bt_taklit.startswith("Sanal") else bt.PENCERE_TARAMA)
    bt_ufuk = 10

    if bt_modu.startswith("Tek"):
        bt_sembol = hisse_secici("Hisse seçin — kod ya da şirket adı:",
                                 anahtar="bt_sembol")
        calistir_bt = st.button("📐 BACKTEST ÇALIŞTIR", type="primary", key="bt_tek_buton")
        if calistir_bt and bt_sembol:
            with st.spinner(f"{bt_sembol} için {bt_yil:.0f} yıllık geçmiş test ediliyor..."):
                try:
                    df_bt = _gecmis(bt_sembol, bt_yil)
                    endeks_bt = _endeks()
                    sonuc_df = bt.backtest_tek_hisse(bt_sembol, df_bt, endeks_bt,
                                                     adim=int(bt_adim), pencere=int(bt_pencere))
                except Exception as e:
                    sonuc_df = pd.DataFrame()
                    st.error(f"Hata: {e}")
            if sonuc_df.empty:
                st.warning("Yeterli geçmiş veri yok veya hisse bulunamadı — daha uzun bir "
                          "periyot deneyin ya da kod yazımını kontrol edin.")
            else:
                ozet = bt.backtest_ozet(sonuc_df, adim=int(bt_adim))
                yarilama = bt.backtest_yarilama(sonuc_df, adim=int(bt_adim))
                _bt_ozet = ozm.backtest_ozeti(ozet)
                if _bt_ozet:
                    with st.container(border=True):
                        st.markdown("#### 📝 Sade Özet — bu ne anlama geliyor?")
                        st.markdown(_bt_ozet)
                with st.expander("🔬 Teknik ayrıntı (istatistikler)", expanded=True):
                    _metin_blogu(bt.metin_raporu(ozet, yarilama))
                if not ozet["ozet_tablo"].empty:
                    _html_tablo(ozet["ozet_tablo"])
                with st.expander("📜 Ham puanlama noktaları"):
                    _html_tablo(sonuc_df)
    else:
        bt_kapsam = st.selectbox("Kapsam", ["TUM", "XU100", "XU030"],
                                 format_func=lambda x: {"TUM": "Tüm BIST (~560 hisse, en yavaş)",
                                                        "XU100": "BIST 100",
                                                        "XU030": "BIST 30 (hızlı)"}[x],
                                 key="bt_coklu_kapsam")
        st.caption("Seçilen kapsamdaki hisselerin tamamı için çalışır — Tüm BIST'te binlerce "
                  "puanlama noktası üretir, uygulama içinde çalıştırırsanız birkaç dakika "
                  "sürebilir. Uygulamayı açık tutmadan, arka planda çalıştırmak isterseniz "
                  "**BACKTEST_CALISTIR.bat** dosyasını kullanın — sonuç "
                  "'backtest_sonuc.txt' dosyasına yazılır.")
        calistir_bt_coklu = st.button("📐 BACKTESTİ ÇALIŞTIR", type="primary",
                                      key="bt_coklu_buton")
        if calistir_bt_coklu:
            semboller_bt = _semboller(bt_kapsam)
            bar_bt = st.progress(0.0, text="Fiyat verileri indiriliyor (toplu)...")
            bar_bt.progress(0.25, text="Fiyat verileri hazırlanıyor...")
            veriler_bt = _toplu_fiyat(tuple(semboller_bt), float(bt_yil))
            endeks_bt = _endeks()

            def _ilerleme_bt(i, n, s):
                bar_bt.progress(min(0.5 + 0.5 * (i + 1) / max(n, 1), 1.0),
                                text=f"Puanlanıyor... {s} ({i+1}/{n})")

            sonuc_df = bt.backtest_evren(veriler_bt, endeks_bt, adim=int(bt_adim),
                                         pencere=int(bt_pencere), ilerleme=_ilerleme_bt)
            bar_bt.progress(1.0, text="Tamamlandı ✅")

            if sonuc_df.empty:
                st.warning("Yeterli veri üretilemedi. İnternet bağlantısını kontrol edin.")
            else:
                ozet = bt.backtest_ozet(sonuc_df, adim=int(bt_adim))
                yarilama = bt.backtest_yarilama(sonuc_df, adim=int(bt_adim))
                _bt_ozet = ozm.backtest_ozeti(ozet)
                if _bt_ozet:
                    with st.container(border=True):
                        st.markdown("#### 📝 Sade Özet — bu ne anlama geliyor?")
                        st.markdown(_bt_ozet)
                with st.expander("🔬 Teknik ayrıntı (istatistikler)", expanded=True):
                    _metin_blogu(bt.metin_raporu(ozet, yarilama))
                if not ozet["ozet_tablo"].empty:
                    _html_tablo(ozet["ozet_tablo"])
                st.download_button("⬇️ Ham veriyi Excel (CSV) olarak indir",
                                   sonuc_df.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"backtest_{dt.date.today()}.csv")


# ─────────────────────────────────────────────────────────────────────────────
# 8) TAVSİYE GEÇMİŞİ & PERFORMANS (ileriye dönük gerçek kanıt)
# ─────────────────────────────────────────────────────────────────────────────
with sekme_tavsiye_gecmisi:
    st.markdown("Motorun **gerçek zamanda verdiği** tavsiyeler burada kalıcı olarak "
                "kaydedilir ve sonradan gerçek fiyatlarla puanlanır. Backtest geçmişi "
                "yeniden oynatır; bu sekme ise motorun sonucu bilinmezken ne dediğini "
                "kaydeder — bu yüzden en dürüst kanıt budur.")

    # ── ÖĞRENME MOTORU: "neden yanıldım?" analizi ───────────────────────────
    with st.expander("🧠 Öğrenme Motoru — hata analizi ve ders çıkarma", expanded=False):
        st.caption("Olgunlaşmış kararları sonuçlarıyla eşleştirir, **karar anında** "
                   "hangi risk koşullarının var olduğunu inceler ve tekrar eden "
                   "hataları bulur. **Hiçbir kuralı otomatik değiştirmez** — "
                   "yalnızca aday öneri üretir.")
        try:
            import ogrenme_motoru as om
            _sorgu_ist = om.sorgu_istatistikleri()
            if _sorgu_ist.get("toplam"):
                oc1, oc2, oc3 = st.columns(3)
                oc1.metric("Asistana sorulan soru", _sorgu_ist["toplam"])
                oc2.metric("Araç seçilemeyen", f"%{_sorgu_ist['arac_secilemeyen_oran']}")
                oc3.metric("En çok kullanılan araç",
                           (_sorgu_ist["en_cok_kullanilan_araclar"] or [("—", 0)])[0][0])

            if st.button("🧠 HATA ANALİZİNİ ÇALIŞTIR", key="ogrenme_calistir"):
                with st.spinner("Kararlar sonuçlarıyla eşleştiriliyor..."):
                    _sonuc = om.ogrenme_dongusu(
                        fiyat_getirici=_gecmis, endeks_df=_endeks())
                st.session_state["_ogrenme_sonuc"] = _sonuc

            _og = st.session_state.get("_ogrenme_sonuc")
            if _og:
                _metin_blogu(_og["rapor"])
                _ht = _og.get("hata_tablosu")
                if _ht is not None and len(_ht):
                    with st.expander("📜 Sınıflandırılmış kararlar (ham tablo)",
                                     expanded=False):
                        _html_tablo(_ht.head(100))
        except Exception as _og_hata:
            st.warning(f"Öğrenme motoru çalıştırılamadı: {_og_hata}")

    gecmis_tv = tkd.gecmisi_getir()
    if gecmis_tv.empty:
        st.info("📭 Henüz kaydedilmiş tavsiye yok.\n\n"
                "**'🚀 Öne Çıkan Hisseler'** veya **'📈 Yükselebilecek Hisseler'** "
                "taramasını çalıştırdığınızda sonuçlar otomatik olarak buraya kaydedilmeye "
                "başlayacak. GUNLUK_TARAMA.bat da her çalıştığında kayıt ekler.\n\n"
                "Anlamlı bir performans ölçümü için en az birkaç haftalık birikim gerekir.")
    else:
        tg1, tg2, tg3 = st.columns(3)
        tg1.metric("Toplam Kayıt", f"{len(gecmis_tv)}")
        tg2.metric("Farklı Hisse", f"{gecmis_tv['sembol'].nunique()}")
        ilk_t, son_t = gecmis_tv["tarih"].min(), gecmis_tv["tarih"].max()
        tg3.metric("Kayıt Aralığı",
                   f"{ilk_t:%d.%m.%Y} – {son_t:%d.%m.%Y}" if pd.notna(ilk_t) else "—")

        st.caption(f"Kaynak dağılımı: " + " · ".join(
            f"{k}: {v}" for k, v in gecmis_tv["kaynak"].value_counts().items()))

        if st.button("📊 PERFORMANSI HESAPLA", type="primary", key="tv_hesapla"):
            bar_tv = st.progress(0.0, text="Fiyat verileri indiriliyor...")

            def _ilerleme_tv(i, n, s):
                bar_tv.progress(min((i + 1) / max(n, 1), 1.0),
                                text=f"Fiyatlar alınıyor... {s} ({i+1}/{n})")

            try:
                perf_tv = tkd.performans_hesapla(
                    lambda s: _gecmis(s, 2.0), endeks_df=_endeks(), ilerleme=_ilerleme_tv)
            except Exception as e:
                perf_tv = pd.DataFrame()
                st.error(f"Performans hesaplanamadı: {e}")
            bar_tv.progress(1.0, text="Tamamlandı ✅")
            st.session_state["tavsiye_perf"] = perf_tv

        if "tavsiye_perf" in st.session_state:
            perf_tv = st.session_state["tavsiye_perf"]
            if perf_tv is None or perf_tv.empty:
                st.warning("Performans tablosu üretilemedi.")
            else:
                ozet_tv = tkd.performans_ozeti(perf_tv)
                _tv_sade = ozm.tavsiye_gecmisi_ozeti(ozet_tv)
                if _tv_sade:
                    with st.container(border=True):
                        st.markdown("#### 📝 Sade Özet — bu ne anlama geliyor?")
                        st.markdown(_tv_sade)
                with st.expander("🔬 Teknik ayrıntı (istatistikler)", expanded=True):
                    _metin_blogu(tkd.metin_raporu(ozet_tv))

                if not ozet_tv["kaynak_tablo"].empty:
                    st.markdown("#### Kaynak Bazlı Performans")
                    _html_tablo(ozet_tv["kaynak_tablo"])
                if not ozet_tv["sinyal_tablo"].empty:
                    st.markdown("#### Sinyal Bazlı Performans")
                    _html_tablo(ozet_tv["sinyal_tablo"])

                # Olgunlaşmış / bekleyen ayrımı GÖRÜNÜR olmalı — dürüstlük gereği.
                olgun_kolon = "olgun_10g"
                if olgun_kolon in perf_tv.columns:
                    olgunlar = perf_tv[perf_tv[olgun_kolon].astype(bool)]
                    bekleyenler = perf_tv[~perf_tv[olgun_kolon].astype(bool)]
                    st.markdown(f"#### Sonucu Belli Olan Tavsiyeler ({len(olgunlar)})")
                    if len(olgunlar):
                        tiklanabilir_tablo(olgunlar.sort_values("tarih", ascending=False),
                                          "tv_olgun", sembol_kolonu="sembol")
                    else:
                        st.caption("Henüz 10 iş günü geçmiş bir tavsiye yok.")
                    if len(bekleyenler):
                        with st.expander(f"⏳ Henüz olgunlaşmamış tavsiyeler ({len(bekleyenler)}) "
                                        "— bunlar ortalamaya DAHİL DEĞİLDİR", expanded=True):
                            tiklanabilir_tablo(bekleyenler.sort_values("tarih", ascending=False),
                                              "tv_bekleyen", sembol_kolonu="sembol",
                                              ipucu=False)

                st.download_button("⬇️ Performans tablosunu CSV indir",
                                   perf_tv.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"tavsiye_performans_{dt.date.today()}.csv")

        with st.expander("📜 Ham tavsiye kayıtları"):
            tiklanabilir_tablo(gecmis_tv.sort_values("tarih", ascending=False),
                              "tv_ham", sembol_kolonu="sembol", ipucu=False)

        with st.expander("🗑️ Tavsiye geçmişini sıfırla"):
            st.caption("TÜM tavsiye kayıtlarını siler, geri alınamaz. Performans ölçümü "
                      "sıfırdan başlar — bunu yalnızca test verisini temizlemek için kullanın.")
            onay_tv = st.checkbox("Silmeyi onaylıyorum", key="tv_sil_onay")
            if st.button("🗑️ Tavsiye Geçmişini Sil", disabled=not onay_tv, key="tv_sil"):
                tkd.temizle()
                st.session_state.pop("tavsiye_perf", None)
                st.success("Tavsiye geçmişi silindi.")
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# 9) SİSTEM DURUMU
# ─────────────────────────────────────────────────────────────────────────────
with sekme_durum:
    st.markdown("### 🔤 Şirket Adları (hisse arama için)")
    _mevcut_adlar = _hisse_adlari()
    st.caption(f"Şu an **{len(_mevcut_adlar)}** hissenin şirket adı biliniyor. Bu adlar "
              "sayesinde hisse kutularında kod yerine şirket adı yazarak arama "
              "yapabilirsiniz (örn. 'ereğli' → EREGL). Adı bilinmeyen hisseler sadece "
              "koduyla görünür — uydurma ad yazılmaz.")
    if st.button("⬇️ Şirket Adlarını İndir / Güncelle (tüm BIST)"):
        with st.spinner("Şirket adları gerçek kaynaktan indiriliyor (paralel, biraz sürebilir)..."):
            try:
                _sem = _semboller("TUM")
                bar_ad = st.progress(0.0, text="Şirket adları indiriliyor...")
                yeni = ha.adlari_indir(
                    _sem, vk.toplu_temel_veriler,
                    ilerleme=lambda x: bar_ad.progress(min(x, 1.0),
                    text=f"Şirket adları indiriliyor... %{x*100:.0f}"))
                bar_ad.progress(1.0, text="Tamamlandı ✅")
                _hisse_adlari.clear()
                st.success(f"{len(yeni)} hissenin adı kaydedildi. Hisse arama kutuları "
                          "artık şirket adıyla da arama yapabilir.")
            except Exception as e:
                st.error(f"Şirket adları indirilemedi: {e}")

    st.divider()
    st.markdown("Veri kaynaklarının çalışıp çalışmadığını test eder.")
    if st.button("🔧 KAYNAKLARI TEST ET"):
        with st.spinner("Kaynaklar test ediliyor..."):
            rapor = vk.kaynak_testi()
        for k, v in rapor.items():
            ikon = "✅" if ("ÇALIŞIYOR" in str(v) or "DİNAMİK" in str(v)) else ("⚠️" if "ALINAMADI" in str(v) or "YEDEK" in str(v) else "❌")
            st.write(f"{ikon} **{k}** → {v}")
    st.divider()
    st.markdown("""
**Kullanılan ücretsiz kaynaklar** — API anahtarı gerekmez:

| Veri | Kaynak |
|---|---|
| Fiyat/hacim geçmişi | Yahoo Finance → borsapy (TradingView) → İş Yatırım |
| F/K, PD/DD, piyasa değeri, halka açıklık | borsapy / Yahoo Finance |
| Yabancı takas oranı | borsapy (Fintables) + İş Yatırım |
| KAP bildirimleri, analist hedefleri | borsapy |
| Endeks bileşenleri (BIST30/100/TÜM) | borsapy |

⚠️ **Yasal uyarı:** Bu yazılım eğitim/bilgilendirme amaçlıdır. Üretilen puan ve sinyaller
yatırım tavsiyesi değildir. Yatırım kararlarınız tamamen kendi sorumluluğunuzdadır.
""")


# ═════════════════════════════════════════════════════════════════════════════
# SAĞ KOLON — AI SOHBET ASİSTANI
# ═════════════════════════════════════════════════════════════════════════════
# Panel EN SONDA çizilir; çünkü asistan, kullanıcıyı bir sekmeye yönlendirdiğinde
# analizi önceden hesaplayıp session_state'e yazar ve ardından st.rerun() çağırır.
# Sekmeler çizildikten sonra çalışması, o hesabın bir sonraki çalıştırmada
# kesinlikle hazır olmasını sağlar.
if _SOHBET_ACIK and _sohbet_kolonu is not None:
    # Asistanın kullanacağı veri erişimcileri. Hepsi app.py'nin ÖNBELLEKLİ
    # fonksiyonlarıdır — asistan yeni ağ isteği yapmaz, ekranda zaten olan
    # veriyi kullanır.
    _sohbet_kaynaklari = {
        "gecmis": _panel_df,          # önce taramadaki toplu veri, yoksa tekil
        "temel": _temel,
        "yabanci": _yabanci,
        "endeks": _endeks,
        "rejim": _rejim,
        "akd": _akd_sinyal_getir,
    }
    # Sohbet paneli, bir hisseyi "Hisse Araştır" sekmesine hazırlarken bu
    # fonksiyonu kullanır (app.py'ye doğrudan bağımlı olmasın diye
    # session_state üzerinden geçirilir).
    st.session_state["_analize_gonder_fn"] = _analize_gonder

    with _sohbet_kolonu:
        try:
            import sohbet_paneli as sp
            sp.ciz(_sohbet_kaynaklari)
        except Exception as _sohbet_hata:
            # Asistan çökerse UYGULAMANIN GERİ KALANI ETKİLENMEMELİDİR.
            st.warning(f"Sohbet asistanı yüklenemedi: {_sohbet_hata}")
