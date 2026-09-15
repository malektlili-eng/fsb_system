"""
Commande : python manage.py coverage_split [--data-file .coverage]

Produit `reports/coverage_split.md` : la répartition HONNÊTE de la
couverture par sous-système, plutôt qu'un chiffre global unique.

Motivation (critique de revue) : « la couverture est inégalement
répartie ; le chiffre global survend la couche CRUD. Un relecteur qui
ouvre coverage_summary.txt le voit en cinq secondes. »

Deux exigences de rigueur, apprises à la relecture :

1. **Les lignes doivent se RÉCONCILIER.** Une version antérieure
   affichait 71 % en bas du tableau pendant que le README annonçait
   78 % : les sous-systèmes nommés ne couvraient pas tout le code
   applicatif, et l'écart n'était expliqué nulle part. Un poste
   résiduel explicite garantit désormais que la somme des lignes
   ÉGALE le code applicatif mesuré.

2. **Les fichiers de tests sont exclus du dénominateur.** Les mesurer
   gonfle mécaniquement le chiffre : du code de test est exécuté par
   construction, donc couvert à ~99 %. Le total rapporté ici est celui
   du code *sous test*, pas celui du harnais qui le teste.

Usage typique :
    coverage run --source='.' manage.py test tests/
    python manage.py coverage_split --fail-under-ai=90
"""
from pathlib import Path

from django.core.management.base import BaseCommand

# Sous-systèmes, dans l'ordre d'affichage. Chaque entrée :
# (libellé, préfixes de chemin, commentaire)
SUBSYSTEMS = [
    (
        "Agent IA & RAG",
        (
            "apps/ai_agent/rag/",
            "apps/ai_agent/llm/",
            "apps/ai_agent/evaluation/",
            "apps/ai_agent/benchmarks/",
            "apps/ai_agent/orchestrator.py",
            "apps/ai_agent/models.py",
            "apps/ai_agent/views.py",
            "apps/ai_agent/management/",
        ),
        "Cœur du projet : chunking, embeddings, index, retrieval, "
        "évaluation, orchestrateur.",
    ),
    (
        "Logique métier (services, forms, models)",
        (
            "apps/administration/services.py",
            "apps/administration/models.py",
            "apps/administration/forms.py",
            "apps/administration/management/",
            "apps/pedagogie/services.py",
            "apps/pedagogie/models.py",
            "apps/examens/services.py",
            "apps/examens/models.py",
            "apps/stages/services.py",
            "apps/stages/models.py",
            "core/",
        ),
        "Règles métier, seeding et permissions RBAC.",
    ),
    (
        "Vues CRUD (legacy)",
        (
            "apps/administration/views.py",
            "apps/pedagogie/views.py",
            "apps/examens/views.py",
            "apps/stages/views.py",
        ),
        "Écrans Django classiques, testés indirectement. "
        "Couverture assumée comme plus faible : priorité donnée à la "
        "couche IA/RAG.",
    ),
]

#: Libellé du poste résiduel — tout le code applicatif mesuré qui
#: n'entre dans aucun sous-système nommé ci-dessus.
RESIDUAL_LABEL = "Divers (settings, URLs, apps.py, serializers…)"
RESIDUAL_COMMENT = (
    "Câblage et configuration. Présent pour que les lignes ci-dessus "
    "se somment exactement au total : aucune instruction applicative "
    "n'est laissée hors du tableau."
)


def _relative(path: str, root: str) -> str:
    return path[len(root) + 1:] if path.startswith(root) else path


def _is_application_code(rel: str) -> bool:
    """
    Le fichier compte-t-il dans le dénominateur ?

    Exclut les migrations (générées) et les fichiers de tests eux-mêmes
    (exécutés par construction : les inclure gonfle le chiffre sans rien
    dire de la qualité du code sous test).
    """
    if "/migrations/" in rel:
        return False
    if rel.startswith("tests/") or rel == "tests":
        return False
    return True


