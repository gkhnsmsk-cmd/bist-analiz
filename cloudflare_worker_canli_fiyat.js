// ═══════════════════════════════════════════════════════════════════════════
// cloudflare_worker_canli_fiyat.js — Pusula'nın hisse detay ekranında "anlık
// fiyat" gösterebilmesi için gereken KÜÇÜK ARACI FONKSİYON.
// ═══════════════════════════════════════════════════════════════════════════
// NEDEN VAR: Pusula (docs/pusula/) statik bir sayfa — kendi başına Python
// çalıştıramaz, backend'i yok. Yahoo Finance'in fiyat API'si ise tarayıcıdan
// DOĞRUDAN çağrılamıyor (CORS engelli — bu Yahoo'nun kısıtlaması, bizim
// kodumuzdan kaynaklı değil). Bu küçük fonksiyon, tarayıcı ile Yahoo Finance
// arasında bir "aracı" (proxy) görevi görür: Pusula buna sorar, o Yahoo'dan
// çekip CORS izniyle geri döner.
//
// NASIL ÇALIŞIR: https://<senin-worker-adresin>.workers.dev/?sembol=ASTOR
// gibi bir isteğe, o hissenin en son (gecikmeli olabilir — Yahoo ücretsiz
// veri genelde 15 dk gecikmelidir, "gerçek gerçek zamanlı" değildir, ama
// günde 1 kez güncellenen mevcut veriden ÇOK daha taze) fiyatını JSON olarak
// döner.
//
// KURULUM (SENİN YAPMAN GEREKEN — Claude bu adımı senin adına yapamaz,
// hesap oluşturma/onaylama gerektiriyor):
//   1) https://dash.cloudflare.com adresine git, ücretsiz bir hesap aç
//      (kredi kartı istemez).
//   2) Sol menüden "Workers & Pages" → "Create" → "Create Worker".
//   3) Worker'a bir isim ver (örn. "pusula-canli-fiyat") → "Deploy".
//   4) Deploy olunca "Edit code" (veya benzeri) butonuna tıkla, açılan
//      editördeki ÖRNEK kodu SİL, bu dosyanın TAMAMINI yapıştır → tekrar
//      "Deploy" / "Save and Deploy".
//   5) Worker sayfasında sana verilen adresi kopyala — şuna benzer:
//      https://pusula-canli-fiyat.SENIN-KULLANICI-ADIN.workers.dev
//   6) Bu adresi bana (Claude'a) gönder — pusula_mobil.html içindeki
//      CANLI_FIYAT_API_URL sabitine ben ekleyip devreye alacağım.
//
// MALİYET: Cloudflare Workers ücretsiz katmanı günde 100.000 isteğe kadar
// bedava — bu kullanım için fazlasıyla yeterli, ödeme bilgisi gerekmez.
// ═══════════════════════════════════════════════════════════════════════════

// ── Kenar (edge) önbellek: Yahoo'yu her istek için değil, sembol başına en
// fazla ~25 saniyede bir çağır. NEDEN EKLENDİ: Yahoo Finance, kimliksiz
// (auth'suz) bu uç noktaya kısa sürede çok sayıda istek gelince 429 (rate
// limit) döndürmeye başlıyor — birden fazla tarayıcı sekmesi/kullanıcı aynı
// anda 5 saniyede bir 40+ sembol için toplu istek attığında bu eşiğe çok
// hızlı ulaşılıyor. Cloudflare'ın paylaşımlı edge Cache API'si sayesinde
// AYNI sembol için farklı kullanıcılardan/sekmelerden gelen istekler tek bir
// Yahoo çağrısını paylaşır — Yahoo'ya giden toplam istek hacmi büyük ölçüde
// azalır ve 429'lar önlenir.
const ONBELLEK_SANIYE = 25;

