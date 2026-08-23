# -*- coding: utf-8 -*-
"""
llm_ajanlari.py — Opsiyonel LLM Konsensüs Katmanı
══════════════════════════════════════════════════
Bu modül TAMAMEN OPSİYONELDİR. Mevcut ücretsiz analiz motoru (analiz_motoru.py)
her zaman ana karar vericidir ve API anahtarı olmadan da tam çalışır.

Bir LLM'i devreye almak için proje klasöründe bir ".env" dosyası oluşturup
ilgili satırı doldurmanız yeterlidir (örnek için .env.example dosyasına bakın):

    GROQ_API_KEY=gsk_...         (Groq — Llama modelleri, ücretsiz kotalı)
    NVIDIA_API_KEY=nvapi-...     (NVIDIA NIM — 100+ model, ücretsiz kotalı)
    OPENAI_API_KEY=sk-...        (ChatGPT)
    ANTHROPIC_API_KEY=sk-ant-... (Claude)
    XAI_API_KEY=xai-...          (Grok/xAI)
    DEEPSEEK_API_KEY=sk-...      (DeepSeek)

Anahtarı girilmeyen ajan otomatik olarak atlanır — hiçbir hata vermez.

ÜCRETSİZ İKİ SEÇENEK (kredi kartı gerekmez):
  • Groq    — console.groq.com/keys  → çok hızlı, sohbet için birincil tercih
  • NVIDIA  — build.nvidia.com       → 100+ model, ~40 istek/dk, OpenAI uyumlu

Diğer ajanların her çağrısı ÜCRETLİDİR ve maliyeti tamamen size (girdiğiniz
anahtarın sahibine) aittir.

OTOMATİK SAĞLAYICI ZİNCİRİ (bkz. sohbet_tamamla):
Sohbet asistanı hangi anahtarların girildiğine kendisi bakar ve sırayla dener:
Groq → NVIDIA → OpenAI → DeepSeek → xAI. Biri kota dolu (429) ya da hatalı
olursa sessizce bir sonrakine geçer; kullanıcı hiçbir ayar yapmaz.
"""
from __future__ import annotations

import os

import requests

_ENV_YUKLENDI = False


def _env_yukle():
    """.env dosyasını basitçe okuyup ortam değişkenlerine yükler.
    Harici bağımlılık (python-dotenv) gerektirmez — kurulum sade kalsın diye."""
    global _ENV_YUKLENDI
    if _ENV_YUKLENDI:
        return
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(yol):
        for satir in open(yol, encoding="utf-8"):
            satir = satir.strip()
            if not satir or satir.startswith("#") or "=" not in satir:
                continue
            k, v = satir.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v:
                os.environ.setdefault(k, v)
    _ENV_YUKLENDI = True


def _anahtar(ad: str) -> str:
    """API anahtarını üç yerden sırayla arar:
    1) ortam değişkeni (zaten ayarlanmışsa — ör. GitHub Actions "secrets")
    2) yerel .env dosyası (bilgisayarda çalışırken)
    3) Streamlit Cloud'un "Secrets" yöneticisi (bulutta çalışırken; .env
       dosyası GÜVENLİK nedeniyle depoya YÜKLENMEDİĞİ için buluta hiç
       gitmez — anahtarları oraya Streamlit Cloud panelinden ayrıca
       girmek gerekir, bkz. STREAMLIT_CLOUD_KURULUM.md).
    Hiçbiri yoksa boş döner; LLM ajanları o zaman sessizce devre dışı kalır,
    uygulama çökmez."""
    _env_yukle()
    deger = os.environ.get(ad, "").strip()
    if deger:
        return deger
    try:
        import streamlit as st
        return str(st.secrets.get(ad, "")).strip()
    except Exception:
        return ""


def aktif_ajan_durumu() -> dict:
    """Hangi LLM ajanlarının anahtarı girilmiş (aktif) olduğunu döner."""
    return {
        "Groq (Llama, ücretsiz kotalı)": bool(_anahtar("GROQ_API_KEY")),
        "NVIDIA NIM (ücretsiz kotalı)": bool(_anahtar("NVIDIA_API_KEY")),
        "ChatGPT (OpenAI)": bool(_anahtar("OPENAI_API_KEY")),
        "Claude (Anthropic)": bool(_anahtar("ANTHROPIC_API_KEY")),
        "Grok (xAI)": bool(_anahtar("XAI_API_KEY")),
        "DeepSeek": bool(_anahtar("DEEPSEEK_API_KEY")),
    }


