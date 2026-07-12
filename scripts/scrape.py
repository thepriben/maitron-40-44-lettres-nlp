#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acquisition des lettres de fusillés depuis le Maitron 1940-1944."""

import csv
import time
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://fusilles-40-44.maitron.fr/"
INDEX = urljoin(BASE, "yzfusillesdivers/1-lettres-de-fusilles/")
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

TIMEOUT = 20
RETRIES = 3
SLEEP_BETWEEN = 1.5
BACKOFF = 1.0

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "data" / "raw.csv"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "MaitronLettersScraper/1.0 (+https://github.com/thepriben/maitron-40-44-lettres)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


def fetch(url: str) -> Optional[str]:
    last_err = None
    for attempt in range(1, RETRIES + 1):
        time.sleep(SLEEP_BETWEEN)
        try:
            response = SESSION.get(url, timeout=TIMEOUT)
            if response.status_code == 200:
                return response.text
            print(f"[WARN] {response.status_code} sur {url} (tentative {attempt}/{RETRIES})")
            last_err = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            print(f"[WARN] erreur réseau sur {url} (tentative {attempt}/{RETRIES}) : {exc}")
            last_err = str(exc)
        time.sleep(BACKOFF * attempt)
    print(f"[ERROR] échec pour {url} : {last_err}")
    return None


def parse_index(html: str) -> List[Tuple[str, str]]:
    people = []
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("div", class_="liste-articles")
    if not container:
        return people
    for link in container.select('a[rel="bookmark"]'):
        name = link.get_text(strip=True)
        href = link.get("href")
        if href:
            people.append((name, urljoin(BASE, href)))
    return people


def extract_letters(soup: BeautifulSoup) -> str:
    """Texte de la lettre. Le balisage du Maitron est incohérent, d'où les replis :
    1. <blockquote class="poesie"> (cas général) ;
    2. balise littérale <poesie> (raccourci SPIP non rendu sur certaines fiches) ;
    3. <blockquote> sans classe ;
    4. long passage en italique dans le corps de la notice.
    """
    blocks = soup.find_all("blockquote", class_="poesie")
    if not blocks:
        blocks = soup.find_all("poesie")
    if not blocks:
        blocks = soup.find_all("blockquote")
    texts = []
    for block in blocks:
        text = block.get_text("\n", strip=True)
        if text:
            texts.append(text)
    if texts:
        return "\n\n".join(texts).strip()

    body = soup.find("div", class_="texte")
    if body:
        italics = [
            tag.get_text("\n", strip=True)
            for tag in body.find_all(["em", "i"])
            if len(tag.get_text(strip=True)) >= 400
        ]
        if italics:
            return "\n\n".join(italics).strip()
    return ""


def extract_bio(soup: BeautifulSoup) -> str:
    """Chapô de la notice : « Né le … à …, fusillé le … ; profession ; engagement. »"""
    chapo = soup.find("div", class_="chapo")
    if not chapo:
        return ""
    return chapo.get_text(" ", strip=True)


def main() -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["first_letter", "person_name", "person_url", "bio", "letter_text"])

        for letter in LETTERS:
            index_url = f"{INDEX}?first_l={letter}"
            print(f"[INFO] Index {letter} -> {index_url}")
            index_html = fetch(index_url)
            if not index_html:
                print(f"[WARN] lettre {letter} ignorée (index inaccessible)")
                continue

            people = parse_index(index_html)
            print(f"[INFO] {len(people)} fiches pour la lettre {letter}")

            for index, (name, url) in enumerate(people, start=1):
                print(f"[INFO] ({letter}) [{index}/{len(people)}] {name}")
                person_html = fetch(url)
                if person_html:
                    soup = BeautifulSoup(person_html, "html.parser")
                    bio = extract_bio(soup)
                    letter_text = extract_letters(soup)
                else:
                    bio, letter_text = "", ""
                writer.writerow([letter, name, url, bio, letter_text])
                total += 1

    print(f"[DONE] {total} fiches écrites dans {OUT_CSV}")


if __name__ == "__main__":
    main()
