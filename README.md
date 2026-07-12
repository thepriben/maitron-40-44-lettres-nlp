# Lettres de fusillés — analyse NLP (Maitron 1940-1944)

Chaîne complète de traitement automatique du langage naturel appliquée aux **dernières lettres de fusillés** publiées sur le [Maitron 1940-1944](https://fusilles-40-44.maitron.fr/yzfusillesdivers/1-lettres-de-fusilles/) : acquisition, croisement avec les notices biographiques, analyse linguistique, cartographie et visualisation.

## Le livre

Ce dépôt est le projet de fin (chapitre 13) du livre :

> **Benoît Prieur**, *Traitement automatique du langage naturel avec Python — Le NLP avec spaCy et NLTK*, Éditions ENI, collection Epsilon, 2024, ISBN 978-2-409-04498-4.
> [Page du livre sur le site des Éditions ENI](https://www.editions-eni.fr/livre/traitement-automatique-du-langage-naturel-avec-python-le-nlp-avec-spacy-et-nltk-9782409044984)

La version publiée ici a été rafraîchie et largement étendue : nouvelle acquisition, croisement biographique, NER, LDA, chronologie, cartographie et site de visualisation.

## Site de visualisation

**https://thepriben.github.io/maitron-40-44-lettres-nlp/**

Pensé comme un cahier d'analyse consultable : chronologie des exécutions, carte des lieux, profils des fusillés (âge, engagement), lexique, entités nommées, références historiques (de Gaulle, Pétain, Dieu, la Marseillaise…), comparaison lexicale par engagement, thèmes latents, concordancier et lecture des lettres reliées à leur notice.

## Le pipeline NLP

Le corpus d'étude compte **~300 lettres** (~115 000 mots), chacune reliée à la notice biographique de son auteur. Traitement avec **spaCy** (`fr_core_news_lg`), **scikit-learn** et **pandas**.

1. **Acquisition** (`scripts/scrape.py`) — parcours alphabétique de l'index du Maitron ; extraction du texte des lettres (`blockquote.poesie`) **et du chapô biographique** (`div.chapo`) de chaque notice ; requêtes espacées et tolérantes aux erreurs.
2. **Croisement biographique** — les notices du Maitron suivent un format quasi régulier (« Né le… à…, fusillé le… à… ; profession ; engagement ») exploité par expressions régulières : dates de naissance et d'exécution, âge, département, lieu d'exécution (géolocalisé), affiliations (PCF, FTP, CGT, réseaux gaullistes, otages, catholiques).
3. **Prétraitement** — normalisation Unicode, tokenisation, retrait des mots vides, **lemmatisation** et **étiquetage morphosyntaxique** (POS) via spaCy.
4. **Analyse lexicale** — fréquences lemmatisées globales et par catégorie grammaticale, fréquence documentaire, expressions récurrentes, **références historiques et spirituelles** (de Gaulle, Pétain, Staline, Dieu, la Marseillaise, l'Internationale…).
5. **Reconnaissance d'entités nommées (NER)** — lieux, personnes et organisations cités dans les lettres, avec fusion des variantes de casse (« Parti Communiste » / « Parti communiste ») et filtrage des faux positifs.
6. **Analyse croisée** — comparaison du vocabulaire des fusillés communistes et des autres condamnés (taux de lettres contenant « dieu », « camarade », « vengeance »…).
7. **Structure latente** — **TF-IDF + K-means** (k=2 : adieu intime vs. adieu patriotique) et **LDA** (thèmes latents).
8. **Restitution** (`scripts/build_data.py`) — chronologie mensuelle des exécutions, agrégats pour la carte (Leaflet), distributions (âges, longueurs), JSON consommés par le site statique (graphiques Chart.js, concordancier KWIC côté client).

## Structure

```
scripts/scrape.py      # acquisition (lettres + notices biographiques)
scripts/build_data.py  # pipeline NLP -> JSON pour le site
data/raw.csv           # corpus brut (fiche, URL, bio, texte)
data/processed.csv     # corpus enrichi (âge, date/lieu d'exécution, engagement, cluster)
docs/                  # site statique (GitHub Pages)
```

## Reproduire l'analyse

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download fr_core_news_lg   # ou fr_core_news_sm (repli automatique)

python scripts/scrape.py        # acquisition (~15 min, requêtes espacées)
python scripts/build_data.py    # pipeline NLP + génération des données du site
```

Aperçu local du site :

```bash
python -m http.server --directory docs 8000
```

## Bibliothèques

`spaCy` · `scikit-learn` · `pandas` · `NLTK` · `BeautifulSoup` / `requests` · côté site : `Chart.js` · `Leaflet`

## Licence & source

Les textes des lettres et les notices appartiennent au **Maitron** (Université Paris 1 / Campus Condorcet) et aux ayants droit ; ils sont exploités ici à des fins de recherche et d'enseignement. Le code est publié sous la licence du dépôt (voir `LICENSE`).
