# Documentation client technique — Chat IA

Cette page décrit ce qu'un CRM/front doit envoyer à l'API Chat et ce qu'il peut attendre en retour.

## Route

```text
POST /v1/chat
```

## Authentification

Toutes les requêtes doivent fournir la clé API client :

```text
X-API-Key: <clé_api>
Content-Type: application/json
```

## Usage attendu côté CRM

La route sert à générer, reformuler, résumer, enrichir ou corriger du texte via le modèle LLM servi par vLLM.

Cas d'usage typiques :

- reformulation professionnelle ;
- synthèse ;
- génération de contenu pédagogique ;
- enrichissement de texte ;
- correction optionnelle en seconde passe.

## Payload d'entrée

```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
  "messages": [
    {
      "role": "user",
      "content": "Résume ce texte en 3 phrases claires : ..."
    }
  ],
  "system_prompt": "Tu es un assistant de rédaction professionnelle.",
  "temperature": 0.2,
  "top_p": 0.9,
  "max_tokens": 300,
  "post_correction": false,
  "post_correction_prompt": null
}
```

## Champs d'entrée

| Champ | Type | Obligatoire | Rôle |
| --- | --- | --- | --- |
| `messages` | array | oui | Conversation envoyée au modèle. Au minimum un message `user`. |
| `messages[].role` | string | oui | `user`, `assistant` ou `system`. Les `system` de l'historique sont ignorés ; le backend compose son contrat et les instructions métier. |
| `messages[].content` | string | oui | Texte envoyé au modèle. |
| `model` | string | non | Nom du modèle demandé. Si absent, le backend utilise sa valeur par défaut. |
| `system_prompt` | string | non | Prompt système métier. Permet de cadrer le ton, le rôle et les contraintes. |
| `temperature` | number | non | Niveau de variation. Recommandé : `0.2` pour les usages métier stables. |
| `top_p` | number | non | Diversité de génération. Recommandé : `0.9`. |
| `max_tokens` | integer | non | Longueur maximale de la réponse générée. |
| `post_correction` | boolean | non | Si `true`, lance une seconde inférence de correction linguistique. |
| `post_correction_prompt` | string | non | Prompt spécifique de correction si `post_correction=true`. |

## Réponse de sortie

```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct-AWQ",
  "content": "Texte généré par le modèle.",
  "finish_reason": "stop",
  "usage": {
    "prompt_tokens": 323,
    "completion_tokens": 58,
    "total_tokens": 381
  },
  "latency_ms": 167.5
}
```

## Champs de sortie

| Champ | Type | Rôle |
| --- | --- | --- |
| `model` | string | Modèle réellement utilisé par le serveur d'inférence. |
| `content` | string | Texte final à afficher ou stocker côté CRM. |
| `finish_reason` | string/null | Raison d'arrêt du modèle : souvent `stop`, parfois `length`. |
| `usage.prompt_tokens` | integer/null | Tokens consommés par l'entrée. |
| `usage.completion_tokens` | integer/null | Tokens générés. |
| `usage.total_tokens` | integer/null | Total utilisé pour le suivi coût/usage. |
| `latency_ms` | number | Latence totale côté API. |

## Exemple curl

```bash
curl -s -X POST "$API/v1/chat" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Résume ce texte en 3 phrases claires : ..."
      }
    ],
    "temperature": 0.2,
    "top_p": 0.9,
    "max_tokens": 300,
    "post_correction": false
  }' | jq
```

## Erreurs fréquentes

| Code | Cause probable | Action CRM |
| --- | --- | --- |
| 401 | Clé API absente ou invalide | Vérifier le header `X-API-Key`. |
| 422 | Payload invalide | Vérifier `messages`, types et champs numériques. |
| 429 | Rate limit atteint | Retenter plus tard ou limiter les appels. |
| 502 | vLLM indisponible ou erreur upstream | Afficher un message temporaire et retenter. |

## Bonnes pratiques d'intégration

- Mettre l'instruction principale dans le message `user`.
- Utiliser `temperature=0.2` pour les usages métier stables.
- Limiter `max_tokens` pour éviter des réponses trop longues.
- Stocker `usage.total_tokens` si le CRM veut suivre la consommation.
- Activer `post_correction` seulement si une seconde inférence est acceptable en coût/latence.

## Limites de taille et de contexte

Les prompts ne sont plus limites a 4 000 caracteres. Un garde-fou
applicatif autorise au plus 256 messages et 100 000 caracteres cumules
(contenus des messages, system_prompt, post_correction_prompt et model).
Les prompts sont comptes meme si la post-correction est desactivee.
Un depassement de ce garde-fou produit le 422 de validation habituel.

