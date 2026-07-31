import streamlit as st
from collecte_brvm import obtenir_cours_brvm

st.title("Test Étape 1 — Cours BRVM")

if st.button("🔄 Actualiser les cours"):
    st.cache_data.clear()

df, statut = obtenir_cours_brvm()
st.info(statut)

if not df.empty:
    st.dataframe(df, use_container_width=True)