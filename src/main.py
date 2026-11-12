"""Point d'entrée. Volet 1 : collecte des données.

Usage (depuis la racine du dépôt) :
    python -m src.main collecter [--nombre 1000] [--tags ramp,removal,...]
    python -m src.main verifier
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from src import donnees
from src.exceptions import DonneeInvalideError, ScryfallError

DOSSIER = "donnees"
CSV = os.path.join(DOSSIER, "commandants_top1000.csv")
CACHE_TOP = os.path.join(DOSSIER, "cache_top.json")
CACHE_TAGS = os.path.join(DOSSIER, "cache_otags.json")
GRAPHIQUE = os.path.join(DOSSIER, "identites_couleur.png")


def commande_collecter(nombre: int, tags: list[str]) -> None:
    """Télécharge le top, interroge les otags, écrit le CSV et le graphique."""
    top = donnees.collecter_top_commandants(nombre, CACHE_TOP)
    par_tag = donnees.collecter_otags({c["id"] for c in top}, tags, CACHE_TAGS)
    df = donnees.construire_dataframe(top, par_tag)
    donnees.sauvegarder_csv(df, CSV)
    donnees.graphique_identites(df, GRAPHIQUE)
    print(f"{len(df)} lignes écrites dans {CSV}")


def commande_verifier() -> None:
    """Affiche forme, types, valeurs manquantes et bilan des critères."""
    if not os.path.exists(CSV):
        raise DonneeInvalideError(
            f"{CSV} introuvable : lancez d'abord « python -m src.main collecter ».")
    df = pd.read_csv(CSV)
    print("Forme :", df.shape)
    print(df.dtypes.to_string())
    print("Valeurs manquantes :", int(df.isna().sum().sum()))
    for critere, ok in donnees.verifier_criteres(df).items():
        print(f"[{'OK' if ok else 'ÉCHEC'}] {critere}")


def main() -> None:
    """Analyse les arguments et exécute la commande demandée."""
    parseur = argparse.ArgumentParser(description="Projet 2 INF1007 : commandants et otags")
    sous = parseur.add_subparsers(dest="commande", required=True)
    collecte = sous.add_parser("collecter", help="télécharger et construire le CSV")
    collecte.add_argument("--nombre", type=int, default=1000)
    collecte.add_argument("--tags", default=",".join(donnees.TAGS_PAR_DEFAUT),
                          help="otags séparés par des virgules")
    sous.add_parser("verifier", help="vérifier les critères du jeu de données")
    args = parseur.parse_args()

    try:
        if args.commande == "collecter":
            commande_collecter(args.nombre, [t.strip() for t in args.tags.split(",") if t.strip()])
        else:
            commande_verifier()
    except (ScryfallError, DonneeInvalideError) as erreur:
        print(f"Erreur : {erreur}")


if __name__ == "__main__":
    main()
