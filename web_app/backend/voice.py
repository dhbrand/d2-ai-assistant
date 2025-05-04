from fastapi import APIRouter, UploadFile, File, HTTPException
from openai import OpenAI
import os

router = APIRouter()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@router.post("/api/voice-to-text")
async def voice_to_text(file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_bytes,
            filename=file.filename
        )
        return {"text": transcript.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}") 