# ═════════════════════════════════════════════════════════════════════════════
# SOHBET KATMANI — sohbet asistanı (sohbet_ajani.py) tarafından kullanılır
# ═════════════════════════════════════════════════════════════════════════════
# Yukarıdaki _*_sor() fonksiyonları TEK SORULUK, kısa cevaplı konsensüs
# çağrıları içindir. Sohbet asistanı ise ÇOK TURLU (geçmişi olan) bir konuşma
# yürütür ve daha uzun yanıt ister. Bu yüzden ayrı bir katman var.
#
# TASARIM: Sağlayıcılar bir ZİNCİR halinde denenir. Amaç, kullanıcının hiçbir
# ayar yapmak zorunda kalmaması: hangi anahtar varsa o kullanılır, kota dolarsa
# (HTTP 429) veya sağlayıcı hata verirse otomatik olarak bir sonrakine geçilir.
# Sıra bilinçlidir:
#   1) Groq   — en hızlı yanıt (sohbette gecikme en çok rahatsız eden şeydir)
#   2) NVIDIA — ücretsiz, güçlü modeller; Groq kotası dolduğunda devreye girer
#   3) OpenAI / DeepSeek / xAI — ücretli, sadece anahtar girilmişse

# (görünen_ad, anahtar_adı, url, model)
_SOHBET_ZINCIRI = [
    ("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions",
     "llama-3.3-70b-versatile"),
    ("NVIDIA", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1/chat/completions",
     "meta/llama-3.3-70b-instruct"),
    ("OpenAI", "OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions",
     "gpt-4o-mini"),
    ("DeepSeek", "DEEPSEEK_API_KEY", "https://api.deepseek.com/chat/completions",
     "deepseek-chat"),
    ("xAI", "XAI_API_KEY", "https://api.x.ai/v1/chat/completions",
     "grok-2-latest"),
]


def sohbet_saglayicilari() -> list:
    """Anahtarı girilmiş, yani şu an KULLANILABİLİR sağlayıcıların adları."""
    return [ad for ad, key_ad, _, _ in _SOHBET_ZINCIRI if _anahtar(key_ad)]


def sohbet_hazir_mi() -> bool:
    return bool(sohbet_saglayicilari())


def _nvidia_model_sec(key: str) -> str | None:
    """NVIDIA'nın model kataloğunu OTOMATİK okuyup uygun bir sohbet modeli seçer.

    NEDEN VAR: NVIDIA kataloğunda 100+ model var ve isimleri zaman zaman
    değişiyor/yenileri ekleniyor. Model adını koda sabitlemek, model
    kullanımdan kalkınca sohbetin sessizce bozulması demek. Burada
    /v1/models ucundan güncel liste çekilir ve tercih sırasına göre ilk
    uyan seçilir. Liste alınamazsa None döner; çağıran taraf sabit
    varsayılana düşer.
    """
    try:
        r = requests.get("https://integrate.api.nvidia.com/v1/models",
                         headers={"Authorization": f"Bearer {key}"}, timeout=15)
        r.raise_for_status()
        adlar = [m.get("id", "") for m in r.json().get("data", [])]
    except Exception:
        return None
    if not adlar:
        return None
    # Tercih sırası: talimat takibi güçlü, makul boyutlu, yaygın modeller.
    for kalip in ("llama-3.3-70b-instruct", "llama-3.1-70b-instruct",
                  "qwen2.5-72b-instruct", "nemotron", "mixtral-8x7b-instruct"):
        for ad in adlar:
            if kalip in ad.lower():
                return ad
    # Hiçbiri yoksa: adında "instruct" geçen ilk model (sohbete uygun olan tip)
    for ad in adlar:
        if "instruct" in ad.lower():
            return ad
    return adlar[0]


_NVIDIA_MODEL_ONBELLEK = {}


