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

// ── Tek sembol için Yahoo'dan çek (chart API — ücretsiz, auth gerektirmez) ──
async function tekFiyatCek(sembol) {
  const yahooUrl =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sembol)}.IS` +
    `?interval=1m&range=1d`;
  try {
    const yahooYaniti = await fetch(yahooUrl, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; PusulaBot/1.0)" },
    });
    if (!yahooYaniti.ok) return { hata: `Yahoo Finance ${yahooYaniti.status} döndü` };
    const veri = await yahooYaniti.json();
    const sonuc = veri?.chart?.result?.[0];
    if (!sonuc || !sonuc.meta) return { hata: "Bu sembol için veri bulunamadı" };
    const meta = sonuc.meta;
    return {
      fiyat: meta.regularMarketPrice ?? null,
      oncekiKapanis: meta.chartPreviousClose ?? meta.previousClose ?? null,
      zaman: meta.regularMarketTime
        ? new Date(meta.regularMarketTime * 1000).toISOString()
        : null,
      piyasaDurumu: meta.marketState || null, // "REGULAR" / "CLOSED" / "PRE" / "POST"
    };
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

export default {
  async fetch(request) {
    // Tarayıcılar bazı isteklerden önce bir "izin var mı?" (preflight/OPTIONS)
    // sorusu sorar — buna da CORS başlıklarıyla cevap vermemiz gerekir.
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsBasliklari() });
    }

    const url = new URL(request.url);

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
    "Access-Control-Allow-Methods": "GET, OPTIONS",
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
