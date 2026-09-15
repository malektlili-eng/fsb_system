"""
tests/test_rag_chunking.py
─────────────────────────────────────────────────────────────────────
Tests de la stratégie de chunking et des backends d'embeddings.
Aucune BD ni réseau requis (SimpleTestCase).
─────────────────────────────────────────────────────────────────────
"""
from django.test import SimpleTestCase

from apps.ai_agent.rag.chunking import (
    DEFAULT_CHUNK_SIZE,
    Chunk,
    chunk_markdown,
    serialize_record,
    split_sentences,
)
from apps.ai_agent.rag.embeddings import TfidfBackend, get_backend

SAMPLE_MD = """# Document de test

## Section A

Première phrase de la section A. Deuxième phrase avec du contenu utile.
Troisième phrase qui parle d'inscription administrative. Quatrième phrase
sur les délais de dépôt. Cinquième phrase de remplissage pour la taille.
Sixième phrase encore plus longue pour dépasser la taille cible du chunk
et forcer la création d'une seconde fenêtre glissante.

## Section B

Une seule phrase courte ici.
"""


class SplitSentencesTest(SimpleTestCase):
    def test_decoupe_sur_ponctuation(self):
        sentences = split_sentences(
            "Première phrase. Deuxième phrase ! Troisième ?"
        )
        self.assertEqual(len(sentences), 3)
        self.assertTrue(sentences[0].startswith("Première"))

    def test_texte_vide(self):
        self.assertEqual(split_sentences("   "), [])


class ChunkMarkdownTest(SimpleTestCase):
    def setUp(self):
        self.chunks = chunk_markdown(SAMPLE_MD, source_doc="test_doc")

    def test_produit_des_chunks(self):
        self.assertGreaterEqual(len(self.chunks), 2)

    def test_chunks_respectent_taille_approx(self):
        """Aucun chunk ne dépasse largement la taille cible (+1 phrase)."""
        for chunk in self.chunks:
            self.assertLessEqual(len(chunk.content), DEFAULT_CHUNK_SIZE + 250)

    def test_prefixe_section_dans_texte_embarque(self):
        """Chaque chunk embarque son chemin de section [Doc > Section]."""
        for chunk in self.chunks:
            self.assertTrue(chunk.text.startswith("["), chunk.text)
            self.assertIn("Document de test", chunk.section)

    def test_sections_distinctes(self):
        sections = {chunk.section for chunk in self.chunks}
        self.assertTrue(any("Section A" in s for s in sections))

    def test_chevauchement_entre_chunks_consecutifs(self):
        """Deux chunks consécutifs d'une même section partagent une phrase."""
        section_a = [c for c in self.chunks if "Section A" in c.section]
        if len(section_a) >= 2:
            first, second = section_a[0], section_a[1]
            last_sentence = split_sentences(first.content)[-1]
            self.assertIn(last_sentence, second.content)

    def test_chunk_ids_uniques_et_stables(self):
        ids = [chunk.chunk_id for chunk in self.chunks]
        self.assertEqual(len(ids), len(set(ids)))
        rebuilt = chunk_markdown(SAMPLE_MD, source_doc="test_doc")
        self.assertEqual(ids, [chunk.chunk_id for chunk in rebuilt])

    def test_serialisation_round_trip(self):
        original = self.chunks[0]
        restored = Chunk.from_dict(original.as_dict())
        self.assertEqual(original.chunk_id, restored.chunk_id)
        self.assertEqual(original.text, restored.text)


class SerializeRecordTest(SimpleTestCase):
    def test_fiche_entite(self):
        chunk = serialize_record(
            kind="filière",
            identifier="LFI",
            fields={"Filière": "Licence Informatique", "Niveau": "L3",
                    "Vide": None},
        )
        self.assertIn("Fiche filière LFI", chunk.text)
        self.assertIn("Licence Informatique", chunk.content)
        self.assertNotIn("Vide", chunk.content)
        self.assertEqual(chunk.metadata["kind"], "filière")