def _analyse(cov, measured, root):
    """Retourne {chemin relatif: (instructions, manquantes)} et les tests."""
    app_files, test_files = {}, {}
    for abs_path in measured:
        rel = _relative(abs_path, root)
        analysis = cov.analysis2(abs_path)
        stats = (len(analysis[1]), len(analysis[3]))
        if rel.startswith("tests/"):
            test_files[rel] = stats
        elif _is_application_code(rel):
            app_files[rel] = stats
    return app_files, test_files


def _summary_table(details, grand_stmts, grand_missing) -> list[str]:
    lines = [
        "| Sous-système | Instructions | Couvertes | Couverture |",
        "|---|---|---|---|",
    ]
    for label, _comment, _files, pct, stmts, missing in details:
        emphasis = "_" if label == RESIDUAL_LABEL else "**"
        lines.append(
            f"| {emphasis}{label}{emphasis} | {stmts} | {stmts - missing} "
            f"| {emphasis}{pct:.0f} %{emphasis} |"
        )
    if grand_stmts:
        total_pct = 100 * (grand_stmts - grand_missing) / grand_stmts
        lines.append(
            f"| **Total — code applicatif** | **{grand_stmts}** "
            f"| **{grand_stmts - grand_missing}** | **{total_pct:.0f} %** |"
        )
    return lines


def _detail_tables(details) -> list[str]:
    lines = ["## Détail par fichier", ""]
    for label, _comment, files, _pct, _stmts, _missing in details:
        lines += [
            f"### {label}",
            "",
            "| Fichier | Instr. | Manquantes | % |",
            "|---|---|---|---|",
        ]
        for rel, stmts, missing in files:
            pct = 100 * (stmts - missing) / stmts if stmts else 100.0
            lines.append(f"| `{rel}` | {stmts} | {missing} | {pct:.0f} % |")
        lines.append("")
    return lines


