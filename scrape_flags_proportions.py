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
    Recherche l'image du drapeau pour un pays donné en utilisant les conventions 
    de nommage spécifiques aux drapeaux sur Wikimedia Commons.
    
    Retourne l'URL de l'image du drapeau ou une chaîne vide si non trouvé.
    """
    try:
        # Normaliser le nom du pays pour les URLs
        country_normalized = country_name.replace(' ', '_')
        
        # Variantes communes de noms de drapeaux sur Wikimedia Commons
        common_flag_names = [
            f"Flag_of_{country_normalized}.svg",
            f"Flag_of_{country_normalized}.png", 
            f"Flag_of_the_{country_normalized}.svg",
            f"Flag_of_the_{country_normalized}.png"
        ]
        
        # Variantes spéciales pour certains pays
        special_cases = {
            "République tchèque": ["Flag_of_the_Czech_Republic.svg", "Flag_of_Czech_Republic.svg"],
            "Birmanie (Myanmar)": ["Flag_of_Myanmar.svg", "Flag_of_Burma.svg"],
            "Chypre du Nord": ["Flag_of_Northern_Cyprus.svg", "Flag_of_the_Turkish_Republic_of_Northern_Cyprus.svg"],
            "Taïwan": ["Flag_of_Taiwan.svg", "Flag_of_the_Republic_of_China.svg"],
            "Transnistrie": ["Flag_of_Transnistria.svg", "Flag_of_Pridnestrovie.svg"],
            "Abkhazie": ["Flag_of_Abkhazia.svg"],
            "Haut-Karabagh": ["Flag_of_Nagorno-Karabakh.svg", "Flag_of_Artsakh.svg"],
            "Ossétie du Sud": ["Flag_of_South_Ossetia.svg"],
            "République arabe sahraouie démocratique": ["Flag_of_the_Sahrawi_Arab_Democratic_Republic.svg"],
            "Somaliland": ["Flag_of_Somaliland.svg"],
            "Macao": ["Flag_of_Macau.svg"],
            "Hong Kong": ["Flag_of_Hong_Kong.svg"],
            "Polynésie française": ["Flag_of_French_Polynesia.svg"],
            "Porto Rico": ["Flag_of_Puerto_Rico.svg"]
        }
        
        if country_name in special_cases:
            common_flag_names = special_cases[country_name]
        
        # Tester chaque variante
        for flag_name in common_flag_names:
            # Construire l'URL directe du fichier sur Wikimedia Commons
            # Format: https://commons.wikimedia.org/wiki/File:Flag_of_X.svg
            commons_url = f"https://commons.wikimedia.org/wiki/File:{flag_name}"
            
            try:
                page_response = requests.get(commons_url, headers=HEADERS, timeout=10)
                if page_response.status_code == 200:
                    page_soup = BeautifulSoup(page_response.text, "html.parser")
                    
                    # Chercher le lien vers le fichier original (plusieurs façons possibles)
                    original_file_link = None
                    
                    # Méthode 1: Rechercher "Original file" ou "Fichier d'origine"
                    for link_text in ["Original file", "Fichier d'origine", "Full resolution"]:
                        original_file_link = page_soup.find("a", string=link_text)
                        if original_file_link:
                            break
                    
                    # Méthode 2: Chercher dans les liens d'images
                    if not original_file_link:
                        # Chercher les liens vers upload.wikimedia.org qui contiennent le nom du fichier
                        for link in page_soup.find_all("a", href=True):
                            href = link["href"]
                            if ("upload.wikimedia.org" in href and 
                                flag_name.replace('.svg', '').replace('.png', '') in href and
                                not "/thumb/" in href):
                                return href
                    
                    # Méthode 3: Parser la page pour trouver l'URL de l'image directement
                    if not original_file_link:
                        # Chercher les balises img qui pointent vers le vrai fichier
                        for img in page_soup.find_all("img"):
                            src = img.get("src", "")
                            if ("upload.wikimedia.org" in src and 
                                flag_name.replace('.svg', '').replace('.png', '') in src and 
                                "/thumb/" not in src):
                                return src
                    
                    if original_file_link and original_file_link.get("href"):
                        file_url = original_file_link["href"]
                        if file_url.startswith("//"):
                            file_url = "https:" + file_url
                        elif file_url.startswith("/"):
                            file_url = "https://commons.wikimedia.org" + file_url
                        return file_url
                        
            except Exception as e:
                print(f"    Erreur lors de la vérification de {flag_name}: {e}")
                continue
        
        # Si aucune variante n'a fonctionné, construire l'URL directement
        # Format direct Wikimedia: https://upload.wikimedia.org/wikipedia/commons/...
        for flag_name in common_flag_names[:2]:  # Tester seulement les 2 premières variantes
            try:
                # Essayer de deviner l'URL directe (cette méthode est moins fiable)
                direct_url = f"https://upload.wikimedia.org/wikipedia/commons/thumb/a/a0/{flag_name}/320px-{flag_name}"
                response = requests.head(direct_url, headers=HEADERS, timeout=5)
                if response.status_code == 200:
                    return direct_url.replace("/thumb", "").replace("/320px-" + flag_name, "")
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