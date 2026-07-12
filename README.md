# Lettres de fusillés — Maitron 1940-1944

Corpus des lettres de fusillés publiées sur le [Maitron 1940-1944](https://fusilles-40-44.maitron.fr/yzfusillesdivers/1-lettres-de-fusilles/), utilisé comme projet de fin du chapitre 13 du livre [*Traitement automatique du langage naturel avec Python*](https://www.editions-eni.fr/livre/traitement-automatique-du-langage-naturel-avec-python-le-nlp-avec-spacy-et-nltk-9782409044984) (Éditions ENI).

## Site d'inspection

**https://thepriben.github.io/maitron-40-44-lettres/**

Interface sobre pour parcourir le corpus, consulter les lettres et visualiser les statistiques lexicales (spaCy, K-means).

## Structure

```
scripts/scrape.py      # acquisition depuis le Maitron
scripts/build_data.py  # traitement NLP et génération des JSON
data/raw.csv           # données brutes
data/processed.csv     # données enrichies
docs/                  # site statique (GitHub Pages)
ch13/                  # matériel du chapitre 13 (livre)
```

## Rafraîchir les données

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download fr_core_news_sm

python scripts/scrape.py
python scripts/build_data.py
```

Le scraping respecte un délai entre les requêtes. Comptez environ 10 minutes pour l'acquisition complète.

## Licence

Les textes appartiennent au Maitron. Ce dépôt ne contient que des scripts d'acquisition et d'analyse à des fins pédagogiques.
