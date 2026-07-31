# -*- coding: utf-8 -*-
"""Diagnostic : montre exactement ce que renvoient les 2 sources."""

import requests
import pandas as pd
import io

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/html",
}

print("=" * 60)
print("TEST 1 : Sika Finance")
print("=" * 60)
try:
    r = requests.post(
        "https://www.sikafinance.com/api/general/GetTickersDayMarket",
        headers=HEADERS, timeout=20
    )
    print("Code HTTP :", r.status_code)
    print("Premiers 500 caractères de la réponse :")
    print(r.text[:500])
except Exception as e:
    print("ERREUR Sika :", e)

print()
print("=" * 60)
print("TEST 2 : Site officiel BRVM")
print("=" * 60)
try:
    r = requests.get(
        "https://www.brvm.org/fr/cours-actions/0",
        headers=HEADERS, timeout=20
    )
    print("Code HTTP :", r.status_code)
    tables = pd.read_html(io.StringIO(r.text))
    print(f"Nombre de tableaux trouvés sur la page : {len(tables)}")
    for i, t in enumerate(tables):
        print(f"--- Tableau {i} : {t.shape[0]} lignes, colonnes = {list(t.columns)}")
except Exception as e:
    print("ERREUR BRVM :", e)