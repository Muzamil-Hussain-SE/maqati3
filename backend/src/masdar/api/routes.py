"""HTTP routes. They ask the repository, apply the publication gates, and shape the
answer -- no other logic lives here."""

from __future__ import annotations

import hmac
import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

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
    UploadDecisionIn,
    UploadDecisionOut,
    UploadMatchOut,
    approved_languages,
    build_topic_tree,
    render_webvtt,
)
from masdar.api.uploads import (
    SUBMISSION_PREFIX,
    KnownHashes,
    Submissions,
    UploadStore,
    UploadTooLarge,
    is_submission_key,
)
from masdar.dedup.fingerprint import FingerprintExtractor, UnreadableMedia
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
def get_submissions() -> Submissions:
    """Dependency placeholder; `create_app` overrides it when uploads are wired."""
    raise NotImplementedError("submissions were not provided to create_app")


Hashes = Annotated[KnownHashes, Depends(get_known_hashes)]
Pending = Annotated[Submissions, Depends(get_submissions)]


def get_upload_key() -> str | None:
    """The key the unlisted upload link carries. None only where `create_app` was built
    without one -- tests; `server.build_app` refuses to start without it."""
    return None


UPLOAD_KEY_REQUIRED = "upload_key_required"


def _check_key(expected: str | None, given: str | None) -> None:
    if expected is None:
        return
    if given is None or not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail=UPLOAD_KEY_REQUIRED)


def require_upload_key(
    expected: Annotated[str | None, Depends(get_upload_key)],
    x_upload_key: Annotated[str | None, Header()] = None,
) -> None:
    """The unlisted link hides the page, not the API behind it. Its key is the credential:
    without it anyone who found the endpoint could fill the disk."""
    _check_key(expected, x_upload_key)


def require_upload_key_or_query(
    expected: Annotated[str | None, Depends(get_upload_key)],
    x_upload_key: Annotated[str | None, Header()] = None,
    k: Annotated[str | None, Query()] = None,
) -> None:
    """Same key, also accepted as ?k= -- only for media, because a <video src> cannot
    send a header."""
    _check_key(expected, x_upload_key if x_upload_key is not None else k)


Keyed = Depends(require_upload_key)
KeyedMedia = Depends(require_upload_key_or_query)

#: The upload was decided already, or never triaged. One answer for both, like
#: ENTRY_NOT_FOUND: a stranger probing hashes learns nothing from the difference.
NOT_AWAITING_DECISION = "not_awaiting_decision"

#: The file has no audio that could be decoded: a photo, a silent screen recording, a
#: document renamed to .mp4. Nothing in it could ever be transcribed.
NO_READABLE_AUDIO = "no_readable_audio"

UPLOAD_TOO_LARGE = "upload_too_large"


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


def visible_match(
    key: str, repository: LibraryRepository, overlap_ms: int | None = None
) -> UploadMatchOut:
    """What the uploader may see of a match, by its match key.

    Same gate as every other route: the upload page is an unlisted link, not a login,
    so it reveals nothing the public API would not. A pending upload is reported as
    such -- the contributor should know another brother sent it in -- but not named.
    """
    if is_submission_key(key):
        return UploadMatchOut.pending_upload(
            preview_id=key.removeprefix(SUBMISSION_PREFIX), overlap_ms=overlap_ms
        )
    entry = repository.entry(key)
    published = entry if entry is not None and is_published(entry) else None
    return UploadMatchOut.of(published, overlap_ms=overlap_ms)


