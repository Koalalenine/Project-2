"""Collecte et préparation des données : top 1000 des commandants Scryfall + otags.

Cible : `position` (1 = commandant le plus populaire selon l'ordre EDHREC de Scryfall).
Entrées : cmc, annee, identite_couleur, type_principal, nb_tags et une colonne 0/1 par otag.
"""
from __future__ import annotations

import json
import os
import time
from functools import wraps
from typing import Callable, Iterator

import pandas as pd
import requests

from src.exceptions import DonneeInvalideError, ScryfallError

BASE = "https://api.scryfall.com"
HEADERS = {"User-Agent": "INF1007Projet2/1.0", "Accept": "application/json"}
PAUSE_ENTRE_REQUETES = 0.1  # Scryfall : environ 10 requêtes/seconde au maximum
REQUETE_COMMANDANTS = "is:commander f:commander"

# Liste de départ. À VÉRIFIER sur tagger.scryfall.com : un tag mal orthographié
# renvoie 0 résultat (la collecte l'affiche). Choisissez et justifiez vos tags
# dans DECISIONS.md.
TAGS_PAR_DEFAUT: list[str] = [
    "ramp", "mana-rock", "mana-dork", "removal", "board-wipe", "draw",
    "tutor", "counterspell", "sacrifice-outlet", "reanimate", "recursion",
    "token-generator", "lifegain", "lifedrain", "burn", "evasion",
    "protection", "haste-enabler", "cost-reducer", "extra-turn",
    "copy-permanent", "blink", "mill", "discard", "treasure",
    "proliferate", "voltron", "stax", "combo-piece", "anthem",
]


def chronometre(fonction: Callable) -> Callable:
    """Décorateur (ch. 7) : affiche la durée d'exécution de la fonction décorée."""
    @wraps(fonction)
    def enveloppe(*args, **kwargs):
        debut = time.perf_counter()
        resultat = fonction(*args, **kwargs)
        print(f"[{fonction.__name__}] terminé en {time.perf_counter() - debut:.1f} s")
        return resultat
    return enveloppe


# ---------------------------------------------------------------- API Scryfall
def _get(url: str, params: dict | None) -> requests.Response:
    """Fait un GET avec 3 tentatives en cas d'erreur 429 (trop de requêtes).

    Lève ScryfallError si le réseau échoue ou si la limite persiste.
    """
    for tentative in range(3):
        try:
            reponse = requests.get(url, headers=HEADERS, params=params, timeout=30)
        except requests.RequestException as erreur:
            raise ScryfallError(f"Requête impossible : {erreur}") from erreur
        if reponse.status_code == 429:
            time.sleep(2 * (tentative + 1))
            continue
        return reponse
    raise ScryfallError("Limite de requêtes Scryfall dépassée (429) de façon répétée.")


def recuperer_cartes(requete: str, maximum: int | None = None) -> list[dict]:
    """Retourne les cartes d'une recherche Scryfall, triées par rang EDHREC croissant.

    Suit la pagination et s'arrête après `maximum` cartes si fourni.
    Retourne [] si rien ne correspond (404). Lève ScryfallError pour toute autre erreur.
    """
    url: str | None = f"{BASE}/cards/search"
    params: dict | None = {"q": requete, "order": "edhrec", "dir": "asc", "unique": "cards"}
    cartes: list[dict] = []

    while url:
        reponse = _get(url, params)
        if reponse.status_code == 404:
            return []
        if reponse.status_code != 200:
            raise ScryfallError(f"Scryfall a répondu {reponse.status_code} pour « {requete} ».")
        donnees = reponse.json()
        cartes.extend(donnees["data"])
        if maximum is not None and len(cartes) >= maximum:
            return cartes[:maximum]
        url = donnees.get("next_page") if donnees.get("has_more") else None
        params = None  # next_page contient déjà tous les paramètres
        time.sleep(PAUSE_ENTRE_REQUETES)
    return cartes


# ------------------------------------------------------------------ Cache JSON
def sauvegarder_json(objet: object, chemin: str) -> None:
    """Écrit `objet` en JSON dans `chemin` (crée le dossier au besoin)."""
    dossier = os.path.dirname(chemin)
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(objet, f, ensure_ascii=False, indent=1)


