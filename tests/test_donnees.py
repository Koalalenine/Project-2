"""Tests hors ligne de src/donnees.py (l'API Scryfall est simulée)."""
import pandas as pd
import pytest

from src import donnees
from src.exceptions import DonneeInvalideError, ScryfallError


def fausse_carte(identifiant: str, nom: str, couleurs: list[str], type_line: str = "Legendary Creature — Elf",
                 cmc: float = 3.0, date: str = "2020-05-01") -> dict:
    return {"id": identifiant, "name": nom, "color_identity": couleurs,
            "type_line": type_line, "cmc": cmc, "released_at": date}


@pytest.fixture
def top() -> list[dict]:
    return [
        fausse_carte("a", "Alpha", ["G", "B"]),
        fausse_carte("b", "Bravo", [], cmc=5.0, date="2023-01-10"),
        fausse_carte("c", "Charlie", ["W"], type_line="Legendary Creature — Human // Legendary Planeswalker"),
    ]


class FausseReponse:
    def __init__(self, statut: int, contenu: dict | None = None):
        self.status_code = statut
        self._contenu = contenu or {}

    def json(self) -> dict:
        return self._contenu


# ---- cas usuels
def test_dataframe_forme_et_positions(top):
    df = donnees.construire_dataframe(top, {"ramp": {"a"}})
    assert df.shape == (3, 8)  # nom, position, cmc, annee, identite, type, tag_ramp, nb_tags
    assert list(df["position"]) == [1, 2, 3]


def test_tags_binaires_et_nb_tags(top):
    df = donnees.construire_dataframe(top, {"ramp": {"a", "b"}, "draw": {"a"}})
    assert list(df["tag_ramp"]) == [1, 1, 0]
    assert list(df["nb_tags"]) == [2, 1, 0]


def test_identite_couleur(top):
    df = donnees.construire_dataframe(top, {})
    assert list(df["identite_couleur"]) == ["GB", "C", "W"]  # vide -> « C » (incolore)


def test_annee_extraite(top):
    df = donnees.construire_dataframe(top, {})
    assert list(df["annee"]) == [2020, 2023, 2020]


# ---- cas limites
def test_type_principal_double_face():
    assert donnees.type_principal("Legendary Creature — Human // Legendary Planeswalker") == "Legendary Creature"
    assert donnees.type_principal("Legendary Artifact") == "Legendary Artifact"


def test_aucun_tag_donne_nb_tags_zero(top):
    df = donnees.construire_dataframe(top, {})
    assert (df["nb_tags"] == 0).all()


# ---- cas d'erreur
def test_top_vide_leve_erreur():
    with pytest.raises(DonneeInvalideError):
        donnees.construire_dataframe([], {})


def test_charger_json_absent(tmp_path):
    with pytest.raises(DonneeInvalideError):
        donnees.charger_json(str(tmp_path / "absent.json"))


def test_charger_json_invalide(tmp_path):
    chemin = tmp_path / "casse.json"
    chemin.write_text("{pas du json", encoding="utf-8")
    with pytest.raises(DonneeInvalideError):
        donnees.charger_json(str(chemin))


def test_lire_csv_par_blocs_fichier_absent(tmp_path):
    with pytest.raises(DonneeInvalideError):
        list(donnees.lire_csv_par_blocs(str(tmp_path / "absent.csv")))


# ---- fichiers
def test_aller_retour_csv_par_blocs(top, tmp_path):
    df = donnees.construire_dataframe(top, {"ramp": {"a"}})
    chemin = str(tmp_path / "sous" / "cartes.csv")
    donnees.sauvegarder_csv(df, chemin)
    blocs = list(donnees.lire_csv_par_blocs(chemin, taille=2))
    assert [len(b) for b in blocs] == [2, 1]
    assert pd.concat(blocs).reset_index(drop=True).equals(df)


# ---- critères du jeu de données
def test_verifier_criteres_jeu_trop_petit(top):
    bilan = donnees.verifier_criteres(donnees.construire_dataframe(top, {"ramp": {"a"}}))
    assert bilan["lignes_500_a_50000"] is False
    assert bilan["une_variable_categorielle"] is True
    assert bilan["une_variable_numerique"] is True


# ---- API simulée
def test_recuperer_cartes_pagination(monkeypatch):
    pages = {
        "debut": FausseReponse(200, {"data": [{"id": "1"}, {"id": "2"}], "has_more": True,
                                     "next_page": "suite"}),
        "suite": FausseReponse(200, {"data": [{"id": "3"}], "has_more": False}),
    }
    appels = []

    def faux_get(url, headers=None, params=None, timeout=None):
        appels.append(url)
        return pages["debut" if params else "suite"]

    monkeypatch.setattr(donnees.requests, "get", faux_get)
    monkeypatch.setattr(donnees.time, "sleep", lambda s: None)
    assert [c["id"] for c in donnees.recuperer_cartes("q")] == ["1", "2", "3"]
    assert len(appels) == 2


def test_recuperer_cartes_maximum(monkeypatch):
    reponse = FausseReponse(200, {"data": [{"id": str(i)} for i in range(5)], "has_more": True,
                                  "next_page": "suite"})
    monkeypatch.setattr(donnees.requests, "get", lambda *a, **k: reponse)
    monkeypatch.setattr(donnees.time, "sleep", lambda s: None)
    assert len(donnees.recuperer_cartes("q", maximum=3)) == 3


def test_recuperer_cartes_404_donne_liste_vide(monkeypatch):
    monkeypatch.setattr(donnees.requests, "get", lambda *a, **k: FausseReponse(404))
    assert donnees.recuperer_cartes("otag:inexistant") == []


def test_recuperer_cartes_erreur_serveur(monkeypatch):
    monkeypatch.setattr(donnees.requests, "get", lambda *a, **k: FausseReponse(500))
    with pytest.raises(ScryfallError):
        donnees.recuperer_cartes("q")


def test_recuperer_cartes_429_persistant(monkeypatch):
    monkeypatch.setattr(donnees.requests, "get", lambda *a, **k: FausseReponse(429))
    monkeypatch.setattr(donnees.time, "sleep", lambda s: None)
    with pytest.raises(ScryfallError):
        donnees.recuperer_cartes("q")