class TfidfBackendTest(SimpleTestCase):
    TEXTS = [
        "L'inscription administrative se fait en septembre.",
        "La session de rattrapage a lieu fin juin.",
        "Le stage de fin d'études dure douze semaines.",
    ]

    def test_encode_retourne_du_creux(self):
        """
        Contrat de passage à l'échelle : le backend par défaut DOIT
        renvoyer du creux. Densifier coûterait ~700 Mo à 20 000 chunks
        (OOM constaté) ; ce test verrouille la propriété.
        """
        import scipy.sparse as sp

        backend = TfidfBackend()
        backend.fit(self.TEXTS)
        vectors = backend.encode(self.TEXTS)
        self.assertTrue(
            sp.issparse(vectors),
            "TfidfBackend doit rester creux (cf. étude de scaling).",
        )

    def test_encode_normalise(self):
        import numpy as np

        backend = TfidfBackend()
        backend.fit(self.TEXTS)
        vectors = backend.encode(self.TEXTS)
        self.assertEqual(vectors.shape[0], 3)
        # Norme L2 ligne par ligne, en restant en creux.
        norms = np.sqrt(np.asarray(vectors.multiply(vectors).sum(axis=1))).ravel()
        for norm in norms:
            self.assertAlmostEqual(float(norm), 1.0, places=5)

    def test_similarite_coherente(self):
        """Une requête proche d'un texte doit lui être la plus similaire."""
        import numpy as np

        backend = TfidfBackend()
        backend.fit(self.TEXTS)
        matrix = backend.encode(self.TEXTS)
        query = backend.encode_one("Quand se fait l'inscription administrative ?")
        scores = np.asarray((matrix @ query.T).todense()).ravel()
        self.assertEqual(int(scores.argmax()), 0)

    def test_svd_produit_du_dense(self):
        """L'option SVD (ablation A5) bascule volontairement en dense."""
        import numpy as np

        backend = TfidfBackend(svd_components=2)
        backend.fit(self.TEXTS)
        vectors = backend.encode(self.TEXTS)
        self.assertIsInstance(vectors, np.ndarray)
        self.assertEqual(vectors.shape, (3, 2))

    def test_encode_avant_fit_leve_erreur(self):
        backend = TfidfBackend()
        with self.assertRaises(RuntimeError):
            backend.encode(["texte"])

    def test_fabrique_retourne_tfidf_par_defaut(self):
        backend = get_backend("tfidf")
        self.assertIsInstance(backend, TfidfBackend)


class SemanticBackendTest(SimpleTestCase):
    """
    Backends sémantiques de l'ablation A4. Ils dépendent d'un modèle
    pré-entraîné : si celui-ci est absent de l'environnement, les tests
    sont ignorés (skip) plutôt que d'échouer — mais le repli est, lui,
    toujours vérifié.
    """

    TEXTS = [
        "L'inscription administrative se fait en septembre.",
        "La session de rattrapage a lieu fin juin.",
        "Le stage de fin d'études dure douze semaines.",
    ]

    def _spacy_or_skip(self):
        from apps.ai_agent.rag.embeddings import SpacyVectorBackend

        try:
            return SpacyVectorBackend()
        except ImportError as exc:
            self.skipTest(f"Modèle spaCy indisponible : {exc}")

    def test_spacy_encode_dense_normalise(self):
        import numpy as np

        backend = self._spacy_or_skip()
        backend.fit(self.TEXTS)
        vectors = backend.encode(self.TEXTS)
        self.assertIsInstance(vectors, np.ndarray)
        self.assertEqual(vectors.shape[0], 3)
        for norm in np.linalg.norm(vectors, axis=1):
            self.assertAlmostEqual(float(norm), 1.0, places=4)

    def test_spacy_capture_la_paraphrase(self):
        """
        Raison d'être du backend : rapprocher des formulations qui ne
        partagent pas leur vocabulaire (limite connue de TF-IDF).
        """
        backend = self._spacy_or_skip()
        backend.fit(self.TEXTS)
        matrix = backend.encode(self.TEXTS)
        query = backend.encode_one("Quand a lieu la seconde chance ?")
        scores = matrix @ query
        # La phrase sur le rattrapage doit ressortir en tête.
        self.assertEqual(int(scores.argmax()), 1)

    def test_hybride_concatene_les_deux_signaux(self):
        from apps.ai_agent.rag.embeddings import HybridDenseSparseBackend

        try:
            backend = HybridDenseSparseBackend(dense_weight=0.5)
        except ImportError as exc:
            self.skipTest(f"Modèle spaCy indisponible : {exc}")
        backend.fit(self.TEXTS)
        vectors = backend.encode(self.TEXTS)
        self.assertEqual(vectors.shape[0], 3)
        # Dimension = dense + lexical concaténés.
        dense_dim = backend._dense.encode(self.TEXTS).shape[1]
        self.assertGreater(vectors.shape[1], dense_dim)

    def test_repli_sur_tfidf_si_backend_indisponible(self):
        """
        get_backend ne doit jamais lever : un backend sémantique absent
        retombe sur TF-IDF (comportement journalisé).
        """
        backend = get_backend("sentence-transformers")
        self.assertIsNotNone(backend)
        self.assertTrue(hasattr(backend, "encode"))

    def test_nom_backend_inconnu_retombe_sur_tfidf(self):
        backend = get_backend("inexistant")
        self.assertIsInstance(backend, TfidfBackend)
