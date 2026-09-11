# -*- coding: utf-8 -*-
"""
favoriler.py — kullanıcının izleme listesi / favori hisseleri (basit JSON deposu).
Kod ezberleme derdini "hisse_adlari.py" arama ile çözdük; bu modül de sık
bakılan hisseleri her seferinde yeniden aramak zorunda kalmadan üstte
tutmak için var (TradingView'deki "Watchlist" paneli gibi).
"""
from __future__ import annotations

import json
import os

KLASOR = os.path.dirname(os.path.abspath(__file__))
DOSYA = os.path.join(KLASOR, "favoriler.json")


def getir() -> list:
    if not os.path.exists(DOSYA):
        return []
    try:
        with open(DOSYA, encoding="utf-8") as f:
            veri = json.load(f)
        return veri if isinstance(veri, list) else []
    except Exception:
        return []


def _yaz(liste: list):
    with open(DOSYA, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=2)


def ekle(sembol: str) -> list:
    sembol = (sembol or "").strip().upper().replace(".IS", "")
    liste = getir()
    if sembol and sembol not in liste:
        liste.append(sembol)
        _yaz(liste)
    return liste


def cikar(sembol: str) -> list:
    sembol = (sembol or "").strip().upper()
    liste = [s for s in getir() if s != sembol]
    _yaz(liste)
    return liste
