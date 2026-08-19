# Model Providers

PCE never assumes a specific LLM. Providers are a thin, swappable interface:

```python
class LLMProvider:
    def generate(self, messages): ...

class EmbeddingProvider:
    def embed(self, texts): ...

class Reranker:
    def rank(self, query, candidates): ...
```

Initial focus is local OpenAI-compatible endpoints (e.g. served by Jan, Open
WebUI, LM Studio, or a bare llama.cpp/vLLM server) plus simple provider
adapters where a service does not speak that protocol.

## Index generations

Every index records the embedding model, embedding version, dimensions,
parser version, chunking version, and schema version it was built with.
Incompatible embeddings are never silently mixed — a model swap that changes
embedding dimensions triggers a new index generation rather than corrupting
the old one.

## Model independence

The same indexed corpus must be usable through at least two different local
model-provider configurations without re-ingestion — swapping the model
should never require rebuilding personal context.