def sohbet_tamamla(mesajlar: list, max_tokens: int = 1200,
                    sicaklik: float = 0.3) -> tuple:
    """Çok turlu sohbet tamamlaması. Sağlayıcı zincirini otomatik dener.

    mesajlar: [{"role": "system"|"user"|"assistant", "content": "..."}]
    Dönüş: (yanit_metni, kullanilan_saglayici) — hiçbiri çalışmazsa
           (None, hata_metni).

    Hiçbir çağrı istisna FIRLATMAZ; sohbet paneli çökmesin diye tüm hatalar
    yakalanır ve bir sonraki sağlayıcı denenir.
    """
    hatalar = []
    for ad, key_ad, url, varsayilan_model in _SOHBET_ZINCIRI:
        key = _anahtar(key_ad)
        if not key:
            continue

        model = varsayilan_model
        if ad == "NVIDIA":
            # Model adını bir kez otomatik çöz, sonra oturum boyunca sakla.
            if key not in _NVIDIA_MODEL_ONBELLEK:
                _NVIDIA_MODEL_ONBELLEK[key] = _nvidia_model_sec(key) or varsayilan_model
            model = _NVIDIA_MODEL_ONBELLEK[key]

        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={"model": model, "messages": mesajlar,
                      "max_tokens": max_tokens, "temperature": sicaklik},
                timeout=60)
            if r.status_code == 429:
                # Kota doldu — bu sağlayıcıda beklemek yerine bir sonrakine geç.
                hatalar.append(f"{ad}: kota doldu (429)")
                continue
            r.raise_for_status()
            icerik = r.json()["choices"][0]["message"]["content"]
            if icerik and icerik.strip():
                return icerik.strip(), ad
            hatalar.append(f"{ad}: boş yanıt")
        except Exception as e:
            hatalar.append(f"{ad}: {e}")

    if not hatalar:
        return None, ("Hiçbir yapay zeka anahtarı tanımlı değil. .env dosyasına "
                      "GROQ_API_KEY veya NVIDIA_API_KEY ekleyin.")
    return None, "Tüm sağlayıcılar başarısız — " + " | ".join(hatalar[:3])


def herhangi_biri_aktif() -> bool:
    return any(aktif_ajan_durumu().values())


def _prompt_olustur(analiz: dict, detayli: bool = False) -> str:
    puanlar = ", ".join(f"{k}: {v}" for k, v in analiz.get("puanlar", {}).items())
    talimat = (
        "Yanıtının İLK KELİMESİ olarak sadece şunlardan birini yaz: AL, SAT veya TUT. "
        + ("Ardından 2-4 cümlelik kısa bir muhakeme yaz: bu puanlara göre neden bu kararı "
           "verdiğini, hangi vade puanının belirleyici olduğunu açıkla."
           if detayli else "Ardından tek cümlelik kısa gerekçe ekle.")
        + " Bu yatırım tavsiyesi değildir, sadece bir analiz katkısı olarak değerlendirilecektir."
    )
    return (
        f"Hisse: {analiz['sembol']} (Borsa İstanbul)\n"
        f"Son fiyat: {analiz['son_fiyat']} TL\n"
        f"Kantitatif motorun genel puanı (0-100, 100=en güçlü AL): {analiz['genel_puan']}\n"
        f"Motorun kararı: {analiz['karar']}\n"
        f"Vade bazlı puanlar: {puanlar}\n\n{talimat}"
    )


def _yon_cikar(metin: str) -> str:
    if not metin:
        return "TUT"
    ust = metin.strip().upper()
    for aday in ("AL", "SAT", "TUT"):
        if ust.startswith(aday):
            return aday
    if "SAT" in ust[:40]:
        return "SAT"
    if ust[:40].count("AL") > 0 and "SAT" not in ust[:40]:
        return "AL"
    return "TUT"


def _openai_uyumlu_sor(url: str, key_ad: str, model: str, prompt: str, max_tokens: int):
    key = _anahtar(key_ad)
    if not key:
        return None
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                 "max_tokens": max_tokens},
            timeout=25)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[HATA: {e}]"


def _groq_sor(prompt: str, max_tokens: int = 300):
    return _openai_uyumlu_sor("https://api.groq.com/openai/v1/chat/completions",
                              "GROQ_API_KEY", "llama-3.3-70b-versatile", prompt, max_tokens)


def _openai_sor(prompt: str, max_tokens: int = 300):
    return _openai_uyumlu_sor("https://api.openai.com/v1/chat/completions",
                              "OPENAI_API_KEY", "gpt-4o-mini", prompt, max_tokens)


def _xai_sor(prompt: str, max_tokens: int = 300):
    return _openai_uyumlu_sor("https://api.x.ai/v1/chat/completions",
                              "XAI_API_KEY", "grok-2-latest", prompt, max_tokens)


