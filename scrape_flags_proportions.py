"""
Script pour scraper les drapeaux du monde depuis la page Wikipedia :
https://fr.wikipedia.org/wiki/Liste_des_drapeaux_nationaux_par_proportions

Cette page contient beaucoup plus de drapeaux organisés par proportions.
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

URL = "https://fr.wikipedia.org/wiki/Liste_des_drapeaux_nationaux_par_proportions"
DRAPEAU_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drapeau")
JSON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drapeaux.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FlagScraper/2.0"
}


def normalize_name(name: str) -> str:
    """
    Convertit un nom de pays en snake_case sans accents ni caractères spéciaux.
    Ex : 'Algérie' -> 'algerie'
         'République démocratique du Congo' -> 'republique_democratique_du_congo'
         'Côte d'Ivoire' -> 'cote_d_ivoire'
         'États-Unis' -> 'etats_unis'
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


def search_flag_in_page(country_name: str) -> str:
    """
    Recherche l'image du drapeau pour un pays donné en cherchant sur la page
    du pays ou en utilisant les conventions de nommage de Wikimedia.
    
    Retourne l'URL de l'image du drapeau ou une chaîne vide si non trouvé.
    """
    # Essayer de trouver l'URL du drapeau via l'API Wikipedia
    try:
        # Chercher la page du pays
        search_url = f"https://fr.wikipedia.org/api/rest_v1/page/summary/{country_name.replace(' ', '_')}"
        response = requests.get(search_url, headers=HEADERS, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if "thumbnail" in data and data["thumbnail"]:
                return data["thumbnail"]["source"]
        
        # Si pas d'image dans le summary, essayer avec les conventions de nommage communes
        common_flag_names = [
            f"Flag_of_{country_name.replace(' ', '_')}.svg",
            f"Flag_of_{country_name.replace(' ', '_')}.png",
            f"Flag_of_the_{country_name.replace(' ', '_')}.svg",
            f"Drapeau_de_{country_name.replace(' ', '_')}.svg",
            f"{country_name.replace(' ', '_')}_flag.svg"
        ]
        
        for flag_name in common_flag_names:
            # Construire l'URL Wikimedia Commons
            filename_encoded = flag_name.replace(" ", "_")
            commons_url = f"https://commons.wikimedia.org/wiki/File:{filename_encoded}"
            
            try:
                page_response = requests.get(commons_url, headers=HEADERS, timeout=10)
                if page_response.status_code == 200:
                    page_soup = BeautifulSoup(page_response.text, "html.parser")
                    # Trouver le lien vers le fichier original
                    original_file_link = page_soup.find("a", string="Fichier d'origine") or page_soup.find("a", string="Original file")
                    if original_file_link:
                        return original_file_link["href"]
            except:
                continue
                
    except Exception as e:
        print(f"    Erreur lors de la recherche du drapeau pour {country_name}: {e}")
    
    return ""


def main():
    os.makedirs(DRAPEAU_DIR, exist_ok=True)

    print(f"Récupération de la page Wikipedia des proportions...")
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    print(f"Page récupérée ({len(response.text)} caractères)")

    soup = BeautifulSoup(response.text, "html.parser")

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
    processed_countries = set()

    # Chercher tous les tableaux de la page
    tables = soup.find_all("table", class_="wikitable")
    if not tables:
        # Si wikitable ne marche pas, essayer d'autres classes
        tables = soup.find_all("table")
    
    print(f"Trouvé {len(tables)} tables")

    for table_idx, table in enumerate(tables):
        print(f"\nAnalyse de la table {table_idx + 1}...")
        
        # Chercher toutes les lignes du tableau
        rows = table.find_all("tr")
        
        for row_idx, row in enumerate(rows):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:  # Il faut au moins 2 colonnes (pays et proportions)
                continue
            
            # La première cellule contient normalement le nom du pays et éventuellement l'image
            first_cell = cells[0]
            
            # Chercher un lien vers un article de pays dans la première cellule
            links = first_cell.find_all("a")
            country_links = []
            
            for link in links:
                href = link.get("href", "")
                link_text = link.get_text(strip=True)
                
                # Filtrer les liens qui ne sont pas des pays (éviter "File:", "Category:", etc.)
                if href and not href.startswith("/wiki/File:") and not href.startswith("/wiki/Category:") and link_text:
                    # Si le texte du lien ressemble à un nom de pays
                    if len(link_text) > 2 and not link_text.lower() in ["drapeau", "flag", "image"]:
                        country_links.append(link_text)
            
            if not country_links:
                continue
            
            # Prendre le premier lien valide comme nom de pays
            country_name = country_links[0]
            
            # Éviter les doublons
            if country_name in processed_countries:
                continue
            processed_countries.add(country_name)
            
            # Générer le nom de fichier en snake_case
            filename_base = normalize_name(country_name)
            if not filename_base:
                continue
                
            # Éviter les doublons dans le JSON
            if filename_base in drapeaux:
                continue

            print(f"  [{count + 1:3d}] Traitement de : {country_name}")
            
            # Chercher une image dans la cellule actuelle
            img_url = ""
            img_tag = first_cell.find("img")
            
            if img_tag:
                img_url = get_image_url(img_tag)
            
            # Si pas d'image trouvée directement, rechercher via l'API
            if not img_url:
                print(f"    🔍 Recherche alternative pour {country_name}...")
                img_url = search_flag_in_page(country_name)
            
            if not img_url:
                print(f"    ❌ Aucun drapeau trouvé pour {country_name}")
                errors += 1
                continue

            # Déterminer l'extension depuis l'URL
            url_path = img_url.split("?")[0]
            if url_path.lower().endswith(".svg"):
                ext = ".svg"
            elif url_path.lower().endswith(".jpg") or url_path.lower().endswith(".jpeg"):
                ext = ".jpg"
            else:
                ext = ".png"
            
            filepath = os.path.join(DRAPEAU_DIR, f"{filename_base}{ext}")
            
            # Télécharger l'image
            success = False
            for attempt in range(3):
                try:
                    print(f"    📥 Téléchargement depuis: {img_url}")
                    img_response = requests.get(img_url, headers=HEADERS, timeout=15)
                    img_response.raise_for_status()
                    
                    with open(filepath, "wb") as f:
                        f.write(img_response.content)
                    
                    print(f"    ✅ Sauvegardé: {filename_base}{ext}")
                    success = True
                    break
                    
                except requests.exceptions.HTTPError as e:
                    if img_response.status_code == 429:
                        wait = 2 ** (attempt + 1)
                        print(f"    ⏳ Rate-limité, attente {wait}s (tentative {attempt + 1}/3)")
                        time.sleep(wait)
                    else:
                        print(f"    ❌ Erreur HTTP: {e}")
                        break
                except Exception as e:
                    print(f"    ❌ Erreur: {e}")
                    break

            if success:
                drapeaux[filename_base] = country_name
                count += 1

                # Sauvegarder le JSON au fur et à mesure
                drapeaux_sorted = dict(sorted(drapeaux.items()))
                with open(JSON_FILE, "w", encoding="utf-8") as f:
                    json.dump(drapeaux_sorted, f, ensure_ascii=False, indent=2)
            else:
                errors += 1

            time.sleep(1)  # Pause entre chaque téléchargement

    print(f"\n{'='*60}")
    print(f"Terminé !")
    print(f"  - {count} drapeaux téléchargés dans '{DRAPEAU_DIR}'")
    if errors:
        print(f"  - {errors} erreurs de téléchargement")
    print(f"  - Mapping JSON sauvegardé dans '{JSON_FILE}'")
    print(f"  - {len(processed_countries)} pays différents traités")


if __name__ == "__main__":
    main()