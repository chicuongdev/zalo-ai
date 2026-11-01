"""Semantic library: rulebook-exact computations over the CDM."""
from . import intents, intents_ops  # noqa: F401  (registers every intent)
from .intents import INTENTS, NotSupported, Unanswerable, execute  # noqa: F401
from .store import RuleConfig, ShopStore  # noqa: F401
