"""Offline retrieval evaluation runner over a labelled golden dataset.

A golden dataset pairs a set of documents (each with a stable ``label``) with
queries whose relevant documents are named by those labels. The runner ingests
the documents into the workspace-scoped stack, runs hybrid retrieval for every
query, maps the returned ``document_id`` values back to labels, and aggregates
recall@k, precision@k and MRR. It reuses the production retrieval path so the
metrics reflect real behaviour rather than a bespoke code path.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.vectorstore.base import VectorStore
from app.core.config import Settings, get_settings
from app.eval import metrics
from app.services import retrieval


@dataclass(slots=True)
class GoldenDocument:
    """A document to ingest, addressed by a stable ``label``."""

    label: str
    text: str


@dataclass(slots=True)
class GoldenCase:
    """A query and the labels of the documents that should be retrieved."""

    query: str
    relevant_labels: set[str]


@dataclass(slots=True)
class GoldenDataset:
    """A corpus plus the queries evaluated against it."""

    documents: list[GoldenDocument]
    cases: list[GoldenCase]


@dataclass(slots=True)
class EvalReport:
    """Aggregated metrics across all cases plus per-case recall."""

    k: int
    recall_at_k: float
    precision_at_k: float
    mrr: float
    per_case_recall: list[float] = field(default_factory=list)


def sample_dataset() -> GoldenDataset:
    """A small, deterministic dataset with clearly separable vocabularies."""
    return GoldenDataset(
        documents=[
            GoldenDocument("capital", "The capital of Nexus is Aurora, a coastal city."),
            GoldenDocument("founded", "Nexus was founded in the year 2021 by engineers."),
            GoldenDocument("cadence", "The team ships product updates every single week."),
        ],
        cases=[
            GoldenCase("What is the capital of Nexus?", {"capital"}),
            GoldenCase("When was Nexus founded?", {"founded"}),
            GoldenCase("How often does the team ship updates?", {"cadence"}),
        ],
    )


async def run_evaluation(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    dataset: GoldenDataset,
    label_to_document_id: dict[str, str],
    embedder: EmbeddingProvider,
    store: VectorStore,
    k: int = 5,
    settings: Settings | None = None,
) -> EvalReport:
    """Run every case through retrieval and aggregate the metrics.

    ``label_to_document_id`` maps each golden label to the ``document_id`` the
    documents received once ingested, so retrieved ids can be scored by label.
    """
    settings = settings or get_settings()
    recalls: list[float] = []
    precisions: list[float] = []
    rrs: list[float] = []
    for case in dataset.cases:
        result = await retrieval.retrieve(
            db,
            workspace_id=workspace_id,
            query=case.query,
            embedder=embedder,
            store=store,
            settings=settings,
        )
        seen: list[str] = []
        for citation in result.citations:
            document_id = str(citation.get("document_id", ""))
            if document_id and document_id not in seen:
                seen.append(document_id)
        relevant_ids = {
            label_to_document_id[label]
            for label in case.relevant_labels
            if label in label_to_document_id
        }
        recalls.append(metrics.recall_at_k(seen, relevant_ids, k))
        precisions.append(metrics.precision_at_k(seen, relevant_ids, k))
        rrs.append(metrics.reciprocal_rank(seen, relevant_ids))
    return EvalReport(
        k=k,
        recall_at_k=metrics.mean(recalls),
        precision_at_k=metrics.mean(precisions),
        mrr=metrics.mean(rrs),
        per_case_recall=recalls,
    )