// ── Tek sembol için Yahoo'dan çek (chart API — ücretsiz, auth gerektirmez) ──
async function tekFiyatCek(sembol) {
  const yahooUrl =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sembol)}.IS` +
    `?interval=1m&range=1d`;

  const onbellek = caches.default;
  // Cache API bir Request/Response nesnesi ister; Yahoo URL'sini anahtar
  // olarak kullanıyoruz (gerçek isteğe hiç çıkmadan önbellekten dönebiliriz).
  const onbellekIstegi = new Request(yahooUrl);
  const onbellekYaniti = await onbellek.match(onbellekIstegi);
  if (onbellekYaniti) {
    try {
      return await onbellekYaniti.json();
    } catch (e) {
      // bozuk önbellek kaydı — yok say, Yahoo'dan tazesini çek
    }
  }

  try {
    const yahooYaniti = await fetch(yahooUrl, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; PusulaBot/1.0)" },
    });
    if (!yahooYaniti.ok) return { hata: `Yahoo Finance ${yahooYaniti.status} döndü` };
    const veri = await yahooYaniti.json();
    const sonuc = veri?.chart?.result?.[0];
    if (!sonuc || !sonuc.meta) return { hata: "Bu sembol için veri bulunamadı" };
    const meta = sonuc.meta;
    const sonucNesnesi = {
      fiyat: meta.regularMarketPrice ?? null,
      oncekiKapanis: meta.chartPreviousClose ?? meta.previousClose ?? null,
      zaman: meta.regularMarketTime
        ? new Date(meta.regularMarketTime * 1000).toISOString()
        : null,
      piyasaDurumu: meta.marketState || null, // "REGULAR" / "CLOSED" / "PRE" / "POST"
    };

    // Sadece BAŞARILI sonuçları önbelleğe al (hatalı/429 yanıtları önbelleğe
    // alırsak, geçici bir hatayı ONBELLEK_SANIYE boyunca donduruk kalırız).
    if (sonucNesnesi.fiyat != null) {
      const yaniti = new Response(JSON.stringify(sonucNesnesi), {
        headers: { "Content-Type": "application/json", "Cache-Control": `max-age=${ONBELLEK_SANIYE}` },
      });
      // Worker'ı erken bitirmemesi için bekletmeden arka planda yaz.
      onbellek.put(onbellekIstegi, yaniti.clone());
    }
    return sonucNesnesi;
  } catch (e) {
    return { hata: `Aracı fonksiyon hatası: ${e.message || e}` };
  }
}

// Cloudflare Workers ücretsiz katmanda TEK bir istekte en fazla 50 "alt
// istek" (subrequest) atılabilir — bu yüzden toplu (batch) modda sembol
// sayısı bu sınırın altında tutulmalı. Liste ekranları (Favoriler,
// Yükselecek Hisseler, Portföy) zaten 40'ı geçmiyor; güvenlik payı için
// burada da sert bir tavan var.
const MAKS_TOPLU_SEMBOL = 45;

// ── GRAFİK MODU: hisse detay ekranındaki "Anlık / 1 Hafta / 1 Ay / 3 Ay /
// 1 Yıl" çipleri için — kullanıcı isteği: "kullanıcı basınca ilgili detaylı
// grafikleri kolayca tarayabilsin". Yahoo'nun chart uç noktası zaten
// dönem+aralık (range/interval) parametrelerini destekliyor; biz sadece
// Pusula'nın Türkçe dönem adlarını Yahoo'nun beklediği değerlere eşliyoruz.
const DONEM_ESLESTIRME = {
  anlik:  { range: "1d",  interval: "5m"  },
  hafta:  { range: "5d",  interval: "60m" },
  ay:     { range: "1mo", interval: "1d"  },
  uc_ay:  { range: "3mo", interval: "1d"  },
  yil:    { range: "1y",  interval: "1wk" },
};

async function grafikVeriCek(sembol, donem) {
  const esleme = DONEM_ESLESTIRME[donem];
  if (!esleme) return { hata: "geçersiz dönem" };
  const yahooUrl =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sembol)}.IS` +
    `?interval=${esleme.interval}&range=${esleme.range}`;

  const onbellek = caches.default;
  const onbellekIstegi = new Request(yahooUrl);
  const onbellekYaniti = await onbellek.match(onbellekIstegi);
  if (onbellekYaniti) {
    try { return await onbellekYaniti.json(); } catch (e) { /* bozuk kayıt — tazesini çek */ }
  }

  try {
    const yahooYaniti = await fetch(yahooUrl, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; PusulaBot/1.0)" },
    });
    if (!yahooYaniti.ok) return { hata: `Yahoo Finance ${yahooYaniti.status} döndü` };
    const veri = await yahooYaniti.json();
    const sonuc = veri?.chart?.result?.[0];
    if (!sonuc || !sonuc.meta) return { hata: "Bu sembol/dönem için veri bulunamadı" };
    const zamanlar = sonuc.timestamp || [];
    const kapanislar = sonuc.indicators?.quote?.[0]?.close || [];
    // Yahoo bazı barlarda null döndürebilir (piyasa kapalıyken vb.) — bunları ele.
    const noktalar = [];
    for (let i = 0; i < zamanlar.length; i++) {
      const k = kapanislar[i];
      if (k != null) noktalar.push({ t: zamanlar[i], f: Math.round(k * 100) / 100 });
    }
    const sonucNesnesi = {
      sembol, donem,
      noktalar,
      guncelFiyat: sonuc.meta.regularMarketPrice ?? null,
    };
    if (noktalar.length > 1) {
      const yaniti = new Response(JSON.stringify(sonucNesnesi), {
        headers: { "Content-Type": "application/json", "Cache-Control": `max-age=${ONBELLEK_SANIYE * 4}` },
      });
      onbellek.put(onbellekIstegi, yaniti.clone());
    }
    return sonucNesnesi;
  } catch (e) {
    return { hata: `Aracı fonksiyon hatası: ${e.message || e}` };
  }
}

