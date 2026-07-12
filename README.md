# Lettres de fusillés — analyse NLP (Maitron 1940-1944)

Chaîne complète de traitement automatique du langage naturel appliquée aux **dernières lettres de fusillés** publiées sur le [Maitron 1940-1944](https://fusilles-40-44.maitron.fr/yzfusillesdivers/1-lettres-de-fusilles/) : acquisition, nettoyage, analyse linguistique et visualisation.

Projet de fin du chapitre 13 du livre [*Traitement automatique du langage naturel avec Python — Le NLP avec spaCy et NLTK*](https://www.editions-eni.fr/livre/traitement-automatique-du-langage-naturel-avec-python-le-nlp-avec-spacy-et-nltk-9782409044984) (Éditions ENI), rafraîchi et étendu.

## Site de visualisation

**https://thepriben.github.io/maitron-40-44-lettres-nlp/**

Corpus consultable, statistiques lexicales, entités nommées, thèmes et concordancier interactif.

## Le pipeline NLP

Le corpus compte **326 fiches** dont **299 lettres** (~115 000 mots). Il est traité avec **spaCy** (modèle `fr_core_news_lg`), **scikit-learn** et **NLTK**.

1. **Acquisition** (`scripts/scrape.py`) — parcours alphabétique de l'index du Maitron, extraction du texte des lettres (`blockquote.poesie`), requêtes espacées et tolérantes aux erreurs.
2. **Prétraitement** — normalisation Unicode, tokenisation, retrait des mots vides français, **lemmatisation** et **étiquetage morphosyntaxique** (POS) via spaCy.
3. **Analyse lexicale** — fréquences globales et par catégorie grammaticale (noms, verbes, adjectifs), fréquence documentaire, relevé d'expressions récurrentes (« petite maman », « adieu », « vive la France »…).
4. **Reconnaissance d'entités nommées (NER)** — extraction et regroupement des **lieux**, **personnes** et **organisations**, avec filtrage des faux positifs et des élisions.
5. **Regroupement non supervisé** — vectorisation **TF-IDF** puis **K-means** (k=2), qui sépare les lettres intimes (à la famille) des lettres plus politiques/patriotiques.
6. **Modélisation thématique** — **LDA** (Latent Dirichlet Allocation) sur sacs de mots pour dégager les thèmes latents du corpus.
7. **Restitution** (`scripts/build_data.py`) — génération de `docs/data/*.json` consommés par le site (dont un concordancier KWIC calculé côté client).

## Structure

```
scripts/scrape.py      # acquisition depuis le Maitron
scripts/build_data.py  # pipeline NLP -> JSON pour le site
data/raw.csv           # corpus brut (fiche, URL, texte)
data/processed.csv     # corpus enrichi (nb de mots, cluster)
docs/                  # site statique (GitHub Pages)
```

## Reproduire l'analyse

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download fr_core_news_lg   # ou fr_core_news_sm (repli automatique)

python scripts/scrape.py        # acquisition (~15 min, requêtes espacées)
python scripts/build_data.py    # traitement NLP + génération des données du site
```

Aperçu local du site :

```bash
python -m http.server --directory docs 8000
```

## Bibliothèques

`spaCy` · `scikit-learn` · `NLTK` · `pandas` · `BeautifulSoup` / `requests`

## Licence & source

Les textes des lettres appartiennent au **Maitron** et à leurs ayants droit ; ils ne sont pas redistribués ici en dehors des données dérivées à but pédagogique. Le code est publié sous la licence du dépôt (voir `LICENSE`).
