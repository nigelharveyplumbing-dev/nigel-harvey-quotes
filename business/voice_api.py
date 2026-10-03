"""Private API: HMAC machine intake and existing staff-authenticated records."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from business.voice_models import VoiceEvent
from business import voice_store
from business.voice_security import INTAKE_PATH, MAX_BODY, verify, settings

router = APIRouter()


def private_response(content, status=200):
    return JSONResponse(content, status_code=status, headers={"Cache-Control": "no-store"})


@router.post(INTAKE_PATH, include_in_schema=False)
async def intake(request: Request):
    try:
        settings()
    except ValueError:
        raise HTTPException(503, "Private voice configuration unavailable")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY:
            raise HTTPException(413, "Voice event too large")
    try:
        nonce = verify(bytes(body), request.headers)
    except PermissionError:
        raise HTTPException(401, "Voice signature rejected")
    try:
        event = VoiceEvent.model_validate_json(bytes(body))
    except ValidationError:
        # Validation errors may contain the submitted personal data.
        raise HTTPException(422, "Invalid synthetic voice event")
    try:
        return private_response(voice_store.ingest(event, nonce))
    except PermissionError:
        raise HTTPException(401, "Voice signature replay rejected")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get("/api/voice/calls", include_in_schema=False)
def calls():
    settings()
    conn = voice_store.get_db()
    try:
        rows = conn.execute("SELECT id,lead_id,root_call_id,outcome,urgency,transfer_requested FROM voice_calls ORDER BY id DESC LIMIT 100").fetchall()
        return private_response([dict(row) for row in rows])
    finally:
        conn.close()


@router.get("/api/voice/calls/{call_id}", include_in_schema=False)
def call_detail(call_id: int):
    record = voice_store.get_call(call_id)
    if record is None:
        raise HTTPException(404, "Call not found")
    return private_response(record)


@router.delete("/api/voice/calls/{call_id}/transcript", include_in_schema=False)
def transcript_delete(call_id: int):
    if not voice_store.delete_transcript(call_id):
        raise HTTPException(404, "Call not found")
    return private_response({"deleted": True})


@router.post("/api/voice/maintenance/expire", include_in_schema=False)
def maintenance():
    return private_response(voice_store.expire())


@router.get("/api/voice/notifications", include_in_schema=False)
def notifications():
    settings()
    conn = voice_store.get_db()
    try:
        rows = conn.execute("SELECT id,call_id,message_id,state,attempts,available_at,last_error,expires_at FROM voice_notifications ORDER BY id DESC LIMIT 100").fetchall()
        return private_response([dict(row) for row in rows])
    finally:
        conn.close()


@router.post("/api/voice/notifications/{notification_id}/retry", include_in_schema=False)
def notification_retry(notification_id: int):
    if not voice_store.retry_notification(notification_id):
        raise HTTPException(409, "Only an unexpired failed notification can be retried")
    return private_response({"queued": True})
