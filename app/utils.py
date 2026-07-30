def sanitize_doc_id(value: str) -> str:
    """Firestore document IDs can't contain '/' - it's parsed as a path separator."""
    return value.replace("/", "__")
