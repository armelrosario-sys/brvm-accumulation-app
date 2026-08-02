# -*- coding: utf-8 -*-
"""
Calcul des indicateurs d'accumulation : A/D Line, OBV, CMF, VWAP.
Scores individuels normalises (percentile 0-100) + composite pondere.
Liquidite (volume moyen 20j + variations) + date du pic de volume.
"""
import pandas as pd
import numpy as np


def calculer_ad_line(df):
    range_jour = (df["Plus_Haut"] - df["Plus_Bas"]).replace(0, np.nan)
    clv = ((df["Cours_Cloture"] - df["Plus_Bas"]) - (df["Plus_Haut"] - df["Cours_Cloture"])) / range_jour
    clv = clv.fillna(0)
    return (clv * df["Volume"]).cumsum()


def calculer_obv(df):
    variation = df["Cours_Cloture"].diff()
    signe = np.sign(variation).fillna(0)
    return (signe * df["Volume"]).cumsum()


def calculer_cmf(df, periode=20):
    range_jour = (df["Plus_Haut"] - df["Plus_Bas"]).replace(0, np.nan)
    mf_multiplier = ((df["Cours_Cloture"] - df["Plus_Bas"]) - (df["Plus_Haut"] - df["Cours_Cloture"])) / range_jour
    mf_multiplier = mf_multiplier.fillna(0)
    mf_volume = mf_multiplier * df["Volume"]
    return mf_volume.rolling(periode).sum() / df["Volume"].rolling(periode).sum()


def calculer_vwap(df, periode=20):
    prix_volume = df["Cours_Cloture"] * df["Volume"]
    return prix_volume.rolling(periode).sum() / df["Volume"].rolling(periode).sum()


def normaliser_percentile(serie):
    return serie.rank(pct=True) * 100


def calculer_scores_marche(df_historique, poids=None):
    """
    poids : dict {'CMF':30,'AD':30,'OBV':25,'VWAP':15} par defaut.
    """
    if poids is None:
        poids = {"CMF": 30, "AD": 30, "OBV": 25, "VWAP": 15}

    resultats = []
    for symbole, groupe in df_historique.groupby("Symbole"):
        groupe = groupe.sort_values("Date").copy()
        if len(groupe) < 25:
            continue

        groupe["AD_Line"] = calculer_ad_line(groupe)
        groupe["OBV_brut"] = calculer_obv(groupe)
        groupe["CMF"] = calculer_cmf(groupe)
        groupe["VWAP"] = calculer_vwap(groupe)

        def pente_recente(serie, fenetre=20):
            recent = serie.tail(fenetre).dropna()
            if len(recent) < 5:
                return np.nan
            x = np.arange(len(recent))
            return np.polyfit(x, recent.values, 1)[0]

        resultats.append({
            "Symbole": symbole,
            "Derniere_Date": groupe["Date"].iloc[-1].strftime("%Y-%m-%d"),
            "Dernier_Cours": groupe["Cours_Cloture"].iloc[-1],
            "Signal_AD_brut": pente_recente(groupe["AD_Line"]),
            "Signal_OBV_brut": pente_recente(groupe["OBV_brut"]),
            "Signal_CMF_brut": groupe["CMF"].tail(20).mean(),
            "Ecart_VWAP_brut": (
                (groupe["Cours_Cloture"].iloc[-1] - groupe["VWAP"].iloc[-1]) / groupe["VWAP"].iloc[-1]
                if not pd.isna(groupe["VWAP"].iloc[-1]) else np.nan
            ),
        })

    df = pd.DataFrame(resultats).dropna()

    df["Score_AD"] = normaliser_percentile(df["Signal_AD_brut"]).round(1)
    df["Score_OBV"] = normaliser_percentile(df["Signal_OBV_brut"]).round(1)
    df["Score_CMF"] = normaliser_percentile(df["Signal_CMF_brut"]).round(1)
    df["Score_VWAP"] = (100 - normaliser_percentile(df["Ecart_VWAP_brut"])).round(1)

    df["Score_Composite"] = (
        df["Score_CMF"] * (poids["CMF"] / 100)
        + df["Score_AD"] * (poids["AD"] / 100)
        + df["Score_OBV"] * (poids["OBV"] / 100)
        + df["Score_VWAP"] * (poids["VWAP"] / 100)
    ).round(1)

    colonnes = ["Symbole", "Derniere_Date", "Dernier_Cours",
                "Score_AD", "Score_OBV", "Score_CMF", "Score_VWAP", "Score_Composite"]
    return df[colonnes].sort_values("Score_Composite", ascending=False).reset_index(drop=True)

