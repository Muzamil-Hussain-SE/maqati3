"""HTTP routes. They ask the repository, apply the publication gates, and shape the
answer -- no other logic lives here."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile

from masdar.api.repository import (
    EntryRow,
    LibraryRepository,
)
from masdar.api.schemas import (
    EntryOut,
    EntryPageOut,
    ScholarListItem,
    TopicNode,
    TranscriptOut,
    UploadCheckOut,
    UploadMatchOut,
    approved_languages,
    build_topic_tree,
    render_webvtt,
)
from masdar.api.uploads import KnownHashes, UploadStore
from masdar.dedup.fingerprint import FingerprintExtractor
from masdar.dedup.triage import (
    ExactDuplicate,
    FingerprintCandidates,
    FingerprintIndex,
    triage_upload,
)
from masdar.domain import (
    Lang,
    ReviewState,
    Visibility,
)
from masdar.register.gates import can_publish

router = APIRouter()

#: Returned for an entry that does not exist AND for one that exists but is not public.
#: The two cases must be indistinguishable -- that a withheld entry exists is itself
#: information about a scholar, so the API does not leak it through a 403.
ENTRY_NOT_FOUND = "entry_not_found"

#: Returned when the entry is public but the requested language has not been approved.
#: Over most of this archive's life the normal state is: Arabic present, translations
#: not. That is not a failure, so the body says which languages the client can ask for
#: instead of only refusing.
TRANSCRIPT_NOT_AVAILABLE = "transcript_not_available"

SCHOLAR_NOT_FOUND = "scholar_not_found"

MAX_PAGE_SIZE = 100


def get_repository() -> LibraryRepository:
    """Dependency placeholder; `create_app` always overrides it."""
    raise NotImplementedError("repository was not provided to create_app")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


Repo = Annotated[LibraryRepository, Depends(get_repository)]


def get_upload_store() -> UploadStore:
    """Dependency placeholder; `create_app` overrides it when uploads are wired."""
    raise NotImplementedError("upload store was not provided to create_app")


def get_extractor() -> FingerprintExtractor:
    """Dependency placeholder; `create_app` overrides it when uploads are wired."""
    raise NotImplementedError("fingerprint extractor was not provided to create_app")


def get_fingerprint_index() -> FingerprintIndex:
    """Dependency placeholder; `create_app` overrides it when uploads are wired."""
    raise NotImplementedError("fingerprint index was not provided to create_app")


def get_known_hashes() -> KnownHashes:
    """Dependency placeholder; `create_app` overrides it when uploads are wired."""
    raise NotImplementedError("known hashes were not provided to create_app")


Store = Annotated[UploadStore, Depends(get_upload_store)]
Extractor = Annotated[FingerprintExtractor, Depends(get_extractor)]
Index = Annotated[FingerprintIndex, Depends(get_fingerprint_index)]
Hashes = Annotated[KnownHashes, Depends(get_known_hashes)]


def arabic_state(entry: EntryRow) -> ReviewState:
    """The Arabic review state, treating a missing row as not started.

    Fails closed on purpose: an entry with no `ar` row at all has certainly not been
    reviewed, and the absence must not read as permission.
    """
    for language in entry.languages:
        if language.lang is Lang.AR:
            return language.state
    return ReviewState.NOT_STARTED


def is_published(entry: EntryRow) -> bool:
    """The publication conditions, delegated to the single definition of them.

    `register.gates.can_publish` is the one place register rule 2 is written down, and
    the database's `public_requires_attribution` CHECK mirrors its attribution half.
    Restating either here would let the three drift apart, which is how a row marked
    public with unreviewed Arabic ends up served: title, question and hukm are produced
    by a model during ingest, so before Arabic approval no human has read them.
    """
    return (
        entry.visibility is Visibility.PUBLIC
        and can_publish(entry.attribution, arabic_state(entry)).allowed
    )


def public_or_404(entry: EntryRow | None) -> EntryRow:
    """The publication gate. Everything that serves entry content goes through here."""
    if entry is None or not is_published(entry):
        raise HTTPException(status_code=404, detail=ENTRY_NOT_FOUND)
    return entry


@router.get("/api/v1/entries/{entry_id}")
def get_entry(entry_id: str, repository: Repo) -> EntryOut:
    return EntryOut.of(public_or_404(repository.entry(entry_id)))


def approved_or_404(entry: EntryRow, lang: Lang) -> None:
    """The translation gate. An unapproved transcript is never served, in any form."""
    available = approved_languages(entry)
    if lang not in available:
        raise HTTPException(
            status_code=404,
            detail={
                "error": TRANSCRIPT_NOT_AVAILABLE,
                "entry_id": entry.id,
                "requested_lang": lang.value,
                "available_languages": [other.value for other in available],
            },
        )


@router.get("/api/v1/entries/{entry_id}/transcript")
def get_transcript(entry_id: str, lang: Lang, repository: Repo) -> TranscriptOut:
    entry = public_or_404(repository.entry(entry_id))
    approved_or_404(entry, lang)
    return TranscriptOut.of(entry, lang, repository.segments(entry_id, lang))


@router.get("/api/v1/entries/{entry_id}/transcript.vtt", response_class=Response)
def get_transcript_vtt(entry_id: str, lang: Lang, repository: Repo) -> Response:
    entry = public_or_404(repository.entry(entry_id))
    approved_or_404(entry, lang)
    body = render_webvtt(list(repository.segments(entry_id, lang)))
    return Response(content=body, media_type="text/vtt; charset=utf-8")


@router.get("/api/v1/scholars/{scholar_id}/entries")
def list_scholar_entries(
    scholar_id: str,
    repository: Repo,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EntryPageOut:
    page = repository.entries_by_scholar(scholar_id, limit=limit, offset=offset)
    if page is None:
        raise HTTPException(status_code=404, detail=SCHOLAR_NOT_FOUND)
    public = [entry for entry in page.items if is_published(entry)]
    return EntryPageOut(
        items=[EntryOut.of(entry) for entry in public],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/v1/scholars")
def list_scholars(repository: Repo) -> list[ScholarListItem]:
    return [ScholarListItem.of(scholar) for scholar in repository.scholars()]


@router.get("/api/v1/topics")
def list_topics(repository: Repo) -> list[TopicNode]:
    return build_topic_tree(list(repository.topics()))


# --------------------------------------------------------------- bulk upload


def visible_match(entry_id: str, repository: LibraryRepository) -> EntryRow | None:
    """The matched entry if the public may see it, else None.

    Same gate as every other route: the upload page is an unlisted link, not a login,
    so it reveals nothing the public API would not.
    """
    entry = repository.entry(entry_id)
    return entry if entry is not None and is_published(entry) else None


@router.post("/api/v1/uploads")
def check_upload(
    file: UploadFile,
    repository: Repo,
    store: Store,
    extractor: Extractor,
    index: Index,
    hashes: Hashes,
) -> UploadCheckOut:
    """Stage one uploaded file and say what it is: rejected, candidates, or new.

    A plain `def`, not `async def`: hashing, ffprobe and fpcalc block, and FastAPI runs
    a sync route in its threadpool instead of stalling the event loop for everyone
    else uploading at the same time.
    """
    staged = store.stage(file.filename or "upload", file.file)
    result = triage_upload(
        staged.path,
        staged.duration_ms,
        sha256=staged.sha256,
        known_sha256=hashes.known(),
        extractor=extractor,
        index=index,
    )
    if isinstance(result, ExactDuplicate):
        # Nothing to decide about identical bytes, so nothing worth keeping on disk.
        store.discard(staged.path)
        return UploadCheckOut(
            sha256=staged.sha256,
            status="rejected",
            duplicate_of=UploadMatchOut.of(visible_match(result.entry_id, repository)),
        )
    if isinstance(result, FingerprintCandidates):
        return UploadCheckOut(
            sha256=staged.sha256,
            status="candidates",
            candidates=[
                UploadMatchOut.of(
                    visible_match(candidate.entry_id, repository),
                    run_length=candidate.match.run_length,
                )
                for candidate in result.candidates
            ],
        )
    return UploadCheckOut(sha256=staged.sha256, status="new")
