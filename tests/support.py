"""
tests/support.py
─────────────────────────────────────────────────────────────────────
Utilitaires partagés par la suite de tests.

Raison d'être : la promesse centrale de ce dépôt est que le pipeline IA
complet (RAG → sélection d'outil → streaming) se teste **sans réseau et
sans clé API**, grâce à `OfflineProvider`. Quelques tests vérifient en
plus le *parsing* propre au SDK Groq (accumulation des tool calls
fragmentés) : ceux-là ont besoin que le paquet `groq` soit importable
pour pouvoir le patcher.

Ils sont donc marqués explicitement. Sans ce marquage, une installation
minimale sans `groq` produirait 4 erreurs et contredirait la promesse
« testable hors-ligne » exactement là où elle est censée tenir.
─────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import importlib.util
import unittest

#: Vrai si le SDK Groq est importable dans cet environnement.
GROQ_SDK_AVAILABLE = importlib.util.find_spec("groq") is not None

#: Décorateur : ignore un test qui a besoin du SDK Groq pour patcher
#: `groq.Groq`. Le comportement testé est propre au fournisseur de
#: production ; le pipeline lui-même reste couvert hors-ligne.
requires_groq_sdk = unittest.skipUnless(
    GROQ_SDK_AVAILABLE,
    "SDK groq absent : test du parsing spécifique au fournisseur de "
    "production ignoré (le pipeline est couvert via OfflineProvider).",
)
