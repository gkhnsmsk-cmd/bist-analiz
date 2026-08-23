# -*- coding: utf-8 -*-
"""
sanal_portfoy_paneli.py — "Sanal Portföy (Paper Trading)" sekmesi.
════════════════════════════════════════════════════════════════════
GERÇEK PARA KULLANMAZ. Motor, kullanıcının belirlediği sanal bir bütçeyle
(varsayılan 1.000.000 TL), kendi kararıyla otonom şekilde sanal hisse alıp
satar; amaç, gerçek paraya geçmeden önce stratejiyi dürüstçe test etmektir.

Kullanıcı kontrolü (bu panelin kalbi):
  • Motoru istediği an AÇIP KAPATABİLİR — kapalıyken otomatik script
    (GUNLUK_SANAL_YATIRIM.bat) hiçbir izleme/işlem yapmaz.
  • Hedefi (aylık %) portföyü SIFIRLAMADAN değiştirebilir.
  • Portföyü SIFIRLAYIP baştan başlatabilir ("iptal et / yenile").
  • Pozisyon tablosunu doğrudan DÜZENLEYEBİLİR (adet/maliyet/ekleme/silme) —
    bu bir motor kararı değildir, işlem geçmişine "MANUEL DÜZENLEME" olarak
    şeffafça not düşülür.
  • Herhangi bir pozisyonu, motorun haftalık döngüsünü beklemeden HEMEN
    manuel olarak satabilir.

Bu panel sanal_yatirimci.py'nin ince bir arayüz katmanıdır — karar mantığının
tamamı orada. Burada: kurulum, aç/kapat, manuel düzenleme, manuel tetikleme
butonları ve DÜRÜST bir performans raporu gösterilir.
"""
import datetime as dt


def _tam_yukseklik(satir_sayisi: int) -> int:
    """st.dataframe'i TÜM satırları gösterecek şekilde boyutlar — kutunun
    kendi iç kaydırması olmasın diye (bkz. app.py'deki aynı adlı fonksiyon)."""
    return 38 + 35 * max(satir_sayisi, 1) + 3


