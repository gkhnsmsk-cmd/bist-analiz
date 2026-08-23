# -*- coding: utf-8 -*-
"""
tavsiye_paneli.py — "Portföy & Tavsiye" sekmesi.
════════════════════════════════════════════════════════════════
SADECE BİLGİLENDİRME/TAVSİYE — hiçbir alım-satım emri gönderilmez veya
simüle edilmez. Üç işlevi vardır:
  1) Portföy Analiz Matrisi: elle girilen pozisyonların (hisse/lot/maliyet)
     Mynet canlı fiyatlarıyla anlık kâr/zarar durumu.
  2) Rebalans & Takas Sinyal Motoru: portfoy_takip.py'deki kurallara göre
     AL / SAT (KAYIP KES) / TAKAS aksiyon listesi + sektörel yoğunlaşma uyarısı.
  3) Opsiyonel LLM Yönetici Özeti: aktif bir LLM ajanı, motorun ürettiği
     önerileri 2-3 cümlelik kurumsal bir özete dönüştürür.
Karar ve işlem HER ZAMAN kullanıcıya aittir.
"""
import datetime as dt


def _canli_fiyat_getir(vk, _gecmis, sembol: str):
    """Mynet üzerinden canlı fiyat; başarısız olursa son kapanışa düşer."""
    try:
        fiyat = vk.canli_fiyat_cek(sembol)
        if fiyat == fiyat and fiyat > 0:  # NaN kontrolü
            return float(fiyat)
    except Exception:
        pass
    try:
        df = _gecmis(sembol, 0.2)
        if df is not None and not df.empty:
            return float(df["Close"].iloc[-1])
    except Exception:
        pass
    return None


