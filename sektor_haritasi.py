# -*- coding: utf-8 -*-
"""
sektor_haritasi.py — BIST hisse → sektör eşlemesi.
════════════════════════════════════════════════════
KAPSAM UYARISI: Bu, BIST100/BIST30'daki likit ve büyük şirketleri kapsayan
KISMİ (elle derlenmiş) bir eşlemedir; resmi/lisanslı bir GICS/BIST sektör
sınıflandırma servisi DEĞİLDİR. Haritada bulunmayan hisseler "Diğer /
Sınıflandırılmamış" olarak işaretlenir ve sektörel yoğunlaşma hesabına
"bilinmeyen" grubu olarak dahil edilir. Kurumsal karar almadan önce hissenin
gerçek sektör sınıflandırmasını KAP/şirket faaliyet raporundan teyit edin.
"""

SEKTOR_HARITASI = {
    # Bankacılık
    "AKBNK": "Bankacılık", "GARAN": "Bankacılık", "ISCTR": "Bankacılık",
    "YKBNK": "Bankacılık", "VAKBN": "Bankacılık", "HALKB": "Bankacılık",
    "SKBNK": "Bankacılık", "ICBCT": "Bankacılık", "QNBTR": "Bankacılık",
    "TSKB": "Bankacılık", "ALBRK": "Bankacılık",
    # Holding
    "KCHOL": "Holding", "SAHOL": "Holding", "DOHOL": "Holding", "AGHOL": "Holding",
    "TKFEN": "Holding", "ALARK": "Holding", "GLYHO": "Holding", "GSDHO": "Holding",
    "SISE": "Holding / Cam", "ENKAI": "Holding",
    # Havacılık / Ulaştırma
    "THYAO": "Havacılık/Ulaştırma", "PGSUS": "Havacılık/Ulaştırma", "TAVHL": "Havacılık/Ulaştırma",
    "CLEBI": "Havacılık/Ulaştırma", "DOCO": "Havacılık/Ulaştırma",
    # Otomotiv
    "TOASO": "Otomotiv", "FROTO": "Otomotiv", "DOAS": "Otomotiv", "OTKAR": "Otomotiv",
    "ASUZU": "Otomotiv", "KARSN": "Otomotiv", "TTRAK": "Otomotiv",
    # Demir-Çelik / Metal
    "EREGL": "Demir-Çelik/Metal", "KRDMD": "Demir-Çelik/Metal", "KRDMA": "Demir-Çelik/Metal",
    "KRDMB": "Demir-Çelik/Metal", "ISDMR": "Demir-Çelik/Metal", "BRSAN": "Demir-Çelik/Metal",
    # Enerji
    "TUPRS": "Enerji", "AKSEN": "Enerji", "AYGAZ": "Enerji", "ENJSA": "Enerji",
    "ZOREN": "Enerji", "ODAS": "Enerji", "GWIND": "Enerji", "CWENE": "Enerji",
    "AKFYE": "Enerji", "NTGAZ": "Enerji",
    # Perakende / Gıda
    "BIMAS": "Perakende", "MGROS": "Perakende", "SOKM": "Perakende", "VAKKO": "Perakende",
    "CCOLA": "Gıda-İçecek", "ULKER": "Gıda-İçecek", "AEFES": "Gıda-İçecek",
    "TATGD": "Gıda-İçecek", "BANVT": "Gıda-İçecek", "PETUN": "Gıda-İçecek",
    # Telekom / Teknoloji
    "TCELL": "Telekom", "TTKOM": "Telekom", "LOGO": "Teknoloji", "NETAS": "Teknoloji",
    "ASELS": "Savunma/Teknoloji", "KAREL": "Teknoloji", "LINK": "Teknoloji",
    # Sigorta
    "AKGRT": "Sigorta", "ANHYT": "Sigorta", "ANSGR": "Sigorta", "AGESA": "Sigorta",
    "TURSG": "Sigorta", "RAYSG": "Sigorta",
    # GYO (Gayrimenkul Yatırım Ortaklığı)
    "EKGYO": "GYO", "ISGYO": "GYO", "TRGYO": "GYO", "SNGYO": "GYO", "AKMGY": "GYO",
    "OZKGY": "GYO", "KLGYO": "GYO", "VKGYO": "GYO",
    # Çimento / İnşaat Malzemeleri
    "CIMSA": "Çimento", "AKCNS": "Çimento", "BTCIM": "Çimento", "NUHCM": "Çimento",
    "GOLTS": "Çimento",
    # Kimya / Sağlık
    "SASA": "Kimya", "HEKTS": "Kimya", "DEVA": "İlaç/Sağlık", "ECZYT": "İlaç/Sağlık",
    "SELEC": "Kimya", "PETKM": "Kimya",
    # Tekstil / Perakende Giyim
    "MAVI": "Tekstil/Giyim", "YATAS": "Tekstil/Giyim", "KORDS": "Tekstil/Giyim",
    # Beyaz Eşya / Elektronik
    "ARCLK": "Dayanıklı Tüketim", "VESTL": "Dayanıklı Tüketim", "VESBE": "Dayanıklı Tüketim",
}

DIGER = "Diğer / Sınıflandırılmamış"


def sektor_bul(sembol: str) -> str:
    return SEKTOR_HARITASI.get(sembol.strip().upper().replace(".IS", ""), DIGER)