// ═════════════════════════════════════════════════════════════════════════
// SANAL PORTFÖY SIFIRLAMA — uygulama içi buton (Task #10, 28.08.2026)
// ═════════════════════════════════════════════════════════════════════════
// NEDEN BURADA: Pusula statik bir sayfa — kendi başına GitHub Actions'ı
// tetikleyemez, bunun için bir GitHub PAT (Actions: write) gerekir ve bu PAT
// ASLA tarayıcı koduna gömülemez (herkes görebilir, kötüye kullanabilir).
// Worker bu PAT'i SUNUCU TARAFINDA (Cloudflare secret) tutar; tarayıcı sadece
// kullanıcının kendi belirlediği bir ANAHTAR (passphrase) gönderir — bu da
// ayrı bir Cloudflare secret'la karşılaştırılır. İki secret de env üzerinden
// gelir, KODDA YAZILI DEĞİLDİR:
//   wrangler secret put SIFIRLA_ANAHTARI      (kullanıcının kendi seçtiği parola)
//   wrangler secret put GITHUB_ACTIONS_PAT    (Actions: write izinli fine-grained PAT)
// Bu iki secret ayarlanmadan bu uç nokta HER ZAMAN 501 döner — yanlışlıkla
// açık bırakılmış bir "herkes tetikleyebilir" uç noktası olmaz.
async function sanalPortfoySifirla(request, env) {
  if (!env.SIFIRLA_ANAHTARI || !env.GITHUB_ACTIONS_PAT) {
    return jsonYanit({ hata: "Sıfırlama uç noktası henüz kurulmadı (secret eksik)." }, 501);
  }
  let govde;
  try {
    govde = await request.json();
  } catch {
    return jsonYanit({ hata: "Geçersiz istek gövdesi (JSON bekleniyor)." }, 400);
  }
  if (!govde || govde.anahtar !== env.SIFIRLA_ANAHTARI) {
    return jsonYanit({ hata: "Anahtar yanlış." }, 403);
  }
  try {
    const yanit = await fetch(
      "https://api.github.com/repos/gkhnsmsk-cmd/bist-analiz/actions/workflows/sanal_portfoy_sifirla.yml/dispatches",
      {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GITHUB_ACTIONS_PAT}`,
          "Accept": "application/vnd.github+json",
          "User-Agent": "pusula-sifirla-worker",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main", inputs: { confirm: "SIFIRLA" } }),
      }
    );
    if (yanit.status === 204) {
      return jsonYanit({ tamam: true, mesaj: "Sıfırlama tetiklendi — birkaç dakika içinde tamamlanır." });
    }
    const metin = await yanit.text();
    return jsonYanit({ hata: `GitHub API hatası (${yanit.status}): ${metin.slice(0, 300)}` }, 502);
  } catch (e) {
    return jsonYanit({ hata: `İstek başarısız: ${e.message || e}` }, 502);
  }
}

export default {
  async fetch(request, env) {
    // Tarayıcılar bazı isteklerden önce bir "izin var mı?" (preflight/OPTIONS)
    // sorusu sorar — buna da CORS başlıklarıyla cevap vermemiz gerekir.
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsBasliklari() });
    }

    const url = new URL(request.url);

    if (url.pathname === "/sifirla" && request.method === "POST") {
      return sanalPortfoySifirla(request, env);
    }

    // TOPLU MOD — liste ekranlarında (Favoriler, Yükselecek Hisseler,
    // Portföy) her satırın anlık fiyatını TEK istekte çekmek için eklendi
    // (kullanıcı isteği: "sadece tıklayınca değil, listede de yanıp
    // sönmeli"). ?semboller=ASTOR,THYAO,PGSUS gibi virgülle ayrılmış liste.
    const topluParam = url.searchParams.get("semboller");
    if (topluParam) {
      const semboller = [...new Set(
        topluParam.split(",").map(s => s.trim().toUpperCase()).filter(Boolean)
      )].slice(0, MAKS_TOPLU_SEMBOL);
      if (semboller.length === 0) {
        return jsonYanit({ hata: "semboller parametresi boş" }, 400);
      }
      const sonuclar = await Promise.all(semboller.map(async s => [s, await tekFiyatCek(s)]));
      const fiyatlar = {};
      for (const [s, r] of sonuclar) fiyatlar[s] = r;
      return jsonYanit({
        zaman: new Date().toISOString(),
        gecikmeNotu: "Yahoo Finance ücretsiz veri, genelde 15 dk'ya kadar gecikmeli olabilir.",
        fiyatlar,
      });
    }

    // GRAFİK MODU — hisse detay ekranındaki dönem çipleri için —
    // ?sembol=ASTOR&grafik=hafta (anlik | hafta | ay | uc_ay | yil)
    const grafikDonem = url.searchParams.get("grafik");
    if (grafikDonem) {
      const gSembol = (url.searchParams.get("sembol") || "").trim().toUpperCase();
      if (!gSembol) return jsonYanit({ hata: "sembol parametresi gerekli" }, 400);
      const g = await grafikVeriCek(gSembol, grafikDonem);
      if (g.hata) return jsonYanit({ hata: g.hata, sembol: gSembol }, 502);
      return jsonYanit(g);
    }

    // TEKLİ MOD (eski davranış, geriye dönük uyumluluk — hisse detay ekranı
    // hâlâ bunu kullanıyor) — ?sembol=ASTOR
    const sembol = (url.searchParams.get("sembol") || "").trim().toUpperCase();
    if (!sembol) {
      return jsonYanit({
        hata: "sembol (tekli) veya semboller (toplu, virgüllü) parametresi gerekli",
      }, 400);
    }
    const r = await tekFiyatCek(sembol);
    if (r.hata) return jsonYanit({ hata: r.hata, sembol }, r.hata.includes("bulunamadı") ? 404 : 502);
    return jsonYanit({
      sembol,
      ...r,
      gecikmeNotu: "Yahoo Finance ücretsiz veri, genelde 15 dk'ya kadar gecikmeli olabilir.",
    });
  },
};

function corsBasliklari() {
  return {
    // NOT: İstersen bunu sadece Pusula'nın adresine kısıtlayabilirsin
    // (Access-Control-Allow-Origin: "https://gkhnsmsk-cmd.github.io"),
    // ama "*" başkasının da bu ücretsiz aracıyı kullanabileceği anlamına
    // gelir (zararsız — sadece halka açık fiyat verisi döndürüyor).
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Cache-Control": "no-store",
  };
}

function jsonYanit(obj, durum = 200) {
  return new Response(JSON.stringify(obj), {
    status: durum,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsBasliklari() },
  });
}
