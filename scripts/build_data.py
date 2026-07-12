#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prépare les données NLP et les statistiques pour le site d'inspection.

Reprend l'esprit du chapitre 13 (fréquences, expressions, K-means) et va plus
loin : entités nommées (spaCy NER), modélisation thématique (LDA) et
concordances côté client.
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import spacy
from sklearn.cluster import KMeans
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw.csv"
DOCS_DATA = ROOT / "docs" / "data"
LETTERS_JSON = DOCS_DATA / "letters.json"
STATS_JSON = DOCS_DATA / "stats.json"

PHRASES = [
    "petite maman",
    "ma chère",
    "mon petit",
    "adieu",
    "courage",
    "vive la france",
    "je meurs",
    "innocent",
]

# Bruit fréquent dans les entités à écarter (faux positifs du petit modèle).
ENTITY_STOP = {
    "n", "s", "d", "l", "c", "j", "m", "t", "qu", "jusqu", "»", "«",
    "vive", "adieu", "maman", "sois", "monsieur", "madame", "cher", "chère",
    "chéri", "chérie", "français", "française", "dieu", "papa", "maman",
    "bonjour", "bonne", "courage", "merci", "petite", "petit", "mort",
}


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def build_clusters(texts: list[str], french_stopwords: set[str]) -> tuple[list[int], list[dict]]:
    non_empty = [(i, t) for i, t in enumerate(texts) if t.strip()]
    if len(non_empty) < 2:
        return [0] * len(texts), []

    indices, corpus = zip(*non_empty)
    vectorizer = TfidfVectorizer(
        max_features=5000,
        stop_words=list(french_stopwords),
        token_pattern=r"[a-zàâäéèêëïîôöùûüÿç]{3,}",
    )
    matrix = vectorizer.fit_transform(corpus)
    kmeans = KMeans(n_clusters=2, random_state=0, n_init=50, max_iter=1000)
    labels = kmeans.fit_predict(matrix)
    terms = vectorizer.get_feature_names_out()
    order = kmeans.cluster_centers_.argsort()[:, ::-1]

    cluster_info = []
    for cluster_id in range(2):
        keywords = [terms[i] for i in order[cluster_id, :15]]
        cluster_info.append({
            "id": cluster_id,
            "size": int((labels == cluster_id).sum()),
            "keywords": keywords,
        })

    result = [0] * len(texts)
    for idx, label in zip(indices, labels):
        result[idx] = int(label)
    return result, cluster_info


def build_topics(texts: list[str], french_stopwords: set[str]) -> list[dict]:
    corpus = [t for t in texts if t.strip()]
    if len(corpus) < 3:
        return []

    vectorizer = CountVectorizer(
        max_features=3000,
        max_df=0.9,
        min_df=3,
        stop_words=list(french_stopwords),
        token_pattern=r"[a-zàâäéèêëïîôöùûüÿç]{3,}",
    )
    matrix = vectorizer.fit_transform(corpus)
    terms = vectorizer.get_feature_names_out()

    lda = LatentDirichletAllocation(
        n_components=4,
        random_state=0,
        max_iter=25,
        learning_method="batch",
    )
    lda.fit(matrix)

    topics = []
    for topic_id, weights in enumerate(lda.components_):
        top = weights.argsort()[::-1][:10]
        topics.append({
            "id": topic_id,
            "keywords": [terms[i] for i in top],
        })
    return topics


def phrase_stats(texts: list[str]) -> list[dict]:
    stats = []
    total = sum(1 for t in texts if t.strip())
    for phrase in PHRASES:
        docs = sum(1 for text in texts if phrase in text.lower())
        occurrences = sum(text.lower().count(phrase) for text in texts)
        stats.append({
            "phrase": phrase,
            "documents": docs,
            "occurrences": occurrences,
            "percentage": round(100 * docs / total, 1) if total else 0,
        })
    return sorted(stats, key=lambda s: s["documents"], reverse=True)


ELISION_RE = re.compile(r"^\s*(?:[a-zàâäéèêëïîôöùûüÿç]{1,3})['’ʼ]", flags=re.IGNORECASE)


def clean_entity(text: str) -> str:
    text = normalize(text)
    # Retire une élision en tête ("j'", "qu'", "jusqu'"…).
    text = ELISION_RE.sub("", text)
    text = text.strip(" \n\t.,;:!?«»\"'’ʼ()")
    return re.sub(r"\s+", " ", text)


def valid_entity(value: str) -> bool:
    if not value or len(value) < 2:
        return False
    if value.lower() in ENTITY_STOP:
        return False
    if "'" in value or "’" in value:
        return False
    # Une entité (lieu, personne, organisation) commence par une majuscule.
    return any(ch.isupper() for ch in value)