def charger_json(chemin: str) -> object:
    """Lit un fichier JSON. Lève DonneeInvalideError s'il est absent ou illisible."""
    if not os.path.exists(chemin):
        raise DonneeInvalideError(f"Fichier introuvable : {chemin}")
    try:
        with open(chemin, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as erreur:
        raise DonneeInvalideError(f"JSON invalide dans {chemin} : {erreur}") from erreur


# --------------------------------------------------------------------- Collecte
@chronometre
def collecter_top_commandants(nombre: int = 1000, chemin_cache: str | None = None) -> list[dict]:
    """Retourne les `nombre` commandants les plus populaires (avec cache JSON optionnel)."""
    if chemin_cache and os.path.exists(chemin_cache):
        return charger_json(chemin_cache)  # type: ignore[return-value]
    top = recuperer_cartes(REQUETE_COMMANDANTS, maximum=nombre)
    if not top:
        raise DonneeInvalideError("Aucun commandant récupéré depuis Scryfall.")
    if chemin_cache:
        sauvegarder_json(top, chemin_cache)
    return top


@chronometre
def collecter_otags(ids_top: set[str], tags: list[str],
                    chemin_cache: str | None = None) -> dict[str, set[str]]:
    """Pour chaque tag, retourne les identifiants du top possédant ce tag.

    Les tags déjà présents dans le cache ne sont pas ré-interrogés.
    Un tag qui ne donne aucun résultat est signalé (faute de frappe probable).
    """
    cache: dict[str, list[str]] = {}
    if chemin_cache and os.path.exists(chemin_cache):
        cache = charger_json(chemin_cache)  # type: ignore[assignment]

    for tag in tags:
        if tag not in cache:
            cartes = recuperer_cartes(f"{REQUETE_COMMANDANTS} otag:{tag}")
            cache[tag] = sorted(c["id"] for c in cartes)
            if chemin_cache:
                sauvegarder_json(cache, chemin_cache)
        trouves = len(set(cache[tag]) & ids_top)
        alerte = "  <-- AUCUN RÉSULTAT : tag à vérifier" if trouves == 0 else ""
        print(f"otag:{tag} -> {trouves} commandants du top{alerte}")

    return {tag: set(cache[tag]) & ids_top for tag in tags}


# --------------------------------------------------------------- Construction
def type_principal(type_line: str) -> str:
    """Retourne la partie « types » du type_line de la première face.

    Ex. « Legendary Creature — Elf Druid » -> « Legendary Creature ».
    Pour une carte à deux faces (« A // B »), seule la première face est utilisée.
    """
    premiere_face = type_line.split(" // ")[0]
    return premiere_face.split(" — ")[0].strip()


def construire_dataframe(top: list[dict], par_tag: dict[str, set[str]]) -> pd.DataFrame:
    """Assemble une ligne par commandant : position, caractéristiques et colonnes 0/1.

    `top` doit être trié par popularité décroissante : la position est le rang (1, 2, ...).
    Lève DonneeInvalideError si `top` est vide.
    """
    if not top:
        raise DonneeInvalideError("Liste de commandants vide : rien à assembler.")

    lignes = []
    for position, carte in enumerate(top, start=1):
        ligne: dict = {
            "nom": carte["name"],
            "position": position,
            "cmc": carte["cmc"],
            "annee": int(carte["released_at"][:4]),
            "identite_couleur": "".join(carte.get("color_identity", [])) or "C",
            "type_principal": type_principal(carte["type_line"]),
        }
        for tag, ids in par_tag.items():
            ligne[f"tag_{tag}"] = int(carte["id"] in ids)
        ligne["nb_tags"] = sum(ligne[f"tag_{tag}"] for tag in par_tag)
        lignes.append(ligne)
    return pd.DataFrame(lignes)


def sauvegarder_csv(df: pd.DataFrame, chemin: str) -> None:
    """Écrit le DataFrame en CSV (crée le dossier au besoin)."""
    dossier = os.path.dirname(chemin)
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    df.to_csv(chemin, index=False)


def lire_csv_par_blocs(chemin: str, taille: int = 200) -> Iterator[pd.DataFrame]:
    """Générateur (ch. 7) : lit le CSV par blocs de `taille` lignes.

    Lève DonneeInvalideError si le fichier n'existe pas.
    """
    if not os.path.exists(chemin):
        raise DonneeInvalideError(f"Fichier introuvable : {chemin}")
    with open(chemin, encoding="utf-8") as f:
        yield from pd.read_csv(f, chunksize=taille)


# ----------------------------------------------------------------- Vérification
def verifier_criteres(df: pd.DataFrame, cible: str = "position") -> dict[str, bool]:
    """Vérifie les critères de la section 2 de l'énoncé et retourne un bilan.

    Les colonnes d'entrée sont toutes sauf `nom` et la cible.
    """
    entrees = df.drop(columns=[c for c in ("nom", cible) if c in df.columns])
    return {
        "lignes_500_a_50000": 500 <= len(df) <= 50_000,
        "au_moins_5_colonnes_entree": entrees.shape[1] >= 5,
        "cible_numerique": cible in df.columns and pd.api.types.is_numeric_dtype(df[cible]),
        "une_variable_numerique": any(
            pd.api.types.is_numeric_dtype(entrees[c]) and not c.startswith("tag_")
            for c in entrees.columns),
        "une_variable_categorielle": any(
            not pd.api.types.is_numeric_dtype(entrees[c]) for c in entrees.columns),
    }


def graphique_identites(df: pd.DataFrame, chemin: str, n: int = 15) -> None:
    """Enregistre un histogramme des `n` identités de couleur les plus fréquentes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    comptes = df["identite_couleur"].value_counts().head(n)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(comptes.index, comptes.values)
    ax.set_title("Commandants du top 1000 par identité de couleur")
    ax.set_xlabel("Identité de couleur")
    ax.set_ylabel("Nombre de commandants")
    dossier = os.path.dirname(chemin)
    if dossier:
        os.makedirs(dossier, exist_ok=True)
    fig.tight_layout()
    fig.savefig(chemin, dpi=150)
    plt.close(fig)
