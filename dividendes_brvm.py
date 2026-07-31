# -*- coding: utf-8 -*-
"""
Scraping du calendrier officiel des dividendes BRVM.
Source : https://www.brvm.org/fr/esv/paiement-de-dividendes
Filtre sur l'exercice comptable N-1 (ex : 2025 si on est en 2026).

Correspondance emetteur -> ticker : d'abord via un dictionnaire de sigles
connus, puis via correspondance approximative avec les noms complets des
societes (colonne "Nom" du scraper cours-actions).

Statut du dividende (termes consacres du secteur) :
- "Verse"        : la date de paiement est passee.
- "Confirme"     : une date de paiement future est officiellement fixee.
- "Previsionnel" : dividende attendu (exercice N-1) mais date pas encore fixee.
- "Non identifie": aucune correspondance trouvee -- ne veut PAS dire "pas de
                   dividende", seulement "non trouve avec la couverture actuelle".
"""

import re
import requests
import pandas as pd
import streamlit as st
import io
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

URL_BASE = "https://www.brvm.org/fr/esv/paiement-de-dividendes"
EXERCICE_CIBLE = str(datetime.now().year - 1)

EMETTEUR_VERS_TICKER = {
    "SOGB": "SOGC", "NSBC": "NSBC", "LNB": "LNBB", "SOLIBRA": "SLBC",
    "CIE CI": "CIEC", "BIIC": "BICC", "ECOBANK TG": "ETIT",
    "TOTAL SENEGAL S.A.": "TTLS", "SIB": "SIBC", "SITAB": "STBC",
    "SMB CI": "SMBC", "SGBCI": "SGBC", "TOTAL CI": "TTLC", "SAPH CI": "SPHC",
    "NEI CEDA CI": "NEIC", "CFAO CI": "CFAC", "SODECI": "SDCC",
}

MOTS_A_IGNORER = {"CI", "SA", "S.A.", "SN", "BF", "BJ", "TG", "COTE", "D'IVOIRE", "SENEGAL", "MARKETING"}

MOIS_FR = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}


def _nettoyer(texte):
    texte = re.sub(r"[^A-ZÀ-Ý0-9\s]", " ", texte.upper())
    mots = [m for m in texte.split() if m not in MOTS_A_IGNORER]
    return " ".join(mots).strip()


def construire_mapping_noms(df_jour):
    """Construit un dictionnaire nom-nettoye -> ticker a partir du scraper cours-actions."""
    mapping = {}
    for _, ligne in df_jour.iterrows():
        cle = _nettoyer(str(ligne["Nom"]))
        if cle:
            mapping[cle] = ligne["Symbole"]
    return mapping


def _trouver_ticker(nom_emetteur, mapping_noms):
    """Cherche d'abord dans le dictionnaire de sigles connus, puis par nom approximatif."""
    nom_emetteur = str(nom_emetteur).strip()
    if nom_emetteur in EMETTEUR_VERS_TICKER:
        return EMETTEUR_VERS_TICKER[nom_emetteur]

    cle = _nettoyer(nom_emetteur)
    if not cle:
        return None

    if cle in mapping_noms:
        return mapping_noms[cle]

    premier_mot = cle.split()[0] if cle.split() else None
    if premier_mot and len(premier_mot) >= 3:
        for nom_complet, ticker in mapping_noms.items():
            if premier_mot in nom_complet.split():
                return ticker
    return None


def _lire_une_page(numero_page):
    url = URL_BASE if numero_page == 0 else f"{URL_BASE}?page={numero_page}"
    try:
        reponse = requests.get(url, headers=HEADERS, timeout=30)
        reponse.raise_for_status()
        tables = pd.read_html(io.StringIO(reponse.text))
        for t in tables:
            if "Emetteur" in [str(c) for c in t.columns]:
                return t
    except Exception:
        return None
    return None


def _parser_date_fr(texte):
    """Parse une date au format francais ('30 juin 2026') sans dependre de la locale systeme."""
    match = re.match(r"(\d{1,2})\s+([A-Za-zéûàè]+)\s+(\d{4})", texte.strip())
    if not match:
        return None
    jour, mois_texte, annee = match.groups()
    mois_num = MOIS_FR.get(mois_texte.lower())
    if not mois_num:
        return None
    try:
        return pd.Timestamp(year=int(annee), month=mois_num, day=int(jour))
    except Exception:
        return None


def _determiner_statut(date_paiement_texte):
    """Renvoie (statut, date_affichee) selon les termes consacres du secteur."""
    if not isinstance(date_paiement_texte, str) or date_paiement_texte.strip() == "":
        return "Previsionnel (date non fixee)", "Non fixee"

    texte = date_paiement_texte.strip()
    if texte.lower() in ("a preciser", "à préciser"):
        return "Previsionnel (date non fixee)", "Non fixee"

    date_parsee = _parser_date_fr(texte)
    if date_parsee is None:
        return "Previsionnel (date non fixee)", texte

    aujourdhui = pd.Timestamp.now().normalize()
    if date_parsee.normalize() < aujourdhui:
        return "Verse", date_parsee.strftime("%d/%m/%Y")
    else:
        return "Confirme (a venir)", date_parsee.strftime("%d/%m/%Y")


@st.cache_data(ttl=3600, show_spinner="Chargement du calendrier des dividendes (peut prendre 1-2 minutes)...")
def charger_dividendes(liste_tickers, mapping_noms, nb_pages_max=30):
    """
    Parcourt jusqu'a nb_pages_max pages du calendrier, filtre sur l'exercice N-1,
    et renvoie Symbole / Date_Paiement_Dividende / Statut_Dividende.
    S'arrete plus tot si tous les tickers ont ete trouves.
    """
    lignes_retenues = []
    tickers_restants = set(liste_tickers)

    for i in range(nb_pages_max):
        if not tickers_restants:
            break
        t = _lire_une_page(i)
        if t is None or "Exercice comptable" not in t.columns:
            continue

        t = t[t["Exercice comptable"].astype(str) == EXERCICE_CIBLE]
        for _, ligne in t.iterrows():
            symbole = _trouver_ticker(ligne["Emetteur"], mapping_noms)
            if symbole and symbole in tickers_restants:
                statut, date_affichee = _determiner_statut(ligne.get("Date de paiement"))
                lignes_retenues.append({
                    "Symbole": symbole,
                    "Date_Paiement_Dividende": date_affichee,
                    "Statut_Dividende": statut,
                })
                tickers_restants.discard(symbole)

    df = pd.DataFrame(lignes_retenues, columns=["Symbole", "Date_Paiement_Dividende", "Statut_Dividende"])
    return df


def completer_avec_non_identifie(df_scores, df_dividendes):
    """Fusionne et marque explicitement les tickers non trouves comme 'Non identifie'."""
    fusion = df_scores.merge(df_dividendes, on="Symbole", how="left")
    fusion["Date_Paiement_Dividende"] = fusion["Date_Paiement_Dividende"].fillna("-")
    fusion["Statut_Dividende"] = fusion["Statut_Dividende"].fillna(
        f"Non identifie (exercice {EXERCICE_CIBLE} non trouve)"
    )
    return fusion