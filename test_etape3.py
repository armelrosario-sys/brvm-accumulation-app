import streamlit as st
import pandas as pd
import plotly.express as px
from collecte_brvm import obtenir_cours_brvm
from historique_brvm import charger_historique_marche
from indicateurs_accumulation import calculer_scores_marche, calculer_liquidite, calculer_pic_volume
from dividendes_brvm import construire_mapping_noms, charger_dividendes, completer_avec_non_identifie

st.set_page_config(page_title="Screener BRVM - Accumulation", layout="wide")
st.title("Etape 3 - Tableau de bord des accumulations BRVM")

# --- Chargement des cours du jour ---
df_jour, statut = obtenir_cours_brvm()
st.caption(statut)

if df_jour.empty:
    st.stop()

tickers = df_jour["Symbole"].tolist()

# --- Chargement de l'historique ---
historique, manquants = charger_historique_marche(tuple(tickers))

if manquants:
    st.warning("Tickers introuvables dans l'historique : " + ", ".join(manquants))

if historique.empty:
    st.error("Aucun historique disponible.")
    st.stop()

# --- Calcul des indicateurs ---
from indicateurs_accumulation import calculer_variation_cours

scores = calculer_scores_marche(historique)
liquidite = calculer_liquidite(historique, df_jour=df_jour)
pics = calculer_pic_volume(historique)
variation_cours = calculer_variation_cours(historique)

mapping_noms = construire_mapping_noms(df_jour)
dividendes = charger_dividendes(tuple(tickers), mapping_noms)

tableau = scores.merge(liquidite, on="Symbole", how="left")
tableau = tableau.merge(pics, on="Symbole", how="left")
tableau = completer_avec_non_identifie(tableau, dividendes)
tableau = tableau.merge(variation_cours, on="Symbole", how="left")


# --- Regle de synthese (transparente) : Lecture rapide + Verdict ---
def generer_lecture_verdict(ligne):
    score = ligne["Score_Composite"]
    var20 = ligne["Variation_Vol_Moyen_20j"]
    varhebdo = ligne["Variation_Hebdo_Volume"]
    liquidite_val = ligne["Liquidite"]
    statut_div = ligne["Statut_Dividende"]

    alerte_dividende = "confirme" in statut_div.lower() or "previsionnel" in statut_div.lower()

    tendance_fond = None
    if pd.notna(var20):
        tendance_fond = "hausse" if var20 > 0 else ("baisse" if var20 < 0 else "stable")

    pic_isole = pd.notna(varhebdo) and varhebdo > 100 and tendance_fond == "baisse"
    var_cours = ligne["Variation_Cours_20j"]
    signal_encore_invisible = (
        pd.notna(var_cours) and pd.notna(var20)
        and var20 > 30 and abs(var_cours) < 3
    )

    if alerte_dividende:
        base = "Dividende proche/recent detecte (" + statut_div + ") : le volume/prix peut refleter ce dividende, pas une accumulation. "
        if pic_isole:
            return (base + "Pic ponctuel egalement observe.", "Prudence - effet dividende")
        return (base, "Prudence - effet dividende")

    if pic_isole:
        return ("Pic ponctuel cette semaine, mais tendance de fond en baisse (" + str(round(var20, 1)) + "%).", "Neutre - pic isole")

    if score >= 70:
        if liquidite_val in ("Faible", "Moyenne") and tendance_fond == "hausse":
            base = "Bon score, liquidite " + liquidite_val.lower() + ", volume en hausse de fond confirmee."
            if signal_encore_invisible:
                base += " Signal encore invisible dans le prix (cours quasi stable malgre le volume)."
            return (base, "Le plus proche de l'objectif")
        elif liquidite_val == "Elevee":
            return ("Bon score, mais valeur deja tres suivie sur le marche.", "Interessant, mais pas discret")
        else:
            return ("Bon score, tendance de fond incertaine.", "A surveiller")

    if score >= 50:
        if tendance_fond == "hausse":
            return ("Score moyen, volume en hausse de fond.", "A surveiller")
        return ("Score moyen, sans confirmation claire du volume.", "Prudence")

    if tendance_fond == "baisse":
        return ("Score faible, tendance de fond negative.", "Ecarter")
    return ("Score faible, aucun signal fort.", "Ecarter")


tableau[["Lecture_Rapide", "Verdict"]] = tableau.apply(
    lambda ligne: pd.Series(generer_lecture_verdict(ligne)), axis=1
)

# --- Filtre / bascule liquidite ---
st.subheader("Vue du tableau")
vue = st.radio(
    "Choisir la vue",
    ["Classement complet (47 valeurs)", "Valeurs peu liquides uniquement"],
    horizontal=True,
    label_visibility="collapsed",
)