def render(st, pd, np, go, dt_mod, vk, am, pt, la, _gecmis, _endeks, ozm=None, tob=None,
           tiklanabilir_tablo=None, hisse_linki=None, mini_analiz_karti=None):
    st.info("ℹ️ Bu sekme sadece bilgilendirme/tavsiye üretir. Hiçbir alım-satım emri "
           "otomatik gönderilmez veya simüle edilmez. Alım/satım kararını ve işlemini "
           "her zaman siz, kendi aracı kurum hesabınızdan gerçekleştirirsiniz. Fiyat "
           "verileri Mynet Finans'tan (canlı) ve mevcut analiz motorundan gelir.")

    ajan_durumu = la.aktif_ajan_durumu()
    aktifler = [ad for ad, acik in ajan_durumu.items() if acik]
    with st.expander(f"🧠 LLM Yönetici Özeti Ajanları — {len(aktifler)}/{len(ajan_durumu)} aktif"):
        for ad, acik in ajan_durumu.items():
            st.write(("🟢 " if acik else "⚪ ") + ad +
                     (" (aktif)" if acik else " (anahtar girilmedi — atlanıyor)"))
        st.caption("Aktif etmek için proje klasöründe bir '.env' dosyası oluşturup ilgili "
                   "API anahtarını girin (.env.example). Groq ücretsiz kotalıdır "
                   "(console.groq.com), diğerleri ücretlidir. Hiçbiri girilmezse yönetici "
                   "özeti bölümü gösterilmez; motor önerileri yine de üretilir.")

    # ── Portföy girişi (dinamik tablo) ──────────────────────────────────────
    st.divider()
    st.markdown("### 💼 Portföyüm")
    st.caption("Hisse kodu, lot miktarı ve maliyet fiyatınızı girin. Satır eklemek/silmek "
              "için tablonun altındaki + / çöp kutusu simgelerini kullanın.")

    mevcut = pt.pozisyonlari_getir()
    baslangic_df = pd.DataFrame([
        {"Hisse Kodu": p["sembol"], "Lot Miktarı": p["adet"], "Maliyet Fiyatı": p["maliyet"]}
        for p in mevcut
    ]) if mevcut else pd.DataFrame({
        "Hisse Kodu": pd.Series(dtype="str"),
        "Lot Miktarı": pd.Series(dtype="float"),
        "Maliyet Fiyatı": pd.Series(dtype="float"),
    })

    duzenlenen_df = st.data_editor(
        baslangic_df, num_rows="dynamic", use_container_width=True, key="portfoy_editor",
        column_config={
            "Hisse Kodu": st.column_config.TextColumn(required=True, help="Örn. THYAO"),
            "Lot Miktarı": st.column_config.NumberColumn(min_value=0.0, step=1.0, required=True),
            "Maliyet Fiyatı": st.column_config.NumberColumn(min_value=0.0, step=0.01, required=True,
                                                            help="Ortalama alış maliyetiniz (₺)"),
        })

    if st.button("💾 Portföyü Kaydet", use_container_width=True):
        kayitlar = duzenlenen_df.to_dict("records")
        pt.portfoyu_degistir(kayitlar)
        st.success("Portföy 'portfoy.json' dosyasına kaydedildi.")
        st.rerun()

    # ═════════════════════════════════════════════════════════════════════════
    # GÜNLÜK KARAR PANELİ — "bugün satmalı mıyım?"
    # ═════════════════════════════════════════════════════════════════════════
    # NEDEN EN ÜSTTE VE BUTONSUZ: Kullanıcının günlük iş akışı bu — hisseyi
    # elle alıyor, her gün "sat sinyali var mı" diye bakıyor. Bu yüzden panel
    # yavaş "PORTFÖYÜ ANALİZ ET" düğmesinin ARKASINDA değil, sayfa açılır
    # açılmaz görünür. Yalnızca önbellekli fiyat geçmişini kullanır (_gecmis),
    # ek ağ isteği yapmaz.
    # ═════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown("### 📌 Bugün Ne Yapmalı? — Pozisyon Çıkış Kararı")

    _poz_var = pt.pozisyonlari_getir()
    if not _poz_var:
        st.caption("Portföyünüz boş. Yukarıdan pozisyon ekleyip 'Portföyü Kaydet'e basın.")
    else:
        try:
            _karar_satirlari = pt.gunluk_cikis_tablosu(_gecmis, atr_fn=am.atr)
        except Exception as _e:
            _karar_satirlari = []
            st.warning(f"Çıkış kararı hesaplanamadı: {_e}")

        if _karar_satirlari:
            _satlar = [r for r in _karar_satirlari if r["Karar"] == "SAT"]
            _tutlar = [r for r in _karar_satirlari if r["Karar"] == "TUT"]
            _bilinmez = [r for r in _karar_satirlari if r["Karar"] == "—"]

            _o1, _o2, _o3 = st.columns(3)
            _o1.metric("🔴 SAT", len(_satlar))
            _o2.metric("🟢 TUT", len(_tutlar))
            _o3.metric("⚪ Karar yok", len(_bilinmez))

            if _satlar:
                st.error("**Çıkış sinyali veren pozisyonlar:** "
                         + ", ".join(f"**{r['Hisse']}**" for r in _satlar))
            elif not _bilinmez:
                st.success("Hiçbir pozisyon çıkış sinyali vermiyor — hepsi stop seviyesinin üzerinde.")

            _kdf = pd.DataFrame(_karar_satirlari)
            st.dataframe(
                _kdf, use_container_width=True, hide_index=True,
                height=38 + 35 * len(_kdf) + 40,
                column_config={
                    "Karar": st.column_config.TextColumn(width="small"),
                    "Alış": st.column_config.NumberColumn(format="%.2f ₺"),
                    "Fiyat": st.column_config.NumberColumn(format="%.2f ₺"),
                    "K/Z %": st.column_config.NumberColumn(format="%+.2f%%"),
                    "Zirve": st.column_config.NumberColumn(format="%.2f ₺",
                        help="Alış tarihinizden bugüne görülen en yüksek kapanış"),
                    "Stop": st.column_config.NumberColumn(format="%.2f ₺",
                        help="Zirveden 2,5×ATR aşağısı. Fiyat buranın altına inerse SAT."),
                    "Stop'a Pay %": st.column_config.NumberColumn(format="%+.1f%%",
                        help="Fiyatın stop seviyesinden ne kadar yukarıda olduğu. "
                             "Küçüldükçe çıkış yaklaşıyor demektir."),
                    "Gün": st.column_config.NumberColumn(help="Kaç gündür elinizde"),
                    "Kaç Gündür SAT": st.column_config.NumberColumn(
                        help="Stop kaç işlem günüdür kırık. Sinyalin bugün mü "
                             "doğduğunu yoksa günlerdir mi beklediğini gösterir."),
                })

            st.caption(
                f"**Kural: takip eden stop.** Aldıktan sonra görülen en yüksek fiyattan "
                f"{pt.STOP_ATR_KATSAYISI:g}×ATR geri çekilirse SAT. Kazanan pozisyonun "
                f"koşmasına izin verir, bozulanı keser. ATR hissenin kendi oynaklığıdır.\n\n"
                f"**Stop tavanı:** stop, alış fiyatınızın en fazla "
                f"%{pt.STOP_TAVAN_YUZDE:g} altında olabilir. Oynaklığı yüksek hisselerde "
                f"saf ATR stop'u çok geniş zarara izin veriyordu (AKSEN'de alışın %13,8 "
                f"altına iniyordu); tavan bu toleransı sınırlar. Tavan stop'u yalnızca "
                f"YUKARI çeker — hisse yükseldikçe ATR stop'u devralır, kazanç kısıtlanmaz.\n\n"
                "⚠️ Motor puanı bu karara KATILMAZ. Backtestte puanın ileri getiriyle "
                "korelasyonu +0,012 çıktı, yani puan yön öngörmüyor; puan düşene kadar "
                "beklemek çıkışı geciktirir. Bu panel fiyatın kendisine bakar."
            )
            if _bilinmez:
                st.info("Karar üretilemeyen pozisyonlar: "
                        + ", ".join(f"{r['Hisse']} ({r['Gerekçe']})" for r in _bilinmez))

    st.divider()
    izleme_metni = st.text_input(
        "Takas aday havuzu — izleme listesi (virgülle ayırın)",
        value=st.session_state.get("izleme_metni_tavsiye", "ASELS, SISE, KCHOL, EREGL, BIMAS, TUPRS, GARAN, ASTOR"),
        help="Portföyünüzdeki zayıf hisseler için bu listeden güçlü bir takas adayı aranır.")
    st.session_state["izleme_metni_tavsiye"] = izleme_metni
    aday_listesi = [s.strip().upper().replace(".IS", "") for s in izleme_metni.split(",") if s.strip()]

    analiz_calistir = st.button("📊 PORTFÖYÜ ANALİZ ET VE TAVSİYE ÜRET", type="primary",
                                use_container_width=True)

    if analiz_calistir:
        pozisyonlar_ham = pt.pozisyonlari_getir()
        if not pozisyonlar_ham:
            st.warning("Portföyünüz boş. Önce yukarıdan pozisyon ekleyip 'Portföyü Kaydet'e basın.")
        else:
            with st.spinner("Canlı fiyatlar çekiliyor, motor puanları hesaplanıyor..."):
                semboller_poz = [p["sembol"] for p in pozisyonlar_ham]
                guncel_fiyatlar = {}
                for s in semboller_poz:
                    f = _canli_fiyat_getir(vk, _gecmis, s)
                    if f is not None:
                        guncel_fiyatlar[s] = f

                durum = pt.portfoy_durumu(guncel_fiyatlar)
                pt.deger_kaydet(guncel_fiyatlar)

                endeks = _endeks()
                portfoy_puanlari = pt.portfoy_puanlarini_hesapla(am, _gecmis, endeks)
                aday_havuzu = pt.aday_havuzunu_tara(am, aday_listesi, _gecmis, endeks,
                                                    mevcut_semboller=set(semboller_poz))
                oneriler = pt.rebalans_onerileri(portfoy_puanlari, aday_havuzu)
                sektor_uyarilari = pt.sektor_yogunlasma_kontrolu(guncel_fiyatlar)
                risk = pt.risk_metrikleri(durum, portfoy_puanlari, pt.deger_egrisi())

                yonetici_ozet = None
                if aktifler:
                    try:
                        yonetici_ozet = la.yonetici_ozeti(durum, oneriler)
                    except Exception:
                        yonetici_ozet = None

            # Sonuçları oturuma kaydet — AŞAĞIDA bir "Fırsat" hisse linkine
            # tıklanınca sayfa yeniden çalışır (st.rerun()); bu düğme basılı
            # DEĞİLDİR artık, ama rapor session_state'ten okunduğu için
            # kaybolmaz (eskiden sadece "if analiz_calistir:" içindeydi ve
            # bir fırsata tıklamak TÜM raporu yok ediyordu).
            st.session_state["oto_sonuc"] = {
                "durum": durum, "portfoy_puanlari": portfoy_puanlari,
                "aday_havuzu": aday_havuzu, "oneriler": oneriler,
                "sektor_uyarilari": sektor_uyarilari, "risk": risk,
                "yonetici_ozet": yonetici_ozet,
            }

    if "oto_sonuc" in st.session_state:
            _s = st.session_state["oto_sonuc"]
            durum, portfoy_puanlari, aday_havuzu, oneriler, sektor_uyarilari, risk, yonetici_ozet = (
                _s["durum"], _s["portfoy_puanlari"], _s["aday_havuzu"], _s["oneriler"],
                _s["sektor_uyarilari"], _s["risk"], _s["yonetici_ozet"])

            # ── EYLEM PLANI: "şunu sat, yerine bunu al" — en üstte, tam genişlikte ──
            if ozm is not None:
                _plan = ozm.portfoy_eylem_plani(oneriler, durum, sektor_uyarilari)
                if _plan:
                    with st.container(border=True):
                        st.markdown("## 🎯 Ne Yapmalı? — Eylem Planı")
                        st.markdown(_plan)
                    st.divider()

            # ── PORTFÖY SAĞLIK METRİKLERİ: profesyonel panellerdeki gibi
            # ağırlıklı puan, çeşitlendirme, volatilite ve maks. düşüş ────────
            st.markdown("### 🩺 Portföy Sağlık Metrikleri")
            r1, r2, r3, r4 = st.columns(4)
            if ozm is not None and risk["agirlikli_puan"] is not None:
                renk_ap = ozm.renk_kodu(risk["agirlikli_puan"])
                r1.markdown(
                    f"<div style='text-align:center'><span style='font-size:.8rem;opacity:.75'>"
                    f"Ağırlıklı Motor Puanı</span><br>"
                    f"<span style='font-size:1.7rem;font-weight:700;color:{renk_ap}'>"
                    f"{risk['agirlikli_puan']:.0f}</span></div>", unsafe_allow_html=True)
            else:
                r1.metric("Ağırlıklı Motor Puanı", "—")
            r2.metric("Çeşitlendirme Skoru",
                     f"{risk['cesitlendirme_skoru']:.0f}/100" if risk["cesitlendirme_skoru"] is not None else "—",
                     help="100 = pozisyonlar eşit ağırlıkta dağılmış, düşük = tek hisseye yığılmış.")
            r3.metric("Yıllık Volatilite",
                     f"%{risk['yillik_volatilite']:.1f}" if risk["yillik_volatilite"] is not None else "—",
                     help="Portföy değerindeki günlük dalgalanmanın yıllıklandırılmış hali (en az birkaç günlük kayıt gerekir).")
            r4.metric("Maks. Düşüş (Drawdown)",
                     f"%{risk['maks_dusus']:.1f}" if risk["maks_dusus"] is not None else "—",
                     help="Kayıt tutulduğu süre içinde tepe değerden en büyük düşüş yüzdesi.")
            if risk["en_iyi"] and risk["en_kotu"] and risk["en_iyi"]["sembol"] != risk["en_kotu"]["sembol"]:
                st.caption(f"💪 En güçlü: **{risk['en_iyi']['sembol']}** (Puan: {risk['en_iyi']['puan']:.0f}) · "
                          f"⚠️ En zayıf: **{risk['en_kotu']['sembol']}** (Puan: {risk['en_kotu']['puan']:.0f})")
            st.divider()

            sol, sag = st.columns([1.3, 1])

            with sol:
                st.markdown("#### 📈 Portföy Analiz Matrisi")
                m1, m2, m3 = st.columns(3)
                m1.metric("Toplam Maliyet", f"{durum['toplam_maliyet']:,.0f} ₺")
                m2.metric("Güncel Değer", f"{durum['toplam_deger']:,.0f} ₺")
                m3.metric("Toplam Kâr/Zarar", f"{durum['toplam_kar_zarar']:+,.0f} ₺",
                         f"%{durum['toplam_kar_zarar_yuzde']:+.2f}")
                if tiklanabilir_tablo is not None:
                    tiklanabilir_tablo(pd.DataFrame(durum["pozisyonlar"]), "oto_pozisyonlar",
                                      sembol_kolonu="Hisse")
                else:
                    st.dataframe(pd.DataFrame(durum["pozisyonlar"]), use_container_width=True, hide_index=True)

                egri = pt.deger_egrisi()
                if len(egri) > 1:
                    st.markdown("##### Portföy Değeri (Zaman İçinde)")
                    fige = go.Figure(go.Scatter(x=egri["zaman"], y=egri["toplam_deger"],
                                                mode="lines+markers", line=dict(color="#0ea5e9")))
                    fige.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10),
                                       template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                                       plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fige, use_container_width=True)

                # ── Sektör dağılımı — çeşitlendirmeyi görsel olarak da göster ──
                sektor_toplam = {}
                for poz in durum["pozisyonlar"]:
                    sektor_toplam[poz["Sektör"]] = sektor_toplam.get(poz["Sektör"], 0.0) + (poz["Güncel Değer"] or 0.0)
                if len(sektor_toplam) > 1:
                    st.markdown("##### Sektör Dağılımı")
                    figs = go.Figure(go.Pie(labels=list(sektor_toplam.keys()),
                                            values=list(sektor_toplam.values()), hole=0.45))
                    figs.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10),
                                       template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                                       showlegend=True)
                    st.plotly_chart(figs, use_container_width=True)

                if aday_havuzu:
                    with st.expander("🔍 Aday Havuzu Puanları (izleme listesi)"):
                        if tiklanabilir_tablo is not None:
                            tiklanabilir_tablo(pd.DataFrame(aday_havuzu), "oto_aday_havuzu",
                                              sembol_kolonu="sembol", ipucu=False)
                        else:
                            st.dataframe(pd.DataFrame(aday_havuzu), use_container_width=True, hide_index=True)

            with sag:
                st.markdown("#### 🤖 YAPAY ZEKA & MOTOR TAVSİYELERİ")

                renk = {
                    "KAYIP KES / ELDEN ÇIKAR (SAT)": "🔴",
                    "TAKAS": "🟠",
                    "ZAYIF / İZLE": "🟡",
                    "TAŞIMAYA DEVAM ET / AĞIRLIK ARTIR (AL)": "🟢",
                    "TUT": "⚪",
                    "VERİ YOK": "⚫",
                }
                for o in sorted(oneriler, key=lambda x: (x["puan"] is None, -(x["puan"] or 0))):
                    ikon = renk.get(o["eylem"], "⚪")
                    st.markdown(f"{ikon} **{o['eylem']}** — {o['mesaj']}")

                if sektor_uyarilari:
                    st.markdown("##### ⚠️ Yoğunlaşma Riskleri")
                    for uyari in sektor_uyarilari:
                        st.warning(uyari)

                if yonetici_ozet:
                    st.markdown("##### 📋 Yönetici Özeti (LLM)")
                    st.info(yonetici_ozet)
                elif aktifler:
                    st.caption("Yönetici özeti bu çalıştırmada üretilemedi (LLM çağrısı başarısız olmuş olabilir).")
                else:
                    st.caption("Yönetici özeti için '.env' dosyasına bir LLM API anahtarı ekleyin "
                              "(opsiyonel — Groq ücretsizdir).")

                st.caption("⚠️ Bu tavsiyeler bilgilendirme amaçlıdır, YATIRIM TAVSİYESİ DEĞİLDİR. "
                          "Alım/satım kararınızı ve işleminizi kendiniz verir ve gerçekleştirirsiniz.")

            # ── 🎯 FIRSATLAR: portföyde olmayan, motor puanı yüksek hisseler ──
            # Kullanıcının "fırsat varsa sun" isteği burada karşılanır. İki
            # kaynaktan beslenir: (1) izleme listesi aday havuzunda, takas
            # önerisi olarak zaten KULLANILMAMIŞ güçlü adaylar, (2) elde varsa
            # tüm-BIST arka plan taraması önbelleği (tarama_onbellek.py) —
            # izleme listesinin dışındaki hisseleri de kapsar.
            kullanilan_takas = {o["takas_adayi"]["sembol"] for o in oneriler if o.get("takas_adayi")}
            firsatlar = [a for a in aday_havuzu
                        if a.get("puan") is not None and a["puan"] >= pt.ESIK_TAKAS_ADAY
                        and a["sembol"] not in kullanilan_takas]

            firsatlar_genis = []
            if tob is not None:
                try:
                    _c_tarama, _, _, _c_zaman, _c_taze = tob.oku()
                    if _c_tarama is not None and len(_c_tarama):
                        mevcut_semboller = {p["sembol"] for p in pt.pozisyonlari_getir()}
                        aday_semboller_set = {a["sembol"] for a in firsatlar}
                        for _, satir in _c_tarama.head(15).iterrows():
                            s = satir.get("Hisse")
                            if s in mevcut_semboller or s in aday_semboller_set:
                                continue
                            firsatlar_genis.append({"sembol": s, "puan": satir.get("Puan"),
                                                    "fiyat": satir.get("Fiyat")})
                except Exception:
                    pass

            if firsatlar or firsatlar_genis:
                st.divider()
                st.markdown("### 🎯 Fırsatlar — Portföyünüzde Olmayan Öne Çıkan Hisseler")
                fc1, fc2 = st.columns(2)
                def _firsat_satiri(a, anahtar_on):
                    renk_f = (ozm.renk_kodu(a["puan"]) if ozm is not None and a.get("puan") is not None
                             else "#16a34a")
                    etiket = (f"● {a['sembol']} — Puan {a['puan']:.0f}"
                             + (f" · {a['fiyat']:.2f} ₺" if a.get("fiyat") else ""))
                    if hisse_linki is not None:
                        hisse_linki(a["sembol"], anahtar_on, etiket=etiket)
                    else:
                        st.markdown(f"<span style='color:{renk_f};font-weight:700'>●</span> "
                                   f"**{a['sembol']}** — Puan {a['puan']:.0f}"
                                   + (f" · {a['fiyat']:.2f} ₺" if a.get("fiyat") else ""),
                                   unsafe_allow_html=True)

                with fc1:
                    st.markdown("##### 👀 İzleme Listenizden")
                    if firsatlar:
                        for a in firsatlar[:5]:
                            _firsat_satiri(a, "firsat_izleme")
                    else:
                        st.caption("İzleme listenizde şu an takas önerisi olarak kullanılmamış güçlü aday yok.")
                with fc2:
                    st.markdown("##### 🌐 Tüm BIST Taramasından (arka plan önbelleği)")
                    if firsatlar_genis:
                        for a in firsatlar_genis[:5]:
                            _firsat_satiri(a, "firsat_genis")
                    elif tob is not None:
                        st.caption("Arka plan taraması önbelleği henüz yok veya boş. "
                                  "'🚀 Öne Çıkan Hisseler' sekmesinden bir kez tarayın ya da "
                                  "ARKA_PLAN_TARAMA.bat'ı çalıştırın.")
                    else:
                        st.caption("—")
                st.caption("Bu liste sadece bilgi amaçlıdır; detaylı gerekçe için hisseyi "
                          "'Hisse Araştır' sekmesinde inceleyin.")

                # Fırsat linklerinden birine tıklanmışsa, analizi hemen burada göster.
                if mini_analiz_karti is not None:
                    for _anahtar_g in ("firsat_izleme", "firsat_genis"):
                        _secilen_g = st.session_state.get("_son_analiz_" + _anahtar_g)
                        if _secilen_g:
                            mini_analiz_karti(_secilen_g)
