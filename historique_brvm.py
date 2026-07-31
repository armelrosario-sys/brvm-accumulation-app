# -*- coding: utf-8 -*-
"""
Chargement de l'historique des cours BRVM (Open/High/Low/Close/Volume).
Source : dépôt public Fredysessie/brvm-data-public (vérifié le 27/07/2026 :
données à jour, cohérentes avec le scraping du jour sur brvm.org).
"""

import pandas as pd
import requests
import streamlit as st
import io

BASE_URL = "https://raw.githubusercontent.com/Fredysessie/brvm-data-public/main/data/{ticker}/{ticker}.daily.csv"

RENOMMAGE = {
    "Date": "Date",
    "Open": "Ouverture",
    "High": "Plus_Haut",
    "Low": "Plus_Bas",
    "Close": "Cours_Cloture",
    "Volume": "Volume",
}


def _charger_un_ticker(ticker):
    """Télécharge l'historique d'un seul ticker. Renvoie None si le ticker n'existe pas dans ce dépôt."""
    url = BASE_URL.format(ticker=ticker)
    try:
        reponse = requests.get(url, timeout=20)
        if reponse.status_code != 200:
            return None
        df = pd.read_csv(io.StringIO(reponse.text))
        df = df.rename(columns=RENOMMAGE)
        df["Symbole"] = ticker
        df["Date"] = pd.to_datetime(df["Date"])
        return df
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner="Chargement de l'historique BRVM (peut prendre 1-2 minutes la première fois)...")
def charger_historique_marche(liste_tickers):
    """
    Charge l'historique de tous les tickers fournis.
    Renvoie (DataFrame combiné, liste des tickers introuvables).
    """
    dfs = []
    tickers_manquants = []
    for ticker in liste_tickers:
        df = _charger_un_ticker(ticker)
        if df is not None and len(df) > 0:
            dfs.append(df)
        else:
            tickers_manquants.append(ticker)

    if not dfs:
        return pd.DataFrame(), tickers_manquants

    historique = pd.concat(dfs, ignore_index=True)
    historique = historique.sort_values(["Symbole", "Date"]).reset_index(drop=True)
    return historique, tickers_manquants