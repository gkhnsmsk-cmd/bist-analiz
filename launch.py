#!/usr/bin/env python3
"""
launch.py
=========
BIST Intelligence Platform — Tek Tık Çalıştırıcı

Kullanım:
    python launch.py              → Web arayüzü + tüm servisler
    python launch.py --ui-only    → Sadece HTML arayüzü
    python launch.py --demo       → Demo veri ile (API gerekmez)
    python launch.py --status     → Sistem durumu kontrol

Gereksinimler:
    pip install -r requirements.txt
"""

import argparse
import os
import platform
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# ─── Renkli terminal çıktısı ──────────────────────────────────────────────────
class C:
    GRN = '\033[92m'; YLW = '\033[93m'; RED = '\033[91m'
    CYN = '\033[96m'; BLD = '\033[1m';  RST = '\033[0m'
    DIM = '\033[2m';  MAG = '\033[95m'

def pr(msg, color=C.RST):   print(f"{color}{msg}{C.RST}")
def ok(msg):                pr(f"  ✅  {msg}", C.GRN)
def warn(msg):              pr(f"  ⚠️   {msg}", C.YLW)
def err(msg):               pr(f"  ❌  {msg}", C.RED)
def info(msg):              pr(f"  ℹ️   {msg}", C.CYN)
def step(msg):              pr(f"\n{C.BLD}{'─'*50}\n  {msg}\n{'─'*50}{C.RST}")

ROOT = Path(__file__).parent
UI_FILE = ROOT / "bist_platform_ui.html"

# ─── Banner ───────────────────────────────────────────────────────────────────
BANNER = f"""{C.CYN}{C.BLD}
╔══════════════════════════════════════════════════╗
║                                                  ║
║    ██████╗ ██╗███████╗████████╗      █████╗ ██╗  ║
║    ██╔══██╗██║██╔════╝╚══██╔══╝     ██╔══██╗██║  ║
║    ██████╔╝██║███████╗   ██║        ███████║██║  ║
║    ██╔══██╗██║╚════██║   ██║        ██╔══██║██║  ║
║    ██████╔╝██║███████║   ██║███████╗██║  ██║██║  ║
║    ╚═════╝ ╚═╝╚══════╝   ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ║
║                                                  ║
║     Intelligence Platform  v1.0                  ║
║     BIST · Teknik · NLP · Whale · MTF            ║
╚══════════════════════════════════════════════════╝
{C.RST}"""


# ─── Sistem Kontrolü ──────────────────────────────────────────────────────────
def check_python():
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 9):
        err(f"Python 3.9+ gerekli. Mevcut: {v.major}.{v.minor}")
        sys.exit(1)
    ok(f"Python {v.major}.{v.minor}.{v.micro}")

def check_packages():
    required = {
        "pandas":       "pandas",
        "numpy":        "numpy",
        "aiohttp":      "aiohttp",
        "asyncpg":      "asyncpg",
        "redis":        "redis",
        "transformers": "transformers",
        "plotly":       "plotly",
        "dash":         "dash",
    }
    optional = {
        "torch": "PyTorch (NLP için önerilir)",
    }
    missing, installed = [], []
    for pkg, name in required.items():
        try:
            __import__(pkg)
            installed.append(name)
        except ImportError:
            missing.append(pkg)

    for pkg, name in optional.items():
        try:
            __import__(pkg)
            ok(f"{name} ✓")
        except ImportError:
            warn(f"{name} yüklü değil (opsiyonel)")

    if installed:
        ok(f"{len(installed)}/{len(required)} paket hazır: {', '.join(installed[:4])}{'...' if len(installed)>4 else ''}")
    if missing:
        warn(f"Eksik paketler: {', '.join(missing)}")
        warn("Yüklemek için: pip install " + " ".join(missing))
    return len(missing) == 0

