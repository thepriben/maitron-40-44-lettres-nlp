#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pipeline NLP du corpus des lettres de fusillés (Maitron 1940-1944).

Croise le texte des lettres avec les notices biographiques du Maitron :
- parsing des notices (naissance, exécution, âge, lieu, engagement) ;
- lexique lemmatisé (spaCy), entités nommées fusionnées par casse ;
- figures et références historiques (de Gaulle, Pétain, la Marseillaise…) ;
- comparaison lexicale par engagement (communistes / autres) ;
- K-means (TF-IDF) et LDA ;
- chronologie des exécutions et géographie (données pour la carte).

Projet de fin du livre « Traitement automatique du langage naturel avec
Python » (Éditions ENI), chapitre 13, rafraîchi et étendu.
"""

import json
import csv
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd
import spacy
from sklearn.cluster import KMeans
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = ROOT / "data" / "raw.csv"
COMMUNES_CSV = ROOT / "data" / "communes.csv"
DOCS_DATA = ROOT / "docs" / "data"

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

# Figures et références historiques recherchées dans le texte des lettres.
FIGURES = [
    ("de Gaulle", re.compile(r"\bde\s+gaulle\b|\bgénéral\s+gaulle\b", re.IGNORECASE)),
    ("Pétain", re.compile(r"pétain", re.IGNORECASE)),
    ("Hitler", re.compile(r"hitler", re.IGNORECASE)),
    ("Staline", re.compile(r"staline", re.IGNORECASE)),
    ("Thorez", re.compile(r"thorez", re.IGNORECASE)),
    ("Laval", re.compile(r"\blaval\b", re.IGNORECASE)),
    ("Jeanne d'Arc", re.compile(r"jeanne\s+d['’]arc", re.IGNORECASE)),
    ("Jésus / le Christ", re.compile(r"\bjésus\b|\bchrist\b", re.IGNORECASE)),
    ("Dieu", re.compile(r"\bdieu\b", re.IGNORECASE)),
    ("La Marseillaise", re.compile(r"marseillaise", re.IGNORECASE)),
    ("L'Internationale", re.compile(r"l['’]\s?Internationale")),
    ("L'Armée rouge", re.compile(r"armée\s+rouge", re.IGNORECASE)),
    ("L'URSS", re.compile(r"\bURSS\b|union\s+soviétique", re.IGNORECASE)),
]

# Termes comparés entre groupes d'engagement.
COMPARISON_TERMS = [
    "dieu", "camarade", "parti", "france", "maman",
    "adieu", "courage", "liberté", "vengeance", "prêtre",
]

# Bruit fréquent dans les entités à écarter (faux positifs du NER).
ENTITY_STOP = {
    "n", "s", "d", "l", "c", "j", "m", "t", "qu", "jusqu", "»", "«",
    "vive", "adieu", "maman", "sois", "monsieur", "madame", "cher", "chère",
    "chéri", "chérie", "français", "française", "dieu", "papa",
    "bonjour", "bonne", "courage", "merci", "petite", "petit", "mort",
    "chers", "amis", "ps", "chers parents", "chers amis", "vive la france",
    "chéris", "mes chers", "mes chers parents", "soyez", "embrasse",
    "allemands", "boches", "vive la france immortelle",
    "humanité et tu me rappelleras", "remerciez", "interné résistant",
    "cher papa", "chère maman", "rosita",
}

# Faux positifs propres au type ORG (prénoms en capitales, lieux, formules).
ORG_STOP = {
    "robert", "europe", "catholique français", "liberté", "france",
    "libération", "alex", "ir", "chers copains",
}

# Variantes d'une même organisation ramenées à une forme canonique
# (dans ces lettres, « le Parti » désigne toujours le Parti communiste).
ORG_ALIASES = {
    "parti": "Parti communiste",
    "parti communiste": "Parti communiste",
    "parti communiste français": "Parti communiste",
    "pcf": "Parti communiste",
    "communiste": "Parti communiste",
    "jeunesses communistes": "Jeunesses communistes",
    "jeunes communistes": "Jeunesses communistes",
    "jeunesse communiste": "Jeunesses communistes",
    "armée rouge": "Armée rouge",
    "union soviétique": "URSS",
    "tireurs partisans": "Francs-tireurs et partisans",
    "francs-tireurs et partisans": "Francs-tireurs et partisans",
}

MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "décembre": 12,
}

BIRTH_RE = re.compile(
    r"née?\s+le\s+(\d{1,2})(?:er)?\s+([a-zéû]+)\s+(\d{4})(?:\s+à\s+([^(,;]+?)\s*\(([^)]+)\))?",
    re.IGNORECASE,
)
EXEC_RE = re.compile(
    r"(fusillée?s?|exécutée?s?|massacrée?s?|décapitée?s?|abattue?s?|guillotinée?s?|pendue?s?)"
    r"[^;]{0,40}?le\s+(\d{1,2})(?:er)?\s+([a-zéû]+)\s+(\d{4})([^;]*)",
    re.IGNORECASE,
)
DEPT_RE = re.compile(r"\(([^)]+)\)")

# Anciens noms de départements -> noms actuels.
DEPT_ALIASES = {
    "seine": "Seine",
    "seine-inférieure": "Seine-Maritime",
    "loire-inférieure": "Loire-Atlantique",
    "côtes-du-nord": "Côtes-d'Armor",
    "basses-pyrénées": "Pyrénées-Atlantiques",
    "basses-alpes": "Alpes-de-Haute-Provence",
    "charente-inférieure": "Charente-Maritime",
}

# Centroïdes approchés des départements (métropole, noms de l'époque inclus).
DEPT_COORDS = {
    "Ain": (46.10, 5.35), "Aisne": (49.55, 3.55), "Allier": (46.40, 3.20),
    "Alpes-de-Haute-Provence": (44.10, 6.25), "Hautes-Alpes": (44.65, 6.25),
    "Alpes-Maritimes": (43.90, 7.10), "Ardèche": (44.75, 4.40),
    "Ardennes": (49.60, 4.65), "Ariège": (42.95, 1.50), "Aube": (48.30, 4.15),
    "Aude": (43.10, 2.40), "Aveyron": (44.30, 2.65),
    "Bouches-du-Rhône": (43.50, 5.10), "Calvados": (49.10, -0.35),
    "Cantal": (45.05, 2.65), "Charente": (45.70, 0.20),
    "Charente-Maritime": (45.75, -0.75), "Cher": (47.05, 2.50),
    "Corrèze": (45.35, 1.90), "Côte-d'Or": (47.45, 4.80),
    "Côtes-d'Armor": (48.45, -2.85), "Creuse": (46.05, 2.00),
    "Dordogne": (45.15, 0.75), "Doubs": (47.15, 6.35), "Drôme": (44.70, 5.15),
    "Eure": (49.10, 1.00), "Eure-et-Loir": (48.40, 1.40),
    "Finistère": (48.25, -4.05), "Gard": (43.95, 4.20),
    "Haute-Garonne": (43.35, 1.20), "Gers": (43.65, 0.45),
    "Gironde": (44.85, -0.55), "Hérault": (43.60, 3.40),
    "Ille-et-Vilaine": (48.15, -1.65), "Indre": (46.80, 1.60),
    "Indre-et-Loire": (47.25, 0.70), "Isère": (45.25, 5.60),
    "Jura": (46.75, 5.70), "Landes": (43.95, -0.75),
    "Loir-et-Cher": (47.60, 1.40), "Loire": (45.75, 4.15),
    "Haute-Loire": (45.10, 3.80), "Loire-Atlantique": (47.35, -1.70),
    "Loiret": (47.90, 2.35), "Lot": (44.60, 1.60),
    "Lot-et-Garonne": (44.35, 0.45), "Lozère": (44.50, 3.50),
    "Maine-et-Loire": (47.40, -0.55), "Manche": (49.08, -1.30),
    "Marne": (48.95, 4.30), "Haute-Marne": (48.10, 5.20),
    "Mayenne": (48.15, -0.65), "Meurthe-et-Moselle": (48.80, 6.20),
    "Meuse": (48.95, 5.40), "Morbihan": (47.85, -2.80),
    "Moselle": (49.05, 6.70), "Nièvre": (47.10, 3.50), "Nord": (50.45, 3.20),
    "Oise": (49.40, 2.40), "Orne": (48.60, 0.10),
    "Pas-de-Calais": (50.50, 2.30), "Puy-de-Dôme": (45.70, 3.15),
    "Pyrénées-Atlantiques": (43.25, -0.75), "Hautes-Pyrénées": (43.05, 0.15),
    "Pyrénées-Orientales": (42.60, 2.50), "Bas-Rhin": (48.65, 7.60),
    "Haut-Rhin": (47.85, 7.25), "Rhône": (45.85, 4.65),
    "Haute-Saône": (47.65, 6.10), "Saône-et-Loire": (46.65, 4.55),
    "Sarthe": (48.00, 0.20), "Savoie": (45.45, 6.45),
    "Haute-Savoie": (46.05, 6.40), "Seine": (48.85, 2.35),
    "Seine-Maritime": (49.65, 1.00), "Seine-et-Marne": (48.60, 2.95),
    "Seine-et-Oise": (48.80, 2.20), "Deux-Sèvres": (46.55, -0.30),
    "Somme": (49.95, 2.30), "Tarn": (43.80, 2.15),
    "Tarn-et-Garonne": (44.10, 1.35), "Var": (43.45, 6.20),
    "Vaucluse": (44.00, 5.15), "Vendée": (46.65, -1.30),
    "Vienne": (46.55, 0.45), "Haute-Vienne": (45.90, 1.20),
    "Vosges": (48.20, 6.40), "Yonne": (47.85, 3.65),
    "Territoire de Belfort": (47.63, 6.90),
}

# Grands lieux d'exécution : coordonnées précises, détectés par mot-clé.
KNOWN_SITES = [
    ("mont-valérien", "Mont-Valérien (Suresnes)", 48.8742, 2.2159),
    ("mont valérien", "Mont-Valérien (Suresnes)", 48.8742, 2.2159),
    ("châteaubriant", "Châteaubriant (carrière de la Sablière)", 47.7160, -1.3746),
    ("souge", "Camp de Souge (Martignas-sur-Jalle)", 44.8390, -0.7860),
    ("citadelle d'arras", "Citadelle d'Arras", 50.2840, 2.7620),
    ("arras", "Citadelle d'Arras", 50.2840, 2.7620),
    ("bondues", "Fort de Bondues", 50.7010, 3.0940),
    ("la blisière", "La Blisière (Juigné-des-Moutiers)", 47.6300, -1.1900),
    ("bois de boulogne", "Bois de Boulogne (Paris)", 48.8700, 2.2500),
    ("ministère de l'air", "Stand de tir du ministère de l'Air (Paris XVe)", 48.8380, 2.2770),
    ("ministere de l'air", "Stand de tir du ministère de l'Air (Paris XVe)", 48.8380, 2.2770),
    ("balard", "Stand de tir de Balard (Paris)", 48.8330, 2.2780),
    ("prison de la santé", "Prison de la Santé (Paris XIVe)", 48.8339, 2.3450),
    ("la santé", "Prison de la Santé (Paris XIVe)", 48.8339, 2.3450),
    ("issy-les-moulineaux", "Issy-les-Moulineaux", 48.8240, 2.2700),
    ("la doua", "La Doua (Villeurbanne)", 45.7830, 4.8720),
    ("montluc", "Fort de Montluc (Lyon)", 45.7480, 4.8620),
    ("fort du ha", "Fort du Hâ (Bordeaux)", 44.8360, -0.5770),
    ("cologne", "Cologne (Allemagne)", 50.9380, 6.9600),
    ("hambourg", "Hambourg (Allemagne)", 53.5510, 9.9940),
    ("stuttgart", "Stuttgart (Allemagne)", 48.7760, 9.1830),
    ("brandebourg", "Brandebourg (Allemagne)", 52.4120, 12.5320),
    ("brandenburg", "Brandebourg (Allemagne)", 52.4120, 12.5320),
    ("munich", "Munich (Allemagne)", 48.1370, 11.5750),
    ("pforzheim", "Pforzheim (Allemagne)", 48.8910, 8.6980),
    ("breendonk", "Fort de Breendonk (Belgique)", 51.0560, 4.3390),
    ("berlin", "Berlin (Allemagne)", 52.5200, 13.4050),
    # Repli générique : exécution à Paris sans site précis identifiable.
    ("paris", "Paris", 48.8566, 2.3522),
]

# Détection de l'engagement dans la notice biographique.
GROUPS = [
    ("communiste", re.compile(r"communiste|pcf|ftpf?\b|ftp-moi|jeunesses?\s+communistes|main-d['’]œuvre\s+immigrée", re.IGNORECASE)),
    ("FTP", re.compile(r"\bftpf?\b|francs?-tireurs", re.IGNORECASE)),
    ("otage", re.compile(r"otage", re.IGNORECASE)),
    ("syndicaliste", re.compile(r"\bcgt\b|syndicalis|syndiqu", re.IGNORECASE)),
    ("gaulliste / réseaux", re.compile(r"gaulliste|france\s+libre|\bffl\b|réseau|\bsoe\b|bureau\s+central", re.IGNORECASE)),
    ("catholique", re.compile(r"catholique|abbé|prêtre|séminariste|\bjoc\b", re.IGNORECASE)),
]


# --- Géocodage des lieux d'exécution ---------------------------------------
# Référentiel officiel des communes françaises (data.gouv, ~35 000 communes)
# pour résoudre le nom de ville de la notice en coordonnées précises, plutôt
# que de retomber sur le centroïde du département.
_COMMUNE_PREFIX = re.compile(
    r"^(fort|camp|citadelle|champ de tir|stand de tir|stand|dunes?|bois|caserne|"
    r"prison|maison d arret|polygone|butte|chateau|colline|plaine|carrieres?|mur|"
    r"terrain|plateau|cimetiere)\s+(de la|de l|du|des|de|d|au|aux|a la|a l|a)\s+",
    re.IGNORECASE)
_COMMUNE_QUAL = re.compile(
    r"\b(apres|comme|sommairement|en represailles?|en representailles|a la suite|"
    r"pour|avec|par|suite|dit|selon|ou il|le meme|puis)\b.*$")
_COMMUNE_LEAD = re.compile(
    r"^(au |a la |a l |a |aux |dans l |dans les |dans la |dans le |sur la |sur le |"
    r"pres de |pres d |le |la |les )")


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(text))
                   if unicodedata.category(c) != "Mn")


def _norm_place(text: str) -> str:
    text = _strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return re.sub(r"\s+", " ", text)


@lru_cache(maxsize=1)
def _communes() -> dict:
    """nom normalisé (avec et sans article) -> [(lat, lon, département), …]."""
    gaz: dict[str, list] = defaultdict(list)
    if not COMMUNES_CSV.exists():
        return gaz
    with COMMUNES_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not row.get("latitude") or not row.get("longitude"):
                continue
            rec = (float(row["latitude"]), float(row["longitude"]), row["nom_departement"])
            for key in {_norm_place(row["nom_commune"]), _norm_place(row["nom_commune_complet"])}:
                if key:
                    gaz[key].append(rec)
    return gaz


def _clean_town(raw: str) -> str:
    town = _norm_place(raw)
    town = re.split(r"[,;]", town)[0]
    town = _COMMUNE_QUAL.sub("", town).strip()
    town = _COMMUNE_PREFIX.sub("", town)
    town = _COMMUNE_LEAD.sub("", town).strip()
    return town


def geocode_commune(raw: str, dept: str | None):
    """Résout un libellé de lieu en (lat, lon) via le référentiel des communes."""
    gaz = _communes()
    if not gaz:
        return None
    dept_norm = _norm_place(dept) if dept else None
    town = _clean_town(raw)
    if not town:
        return None
    candidates = [town]
    if " " in town:
        tokens = [t for t in town.split() if len(t) > 2]
        candidates += [" ".join(tokens[i:]) for i in range(1, len(tokens))]
        candidates += tokens[::-1]
    # 1er passage : exiger la concordance de département (lève les homonymes).
    if dept_norm:
        for cand in candidates:
            for lat, lon, dep in gaz.get(cand, ()):  # type: ignore[union-attr]
                if _norm_place(dep) == dept_norm:
                    return (lat, lon)
    # 2e passage : première correspondance de nom (noms uniques surtout).
    for cand in candidates:
        hits = gaz.get(cand)
        if hits:
            return (hits[0][0], hits[0][1])
    return None


def display_place(segment: str) -> str | None:
    place = re.sub(r"\([^)]*\)", "", segment)
    place = re.split(r"[;,]", place)[0]
    place = re.sub(r"(?i)\b(après|comme|sommairement|en repr|à la suite|pour|avec|selon|dit)\b.*$", "", place)
    place = re.sub(
        r"(?i)^\s*(au\s+|à\s+la\s+|à\s+l['’]|à\s+|aux\s+|dans\s+l['’]|dans\s+les\s+|"
        r"dans\s+la\s+|dans\s+le\s+|sur\s+la\s+|sur\s+le\s+|près\s+de\s+|près\s+d['’])",
        "", place.strip())
    return place.strip(" ,.;") or None


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text))


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def parse_french_date(day: str, month: str, year: str):
    month_num = MONTHS_FR.get(month.lower())
    if not month_num:
        return None
    try:
        return date(int(year), month_num, int(day))
    except ValueError:
        return None


def canonical_dept(raw: str) -> str | None:
    """Premier nom de département dans une parenthèse « (Seine, Hauts-de-Seine) »."""
    name = raw.split(",")[0].strip()
    name = DEPT_ALIASES.get(name.lower(), name)
    return name if name in DEPT_COORDS else None


def parse_bio(bio: str) -> dict:
    info = {
        "birth_date": None, "birth_dept": None,
        "exec_date": None, "exec_place": None, "exec_dept": None,
        "exec_lat": None, "exec_lon": None,
        "age": None, "groups": [],
    }
    if not bio:
        return info
    bio = normalize(bio).replace("\u00a0", " ")

    match = BIRTH_RE.search(bio)
    if match:
        birth = parse_french_date(match.group(1), match.group(2), match.group(3))
        info["birth_date"] = birth.isoformat() if birth else None
        if match.group(5):
            info["birth_dept"] = canonical_dept(match.group(5))

    match = EXEC_RE.search(bio)
    if match:
        executed = parse_french_date(match.group(2), match.group(3), match.group(4))
        info["exec_date"] = executed.isoformat() if executed else None
        segment = match.group(5) or ""
        segment_lower = segment.lower()

        # Département cité entre parenthèses (sert de désambiguïsation).
        # On balaie toutes les parenthèses et chaque terme séparé par une virgule
        # (« (Fontevrault-l'Abbaye, Maine-et-Loire) »).
        dept = None
        for paren in DEPT_RE.findall(segment):
            for part in paren.split(","):
                candidate = canonical_dept(part)
                if candidate:
                    dept = candidate
                    break
            if dept:
                break
        info["exec_dept"] = dept

        # 1) Grand lieu d'exécution connu -> coordonnées précises.
        for keyword, label, lat, lon in KNOWN_SITES:
            if keyword in segment_lower:
                info["exec_place"] = label
                info["exec_lat"], info["exec_lon"] = lat, lon
                break

        # 2) Résolution du nom de commune via le référentiel officiel.
        if info["exec_lat"] is None:
            coords = geocode_commune(re.sub(r"\([^)]*\)", " ", segment), dept)
            if coords:
                info["exec_lat"], info["exec_lon"] = coords
                info["exec_place"] = display_place(segment) or dept

        # 3) Repli : centroïde du département.
        if info["exec_lat"] is None and dept and dept in DEPT_COORDS:
            info["exec_lat"], info["exec_lon"] = DEPT_COORDS[dept]
            info["exec_place"] = display_place(segment) or dept

    if info["birth_date"] and info["exec_date"]:
        born = date.fromisoformat(info["birth_date"])
        died = date.fromisoformat(info["exec_date"])
        age = (died - born).days // 365
        if 14 <= age <= 90:
            info["age"] = age

    info["groups"] = [name for name, pattern in GROUPS if pattern.search(bio)]
    return info


def build_clusters(texts: list[str], french_stopwords: set[str]) -> tuple[list[int], list[dict]]:
    vectorizer = TfidfVectorizer(
        max_features=5000,
        stop_words=list(french_stopwords),
        token_pattern=r"[a-zàâäéèêëïîôöùûüÿç]{3,}",
    )
    matrix = vectorizer.fit_transform(texts)
    kmeans = KMeans(n_clusters=2, random_state=0, n_init=50, max_iter=1000)
    labels = kmeans.fit_predict(matrix)
    terms = vectorizer.get_feature_names_out()
    order = kmeans.cluster_centers_.argsort()[:, ::-1]

    cluster_info = []
    for cluster_id in range(2):
        cluster_info.append({
            "id": cluster_id,
            "size": int((labels == cluster_id).sum()),
            "keywords": [terms[i] for i in order[cluster_id, :15]],
        })
    return [int(l) for l in labels], cluster_info


def build_topics(texts: list[str], french_stopwords: set[str]) -> list[dict]:
    vectorizer = CountVectorizer(
        max_features=3000,
        max_df=0.9,
        min_df=3,
        stop_words=list(french_stopwords),
        token_pattern=r"[a-zàâäéèêëïîôöùûüÿç]{3,}",
    )
    matrix = vectorizer.fit_transform(texts)
    terms = vectorizer.get_feature_names_out()

    lda = LatentDirichletAllocation(n_components=4, random_state=0, max_iter=25, learning_method="batch")
    lda.fit(matrix)

    topics = []
    for topic_id, weights in enumerate(lda.components_):
        top = weights.argsort()[::-1][:10]
        topics.append({"id": topic_id, "keywords": [terms[i] for i in top]})
    return topics


ELISION_RE = re.compile(r"^\s*(?:[a-zàâäéèêëïîôöùûüÿç]{1,3})['’ʼ]", flags=re.IGNORECASE)
LEADING_ARTICLE_RE = re.compile(r"^(?:la|le|les|de|du|des)\s+", flags=re.IGNORECASE)


def clean_entity(text: str, strip_article: bool = False) -> str:
    text = ELISION_RE.sub("", normalize(text))
    # Coupe à la première ponctuation forte (« Parti Communiste ! Adieu » -> « Parti Communiste »).
    text = re.split(r"[!?;]", text)[0]
    text = text.strip(" \n\t.,;:!?«»\"'’ʼ()")
    text = re.sub(r"\s+", " ", text)
    if strip_article:
        text = LEADING_ARTICLE_RE.sub("", text)
    return text


def valid_entity(value: str) -> bool:
    if not value or len(value) < 2:
        return False
    if value.lower() in ENTITY_STOP:
        return False
    if "'" in value or "’" in value:
        return False
    return any(ch.isupper() for ch in value)


class CaseMergingCounter:
    """Compte les entités en fusionnant les variantes de casse
    (« Parti Communiste » et « Parti communiste » ne font qu'un)."""

    def __init__(self):
        self.counts = Counter()
        self.variants = defaultdict(Counter)

    def add(self, value: str):
        key = value.casefold()
        self.counts[key] += 1
        self.variants[key][value] += 1

    def most_common(self, n: int) -> list[tuple[str, int]]:
        return [
            (self.variants[key].most_common(1)[0][0], count)
            for key, count in self.counts.most_common(n)
        ]


def make_bins(values: list[int], edges: list[int], labels: list[str]) -> list[dict]:
    counts = [0] * len(labels)
    for value in values:
        for i in range(len(edges) - 1):
            if edges[i] <= value < edges[i + 1]:
                counts[i] += 1
                break
    return [{"label": label, "count": count} for label, count in zip(labels, counts)]


def month_range(start: str, end: str) -> list[str]:
    result = []
    year, month = int(start[:4]), int(start[5:7])
    end_year, end_month = int(end[:4]), int(end[5:7])
    while (year, month) <= (end_year, end_month):
        result.append(f"{year}-{month:02d}")
        month += 1
        if month > 12:
            month, year = 1, year + 1
    return result


def main() -> None:
    if not RAW_CSV.exists():
        raise FileNotFoundError(f"Fichier introuvable : {RAW_CSV}. Lancez d'abord scripts/scrape.py")

    df = pd.read_csv(RAW_CSV)
    if "bio" not in df.columns:
        df["bio"] = ""
    df["bio"] = df["bio"].fillna("").astype(str).map(normalize)
    df["letter_text"] = df["letter_text"].fillna("").astype(str).map(normalize)
    df["has_letter"] = df["letter_text"].str.strip().astype(bool)

    total_records = len(df)
    excluded = int((~df["has_letter"]).sum())

    # Le corpus d'étude : uniquement les fiches avec lettre.
    df = df[df["has_letter"]].reset_index(drop=True)
    df["word_count"] = df["letter_text"].apply(word_count)

    bio_infos = [parse_bio(bio) for bio in df["bio"]]

    try:
        nlp = spacy.load("fr_core_news_lg")
        model_name = "fr_core_news_lg"
    except OSError:
        nlp = spacy.load("fr_core_news_sm")
        model_name = "fr_core_news_sm"
    french_stopwords = nlp.Defaults.stop_words

    texts = df["letter_text"].tolist()
    letter_docs = list(nlp.pipe(texts, batch_size=32))

    word_freq = Counter()
    noun_freq = Counter()
    verb_freq = Counter()
    adj_freq = Counter()
    word_in_docs = defaultdict(set)
    loc_freq = CaseMergingCounter()
    per_freq = CaseMergingCounter()
    org_freq = CaseMergingCounter()

    for row_idx, doc in enumerate(letter_docs):
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
            value = clean_entity(ent.text, strip_article=(ent.label_ in ("LOC", "ORG")))
            if not valid_entity(value):
                continue
            if ent.label_ == "LOC":
                loc_freq.add(value)
            elif ent.label_ == "PER":
                per_freq.add(value)
            elif ent.label_ == "ORG":
                if value.casefold() in ORG_STOP:
                    continue
                # Un nom de famille en capitales n'est pas une organisation
                # (les vrais sigles — URSS, SNCF, CGT… — font 5 lettres ou moins).
                if value.isupper() and " " not in value and len(value) > 5 and value != "GESTAPO":
                    continue
                org_freq.add(ORG_ALIASES.get(value.casefold(), value))

    doc_freq = Counter({word: len(docs) for word, docs in word_in_docs.items()})

    clusters, cluster_info = build_clusters(texts, french_stopwords)
    df["cluster"] = clusters
    topics = build_topics(texts, french_stopwords)

    # Figures historiques : nombre de lettres qui les mentionnent.
    figures = []
    for label, pattern in FIGURES:
        docs = sum(1 for text in texts if pattern.search(text))
        if docs:
            figures.append({
                "figure": label,
                "documents": docs,
                "percentage": round(100 * docs / len(texts), 1),
            })
    figures.sort(key=lambda f: f["documents"], reverse=True)

    # Expressions.
    phrase_list = []
    for phrase in PHRASES:
        docs = sum(1 for text in texts if phrase in text.lower())
        phrase_list.append({
            "phrase": phrase,
            "documents": docs,
            "percentage": round(100 * docs / len(texts), 1),
        })
    phrase_list.sort(key=lambda p: p["documents"], reverse=True)

    # Comparaison lexicale communistes / autres (bios exploitables uniquement).
    group_indices = {"communiste": [], "autres": []}
    for idx, info in enumerate(bio_infos):
        if not df.iloc[idx]["bio"]:
            continue
        key = "communiste" if "communiste" in info["groups"] else "autres"
        group_indices[key].append(idx)

    comparison = {"groups": [], "terms": COMPARISON_TERMS, "rates": {}}
    for group, indices in group_indices.items():
        if not indices:
            continue
        comparison["groups"].append({
            "name": group,
            "size": len(indices),
            "avg_words": round(float(df.iloc[indices]["word_count"].mean()), 0),
        })
        rates = []
        for term in COMPARISON_TERMS:
            pattern = re.compile(r"\b" + re.escape(term), re.IGNORECASE)
            hits = sum(1 for i in indices if pattern.search(texts[i]))
            rates.append(round(100 * hits / len(indices), 1))
        comparison["rates"][group] = rates

    # Chronologie des exécutions par mois.
    exec_months = [info["exec_date"][:7] for info in bio_infos if info["exec_date"]]
    timeline = []
    if exec_months:
        counts = Counter(exec_months)
        months = month_range(min(exec_months), max(exec_months))
        timeline = [{"month": m, "count": counts.get(m, 0)} for m in months]

    # Carte : lieux d'exécution agrégés.
    site_agg = {}
    for idx, info in enumerate(bio_infos):
        if info["exec_lat"] is None:
            continue
        key = (info["exec_place"], info["exec_lat"], info["exec_lon"])
        entry = site_agg.setdefault(key, {"count": 0, "names": []})
        entry["count"] += 1
        if len(entry["names"]) < 10:
            entry["names"].append(df.iloc[idx]["person_name"])
    map_places = [
        {"place": place, "lat": lat, "lon": lon, "count": data["count"], "names": data["names"]}
        for (place, lat, lon), data in sorted(site_agg.items(), key=lambda kv: -kv[1]["count"])
    ]

    # Âges et longueurs.
    ages = [info["age"] for info in bio_infos if info["age"] is not None]
    age_bins = make_bins(
        ages,
        [14, 20, 25, 30, 35, 40, 45, 50, 60, 91],
        ["14-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-59", "60+"],
    )
    length_bins = make_bins(
        df["word_count"].tolist(),
        [0, 100, 200, 300, 450, 600, 800, 1000, 1500, 10**6],
        ["<100", "100-199", "200-299", "300-449", "450-599", "600-799", "800-999", "1000-1499", "1500+"],
    )

    # Engagements (une lettre peut relever de plusieurs catégories).
    group_counts = Counter()
    for info in bio_infos:
        for group in info["groups"]:
            group_counts[group] += 1

    letters = []
    for idx, row in df.iterrows():
        info = bio_infos[idx]
        letters.append({
            "person_name": row["person_name"],
            "person_url": row["person_url"],
            "bio": row["bio"],
            "letter_text": row["letter_text"],
            "word_count": int(row["word_count"]),
            "cluster": int(row["cluster"]),
            "age": info["age"],
            "exec_date": info["exec_date"],
            "exec_place": info["exec_place"],
            "groups": info["groups"],
        })

    stats = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": "https://fusilles-40-44.maitron.fr/yzfusillesdivers/1-lettres-de-fusilles/",
        "model": model_name,
        "summary": {
            "letters": len(df),
            "total_records": total_records,
            "excluded_records": excluded,
            "total_words": int(df["word_count"].sum()),
            "avg_words": round(float(df["word_count"].mean()), 0),
            "max_words": int(df["word_count"].max()),
            "with_bio": sum(1 for b in df["bio"] if b),
            "with_age": len(ages),
            "median_age": int(pd.Series(ages).median()) if ages else None,
            "located": sum(p["count"] for p in map_places),
        },
        "timeline": timeline,
        "age_bins": age_bins,
        "length_bins": length_bins,
        "group_counts": [
            {"group": g, "count": c} for g, c in group_counts.most_common()
        ],
        "map_places": map_places,
        "top_words": [{"word": w, "count": c} for w, c in word_freq.most_common(40)],
        "top_nouns": [{"word": w, "count": c} for w, c in noun_freq.most_common(20)],
        "top_verbs": [{"word": w, "count": c} for w, c in verb_freq.most_common(20)],
        "top_adjectives": [{"word": w, "count": c} for w, c in adj_freq.most_common(15)],
        "top_words_by_doc": [{"word": w, "count": c} for w, c in doc_freq.most_common(20)],
        "entities": {
            "locations": [{"word": w, "count": c} for w, c in loc_freq.most_common(25)],
            "persons": [{"word": w, "count": c} for w, c in per_freq.most_common(20)],
            # Les hapax en un seul mot hors sigles (« Toto », « Police »…) sont
            # des faux positifs du NER : on ne garde un singleton que s'il est
            # multi-mots ou en capitales (SNCF, FFI…).
            "organisations": [
                {"word": w, "count": c}
                for w, c in org_freq.most_common(30)
                if c > 1 or " " in w or w.isupper()
            ][:15],
        },
        "figures": figures,
        "phrase_stats": phrase_list,
        "comparison": comparison,
        "clusters": cluster_info,
        "topics": topics,
    }

    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    (DOCS_DATA / "letters.json").write_text(
        json.dumps(letters, ensure_ascii=False), encoding="utf-8")
    (DOCS_DATA / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    processed_csv = ROOT / "data" / "processed.csv"
    export = df.copy()
    export["age"] = [info["age"] for info in bio_infos]
    export["exec_date"] = [info["exec_date"] for info in bio_infos]
    export["exec_place"] = [info["exec_place"] for info in bio_infos]
    export["groups"] = ["|".join(info["groups"]) for info in bio_infos]
    export.to_csv(processed_csv, index=False)

    print(f"[DONE] {len(letters)} lettres (sur {total_records} fiches) -> {DOCS_DATA / 'letters.json'}")
    print(f"[DONE] statistiques ({model_name}) -> {DOCS_DATA / 'stats.json'}")
    print(f"[DONE] CSV enrichi -> {processed_csv}")


if __name__ == "__main__":
    main()
