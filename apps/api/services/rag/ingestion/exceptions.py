class DuplicateSourceError(ValueError):
    """Erreur levée quand une source existe déjà dans un corpus."""

    def __init__(
        self,
        *,
        message: str,
        existing_source,
    ) -> None:
        self.detail = {
            "message": message,
            "existing_source_id": existing_source.source_id,
            "existing_source_name": existing_source.source_name,
            "existing_source_type": existing_source.source_type,
            "existing_status": existing_source.status,
            "client_id": existing_source.client_id,
            "corpus_id": existing_source.corpus_id,
        }

        super().__init__(message)