@router.post("/api/v1/uploads", dependencies=[Keyed])
def check_upload(
    file: UploadFile,
    repository: Repo,
    store: Store,
    extractor: Extractor,
    index: Index,
    hashes: Hashes,
    submissions: Pending,
) -> UploadCheckOut:
    """Stage one uploaded file and say what it is: rejected, candidates, or new.

    A plain `def`, not `async def`: hashing, ffprobe and fpcalc block, and FastAPI runs
    a sync route in its threadpool instead of stalling the event loop for everyone
    else uploading at the same time.
    """
    name = file.filename or "upload"
    try:
        staged = store.stage(name, file.file)
    except UploadTooLarge as exc:
        raise HTTPException(status_code=413, detail=UPLOAD_TOO_LARGE) from exc
    try:
        result = triage_upload(
            staged.path,
            sha256=staged.sha256,
            known_sha256=hashes.known(),
            extractor=extractor,
            index=index,
        )
    except UnreadableMedia as exc:
        store.discard(staged.path)
        raise HTTPException(status_code=422, detail=NO_READABLE_AUDIO) from exc
    if isinstance(result, ExactDuplicate):
        # Nothing to decide about identical bytes, so nothing worth keeping on disk.
        store.discard(staged.path)
        return UploadCheckOut(
            sha256=staged.sha256,
            status="rejected",
            duplicate_of=visible_match(result.entry_id, repository),
        )

    candidates = result.candidates if isinstance(result, FingerprintCandidates) else []
    recorded = submissions.record(
        sha256=staged.sha256,
        original_name=name,
        staged_path=staged.path,
        fingerprint=result.fingerprint,
        candidate_keys=[candidate.entry_id for candidate in candidates],
    )
    if not recorded:
        # Identical bytes arrived from someone else between our hash check and our
        # insert. Theirs won; this copy is the duplicate.
        store.discard(staged.path)
        return UploadCheckOut(
            sha256=staged.sha256,
            status="rejected",
            duplicate_of=UploadMatchOut.pending_upload(preview_id=staged.sha256),
        )
    if candidates:
        return UploadCheckOut(
            sha256=staged.sha256,
            status="candidates",
            candidates=[
                visible_match(c.entry_id, repository, overlap_ms=c.match.overlap_ms)
                for c in candidates
            ],
        )
    return UploadCheckOut(sha256=staged.sha256, status="new")


@router.post("/api/v1/uploads/{sha256}/decision", dependencies=[Keyed])
def decide_upload(
    sha256: str, decision: UploadDecisionIn, store: Store, submissions: Pending
) -> UploadDecisionOut:
    """The contributor keeps a triaged upload, with what they know about it, or drops it."""
    if not decision.keep:
        path = submissions.drop(sha256)
        if path is None:
            raise HTTPException(status_code=409, detail=NOT_AWAITING_DECISION)
        store.discard(path)
        return UploadDecisionOut(sha256=sha256, status="dropped")

    if decision.contributor is None:
        # UploadDecisionIn already refuses this; checked again because the schema's own
        # CHECK is the last line, and an assert would vanish under -O.
        raise HTTPException(status_code=422, detail="contributor is required")
    kept = submissions.keep(sha256, decision.contributor)
    if not kept:
        raise HTTPException(status_code=409, detail=NOT_AWAITING_DECISION)
    return UploadDecisionOut(sha256=sha256, status="kept")


#: What phones and messengers produce, pinned: `mimetypes` answers audio/mp4a-latm for
#: .m4a, a raw-stream type no browser plays from a file.
PREVIEW_TYPES = {
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".3gp": "video/3gpp",
    ".opus": "audio/ogg",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".webm": "video/webm",
}


@router.get("/api/v1/uploads/{sha256}/media", dependencies=[KeyedMedia])
def upload_media(sha256: str, store: Store, submissions: Pending) -> FileResponse:
    """A recorded upload's file, for the contributor comparing a candidate by ear.

    FileResponse answers byte ranges, which is what lets a browser seek in a video. The
    path comes back out of the database; the store decides whether it is a staged file.
    """
    recorded = submissions.staged_path(sha256)
    path = store.locate(recorded) if recorded is not None else None
    if path is None:
        raise HTTPException(status_code=404, detail="media_not_found")
    media_type = PREVIEW_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0]
    return FileResponse(path, media_type=media_type or "application/octet-stream")