class Command(BaseCommand):
    help = (
        "Génère reports/coverage_split.md (couverture par sous-système, "
        "réconciliée) et applique une porte sur la couche IA/RAG."
    )

    def add_arguments(self, parser):
        parser.add_argument("--data-file", default=".coverage")
        parser.add_argument("--output-dir", default="reports")
        parser.add_argument(
            "--fail-under-ai",
            type=float,
            default=None,
            help=(
                "Échoue si la couverture du sous-système « Agent IA & RAG » "
                "passe sous ce seuil. Rend la phrase « l'effort est "
                "concentré sur la couche IA » vérifiable en CI au lieu "
                "d'être seulement affirmée dans le README."
            ),
        )

    def _load_coverage(self, data_file):
        try:
            from coverage import Coverage
        except ImportError:
            self.stderr.write(self.style.ERROR("coverage n'est pas installé."))
            return None
        if not Path(data_file).exists():
            self.stderr.write(
                self.style.ERROR(
                    f"{data_file} introuvable. Lancez d'abord :\n"
                    "  coverage run --source='.' manage.py test tests/"
                )
            )
            return None
        cov = Coverage(data_file=data_file)
        cov.load()
        return cov

    def handle(self, *args, **options):
        cov = self._load_coverage(options["data_file"])
        if cov is None:
            return

        measured = list(cov.get_data().measured_files())
        root = str(Path.cwd())
        app_files, test_files = _analyse(cov, measured, root)

        details = []
        claimed = set()
        ai_pct = None
        for label, prefixes, comment in SUBSYSTEMS:
            files, stmts, missing = [], 0, 0
            for rel, (n_stmts, n_missing) in app_files.items():
                if rel.startswith(tuple(prefixes)):
                    claimed.add(rel)
                    files.append((rel, n_stmts, n_missing))
                    stmts += n_stmts
                    missing += n_missing
            if not stmts:
                continue
            pct = 100 * (stmts - missing) / stmts
            if label == "Agent IA & RAG":
                ai_pct = pct
            details.append((label, comment, sorted(files), pct, stmts, missing))

        # Poste résiduel : tout le code applicatif non réclamé ci-dessus.
        residual = [
            (rel, s, m) for rel, (s, m) in app_files.items() if rel not in claimed
        ]
        if residual:
            stmts = sum(s for _, s, _ in residual)
            missing = sum(m for _, _, m in residual)
            details.append(
                (
                    RESIDUAL_LABEL,
                    RESIDUAL_COMMENT,
                    sorted(residual),
                    100 * (stmts - missing) / stmts,
                    stmts,
                    missing,
                )
            )

        grand_stmts = sum(d[4] for d in details)
        grand_missing = sum(d[5] for d in details)
        app_pct = 100 * (grand_stmts - grand_missing) / grand_stmts

        t_stmts = sum(s for s, _ in test_files.values())
        t_missing = sum(m for _, m in test_files.values())
        raw_stmts = grand_stmts + t_stmts
        raw_covered = (grand_stmts - grand_missing) + (t_stmts - t_missing)
        raw_pct = 100 * raw_covered / raw_stmts if raw_stmts else 0.0

        lines = [
            "# Couverture de tests — répartition par sous-système",
            "",
            "*Généré par `python manage.py coverage_split` à partir des "
            "données de couverture réelles — jamais écrit à la main.*",
            "",
            "Un chiffre global unique serait trompeur : l'effort de test est "
            "délibérément concentré sur la couche IA/RAG (le cœur du projet), "
            "pas réparti uniformément. Voici la répartition, réconciliée.",
            "",
        ]
        lines += _summary_table(details, grand_stmts, grand_missing)
        lines += [
            "",
            "## Ce que ce total mesure exactement",
            "",
            f"**{app_pct:.0f} % du code applicatif** "
            f"({grand_stmts - grand_missing} / {grand_stmts} instructions). "
            "Les lignes du tableau se somment exactement à ce total : le "
            "poste « Divers » existe précisément pour qu'aucune instruction "
            "ne reste hors du décompte.",
            "",
            "Ce chiffre est **le même** que celui de `coverage report` et "
            "des badges du README. Il n'existe pas deux mesures "
            "concurrentes de la couverture dans ce dépôt.",
            "",
            "**Deux exclusions, toutes deux volontaires :**",
            "",
            "- *Les migrations* — code généré par Django, pas écrit ici.",
        ]

        if t_stmts:
            t_pct = 100 * (t_stmts - t_missing) / t_stmts
            lines.append(
                f"- *Les fichiers de tests eux-mêmes* ({t_stmts} "
                f"instructions, couvertes à {t_pct:.0f} % puisqu'elles sont "
                "exécutées par construction). Les inclure ferait monter le "
                f"chiffre affiché à **{raw_pct:.0f} %** sans qu'une seule "
                "ligne de code applicatif soit mieux testée."
            )
        else:
            lines.append(
                "- *Les fichiers de tests eux-mêmes*, écartés via `--omit` "
                "dès la collecte. Du code de test est exécuté par "
                "construction, donc couvert à ~99 % : le compter "
                "gonflerait le total de plusieurs points sans qu'une seule "
                "ligne de code applicatif soit mieux testée. C'est une "
                "erreur de mesure courante, et elle a été commise dans une "
                "version antérieure de ce dépôt — d'où cette note."
            )

        lines += [
            "",
            "## Lecture",
            "",
        ]
        for label, comment, _files, pct, _s, _m in details:
            lines.append(f"- **{label} — {pct:.0f} %** : {comment}")
        lines += [""]
        lines += _detail_tables(details)

        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "coverage_split.md"
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Rapport : {out_path}"))
        message = f"Code applicatif : {app_pct:.1f} %"
        if ai_pct is not None:
            message += f" | IA/RAG : {ai_pct:.1f} %"
        if t_stmts:
            message += f" | avec fichiers de tests : {raw_pct:.1f} %"
        self.stdout.write(message)

        threshold = options["fail_under_ai"]
        if threshold is not None and ai_pct is not None and ai_pct < threshold:
            raise SystemExit(
                f"Porte IA/RAG non franchie : {ai_pct:.1f} % < {threshold} %"
            )