def render(st, pd, np, go, dt_mod, vk, am, sv, _gecmis, _endeks, _semboller,
           ozm=None, _toplu_fiyat=None, tiklanabilir_tablo=None, hisse_linki=None):
    st.info("ℹ️ Bu sekme SANAL PARA ile çalışır. Gerçek bir aracı kuruma hiçbir "
           "emir gönderilmez. Motor, her çalıştırmada kural tabanlı olarak kendi "
           "puanlama sistemine göre otonom AL/SAT kararı verir; günlük "
           "çalıştırmalarda sadece izler, işlem yapmaz.")

    portfoy = sv.portfoy_getir()
    ilk_kurulum = portfoy["nakit"] == portfoy["baslangic_butce"] and not portfoy["pozisyonlar"] \
        and not sv.islem_gecmisi()
    aktif = sv.motor_aktif_mi()

    # ── Motor durumu: aç/kapat (en üstte, en görünür yer) ────────────────────
    d1, d2 = st.columns([3, 1])
    with d1:
        if aktif:
            st.success("🟢 MOTOR AKTİF — her gün izliyor, gerekçe oluştuğunda alım-satım yapıyor.")
        else:
            st.error("🔴 MOTOR DURAKLATILMIŞ — GUNLUK_SANAL_YATIRIM.bat çalışsa bile hiçbir "
                    "izleme veya alım-satım yapılmıyor. Mevcut pozisyonlar olduğu gibi duruyor.")
    with d2:
        if aktif:
            if st.button("⏸️ Motoru Durdur", use_container_width=True):
                sv.motoru_kapat()
                st.rerun()
        else:
            if st.button("▶️ Motoru Başlat", use_container_width=True, type="primary"):
                sv.motoru_ac()
                st.rerun()
    st.caption("Motor kapalıyken de aşağıdaki 'Manuel Çalıştırma' butonlarını elle "
              "kullanabilirsiniz — kapatma sadece OTOMATİK (zamanlanmış) çalışmayı durdurur.")

    askida = sv.askidaki_satislari_bul()
    if askida:
        st.error(
            "⚠️ **Askıda satış** — motor aşağıdaki pozisyonları puan sıralamasında gerilediği "
            "için satmak istiyor, ama güncel fiyat alınamadığından satamıyor ve pozisyon(lar) "
            "günlerdir elde kalmış:\n\n" +
            "\n".join(f"- **{a['sembol']}**: {a['ilk_tarih']} tarihinden beri "
                     f"({a['deneme']} başarısız deneme)" for a in askida) +
            "\n\nBir dahaki 'Kararı Şimdi Çalıştır' veya otomatik çalıştırmada tekil "
            "yedek denemeyle satış tekrar denenecek. Beklemek istemiyorsanız aşağıdaki "
            "'Şimdi Sat' ile elle satabilirsiniz.")

    st.divider()

    # ── Hedef güncelleme (portföyü SIFIRLAMADAN) ─────────────────────────────
    st.markdown("### 🎯 Hedef")
    h1, h2 = st.columns([2, 1])
    with h1:
        yeni_hedef_canli = st.number_input(
            "Hedef aylık getiri (%) — mevcut portföyü etkilemez, sadece performans ölçütünü değiştirir",
            min_value=0.0, value=float(portfoy["hedef_aylik_yuzde"]), step=1.0, key="sanal_hedef_canli")
    with h2:
        st.write("")
        if st.button("💾 Hedefi Güncelle", use_container_width=True):
            sv.hedefi_guncelle(yeni_hedef_canli)
            st.success(f"Hedef aylık %{yeni_hedef_canli:.0f} olarak güncellendi.")
            st.rerun()

    with st.expander("🗑️ Portföyü İptal Et / Sıfırdan Başlat"):
        st.caption("Bu, TÜM sanal işlem ve değer geçmişini SİLER, geri alınamaz. Sadece hedefi "
                  "değiştirmek için bunu kullanmanıza gerek yok (yukarıdaki 'Hedefi Güncelle' yeterli).")
        c1, c2 = st.columns(2)
        with c1:
            yeni_butce = st.number_input("Yeni sanal başlangıç bütçesi (₺)",
                                        min_value=10_000.0, value=float(portfoy["baslangic_butce"]),
                                        step=50_000.0, key="sanal_butce_input")
        with c2:
            yeni_hedef_sifirla = st.number_input("Yeni hedef aylık getiri (%)", min_value=0.0,
                                                value=float(portfoy["hedef_aylik_yuzde"]), step=1.0,
                                                key="sanal_hedef_sifirla_input")
        onay_sifirla = st.checkbox("Sıfırlamayı onaylıyorum (TÜM sanal işlem/değer geçmişi SİLİNİR, "
                                   "geri alınamaz)", key="sanal_sifirla_onay")
        if st.button("🗑️ Sanal Portföyü Sıfırla ve Yeniden Başlat", disabled=not onay_sifirla):
            sv.sifirla(yeni_butce, yeni_hedef_sifirla)
            st.success("Sanal portföy sıfırlandı.")
            st.rerun()

    st.divider()

    # ── Manuel düzenleme (kullanıcı müdahalesi) ──────────────────────────────
    st.markdown("### ✏️ Manuel Düzenleme (Müdahale)")
    st.caption("Pozisyon tablosunu doğrudan düzenleyebilirsiniz: adet/maliyet değiştirme, yeni "
              "satır ekleme, satır silme. Bu bir motor kararı DEĞİLDİR — işlem geçmişine "
              "şeffaflık için not düşülür. Nakit miktarını da burada elle ayarlayabilirsiniz.")

    duzenleme_df = pd.DataFrame([
        {"Hisse": p["sembol"], "Adet": p["adet"], "Maliyet": p["maliyet"]}
        for p in portfoy["pozisyonlar"]
    ]) if portfoy["pozisyonlar"] else pd.DataFrame({
        "Hisse": pd.Series(dtype="str"), "Adet": pd.Series(dtype="float"),
        "Maliyet": pd.Series(dtype="float"),
    })

    duzenlenen = st.data_editor(
        duzenleme_df, num_rows="dynamic", use_container_width=True, key="sanal_pozisyon_editor",
        column_config={
            "Hisse": st.column_config.TextColumn(required=True, help="Örn. THYAO"),
            "Adet": st.column_config.NumberColumn(min_value=0.0, step=1.0, required=True),
            "Maliyet": st.column_config.NumberColumn(min_value=0.0, step=0.01, required=True,
                                                     help="Sanal ortalama alış maliyeti (₺)"),
        })
    yeni_nakit_manuel = st.number_input("Nakit (₺)", min_value=0.0, value=float(portfoy["nakit"]),
                                        step=1000.0, key="sanal_nakit_manuel")
    if st.button("💾 Manuel Değişiklikleri Kaydet"):
        sv.manuel_duzenle(duzenlenen.to_dict("records"), yeni_nakit_manuel)
        st.success("Manuel değişiklikler kaydedildi.")
        st.rerun()

    if portfoy["pozisyonlar"]:
        st.markdown("**Bir pozisyonu hemen (motoru beklemeden) sat:**")
        s1, s2, s3 = st.columns([1.5, 1.5, 1])
        semboller_mevcut = [p["sembol"] for p in portfoy["pozisyonlar"]]
        with s1:
            secilen = st.selectbox("Hisse", semboller_mevcut, key="sanal_manuel_sat_sembol")
        with s2:
            varsayilan_fiyat = None
            try:
                f = vk.canli_fiyat_cek(secilen)
                if f == f and f > 0:
                    varsayilan_fiyat = float(f)
            except Exception:
                pass
            satis_fiyati = st.number_input("Satış fiyatı (₺)", min_value=0.01,
                                           value=varsayilan_fiyat or 1.0, step=0.5,
                                           key="sanal_manuel_sat_fiyat")
        with s3:
            st.write("")
            if st.button("🔴 Şimdi Sat", use_container_width=True):
                kayit = sv.pozisyonu_manuel_sat(secilen, satis_fiyati)
                if kayit:
                    st.success(f"{secilen} manuel olarak satıldı: {kayit['tutar']:,.0f} ₺")
                st.rerun()

    st.divider()

    # ── Manuel tetikleme (motorun kendi kararı) ──────────────────────────────
    st.markdown("### 🕹️ Manuel Çalıştırma (motorun kendi kararı)")
    st.caption("Normalde bu motor GUNLUK_SANAL_YATIRIM.bat ile Windows Görev Zamanlayıcısı "
              "üzerinden kendi kendine çalışır (her gün izleme + gerekçe varsa alım-satım). "
              "Burada, uygulamayı kapatmadan test etmek için manuel de çalıştırabilirsiniz "
              "(motor duraklatılmış olsa bile bu butonlar çalışır).")
    kapsam = st.selectbox("Tarama kapsamı (karar için)", ["TUM", "XU100", "XU030"],
                          format_func=lambda x: {"TUM": "Tüm BIST (~600 hisse, en yavaş)",
                                                 "XU100": "BIST 100",
                                                 "XU030": "BIST 30 (hızlı)"}[x],
                          key="sanal_kapsam")
    mc1, mc2 = st.columns(2)
    with mc1:
        izle_tetik = st.button("👁️ Bugünün İzlemesini Çalıştır", use_container_width=True)
    with mc2:
        rebalans_tetik = st.button("🔁 Karar Motorunu ŞİMDİ Çalıştır",
                                   use_container_width=True)

    if izle_tetik or rebalans_tetik:
        with st.spinner("Veriler indiriliyor ve motor çalıştırılıyor..."):
            semboller = _semboller(kapsam)
            # HIZ: önbellekli toplu indirme (app.py'den geçirilir); yoksa doğrudan çağrı.
            veriler = (_toplu_fiyat(tuple(semboller), 2.0) if _toplu_fiyat is not None
                       else vk.toplu_fiyat(semboller, yil=2.0))

            def fiyat_getirici(s):
                df = veriler.get(s)
                if df is not None and len(df):
                    return df
                # Toplu indirmede eksik kalan sembol için tek tek yedek deneme —
                # aksi halde bu sembol satılmak istenirse fiyat bulunamayıp
                # pozisyon süresiz 'askıda' kalabilir (bkz. sv.askidaki_satislari_bul).
                try:
                    tekil = vk.fiyat_gecmisi(s, 1.0)
                    return tekil if tekil is not None and len(tekil) else None
                except Exception:
                    return None

            endeks = _endeks()

            portfoy_guncel = sv.portfoy_getir()
            guncel_fiyatlar = {}
            for p in portfoy_guncel["pozisyonlar"]:
                df = veriler.get(p["sembol"])
                if df is not None and len(df):
                    guncel_fiyatlar[p["sembol"]] = float(df["Close"].iloc[-1])

            izleme = sv.gunluk_izle(am, fiyat_getirici, endeks, guncel_fiyatlar)
            st.session_state["sanal_son_izleme"] = izleme

            if rebalans_tetik:
                sonuc = sv.gunluk_karar(am, fiyat_getirici, endeks, semboller)
                st.session_state["sanal_son_rebalans"] = sonuc

        st.success("Çalıştırma tamamlandı.")
        st.rerun()

    if "sanal_son_rebalans" in st.session_state:
        sonuc = st.session_state["sanal_son_rebalans"]
        with st.expander("📋 Son karar sonucu", expanded=True):
            st.write(sonuc["neden"])
            if sonuc.get("zayif_piyasa_uyarisi"):
                st.warning("⚠️ Zayıf piyasa uyarısı: motor yine de 'her zaman tam yatırımlı' "
                          "kuralı gereği pozisyon açtı — bu daha riskli bir durumdur.")
            if sonuc.get("islemler"):
                if tiklanabilir_tablo is not None:
                    tiklanabilir_tablo(pd.DataFrame(sonuc["islemler"]), "sanal_rebalans_islemler",
                                      sembol_kolonu="sembol", ipucu=False)
                else:
                    _df = pd.DataFrame(sonuc["islemler"])
                    st.dataframe(_df, use_container_width=True, hide_index=True,
                                 height=_tam_yukseklik(len(_df)))

    st.divider()

    # ── Performans raporu (dürüst) ───────────────────────────────────────────
    st.markdown("### 📊 Sanal Portföy Performansı")
    guncel_fiyatlar = {}
    for p in portfoy["pozisyonlar"]:
        try:
            f = vk.canli_fiyat_cek(p["sembol"])
            if f == f and f > 0:
                guncel_fiyatlar[p["sembol"]] = float(f)
                continue
        except Exception:
            pass
        try:
            df = _gecmis(p["sembol"], 0.2)
            if df is not None and len(df):
                guncel_fiyatlar[p["sembol"]] = float(df["Close"].iloc[-1])
        except Exception:
            pass

    # NOT: `endeks` yerel değişkeni yalnızca yukarıdaki BUTON bloğunda
    # tanımlanıyor; burada (buton basılmadan da çalışan bölümde) yoktu ve
    # UnboundLocalError ile TÜM sekmeyi çökertiyordu (AppTest yakaladı).
    # Önbellekli _endeks() doğrudan çağrılır; başarısız olursa None geçilir
    # ve karşılaştırma "veri yok" olarak gösterilir — uydurma yapılmaz.
    try:
        _endeks_df = _endeks()
    except Exception:
        _endeks_df = None
    rapor = sv.performans_raporu(guncel_fiyatlar, _endeks_df)

    if ozm is not None:
        _sanal_ozet = ozm.sanal_portfoy_ozeti(rapor)
        if _sanal_ozet:
            with st.container(border=True):
                st.markdown("#### 📝 Sade Özet — bu ne anlama geliyor?")
                st.markdown(_sanal_ozet)

    # ── ŞEFFAFLIK: değerin ne kadarı GERÇEK güncel fiyattan geliyor? ────────
    # Gerekçe: fiyatı çözülemeyen pozisyonlar eskiden sessizce 0 TL sayılıyor
    # ve portföy düşmüş gibi görünüyordu. Artık son bilinen fiyat/maliyetle
    # değerleniyorlar; ama bunun TAHMİN olduğu kullanıcıdan gizlenmiyor.
    _fiyatsiz = rapor.get("fiyatsiz_semboller") or []
    if _fiyatsiz:
        st.warning(
            f"⚠️ **{len(_fiyatsiz)} pozisyonun güncel fiyatı alınamadı** "
            f"({', '.join(_fiyatsiz)}). Bu pozisyonlar **son bilinen fiyat / alış "
            f"maliyeti** ile değerlendi — yani toplam değerin yaklaşık "
            f"**%{rapor.get('tahmini_deger_yuzde', 0):.0f}'i tahminidir**. "
            "Aşağıdaki tabloda her pozisyonun 'Fiyat Kaynağı' sütununa bakabilirsiniz.")

    # ═══════════════════════════════════════════════════════════════════════
    # ENDEKS KARŞILAŞTIRMASI — EN ÜSTTE, çünkü ASIL BAŞARI ÖLÇÜTÜ BU.
    # ═══════════════════════════════════════════════════════════════════════
    # 22.08.2026'ya kadar bu panel sadece "%-1,59 getiri" diyordu. Elle
    # bakınca BIST 100'ün aynı dönemde %+5,89 yükseldiği, yani motorun
    # endeksin %7,49 GERİSİNDE kaldığı ortaya çıktı. Mutlak getiri tek
    # başına yanıltıcıdır: piyasa düşerken -%2 başarıdır, piyasa +%6
    # çıkarken -%2 başarısızlıktır. Bu blok o boşluğu kapatır.
    _e = rapor.get("endeks") or {}
    if _e.get("veri_var"):
        with st.container(border=True):
            st.markdown("#### 🎯 Endeksi Yeniyor mu? — asıl başarı ölçütü")
            e1, e2, e3 = st.columns(3)
            e1.metric("Sanal Portföy", f"%{_e['portfoy_yuzde']:+.2f}")
            e2.metric("BIST 100", f"%{_e['endeks_yuzde']:+.2f}",
                      help=f"{_e['endeks_bas']:,.2f} → {_e['endeks_son']:,.2f}")
            e3.metric("Endeks Üstü", f"%{_e['endeks_ustu_yuzde']:+.2f}",
                      delta=f"%{_e['endeks_ustu_yuzde']:+.2f}",
                      help="Pozitifse motor endeksten iyi, negatifse endekse "
                           "yatırmak daha iyi olurdu.")
            if _e["yeniyor_mu"]:
                st.success("✅ Motor endeksi YENİYOR.")
            else:
                _bas = rapor["baslangic_butce"]
                _endekste = _bas * (1 + _e["endeks_yuzde"] / 100)
                st.error(
                    f"⚠️ Motor endeksin **%{abs(_e['endeks_ustu_yuzde']):.2f} GERİSİNDE**. "
                    f"Aynı parayı hiç düşünmeden endekse koysaydınız "
                    f"**{_endekste:,.0f} ₺** olurdu; motor **{rapor['toplam_deger']:,.0f} ₺** yaptı "
                    f"(**{_endekste - rapor['toplam_deger']:,.0f} ₺** fark).")
            st.caption("⚠️ Kısa dönem sonuçları yanıltıcıdır — bir stratejinin "
                       "değerlendirilmesi için en az birkaç ay gerekir.")
    else:
        st.info("Endeks verisi alınamadığı için karşılaştırma yapılamadı. "
                "Mutlak getiri tek başına yanıltıcıdır — piyasanın ne yaptığı "
                "bilinmeden 'iyi' ya da 'kötü' denemez.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Toplam Değer", f"{rapor['toplam_deger']:,.0f} ₺",
             f"%{rapor['gerceklesen_kumulatif_yuzde']:+.2f}")
    m2.metric("Başlangıç Bütçesi", f"{rapor['baslangic_butce']:,.0f} ₺")
    m3.metric("Geçen Süre", f"{rapor['gun_sayisi']} gün ({rapor['ay_sayisi']:.1f} ay)")
    m4.metric("Nakit", f"{rapor['nakit']:,.0f} ₺")

    hedef_metin = rapor["hedefe_gore_beklenen_kumulatif_yuzde"]
    if rapor["hedefi_yakaliyor_mu"] is None:
        st.caption(f"Hedef: aylık %{rapor['hedef_aylik_yuzde']:.0f}. Henüz karşılaştırma için "
                  "yeterli süre geçmedi.")
    elif rapor["hedefi_yakaliyor_mu"]:
        st.success(f"✅ Hedefi YAKALIYOR — gerçekleşen kümülatif getiri %{rapor['gerceklesen_kumulatif_yuzde']:+.2f}, "
                  f"hedefin gerektirdiği %{hedef_metin:+.2f} (aylık %{rapor['hedef_aylik_yuzde']:.0f} hedefe göre).")
    else:
        st.warning(f"⚠️ Hedefi YAKALAYAMIYOR — gerçekleşen kümülatif getiri %{rapor['gerceklesen_kumulatif_yuzde']:+.2f}, "
                  f"hedefin gerektirdiği %{hedef_metin:+.2f} (aylık %{rapor['hedef_aylik_yuzde']:.0f} hedefe göre). "
                  "Bu, motorun performansının şu an hedefin altında olduğu anlamına gelir — bilgi saklanmaz.")

    if rapor["maksimum_dusus_yuzde"] is not None:
        st.caption(f"Şimdiye kadarki maksimum düşüş (tepe değerden): %{rapor['maksimum_dusus_yuzde']:.2f} · "
                  f"Toplam sanal işlem sayısı: {rapor['toplam_islem_sayisi']}")

    egri = sv.deger_egrisi()
    if len(egri) > 1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=egri["tarih"], y=egri["toplam_deger"], mode="lines+markers",
                                 name="Sanal Portföy Değeri", line=dict(color="#0ea5e9")))
        gun_sayisi_max = (egri["tarih"].iloc[-1] - egri["tarih"].iloc[0]).days
        if gun_sayisi_max > 0:
            aylik_carpan = (1 + rapor["hedef_aylik_yuzde"] / 100) ** (1 / 30.44)
            hedef_egrisi = [rapor["baslangic_butce"] * (aylik_carpan ** g)
                           for g in range((egri["tarih"].iloc[-1] - egri["tarih"].iloc[0]).days + 1)]
            hedef_tarihler = pd.date_range(egri["tarih"].iloc[0], egri["tarih"].iloc[-1])
            fig.add_trace(go.Scatter(x=hedef_tarihler, y=hedef_egrisi, mode="lines",
                                     name=f"Hedef eğrisi (aylık %{rapor['hedef_aylik_yuzde']:.0f})",
                                     line=dict(color="#94a3b8", dash="dash")))
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=30, b=10),
                          legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Değer eğrisi için henüz yeterli veri yok — en az bir 'İzleme' veya "
                  "Karar motoru çalıştıktan sonra burada görünecek.")

    if rapor["pozisyonlar"]:
        st.markdown("#### Güncel Sanal Pozisyonlar")
        if tiklanabilir_tablo is not None:
            tiklanabilir_tablo(pd.DataFrame(rapor["pozisyonlar"]), "sanal_pozisyonlar",
                              sembol_kolonu="Hisse")
        else:
            _df = pd.DataFrame(rapor["pozisyonlar"])
            st.dataframe(_df, use_container_width=True, hide_index=True,
                         height=_tam_yukseklik(len(_df)))
    else:
        st.caption("Henüz açık pozisyon yok. Karar motoru ilk kez çalıştığında motor otomatik olarak "
                  "hisse seçip sanal alım yapacak.")

    with st.expander("📜 Sanal İşlem Geçmişi (tüm zamanlar)"):
        gecmis = sv.islem_gecmisi()
        if gecmis:
            if tiklanabilir_tablo is not None:
                tiklanabilir_tablo(pd.DataFrame(list(reversed(gecmis))), "sanal_islem_gecmisi",
                                  sembol_kolonu="sembol", ipucu=False)
            else:
                _df = pd.DataFrame(list(reversed(gecmis)))
                st.dataframe(_df, use_container_width=True, hide_index=True,
                             height=_tam_yukseklik(len(_df)))
        else:
            st.caption("Henüz hiç sanal işlem yapılmadı.")

    st.caption("⚠️ Bu bir SİMÜLASYONDUR. Geçmiş performans gelecekteki sonuçların garantisi "
              "değildir. Gerçek para ile işlem yapmadan önce bu motoru en az birkaç hafta/ay "
              "gözlemlemeniz önerilir. Yatırım tavsiyesi değildir.")