if vue == "Valeurs peu liquides uniquement":
    tableau_affiche = tableau[tableau["Liquidite"] == "Faible"].reset_index(drop=True)
    st.caption(str(len(tableau_affiche)) + " valeur(s) classee(s) Faible liquidite.")
else:
    tableau_affiche = tableau
    st.caption(str(len(tableau_affiche)) + " valeurs au total.")

# --- Selecteur de colonnes optionnelles ---
colonnes_scores = ["Score_AD", "Score_OBV", "Score_CMF", "Score_VWAP", "Score_Composite"]
colonnes_optionnelles = colonnes_scores + ["Date_Pic_Volume", "Volume_Pic"]
scores_choisis = st.multiselect(
    "Afficher les colonnes optionnelles (scores detailles + date du pic de volume)",
    options=colonnes_optionnelles,
    default=[],
)

# --- Ordre des colonnes demande ---
colonnes_base = [
    colonnes_base = [
    "Symbole", "Dernier_Cours", "Lecture_Rapide", "Verdict", "Liquidite",
    "Variation_Hebdo_Volume", "Volume_Moyen_20j", "Variation_Vol_Moyen_20j",
    "Variation_Cours_20j",
]
colonnes_affichees = colonnes_base + scores_choisis + ["Date_Paiement_Dividende"]
tableau_affiche = tableau_affiche.sort_values("Score_Composite", ascending=False)[colonnes_affichees].reset_index(drop=True)


# --- Formatage / couleurs ---
def couleur_liquidite(val):
    couleurs = {"Faible": "background-color: #4a1f1f", "Moyenne": "background-color: #4a3f1f", "Elevee": "background-color: #1f3f1f"}
    return couleurs.get(val, "")


def couleur_tendance(val):
    if pd.isna(val):
        return ""
    if val > 0:
        return "color: #52e070; font-weight: bold"
    if val < 0:
        return "color: #e05252; font-weight: bold"
    return ""


def couleur_verdict(val):
    if "objectif" in val:
        return "background-color: #1f3f1f"
    if "Ecarter" in val:
        return "background-color: #4a1f1f"
    if "dividende" in val.lower():
        return "background-color: #3f2f1f"
    if "Neutre" in val or "Prudence" in val:
        return "background-color: #4a3f1f"
    return "background-color: #1f2f4a"


style = tableau_affiche.style
if "Liquidite" in tableau_affiche.columns:
    style = style.map(couleur_liquidite, subset=["Liquidite"])
style = style.map(couleur_tendance, subset=["Variation_Vol_Moyen_20j", "Variation_Hebdo_Volume", "Variation_Cours_20j"])
style = style.map(couleur_verdict, subset=["Verdict"])

format_colonnes = {
    format_colonnes = {
    "Dernier_Cours": "{:.0f}",
    "Volume_Moyen_20j": "{:.0f}",
    "Variation_Vol_Moyen_20j": "{:.1f}%",
    "Variation_Hebdo_Volume": "{:.1f}%",
    "Variation_Cours_20j": "{:.1f}%",
}
if "Volume_Pic" in tableau_affiche.columns:
    format_colonnes["Volume_Pic"] = "{:.0f}"
for col in colonnes_scores:
    if col in tableau_affiche.columns:
        format_colonnes[col] = "{:.1f}"

style = style.format(format_colonnes, na_rep="-")

st.dataframe(style, use_container_width=True, height=550)

if pd.Timestamp.now().weekday() != 4:
    st.caption("La colonne Variation Lun-Ven n'est renseignee que le vendredi.")

st.caption("Dividende : correspondance automatique par sigle/nom, calendrier officiel BRVM, exercice N-1. "
           "Statuts : Verse (paiement passe) / Confirme (date future fixee) / Previsionnel (date pas encore fixee) / "
           "Non identifie (aucune correspondance trouvee -- ne signifie pas absence de dividende). "
           "Lecture rapide / Verdict : synthese automatique, pas un conseil financier.")

# --- Graphique ---
st.subheader("Top 15 - Score composite")
top15 = tableau.sort_values("Score_Composite", ascending=False).head(15)
fig = px.bar(
    top15, x="Score_Composite", y="Symbole", orientation="h", color="Liquidite",
    color_discrete_map={"Faible": "#e05252", "Moyenne": "#e0c352", "Elevee": "#52e070"},
    hover_data=["Dernier_Cours", "Verdict", "Date_Paiement_Dividende"],
)
fig.update_layout(yaxis={"categoryorder": "total ascending"})
st.plotly_chart(fig, use_container_width=True)