def check_services():
    services = {}
    # Redis
    try:
        import socket
        s = socket.socket()
        s.settimeout(1)
        s.connect(('localhost', 6379))
        s.close()
        services['Redis'] = True
        ok("Redis bağlantısı: localhost:6379")
    except:
        services['Redis'] = False
        warn("Redis çalışmıyor → InMemory buffer kullanılacak")

    # PostgreSQL
    try:
        import socket
        s = socket.socket()
        s.settimeout(1)
        s.connect(('localhost', 5432))
        s.close()
        services['PostgreSQL'] = True
        ok("PostgreSQL bağlantısı: localhost:5432")
    except:
        services['PostgreSQL'] = False
        warn("PostgreSQL çalışmıyor → Dry-run modu aktif")

    return services

def check_env():
    env_file = ROOT / ".env"
    if env_file.exists():
        ok(".env dosyası bulundu")
    else:
        warn(".env dosyası yok — Örnek oluşturuluyor...")
        create_env_template()

def create_env_template():
    template = """# BIST Intelligence Platform — Ortam Değişkenleri
# Bu dosyayı kopyalayın: cp .env.example .env

# ── Veritabanı ──────────────────────────────
DB_DSN=postgresql://bist_user:password@localhost:5432/bist_db
REDIS_URL=redis://localhost:6379/0

# ── API Anahtarları ──────────────────────────
EODHD_API_KEY=your_eodhd_api_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# ── Sistem Ayarları ───────────────────────────
DATA_SOURCE=demo          # demo | yahoo | eodhd
TICK_INTERVAL=5           # saniye
OHLC_BUILD_INTERVAL=60    # saniye
LOG_LEVEL=INFO
MAX_WORKERS=20

# ── Strateji Ayarları ─────────────────────────
TECH_WEIGHT=0.60
NLP_WEIGHT=0.40
MIN_SIGNAL_SCORE=0.55
MIN_RR_RATIO=2.0
MAX_RISK_PER_TRADE=0.02   # portföyün %2'si
"""
    env_path = ROOT / ".env.example"
    env_path.write_text(template, encoding='utf-8')
    ok(f".env.example oluşturuldu → {env_path}")


# ─── Arayüz Açma ──────────────────────────────────────────────────────────────
def open_ui():
    if not UI_FILE.exists():
        err(f"Arayüz dosyası bulunamadı: {UI_FILE}")
        return False

    url = f"file://{UI_FILE.resolve()}"
    info(f"Arayüz açılıyor: {url}")

    try:
        webbrowser.open(url)
        ok("Tarayıcı açıldı!")
        return True
    except Exception as e:
        warn(f"Tarayıcı otomatik açılamadı: {e}")
        pr(f"\n  👉 Manuel olarak açın:", C.BLD)
        pr(f"     {url}\n", C.CYN)
        return False


