# -*- coding: utf-8 -*-
"""
sanal_portfoy_sifirla_cli.py — Sanal Portföy'ü baştan başlatan komut satırı
aracı.
══════════════════════════════════════════════════════════════════════════
NEDEN VAR: Kullanıcı isteği — "sanal portföyü yazılım kendisi programlanmalı,
kullanıcı sadece genel olarak sıfırlayabilmeli; başka müdahale alanı değil,
yazılım burada özgür (ne alıp satacağına, ne zaman nakde geçeceğine kendisi
karar verir)." Yani kullanıcının BURADAKİ tek meşru kontrolü "baştan başlat"
düğmesidir — pozisyon ekleme/çıkarma/manuel al-sat YOKTUR (o kontrol zaten
ayrı olan "Portföyüm" bölümünde var).

NASIL ÇALIŞIR: sanal_yatirimci.sifirla() fonksiyonunu çağırır — bu, mevcut
sanal_portfoy.json / sanal_islem_gecmisi.json / sanal_deger_gecmisi.json
dosyalarını SİLER ve VARSAYILAN_BUTCE (1.000.000 ₺) ile sıfırdan, pozisyonsuz
bir portföy kurar. GERİ ALINAMAZ.

NASIL TETİKLENİR: Pusula statik bir sayfa olduğu için tarayıcıdan doğrudan
çalıştırılamaz. Bunun yerine GitHub Actions'taki "Sanal Portföy Sıfırlama"
iş akışı (.github/workflows/sanal_portfoy_sifirla.yml) elle (workflow_dispatch)
tetiklenir — GitHub'a giriş gerektirdiği için sadece depo sahibi (SEN)
çalıştırabilir, Pusula'yı gezen başka biri bunu tetikleyemez.
"""
from __future__ import annotations

import sys

import sanal_yatirimci as sy


def main() -> None:
    onceki = sy._oku(sy.SANAL_PORTFOY_DOSYASI, None)
    if onceki:
        print(f"Önceki durum: nakit={onceki.get('nakit'):.2f} ₺, "
              f"{len(onceki.get('pozisyonlar', []))} pozisyon, "
              f"başlangıç tarihi={onceki.get('baslangic_tarihi')}")
    else:
        print("Önceki bir sanal portföy bulunamadı (ilk kurulum olacak).")

    yeni = sy.sifirla()
    print(f"Sıfırlandı → nakit={yeni['nakit']:.2f} ₺, "
          f"pozisyon=0, başlangıç tarihi={yeni['baslangic_tarihi']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
