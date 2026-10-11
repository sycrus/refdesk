"""Every retriever by name. Shared tests (e.g. the reproduction rights filter) run over
this registry, so a new retriever is covered as soon as it is registered."""

from refdesk.retrieval.metadata import JaccardRetriever

RETRIEVERS = {"jaccard": JaccardRetriever}
