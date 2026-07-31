# -*- coding: utf-8 -*-
"""
Module de collecte des cours BRVM — 100% Open Source
Source unique : site officiel BRVM (www.brvm.org)

Note (27/07/2026) : l'API Sika Finance (GetTickersDayMarket) a été testée et
retirée — elle renvoie une erreur 400 en appel direct (protection probable
côté serveur). Le site officiel BRVM suffit et fournit toutes les colonnes
nécessaires (Symbole, Ouverture, Cours, Veille, Variation_%, Volume).

Point ouvert non résolu : la référence exacte utilisée par le site pour
calculer "Variation (%)" (Veille ou Ouverture) n'est pas certaine à 100% —
une seule vérification manuelle (UNXC) a suggéré Ouverture, mais une
comparaison sur Sika Finance a montré un indice contraire (SGBCI : Ouverture
= Dernier = 38000 mais Variation = 0.01%, incompatible avec une base
Ouverture stricte). D'où le calcul de contrôle Variation_calculee et le
signal Ecart_suspect ci-dessous, qui n'affirment rien silencieusement.

Décision définitive sur la colonne Variation (%) (27/07/2026) : vérifiée
ligne par ligne sur 7 valeurs (SNTS, SPHC, UNLC, STAC, TTLS, UNXC, SOGC).
Résultat : aucune formule universelle (ni base Veille, ni base Ouverture)
n'explique toutes les lignes — SOGC ne correspond à aucune des deux. La
colonne est donc acceptée comme donnée brute officielle du site, sans
tentative de recalcul ou de contrôle de cohérence.
"""

import requests
import pandas as pd
import streamlit as st
import io
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0 Safari/537.36",
    "Accept": "text/html",
}

URL_BRVM = "https://www.brvm.org/fr/cours-actions/0"

RENOMMAGE_BRVM = {
    "Cours veille (FCFA)": "Veille",
    "Cours Ouverture (FCFA)": "Ouverture",
    "Cours Clôture (FCFA)": "Cours",
    "Variation (%)": "Variation_%",
}


def _nettoyer_nombre(valeur):
    if valeur is None:
        return None
    texte = str(valeur).replace("\u202f", "").replace("\xa0", "")
    texte = texte.replace(" ", "").replace("%", "").replace(",", ".")
    try:
        return float(texte)
    except ValueError:
        return None


def _trouver_table_cours(tables):
    """Cherche, parmi tous les tableaux de la page, celui qui contient réellement les cours."""
    for t in tables:
        colonnes = [str(c) for c in t.columns]
        if "Symbole" in colonnes and len(t) > 10:
            return t
    raise ValueError("Aucun tableau avec une colonne 'Symbole' et plus de 10 lignes n'a été trouvé.")


def _collecter_brvm_officiel():
    reponse = requests.get(URL_BRVM, headers=HEADERS, timeout=40)
    reponse.raise_for_status()
    tables = pd.read_html(io.StringIO(reponse.text), thousands=None, decimal=",")

    df = _trouver_table_cours(tables)
    df = df.rename(columns=RENOMMAGE_BRVM)

    for col in ["Cours", "Veille", "Ouverture", "Variation_%", "Volume"]:
        if col in df.columns:
            df[col] = df[col].apply(_nettoyer_nombre)
        else:
            df[col] = None

    df = df.dropna(subset=["Cours"])

    # Décision définitive (27/07/2026, après vérification croisée sur 7+ valeurs) :
    # La colonne Variation_% du site ne suit ni Veille ni Ouverture de façon
    # universelle (probable "cours de référence" ajusté au cas par cas selon
    # opérations sur titre). Elle est donc conservée telle quelle, sans
    # recalcul ni signal de contrôle — voir historique de vérification en
    # tête de fichier pour le détail de l'investigation.

    return df[["Symbole", "Nom", "Ouverture", "Cours", "Veille", "Variation_%", "Volume"]]


@st.cache_data(ttl=600, show_spinner="Récupération des cours BRVM en cours...")
def obtenir_cours_brvm():
    heure = datetime.now().strftime("%d/%m/%Y à %H:%M")
    try:
        df = _collecter_brvm_officiel()
        if len(df) > 10:
            return df, f"✅ Cours BRVM (site officiel) récupérés le {heure} ({len(df)} valeurs)"
        return pd.DataFrame(), "❌ Le site a répondu mais avec trop peu de valeurs exploitables."
    except Exception as erreur:
        return pd.DataFrame(), (
            "❌ Impossible de récupérer les cours pour le moment. "
            f"(Détail technique : {erreur})"
        )