def calculer_liquidite(df_historique, df_jour=None, fenetre=20):
    """
    df_jour (optionnel) : DataFrame du scraping du jour (collecte_brvm.py).

    Variation_Hebdo_Volume : compare le volume du "jour de reference" de la
    semaine en cours au volume du lundi de cette meme semaine. Le jour de
    reference progresse au fil de la semaine :
    - Lundi : pas de comparaison (c'est la reference elle-meme)
    - Mardi a Vendredi : volume du jour scrape en direct (df_jour)
    - Samedi/Dimanche : dernier volume de vendredi disponible dans l'historique
      (persistance, pas de recalcul le week-end)
    """
    volumes_jour = {}
    if df_jour is not None and "Volume" in df_jour.columns:
        volumes_jour = dict(zip(df_jour["Symbole"], df_jour["Volume"]))

    aujourdhui_reel = pd.Timestamp.now().normalize()
    jour_semaine = aujourdhui_reel.weekday()  # 0=Lundi ... 6=Dimanche
    annee, semaine, _ = aujourdhui_reel.isocalendar()

    resultats = []
    for symbole, groupe in df_historique.groupby("Symbole"):
        groupe = groupe.sort_values("Date").reset_index(drop=True)

        volume_moyen_actuel = groupe["Volume"].tail(fenetre).mean()

        if len(groupe) >= 2 * fenetre:
            fenetre_precedente = groupe["Volume"].iloc[-2 * fenetre:-fenetre]
            volume_moyen_precedent = fenetre_precedente.mean()
            variation_vol_moyen = (
                (volume_moyen_actuel - volume_moyen_precedent) / volume_moyen_precedent * 100
                if volume_moyen_precedent > 0 else None
            )
        else:
            variation_vol_moyen = None

        # --- Variation hebdomadaire progressive ---
        variation_hebdo = None
        semaine_courante = groupe[
            (groupe["Date"].dt.isocalendar().year == annee)
            & (groupe["Date"].dt.isocalendar().week == semaine)
        ]
        lundi = semaine_courante[semaine_courante["Date"].dt.weekday == 0]
        vol_lundi = lundi["Volume"].iloc[0] if not lundi.empty else None

        if vol_lundi is not None and vol_lundi > 0:
            if jour_semaine == 0:
                variation_hebdo = None  # lundi = reference, rien a comparer encore
            elif jour_semaine in (1, 2, 3, 4):  # mardi a vendredi
                vol_reference = volumes_jour.get(symbole)
                if vol_reference is not None:
                    variation_hebdo = (vol_reference - vol_lundi) / vol_lundi * 100
            else:  # samedi/dimanche : persiste la valeur de vendredi
                vendredi = semaine_courante[semaine_courante["Date"].dt.weekday == 4]
                if not vendredi.empty:
                    vol_vendredi = vendredi["Volume"].iloc[0]
                    variation_hebdo = (vol_vendredi - vol_lundi) / vol_lundi * 100

        resultats.append({
            "Symbole": symbole,
            "Volume_Moyen_20j": round(volume_moyen_actuel, 0),
            "Variation_Vol_Moyen_20j": round(variation_vol_moyen, 1) if variation_vol_moyen is not None else None,
            "Variation_Hebdo_Volume": round(variation_hebdo, 1) if variation_hebdo is not None else None,
        })

    df = pd.DataFrame(resultats)
    df["Rang_Liquidite"] = df["Volume_Moyen_20j"].rank(pct=True)

    def classer(rang):
        if rang <= 0.33:
            return "Faible"
        elif rang <= 0.66:
            return "Moyenne"
        else:
            return "Elevee"

    df["Liquidite"] = df["Rang_Liquidite"].apply(classer)
    return df[["Symbole", "Volume_Moyen_20j", "Liquidite", "Variation_Vol_Moyen_20j", "Variation_Hebdo_Volume"]]

def calculer_pic_volume(df_historique, fenetre=20):
    """
    Pour chaque valeur, identifie la date et le volume du jour le plus
    actif sur les 'fenetre' derniers jours de bourse -- pour verification
    manuelle des pics detectes par les autres indicateurs.
    """
    resultats = []
    for symbole, groupe in df_historique.groupby("Symbole"):
        groupe = groupe.sort_values("Date").tail(fenetre)
        if groupe.empty:
            continue
        ligne_pic = groupe.loc[groupe["Volume"].idxmax()]
        resultats.append({
            "Symbole": symbole,
            "Date_Pic_Volume": ligne_pic["Date"].strftime("%d/%m/%Y"),
            "Volume_Pic": int(ligne_pic["Volume"]),
        })
    return pd.DataFrame(resultats)

def calculer_variation_cours(df_historique, fenetre=20):
    """
    Variation du cours de cloture sur 'fenetre' jours de bourse (meme fenetre
    que Variation_Vol_Moyen_20j, pour permettre une lecture croisee directe) :
    cours actuel vs cours d'il y a 'fenetre' jours de bourse.
    """
    resultats = []
    for symbole, groupe in df_historique.groupby("Symbole"):
        groupe = groupe.sort_values("Date").reset_index(drop=True)
        if len(groupe) < fenetre + 1:
            resultats.append({"Symbole": symbole, "Variation_Cours_20j": None})
            continue

        cours_actuel = groupe["Cours_Cloture"].iloc[-1]
        cours_ancien = groupe["Cours_Cloture"].iloc[-(fenetre + 1)]

        variation = (
            (cours_actuel - cours_ancien) / cours_ancien * 100
            if cours_ancien > 0 else None
        )
        resultats.append({
            "Symbole": symbole,
            "Variation_Cours_20j": round(variation, 1) if variation is not None else None,
        })

    return pd.DataFrame(resultats)