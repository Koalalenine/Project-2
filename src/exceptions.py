"""Exceptions personnalisées du projet."""


class DonneeInvalideError(Exception):
    """Levée quand des données sont absentes, vides ou ne respectent pas les critères."""


class ScryfallError(Exception):
    """Levée quand l'API Scryfall est injoignable ou répond avec une erreur."""