def main() -> None:
    if not RAW_CSV.exists():
        raise FileNotFoundError(f"Fichier introuvable : {RAW_CSV}. Lancez d'abord scripts/scrape.py")

    df = pd.read_csv(RAW_CSV)
    df["letter_text"] = df["letter_text"].fillna("").astype(str).map(normalize)
    df["word_count"] = df["letter_text"].apply(word_count)
    df["has_letter"] = df["letter_text"].str.strip().astype(bool)

    nlp = spacy.load("fr_core_news_sm")
    french_stopwords = nlp.Defaults.stop_words

    texts = df["letter_text"].tolist()
    letter_docs = list(nlp.pipe(texts, batch_size=32))

    word_freq = Counter()
    noun_freq = Counter()
    verb_freq = Counter()
    adj_freq = Counter()
    word_in_docs = defaultdict(set)
    loc_freq = Counter()
    per_freq = Counter()
    org_freq = Counter()

    for row_idx, doc in enumerate(letter_docs):
        if not df.iloc[row_idx]["has_letter"]:
            continue
        seen = set()
        for token in doc:
            if not token.is_alpha or token.is_stop or len(token.lemma_) < 3:
                continue
            lemma = token.lemma_.lower()
            word_freq[lemma] += 1
            seen.add(lemma)
            if token.pos_ == "NOUN":
                noun_freq[lemma] += 1
            elif token.pos_ == "VERB":
                verb_freq[lemma] += 1
            elif token.pos_ == "ADJ":
                adj_freq[lemma] += 1
        for lemma in seen:
            word_in_docs[lemma].add(row_idx)
        for ent in doc.ents:
            value = clean_entity(ent.text)
            if not valid_entity(value):
                continue
            if ent.label_ == "LOC":
                loc_freq[value] += 1
            elif ent.label_ == "PER":
                per_freq[value] += 1
            elif ent.label_ == "ORG":
                org_freq[value] += 1

    doc_freq = Counter({word: len(docs) for word, docs in word_in_docs.items()})

    clusters, cluster_info = build_clusters(texts, french_stopwords)
    df["cluster"] = clusters
    topics = build_topics(texts, french_stopwords)

    letters = []
    for _, row in df.iterrows():
        letters.append({
            "first_letter": row["first_letter"],
            "person_name": row["person_name"],
            "person_url": row["person_url"],
            "letter_text": row["letter_text"],
            "word_count": int(row["word_count"]),
            "has_letter": bool(row["has_letter"]),
            "cluster": int(row["cluster"]),
        })

    by_letter = (
        df.groupby("first_letter")
        .agg(total=("person_name", "count"), with_letter=("has_letter", "sum"))
        .reset_index()
        .sort_values("first_letter")
    )

    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": "https://fusilles-40-44.maitron.fr/yzfusillesdivers/1-lettres-de-fusilles/",
        "summary": {
            "total_persons": int(len(df)),
            "with_letter": int(df["has_letter"].sum()),
            "without_letter": int((~df["has_letter"]).sum()),
            "total_words": int(df["word_count"].sum()),
            "avg_words": round(float(df.loc[df["has_letter"], "word_count"].mean()), 1)
            if df["has_letter"].any()
            else 0,
            "max_words": int(df["word_count"].max()),
        },
        "by_letter": [
            {
                "letter": row["first_letter"],
                "total": int(row["total"]),
                "with_letter": int(row["with_letter"]),
            }
            for _, row in by_letter.iterrows()
        ],
        "top_words": [{"word": w, "count": c} for w, c in word_freq.most_common(40)],
        "top_nouns": [{"word": w, "count": c} for w, c in noun_freq.most_common(20)],
        "top_verbs": [{"word": w, "count": c} for w, c in verb_freq.most_common(20)],
        "top_adjectives": [{"word": w, "count": c} for w, c in adj_freq.most_common(15)],
        "top_words_by_doc": [{"word": w, "count": c} for w, c in doc_freq.most_common(20)],
        "entities": {
            "locations": [{"word": w, "count": c} for w, c in loc_freq.most_common(25)],
            "persons": [{"word": w, "count": c} for w, c in per_freq.most_common(20)],
            "organisations": [{"word": w, "count": c} for w, c in org_freq.most_common(15)],
        },
        "phrase_stats": phrase_stats(texts),
        "clusters": cluster_info,
        "topics": topics,
    }

    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    LETTERS_JSON.write_text(json.dumps(letters, ensure_ascii=False, indent=2), encoding="utf-8")
    STATS_JSON.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    processed_csv = ROOT / "data" / "processed.csv"
    df.to_csv(processed_csv, index=False)
    print(f"[DONE] {len(letters)} lettres -> {LETTERS_JSON}")
    print(f"[DONE] statistiques -> {STATS_JSON}")
    print(f"[DONE] CSV traité -> {processed_csv}")


if __name__ == "__main__":
    main()
