---
name: quick-pick
description: "Déléguer des séries d'arbitrages ou de tris rapides à l'humain via une pile de cartes swipables (mobile & desktop)."
version: 2.0.0
license: MIT
platforms: [linux, darwin, windows]
metadata:
  tags: [triage, arbitration, decision, review, swipe, mobile-first, async, byok]
---

# Quick-Pick Skill

Permet aux agents d'IA de soumettre des lots d'arbitrages à l'utilisateur sous forme de pile de cartes tactiles (1 carte à la fois, swipe physique mobile / raccourcis clavier desktop).

## Quand l'utiliser

Utiliser ce skill dès qu'un agent doit faire arbitrer plusieurs éléments :
- Tri ou élagage de backlog / tickets de gestion de projet.
- Revue de règles de prompt / doctrine à conserver, modifier ou supprimer.
- Audit de skills ou dépendances à garder ou purger.
- Validation d'options d'architecture ou de design.
- Relecture de PRs ou propositions de refactoring.

> **Avantage** : Évite les pavés illisibles de 20 questions en chat. L'utilisateur swipe le deck en 60 secondes sur son téléphone ou son poste.

---

## 1. Créer un Deck d'Arbitrage

### Méthode recommandée : CLI `deck_cli.py`

Préparez un fichier JSON d'items :
```json
[
  {
    "id": "item-1",
    "title": "Nom de l'élément à trancher",
    "badges": [
      { "label": "URGENT", "variant": "warning" },
      { "label": "BACKEND", "variant": "neutral" }
    ],
    "bullets": [
      "Argument ou fait 1",
      "Argument ou fait 2"
    ],
    "description": "Détail optionnel contextuel"
  }
]
```

Lancez la création du deck :
```bash
python3 deck_cli.py create \
  --id "mon-arbitrage" \
  --title "Titre explicite de l'arbitrage" \
  --category "AUDIT" \
  --template "triage" \
  --items-file items.json
```

### Méthode alternative : API HTTP `POST /api/decks`

Même chose sans fichier JSON, à partir d'une simple liste de lignes (une ligne = une carte) :

```bash
curl -X POST http://localhost:8791/api/decks \
  -H 'Content-Type: application/json' \
  -d '{"title": "Mon-arbitrage", "template": "triage", "items": ["Élément 1", "Élément 2"]}'
```

`items` est un tableau de lignes non vides (200 cartes max, 500 caractères par carte), `template` vaut `triage` (défaut), `binary` ou `priority`. Sans champ `id`, l'identifiant est dérivé du titre ; avec un `id` explicite, la création échoue en `409` si le deck existe déjà (jamais d'écrasement). La réponse `201` contient l'état du deck, prêt à être joué.

L'interface web expose exactement le même parcours (bouton **Créer un deck** sur l'écran d'accueil).

### Convention canonique des options par défaut

Pour garantir la mémoire musculaire, tout deck standard suit la polarité et les directions canoniques :

| Ordre | Polarité | Direction swipe | Touche | Couleur | Action par défaut (template `triage`) |
|---|---|---|---|---|---|
| **Option 1** | **Positif** | **Droite** (`east`) | `d` | `success` | *Conserver / Valider* |
| **Option 2** | **Négatif** | **Gauche** (`west`) | `a` | `danger` | *Élaguer / Rejeter* |
| **Option 3** | **Neutre** | **Haut** (`north`) | `w` | `warning` | *À revoir / Modifier* |
| **Option 4** | **Spécial** | **Bas** (`south`) | `s` | `info` | *Archiver / Escalader* |
| **5+** | **Custom** | Dock / Boutons | Clavier | `neutral` | Personnalisable (`--actions-file`) |

### Templates d'actions intégrés

* **`triage`** (3 voies, par défaut) :
  - Est (`d`) : *Conserver / Valider* (vert)
  - Ouest (`a`) : *Élaguer / Rejeter* (rouge)
  - Nord (`w`) : *À revoir / Modifier* (jaune)
* **`binary`** (2 voies) :
  - Est (`d`) : *Oui / Valider*
  - Ouest (`a`) : *Non / Rejeter*
* **`priority`** (3 voies) :
  - Est (`d`) : *Immédiat*
  - Ouest (`a`) : *Ignorer*
  - Nord (`w`) : *Plus tard*

---

## 2. Inviter l'Utilisateur à Trancher

Donnez le lien direct avec le nom du deck :
> *"J'ai préparé un deck de tri [Titre du deck] sur http://localhost:8791/#mon-arbitrage."*

L'utilisateur peut trancher :
- En swipant librement sur mobile ou via raccourcis clavier (`d`, `a`, `w` ou flèches directionnelles).
- En ajoutant un **commentaire optionnel** dans le champ texte dédié avant de trancher.
- En différant une carte hésitante via **`Echap`** ou **`x`** (skip en fond de pile).
- En annulant à tout moment via `Ctrl+Z` ou le bouton mobile `↩ Annuler`.

---

## 3. Récupérer les Décisions

### Vérifier l'avancement
```bash
python3 deck_cli.py status mon-arbitrage
```
Retourne l'objet d'état avec `is_completed: true|false`, `pending_count` et `decided_count`.

### Lire le récapitulatif final
```bash
python3 deck_cli.py summary mon-arbitrage --format md
```
Retourne un rapport Markdown directement exploitable, ou en JSON brut (`--format json`).

---

## 4. Suggestions IA & BYOK (OpenAI, Ollama, Custom)

L'interface Quick-Pick permet de brancher n'importe quel modèle de décision (OpenAI, Ollama local, Groq, OpenRouter ou API FastAPI custom) pour afficher des badges de pré-qualification sur les cartes.

1. **Test en CLI** :
   ```bash
   python3 deck_cli.py classifier --endpoint "http://localhost:11434/v1" --api-key ""
   ```
2. **Configuration dans l'interface** :
   - Bouton **`⚙️`** dans le header de l'application.
   - Saisie du protocole (OpenAI-compatible ou Custom Webhook), de l'Endpoint, du Modèle et de la clé API (BYOK).
   - Les clés sont conservées dans le `localStorage` du navigateur de l'utilisateur, sans jamais fuiter dans des fichiers serveur ou dépôts Git.
