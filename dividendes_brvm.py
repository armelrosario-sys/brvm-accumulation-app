# -*- coding: utf-8 -*-
"""
Calendrier des dividendes BRVM -- deux sources combinees :
1. BRVM officiel (dates precises de paiement/detachement, page 0 uniquement --
   la pagination ?page=N a ete testee et confirmee cassee, voir tests du 31/07/2026).
2. Sika Finance /marches/dividendes (page unique, pas de pagination) :
   - table "a venir" : dates de detachement connues ou "A preciser"
   - table historique 3 ans : confirme si un dividende exercice 2025 a ete
     verse, meme sans date exacte disponible.

Statuts (termes consacres du secteur) :
- "Verse"        : paiement passe (date exacte ou montant historique confirme).
- "Confirme"     : date de paiement ou de detachement future connue.
- "Previsionnel" : dividende attendu, montant connu, date pas encore fixee.
- "Non identifie": aucune trace trouvee dans les 2 sources.
"""

import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
import streamlit as st
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
}

URL_BRVM = "https://www.brvm.org/fr/esv/paiement-de-dividendes"
URL_SIKA = "https://www.sikafinance.com/marches/dividendes"
EXERCICE_CIBLE = str(datetime.now().year - 1)

MOIS_FR = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}


def _parser_date_fr(texte):
    match = re.match(r"(\d{1,2})[/\s]([A-Za-zéûàè]+|\d{1,2})[/\s](\d{4})", texte.strip())
    if not match:
        return None
    jour, mois_texte, annee = match.groups()
    if mois_texte.isdigit():
        mois_num = int(mois_texte)
    else:
        mois_num = MOIS_FR.get(mois_texte.lower())
    if not mois_num:
        return None
    try:
        return pd.Timestamp(year=int(annee), month=mois_num, day=int(jour))
    except Exception:
        return None


def _statut_depuis_date(date_parsee, prefixe="Confirme"):
    aujourdhui = pd.Timestamp.now().normalize()
    if date_parsee.normalize() < aujourdhui:
        return "Verse", date_parsee.strftime("%d/%m/%Y")
    return f"{prefixe} (a venir)", date_parsee.strftime("%d/%m/%Y")


def _charger_brvm_officiel():
    """Page 0 uniquement (pagination cassee -- voir note en tete de fichier)."""
    resultats = {}
    try:
        reponse = requests.get(URL_BRVM, headers=HEADERS, timeout=30)
        reponse.raise_for_status()
        soup = BeautifulSoup(reponse.text, "lxml")
        table = soup.find("table")
        if table is None:
            return resultats
        lignes = table.find_all("tr")[1:]
        for ligne in lignes:
            cellules = ligne.find_all("td")
            if len(cellules) < 5:
                continue
            emetteur = cellules[0].get_text(strip=True)
            exercice = cellules[3].get_text(strip=True)
            date_paiement_texte = cellules[4].get_text(strip=True)
            if exercice != EXERCICE_CIBLE:
                continue
            date_parsee = _parser_date_fr(date_paiement_texte)
            if date_parsee is not None:
                statut, date_aff = _statut_depuis_date(date_parsee)
                resultats[emetteur.upper()] = (date_aff, statut)
    except Exception:
        pass
    return resultats


def _extraire_ticker(lien_href):
    match = re.search(r"cotation_([A-Z0-9]+)\.", lien_href or "")
    return match.group(1) if match else None


def _a_une_valeur(texte):
    """Verifie si une cellule contient un vrai chiffre, peu importe le caractere de tiret utilise."""
    return bool(re.search(r"\d", texte or ""))


def _charger_sika():
    a_venir = {}
    historique_2025 = set()
    try:
        reponse = requests.get(URL_SIKA, headers=HEADERS, timeout=30)
        reponse.raise_for_status()
        soup = BeautifulSoup(reponse.text, "lxml")
        tables = soup.find_all("table")

        for table in tables:
            entetes = [th.get_text(strip=True) for th in table.find_all("th")]
            lignes = table.find_all("tr")[1:]

            if any("détachement" in e.lower() for e in entetes):
                for ligne in lignes:
                    cellules = ligne.find_all("td")
                    if len(cellules) < 2:
                        continue
                    date_texte = cellules[0].get_text(strip=True)
                    lien = cellules[1].find("a")
                    ticker = _extraire_ticker(lien["href"] if lien else None)
                    if not ticker:
                        continue
                    if date_texte.lower() in ("a preciser", "à préciser"):
                        a_venir[ticker] = ("Non fixee", "Previsionnel (date non fixee)")
                    else:
                        date_parsee = _parser_date_fr(date_texte)
                        if date_parsee is not None:
                            statut, date_aff = _statut_depuis_date(date_parsee, prefixe="Confirme (detachement)")
                            a_venir[ticker] = (date_aff, statut)

            elif any("2025" in e for e in entetes):
                for ligne in lignes:
                    lien = ligne.find("a")
                    ticker = _extraire_ticker(lien["href"] if lien else None)
                    cellules = ligne.find_all("td")
                    if ticker and len(cellules) >= 2:
                        valeur_2025 = cellules[-2].get_text(strip=True)
                        if _a_une_valeur(valeur_2025):
                            historique_2025.add(ticker)
    except Exception:
        pass
    return a_venir, historique_2025


@st.cache_data(ttl=3600, show_spinner="Chargement du calendrier des dividendes...")
def charger_dividendes(liste_tickers, mapping_noms=None):
    brvm = _charger_brvm_officiel()
    sika_a_venir, sika_historique = _charger_sika()
    aujourdhui = pd.Timestamp.now().normalize()

    lignes = []
    for ticker in liste_tickers:
        date_affichee, statut = None, None

        # Priorite 1 : BRVM officiel (date exacte de paiement)
        for emetteur, (date_brute, _) in brvm.items():
            if ticker in emetteur or emetteur in ticker:
                d = pd.to_datetime(date_brute, format="%d/%m/%Y")
                if d < aujourdhui:
                    date_affichee = f"Paye le {date_brute}"
                    statut = "Verse"
                else:
                    date_affichee = f"Prevu le {date_brute}"
                    statut = "Confirme (a venir)"
                break

        # Priorite 2 : Sika "a venir" (detachement)
        if date_affichee is None and ticker in sika_a_venir:
            date_brute, _ = sika_a_venir[ticker]
            if date_brute == "Non fixee":
                date_affichee = "Prevu (date non fixee)"
                statut = "Previsionnel"
            else:
                d = pd.to_datetime(date_brute, format="%d/%m/%Y")
                if d < aujourdhui:
                    date_affichee = f"Detache le {date_brute}"
                    statut = "Verse"
                else:
                    date_affichee = f"Detachement prevu le {date_brute}"
                    statut = "Confirme (a venir)"

        # Priorite 3 : historique Sika (verse, date exacte inconnue)
        if date_affichee is None and ticker in sika_historique:
            date_affichee = "Paye en 2026 (date exacte inconnue)"
            statut = "Verse"

        if date_affichee is None:
            date_affichee = "Non identifie"
            statut = f"Non identifie (exercice {EXERCICE_CIBLE} non trouve)"

        lignes.append({"Symbole": ticker, "Date_Paiement_Dividende": date_affichee, "Statut_Dividende": statut})

    return pd.DataFrame(lignes)

def construire_mapping_noms(df_jour):
    """Conserve pour compatibilite avec test_etape3.py (plus utilise activement)."""
    return {}


def completer_avec_non_identifie(df_scores, df_dividendes):
    return df_scores.merge(df_dividendes, on="Symbole", how="left")