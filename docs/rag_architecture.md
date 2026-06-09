# Architecture du module RAG documentaire

## Objectif

Le module RAG permet d'exposer un chatbot documentaire multi-client pour FormDev.

Il doit permettre à l'ERP ou aux extranets clients de poser des questions
sur une base documentaire composée de PDF, DOCX, TXT et URLs.

## Architecture cible

```text
ERP / Extranet FormDev
        ↓
API FastAPI /rag/*
        ↓
Qdrant : recherche des chunks documentaires
        ↓
Prompt RAG
        ↓
vLLM : génération de la réponse
        ↓
Réponse + sources
Composants
FastAPI : endpoints HTTP.
PostgreSQL : sources, clients, corpus, conversations.
Qdrant : chunks documentaires vectorisés.
vLLM : génération locale.
FastEmbed : embeddings locaux.
Redis/RQ : ingestion asynchrone des documents.
Collection Qdrant

Collection dédiée :

rag_chunks

Payload minimal :

{
  "client_id": "client_demo",
  "corpus_id": "default",
  "source_id": "src_123",
  "source_type": "pdf",
  "source_name": "guide.pdf",
  "page": 4,
  "chunk_index": 12,
  "is_active": true,
  "text": "..."
}
Principe multi-client

Toutes les recherches Qdrant doivent être filtrées par :

client_id + corpus_id + is_active=true

Cela évite qu'un client puisse récupérer des documents appartenant à un autre client.

Routes prévues
GET    /rag/health
POST   /rag/sources/upload
POST   /rag/sources/url
GET    /rag/sources
DELETE /rag/sources/{source_id}
POST   /rag/resync
POST   /rag/chat