def _deepseek_sor(prompt: str, max_tokens: int = 300):
    return _openai_uyumlu_sor("https://api.deepseek.com/chat/completions",
                              "DEEPSEEK_API_KEY", "deepseek-chat", prompt, max_tokens)


def _anthropic_sor(prompt: str, max_tokens: int = 300):
    key = _anahtar("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={"model": "claude-3-5-haiku-20241022", "max_tokens": max_tokens,
                 "messages": [{"role": "user", "content": prompt}]},
            timeout=25)
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    except Exception as e:
        return f"[HATA: {e}]"


_AJANLAR = {
    "Groq (Llama, ücretsiz kotalı)": _groq_sor,
    "ChatGPT (OpenAI)": _openai_sor,
    "Claude (Anthropic)": _anthropic_sor,
    "Grok (xAI)": _xai_sor,
    "DeepSeek": _deepseek_sor,
}


def konsensus_al(analiz: dict, detayli: bool = False) -> dict | None:
    """Aktif LLM ajanlarına hisseyi sorar ve oylarını toplar.
    detayli=True ise ajanlardan kısa gerekçe yerine 2-4 cümlelik muhakeme istenir
    (Agent Modu / detaylı analiz için).
    Hiçbir anahtar girilmemişse None döner — motor kararı tek başına kullanılır."""
    if not herhangi_biri_aktif():
        return None

    prompt = _prompt_olustur(analiz, detayli=detayli)
    max_tokens = 300 if detayli else 120
    detay = {}
    for ad, fn in _AJANLAR.items():
        cevap = fn(prompt, max_tokens)
        if cevap is not None:
            detay[ad] = {"cevap": cevap, "yon": _yon_cikar(cevap)}

    if not detay:
        return None

    yonler = [v["yon"] for v in detay.values()]
    oy = {"AL": yonler.count("AL"), "SAT": yonler.count("SAT"), "TUT": yonler.count("TUT")}
    if oy["AL"] > oy["SAT"] and oy["AL"] >= oy["TUT"]:
        konsensus = "AL"
    elif oy["SAT"] > oy["AL"] and oy["SAT"] >= oy["TUT"]:
        konsensus = "SAT"
    else:
        konsensus = "TUT"

    return {"detay": detay, "konsensus": konsensus, "oy": oy}


# ─────────────────────────────────────────────────────────────────────────────
# Portföy Yönetici Özeti (Executive Summary)
# ─────────────────────────────────────────────────────────────────────────────
def yonetici_ozeti(portfoy_ozeti: dict, oneriler: list) -> str | None:
    """Aktif olan İLK LLM ajanına (öncelik sırası: Groq → ChatGPT → Claude →
    Grok → DeepSeek) portföyün sayısal özetini ve motorun ürettiği AL/SAT/TAKAS
    önerilerini vererek 2-3 cümlelik kurumsal bir yönetici özeti hazırlatır.
    Bu bir konsensüs değil, tek bir özetleme çağrısıdır. Hiçbir ajan aktif
    değilse None döner — arayüz bu durumda özet bölümünü göstermez."""
    if not herhangi_biri_aktif():
        return None

    oneri_metni = "\n".join(f"- {o['mesaj']}" for o in oneriler)
    prompt = (
        "Aşağıda bir yatırımcının portföy özeti ve kantitatif bir analiz motorunun "
        "ürettiği aksiyon önerileri var. Bunu, dışarıdan bakan kurumsal bir gözlemci/"
        "denetçi üslubuyla, profesyonel ve nesnel bir dille 2-3 cümlelik bir "
        "'Yönetici Özeti' (Executive Summary) haline getir. Sayısal verilere sadık kal, "
        "abartılı ifade kullanma. Bu yatırım tavsiyesi değildir, bir analiz katkısıdır.\n\n"
        f"Toplam maliyet: {portfoy_ozeti.get('toplam_maliyet', 0):,.0f} TL\n"
        f"Güncel değer: {portfoy_ozeti.get('toplam_deger', 0):,.0f} TL\n"
        f"Toplam kâr/zarar: {portfoy_ozeti.get('toplam_kar_zarar', 0):+,.0f} TL "
        f"(%{portfoy_ozeti.get('toplam_kar_zarar_yuzde', 0):+.2f})\n\n"
        f"Motorun aksiyon önerileri:\n{oneri_metni}"
    )

    for ad, fn in _AJANLAR.items():
        cevap = fn(prompt, 260)
        if cevap and not cevap.startswith("[HATA"):
            return cevap.strip()
    return None
