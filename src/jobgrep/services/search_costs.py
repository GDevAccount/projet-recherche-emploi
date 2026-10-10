"""Coût d'une recherche, calculé à la lecture à partir de ce qu'elle a consommé et des tarifs de config.py.

Rien de ceci n'est enregistré : un tarif corrigé corrige aussi le coût affiché des recherches passées.
"""

from collections.abc import Iterable

from jobgrep.config import MODEL_PRICES_USD, TAVILY_CREDIT_PRICE_USD, TAVILY_CREDITS_PER_SEARCH

TOKENS_PER_PRICE_UNIT = 1_000_000
# Un appel au modèle coûte des fractions de centime : arrondir plus court effacerait le coût d'une page
COST_DECIMALS = 6


def search_cost_usd(search_calls: int | None) -> float | None:
    """Renvoie le coût des appels au moteur de recherche, ou None si leur nombre n'est pas connu."""
    if search_calls is None:
        return None
    return round(search_calls * TAVILY_CREDITS_PER_SEARCH * TAVILY_CREDIT_PRICE_USD, COST_DECIMALS)


def model_cost_usd(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
) -> float | None:
    """Renvoie le coût des appels au modèle, ou None si ses jetons ou son tarif ne sont pas connus.

    Les jetons lus ou écrits en cache font partie des jetons d'entrée, à un autre tarif.
    """
    price = MODEL_PRICES_USD.get(model)
    if price is None or input_tokens is None:
        return None
    cache_read = cache_read_tokens or 0
    cache_write = cache_write_tokens or 0
    fresh = max(input_tokens - cache_read - cache_write, 0)
    cost = (
        fresh * price.input
        + cache_read * price.cache_read
        + cache_write * price.cache_write
        + (output_tokens or 0) * price.output
    )
    return round(cost / TOKENS_PER_PRICE_UNIT, COST_DECIMALS)


def total_cost_usd(search_cost: float | None, model_cost: float | None, has_model_usage: bool) -> float | None:
    """Renvoie le coût total, ou None s'il manque une part qu'on sait avoir été consommée.

    Une recherche arrêtée avant l'évaluation n'a rien coûté au modèle : son total est celui du moteur de recherche.
    """
    if search_cost is None or (has_model_usage and model_cost is None):
        return None
    return round(search_cost + (model_cost or 0), COST_DECIMALS)


def sum_costs(costs: Iterable[float | None]) -> float | None:
    """Additionne des coûts, et renvoie None si l'un d'eux n'est pas connu : un total partiel tromperait."""
    costs = list(costs)
    return None if None in costs else round(sum(costs), COST_DECIMALS)
