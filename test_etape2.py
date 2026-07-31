import streamlit as st
from collecte_brvm import obtenir_cours_brvm
from historique_brvm import charger_historique_marche
from indicateurs_accumulation import calculer_scores_marche

st.title("Test Étape 2 — Scores d'accumulation")

df_jour, statut = obtenir_cours_brvm()
st.info(statut)

if not df_jour.empty:
    tickers = df_jour["Symbole"].tolist()
    historique, manquants = charger_historique_marche(tuple(tickers))

    if manquants:
        st.warning(f"⚠️ {len(manquants)} ticker(s) introuvables dans l'historique : {', '.join(manquants)}")

    if not historique.empty:
        scores = calculer_scores_marche(historique)
        st.dataframe(scores, use_container_width=True)
    else:
        st.error("Aucun historique n'a pu être chargé.")