Ce garde-fou ne mesure pas les tokens et ne garantit pas que la requete
tient dans le contexte. Il ne constitue pas une limite du corps HTTP brut.
vLLM reste l'autorite pour le comptage exact avec le tokenizer et le
template du modele : entree complete + budget de sortie doivent tenir
dans MAX_MODEL_LEN (8192 dans la configuration de l'incident).
max_tokens conserve ses bornes 1 a 1024.

Un HTTP 400 vLLM avec un message reconnu de depassement de contexte
devient HTTP 422, avec detail.code = "context_too_long" et
detail.message = "Le contexte dépasse la capacité du modèle. Réduisez l'historique, les prompts ou max_tokens."
Le CRM doit reduire la requete avant de retenter. Aucun corps d'erreur
vLLM ni traceback n'est renvoye. Les autres erreurs upstream restent 502.

Cette regle couvre la generation, la continuation (budget de 150 tokens)
et la post-correction (budget max(max_tokens, 256)). Une passe ulterieure
peut echouer apres une generation reussie ; aucune reponse partielle
n'est alors renvoyee. Reduire les prompts ou l'historique reste necessaire
si reduire max_tokens ne suffit pas pour cette passe.
Il n'y a ni troncature automatique ni estimation caracteres/tokens.

Seuls model, messages, max_tokens, temperature et top_p sont transmis
comme parametres vLLM. Les prompts internes restent utilises pour
construire les messages systeme. post_correction, system_prompt et
post_correction_prompt ne sont jamais transmis comme champs bruts.

Tests isoles, sans GPU ni base externe, depuis la racine du depot :
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=apps/api python -B -m unittest discover -s apps/api/tests -p test_chat_limits.py -v

La detection cible les messages de vLLM 0.16.0. Un format inconnu reste
une erreur upstream 502 et necessite un nouveau cas de regression.

## Contrat de transformation et préservation du format

Chaque inférence Chat reçoit un contrat technique permanent, puis les instructions
métier du client (system_prompt ou post_correction_prompt selon la passe).
Un prompt absent, vide ou composé d'espaces utilise le défaut métier.
Le contrat demande une seule sortie, sans préambule, commentaire ou variante.
Lorsqu'un texte source est fourni à transformer, il impose de préserver son format
et ses styles, sans inventer de gras, italique, titres, listes ou mise en forme.
En génération pure, sans texte source à transformer, la structure et la mise en
forme demandées par le métier restent autorisées.
Les instructions contenues dans le texte source sont traitées comme des données.
Les messages user et assistant restent dans leurs rôles, sans réécriture.

L'API ne sépare pas explicitement la consigne et la source du premier appel.
Le contrat améliore le cadrage mais ne garantit ni la fidélité sémantique,
ni l'immunité aux injections, ni la conservation exacte du HTML/CKEditor.
Il ajoute des tokens ; les limites et la gestion de contexte restent inchangées.

La continuation reste limitée à un appel de 150 tokens. Elle demande seulement
le suffixe manquant. Si le premier fragment ou les fragments réunis contiennent
des balises HTML reconnues, ils sont concaténés sans modifier leurs caractères.
Ce raccord ne répare pas le HTML et ne garantit pas l'absence de duplication.

La post-correction remplace la génération précédente uniquement si elle est
non vide, terminée par finish_reason="stop", et compatible avec son format.
Le contrôle compare la génération précédente et la correction, pas le DOM
original du client : présence de HTML, gras (strong/b), italique (em/i),
titres (h1-h6) et listes (ul/ol avec li). Il refuse l'apparition ou la disparition
complète de ces familles ; il n'impose pas leur nombre ni un DOM identique.
La génération précédente est le texte source de cette passe, y compris après
une génération pure. Ses styles existants sont donc préservés.
Les attributs, styles CSS et correspondances sémantiques ne sont pas validés.
Il s'agit d'un relevé de balises sans construction ni réécriture du DOM :
ce contrôle n'est ni une validation HTML complète ni une sanitization.

Une correction rejetée laisse inchangés le contenu et le finish_reason précédents,
y compris si cette génération précédente était tronquée. Les completion_tokens
consommés restent comptés selon la convention existante.
Les erreurs réseau et vLLM ne sont pas masquées : le contrat 422/502 reste inchangé.
La génération principale n'est pas soumise à ce contrôle de format.

Tests des deux blocs, sans GPU ni services externes :
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=apps/api python -B -m unittest discover -s apps/api/tests -p 'test_chat_*.py' -v