# ─── Servis Başlatıcılar ──────────────────────────────────────────────────────
def start_streamer_demo():
    demo_script = ROOT / "streamer_demo.py"
    if not demo_script.exists():
        warn("streamer_demo.py bulunamadı")
        return None
    info("Data Streamer demo başlatılıyor...")
    proc = subprocess.Popen(
        [sys.executable, str(demo_script)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )
    ok(f"Data Streamer PID: {proc.pid}")
    return proc

def start_strategy_demo():
    demo_script = ROOT / "strategy_demo.py"
    if not demo_script.exists():
        warn("strategy_demo.py bulunamadı")
        return None
    info("Strateji motoru demo başlatılıyor...")
    result = subprocess.run(
        [sys.executable, str(demo_script)],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode == 0:
        ok("Strateji motoru tamamlandı")
        # Top-10'u göster
        lines = result.stdout.split('\n')
        for line in lines:
            if any(x in line for x in ['#1','#2','#3','HİSSE','═','TOP-10']):
                print(f"     {line}")
    else:
        warn(f"Strateji motoru hatası: {result.stderr[:200]}")
    return None


# ─── Status Kontrolü ──────────────────────────────────────────────────────────
def show_status():
    step("SİSTEM DURUMU")
    check_python()
    print()
    info("Paketler kontrol ediliyor...")
    check_packages()
    print()
    info("Servisler kontrol ediliyor...")
    check_services()
    print()
    info("Proje dosyaları:")
    modules = [
        ("data_ingestion/data_streamer.py", "Data Streamer"),
        ("nlp_module/sentiment_analyzer.py", "NLP Analyzer"),
        ("analysis_engine/scanner.py", "Market Scanner"),
        ("strategies/hybrid_strategy.py", "Hybrid Strategy"),
        ("strategies/scoring_engine.py", "Scoring Engine"),
        ("bist_platform_ui.html", "Web Arayüzü"),
    ]
    for path, name in modules:
        fpath = ROOT / path
        if fpath.exists():
            size = fpath.stat().st_size
            ok(f"{name:<25} ({size//1024} KB)")
        else:
            warn(f"{name:<25} — bulunamadı")


# ─── Ana Çalıştırıcı ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='BIST Intelligence Platform Launcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python launch.py                  → Tam platform (UI + demo)
  python launch.py --ui-only        → Sadece HTML arayüzü aç
  python launch.py --demo           → Demo analizleri çalıştır
  python launch.py --status         → Sistem sağlık kontrolü
  python launch.py --install        → Gereksinimleri yükle
        """
    )
    parser.add_argument('--ui-only',  action='store_true', help='Sadece web arayüzünü aç')
    parser.add_argument('--demo',     action='store_true', help='Demo analizleri çalıştır')
    parser.add_argument('--status',   action='store_true', help='Sistem durumu kontrol')
    parser.add_argument('--install',  action='store_true', help='pip install -r requirements.txt çalıştır')
    parser.add_argument('--no-browser', action='store_true', help='Tarayıcı açma')
    args = parser.parse_args()

    print(BANNER)

    if args.install:
        step("PAKET KURULUMU")
        req = ROOT / "requirements.txt"
        if req.exists():
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)])
        else:
            err("requirements.txt bulunamadı")
        return

    if args.status:
        show_status()
        return

    # ── Başlangıç kontrolleri ──────────────────────────────────────────────
    step("BAŞLANGIÇ KONTROLLERI")
    check_python()
    check_env()
    all_pkgs_ok = check_packages()
    print()
    services = check_services()

    if args.ui_only:
        step("ARAYÜZ AÇILIYOR")
        open_ui()
        pr("\n  Platform hazır! Tarayıcıdan kullanabilirsiniz.\n", C.GRN)
        return

    if args.demo:
        step("DEMO MOD")
        start_strategy_demo()
        print()

    # ── Tam başlatma ──────────────────────────────────────────────────────
    step("PLATFORM BAŞLATILIYOR")
    procs = []

    # Streamer demo (arka planda)
    if not args.demo:
        proc = start_streamer_demo()
        if proc:
            procs.append(proc)
            time.sleep(1)

    # Arayüzü aç
    if not args.no_browser:
        print()
        step("WEB ARAYÜZÜ")
        open_ui()

    # ── Özet ──────────────────────────────────────────────────────────────
    print()
    pr("═" * 52, C.DIM)
    pr(f"  {C.BLD}{C.GRN}BIST Intelligence Platform Hazır!{C.RST}")
    pr("═" * 52, C.DIM)
    pr(f"\n  📊 Dashboard    : bist_platform_ui.html (tarayıcı)", C.CYN)
    pr(f"  🤖 AI Asistan   : Arayüzde sağ altta", C.CYN)
    pr(f"  📡 Data Streamer: {'✅ Çalışıyor' if procs else '⚠️  Demo mod'}", C.GRN if procs else C.YLW)
    pr(f"  💾 Redis        : {'✅ Bağlı' if services.get('Redis') else '⚠️  InMemory'}", C.GRN if services.get('Redis') else C.YLW)
    pr(f"  🗄️  PostgreSQL  : {'✅ Bağlı' if services.get('PostgreSQL') else '⚠️  Dry-run'}", C.GRN if services.get('PostgreSQL') else C.YLW)

    if procs:
        print()
        info("Çıkmak için Ctrl+C basın...")
        try:
            while True:
                time.sleep(5)
                alive = [p for p in procs if p.poll() is None]
                if not alive:
                    warn("Tüm servisler durdu.")
                    break
        except KeyboardInterrupt:
            print()
            info("Kapatılıyor...")
            for p in procs:
                p.terminate()
            ok("Platform durduruldu.")
    else:
        print()
        ok("Arayüz bağımsız çalışıyor — kapatmak için tarayıcıyı kapatın.")
        print()


if __name__ == "__main__":
    main()
