"""
Script pour scraper les drapeaux du monde depuis la page Wikipedia :
https://fr.wikipedia.org/wiki/Galerie_des_drapeaux_des_pays_du_monde

Télécharge chaque drapeau dans le dossier 'drapeau/' avec un nom en snake_case
sans accents ni caractères spéciaux, et génère un fichier drapeaux.json
contenant la correspondance nom_fichier -> label original.
"""

import requests
from bs4 import BeautifulSoup
import os
import json
import re
import unicodedata
import time

URL = "https://fr.wikipedia.org/wiki/Galerie_des_drapeaux_des_pays_du_monde"
DRAPEAU_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drapeau")
JSON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drapeaux.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FlagScraper/1.0"
}


def normalize_name(name: str) -> str:
    """
    Convertit un nom de pays en snake_case sans accents ni caractères spéciaux.
    Ex : 'Algérie' -> 'algerie'
         'République démocratique du Congo' -> 'republique_democratique_du_congo'
         'Côte d'Ivoire' -> 'cote_d_ivoire'
    """
    # Normalise les apostrophes typographiques en apostrophes simples
    name = name.replace("\u2019", "'").replace("\u2018", "'")
    # Décompose les caractères Unicode (sépare les accents des lettres)
    nfkd = unicodedata.normalize("NFKD", name)
    # Supprime les diacritiques (accents)
    ascii_name = nfkd.encode("ascii", "ignore").decode("ascii")
    # Met en minuscules
    ascii_name = ascii_name.lower()
    # Remplace tout ce qui n'est pas alphanumérique par un underscore
    ascii_name = re.sub(r"[^a-z0-9]+", "_", ascii_name)
    # Supprime les underscores en début/fin
    ascii_name = ascii_name.strip("_")
    return ascii_name


def extract_country_name(cell) -> str:
    """
    Extrait le nom du pays à partir de la cellule HTML.
    Le dernier lien <a> de la cellule pointe toujours vers le pays.
    Ex : 'Afghanistan', 'Algérie', 'Bosnie-Herzégovine'
    """
    links = cell.find_all("a")
    if not links:
        return ""
    # Le dernier lien est celui du pays
    country_link = links[-1]
    return country_link.get_text(strip=True)


def get_image_url(img_tag) -> str:
    """
    Récupère l'URL du fichier original en haute résolution depuis Wikimedia.
    Transforme l'URL thumbnail en URL originale :
      thumb/.../7/77/Flag.svg/120px-Flag.svg.png
      ->   .../7/77/Flag.svg
    """
    src = img_tag.get("src", "")
    if not src:
        return ""
    if not src.startswith("http"):
        src = "https:" + src

    # Transformer l'URL thumbnail en URL du fichier original
    if "/thumb/" in src:
        # Supprimer /thumb/ et le dernier segment (ex: 120px-Flag.svg.png)
        src = src.replace("/thumb/", "/")
        src = src.rsplit("/", 1)[0]

    return src


def main():
    os.makedirs(DRAPEAU_DIR, exist_ok=True)

    print(f"Récupération de la page Wikipedia...")
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    print(f"Page récupérée ({len(response.text)} caractères)")

    soup = BeautifulSoup(response.text, "html.parser")

    # Les drapeaux sont dans des tables avec la classe "toccolours"
    tables = soup.find_all("table", class_="toccolours")
    print(f"Trouvé {len(tables)} tables de drapeaux")

    # Charger le JSON existant si reprise après interruption
    drapeaux = {}
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                drapeaux = json.load(f)
            print(f"Reprise : {len(drapeaux)} drapeaux déjà présents dans le JSON")
        except Exception:
            pass

    count = len(drapeaux)
    errors = 0

    for table in tables:
        cells = table.find_all("td")
        for cell in cells:
            # Ignorer les cellules vides (sans image)
            img = cell.find("img", class_="mw-file-element")
            if not img:
                continue

            # Vérifier que la cellule contient un drapeau
            cell_text = cell.get_text(" ", strip=True)
            if "Drapeau" not in cell_text:
                continue

            # Extraire le nom du pays depuis le dernier lien <a>
            country_label = extract_country_name(cell)
            if not country_label:
                continue

            # Générer le nom de fichier en snake_case
            filename_base = normalize_name(country_label)
            if not filename_base:
                continue

            # Éviter les doublons
            if filename_base in drapeaux:
                continue

            # Récupérer l'URL de l'image
            img_url = get_image_url(img)
            if not img_url:
                continue

            # Déterminer l'extension depuis l'URL originale
            url_path = img_url.split("?")[0]  # retirer les query params
            if url_path.lower().endswith(".svg"):
                ext = ".svg"
            elif url_path.lower().endswith(".jpg") or url_path.lower().endswith(".jpeg"):
                ext = ".jpg"
            else:
                ext = ".png"
            filepath = os.path.join(DRAPEAU_DIR, f"{filename_base}{ext}")

            # Télécharger l'image avec retry en cas de rate-limiting
            print(f"  [{count + 1:3d}] {country_label} -> {filename_base}{ext}")
            success = False
            for attempt in range(5):
                try:
                    img_response = requests.get(img_url, headers=HEADERS, timeout=15)
                    img_response.raise_for_status()
                    with open(filepath, "wb") as f:
                        f.write(img_response.content)
                    success = True
                    break
                except requests.exceptions.HTTPError as e:
                    if img_response.status_code == 429:
                        wait = 2 ** (attempt + 1)  # 2, 4, 8, 16, 32 secondes
                        print(f"    ⏳ Rate-limité, attente {wait}s (tentative {attempt + 1}/5)")
                        time.sleep(wait)
                    else:
                        print(f"    ❌ Erreur HTTP: {e}")
                        break
                except Exception as e:
                    print(f"    ❌ Erreur: {e}")
                    break

            if success:
                drapeaux[filename_base] = country_label
                count += 1

                # Sauvegarder le JSON au fur et à mesure
                drapeaux_sorted = dict(sorted(drapeaux.items()))
                with open(JSON_FILE, "w", encoding="utf-8") as f:
                    json.dump(drapeaux_sorted, f, ensure_ascii=False, indent=2)
            else:
                errors += 1

            time.sleep(0.5)  # Pause entre chaque téléchargement

    print(f"\n{'='*50}")
    print(f"Terminé !")
    print(f"  - {count} drapeaux téléchargés dans '{DRAPEAU_DIR}'")
    if errors:
        print(f"  - {errors} erreurs")
    print(f"  - Mapping JSON sauvegardé dans '{JSON_FILE}'")


if __name__ == "__main__":
    main()
