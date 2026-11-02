"""Voice input for a manager on the floor.

The phone or laptop browser does the listening when it can (Web Speech API, in voice.js). When it cannot (Firefox, some
in-app browsers) the page records a short clip and sends it here; the server transcribes it with the configured OpenAI
speech model and returns text. The audio is not stored. Either way the text then goes through the normal chat, so every
rule still applies: actions are previewed and need the exact confirmation phrase, which voice input never sends on its own.

POST /api/v1/voice/transcribe   body: the audio bytes (audio/webm, audio/ogg, audio/mp4, audio/wav; at most 4 MB)
                                -> {"text": "...", "normalized": "...", "model": "..."}
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=['Voice'])
MAX_BYTES = 4 * 1024 * 1024
EXTENSIONS = {'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'mp4', 'audio/mpeg': 'mp3', 'audio/wav': 'wav', 'audio/x-wav': 'wav'}
from ..services.order_refs import DIGITS, ORDER_RE, normalize_order_refs  # noqa: F401  (shared with typed messages)


def normalize_spoken(text: str) -> str:
    """Spoken order numbers into the form the system uses; see services/order_refs.py."""
    return normalize_order_refs(text)


def vocabulary(request: Request) -> str:
    """A short prompt with the factory's own words, so names and order IDs are transcribed as written."""
    try:
        rows = request.app.state.workflow.tools.rows('orders.csv')
        customers = sorted({e.record['customer'] for e in rows})[:20]
        products = sorted({e.record['product'] for e in rows})[:20]
    except Exception:
        customers, products = [], []
    return ('A garment factory manager asks about orders such as ORD-005 or ORD-120, stages KNITTING, ASSEMBLY, WASHING, PACKING, '
            'customers ' + ', '.join(customers) + '; products ' + ', '.join(products) + '.')


@router.post('/api/v1/voice/transcribe')
async def transcribe(request: Request) -> dict:
    client = getattr(request.app.state, 'client', None)
    if client is None:
        raise HTTPException(503, {'code': 'VOICE_UNAVAILABLE', 'message': 'Voice transcription needs the model key on the server. Type the question instead.'})
    kind = (request.headers.get('content-type') or '').split(';')[0].strip().lower()
    if kind not in EXTENSIONS:
        raise HTTPException(415, {'code': 'UNSUPPORTED_AUDIO', 'message': 'Send audio/webm, audio/ogg, audio/mp4, audio/mpeg or audio/wav.'})
    audio = await request.body()
    if not audio:
        raise HTTPException(422, {'code': 'EMPTY_AUDIO', 'message': 'No audio received. Hold the button and speak.'})
    if len(audio) > MAX_BYTES:
        raise HTTPException(413, {'code': 'AUDIO_TOO_LONG', 'message': 'Keep a voice question under about a minute.'})
    model = request.app.state.settings.transcribe_model
    try:
        result = await client.audio.transcriptions.create(model=model, file=(f'question.{EXTENSIONS[kind]}', audio, kind), prompt=vocabulary(request))
    except Exception:
        raise HTTPException(502, {'code': 'VOICE_PROVIDER_ERROR', 'message': 'The speech service did not answer. Type the question or try again.'})
    text = (getattr(result, 'text', None) or (result.get('text') if isinstance(result, dict) else '') or '').strip()
    return {'text': text, 'normalized': normalize_spoken(text), 'model': model}
