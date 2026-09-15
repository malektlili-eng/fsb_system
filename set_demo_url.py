#!/usr/bin/env python3
"""
set_demo_url.py — Reporte l'URL de démonstration dans tout le dépôt.

    python set_demo_url.py https://fsb-system-xxxx.onrender.com

Pourquoi ce script : après le déploiement, l'URL réelle doit remplacer
l'espace réservé à PLUSIEURS endroits (README, DEPLOYMENT). Le faire à
la main, c'est en oublier un et laisser traîner une URL morte — le
genre de détail qu'un relecteur remarque immédiatement sur un projet
qui se présente comme une ancre d'ingénierie.

Le script est idempotent et vérifie l'URL avant d'écrire quoi que ce
soit. Sans argument, il signale simplement l'état courant.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PLACEHOLDER = "https://fsb-system.onrender.com"

#: Fichiers susceptibles de contenir l'URL de démonstration.
TARGETS = ("README.md", "DEPLOYMENT.md")

URL_RE = re.compile(r"^https://[A-Za-z0-9._-]+(?::\d+)?(?:/\S*)?$")


def _current_urls() -> dict[str, list[str]]:
    """URL(s) de démonstration actuellement inscrites, par fichier."""
    found: dict[str, list[str]] = {}
    pattern = re.compile(r"https://[A-Za-z0-9._-]*onrender\.com[^\s`)\"']*")
    for name in TARGETS:
        path = Path(name)
        if not path.exists():
            continue
        hits = sorted(set(pattern.findall(path.read_text(encoding="utf-8"))))
        if hits:
            found[name] = hits
    return found


def _report_state() -> int:
    urls = _current_urls()
    if not urls:
        print("Aucune URL de démonstration trouvée dans", ", ".join(TARGETS))
        return 0
    print("État actuel :")
    for name, hits in urls.items():
        for url in hits:
            flag = "  (ESPACE RÉSERVÉ)" if url == PLACEHOLDER else ""
            print(f"  {name:16s} → {url}{flag}")
    if any(PLACEHOLDER in h for h in urls.values()):
        print(
            "\nL'espace réservé est toujours en place. Après déploiement :"
            f"\n  python {Path(__file__).name} https://votre-url.onrender.com"
        )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return _report_state()

    new_url = argv[1].rstrip("/")
    if not URL_RE.match(new_url):
        print(f"URL invalide : {new_url!r} (attendu : https://…)", file=sys.stderr)
        return 2

    changed = []
    for name in TARGETS:
        path = Path(name)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if PLACEHOLDER not in text:
            continue
        path.write_text(text.replace(PLACEHOLDER, new_url), encoding="utf-8")
        changed.append(name)

    if not changed:
        print(
            "Rien à remplacer : l'espace réservé n'apparaît plus.\n"
            "L'URL a probablement déjà été reportée."
        )
        return _report_state()

    print(f"URL reportée dans : {', '.join(changed)}")
    print(f"  → {new_url}")
    print(
        "\nReste à faire à la main (une phrase, pas une URL) : retirer la "
        "mention « espace réservé » sous le badge du README, qui n'a plus "
        "lieu d'être une fois l'instance en service."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
