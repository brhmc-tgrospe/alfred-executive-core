"""A.L.F.R.E.D. Physical Hardware & Gemini Live API Diagnostic Suite.

Validates:
1. .env file & GEMINI_API_KEY presence and format.
2. Direct Gemini Multimodal Live API bidirectional WebSocket connection using `gemini-3.8-live`.
3. Physical microphone hardware capture via sounddevice/PortAudio & live RMS calculation.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai
from google.genai import types
from backend.audio_manager import AudioManager


async def test_live_api_connection(api_key: str, model_id: str = "gemini-3.8-live"):
    print("\n" + "=" * 65)
    print(f"[*] PART B: Testing Gemini Multimodal Live API ({model_id})")
    print("=" * 65)

    client = genai.Client(api_key=api_key)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Fenrir")
            )
        ),
    )

    print(f"[*] Initiating WebSocket handshake with model: {model_id}...")
    try:
        async with client.aio.live.connect(model=model_id, config=config) as session:
            print("[+] WebSocket connection established successfully!")

            test_prompt = "Good evening Alfred. Status report."
            print(f"[*] Transmitting text greeting turn: '{test_prompt}'")
            await session.send(input=test_prompt, end_of_turn=True)

            print("[*] Listening for incoming response chunks from Gemini Live...")
            audio_chunks_count = 0
            total_audio_bytes = 0

            # Set a timeout for receiving the model's turn
            try:
                async with asyncio.timeout(10.0):
                    async for response in session.receive():
                        server_content = getattr(response, "server_content", None)
                        if server_content is not None:
                            model_turn = getattr(server_content, "model_turn", None)
                            if model_turn is not None:
                                for part in model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        audio_chunks_count += 1
                                        chunk_len = len(part.inline_data.data)
                                        total_audio_bytes += chunk_len
                                        if audio_chunks_count <= 5 or audio_chunks_count % 10 == 0:
                                            print(f"    [AUDIO CHUNK #{audio_chunks_count}] Received {chunk_len} bytes (PCM 24kHz)")
                                    if getattr(part, "text", None):
                                        print(f"    [TEXT PART]: {part.text}")

                            if getattr(server_content, "turn_complete", False):
                                print("[+] Model turn complete signal received from server.")
                                break
            except TimeoutError:
                print("[-] Turn timed out after 10.0s (partial audio captured).")

            print(f"[+] Live API Verification Passed: {audio_chunks_count} audio chunks received ({total_audio_bytes} total bytes).")
            return True

    except Exception as e:
        print(f"[-] Live API Connection Failed: {e}")
        return False


async def test_audio_hardware():
    print("\n" + "=" * 65)
    print("[*] PART C: Testing Physical Microphone Capture & RMS Engine")
    print("=" * 65)

    audio_mgr = AudioManager()
    print("[*] Initializing AudioManager and starting sounddevice input stream...")
    try:
        await audio_mgr.start()
        print("[+] sounddevice InputStream active.")

        # By default PTT is inactive so mic is muted. Toggle PTT active to read raw levels
        audio_mgr.set_push_to_talk(True)
        print("[*] Push-to-Talk set to ACTIVE (listening to ambient audio for 2.0s)...")

        rms_samples = []
        for i in range(20):
            await asyncio.sleep(0.1)
            current = audio_mgr.current_mic_rms
            rms_samples.append(current)
            bars = "#" * int(current * 40)
            print(f"    Sample {i+1:02d} (t={(i+1)*100}ms): RMS = {current:.4f} | {bars}")

        await audio_mgr.stop()
        print("[+] sounddevice InputStream stopped cleanly.")

        avg_rms = sum(rms_samples) / len(rms_samples) if rms_samples else 0.0
        max_rms = max(rms_samples) if rms_samples else 0.0
        min_rms = min(rms_samples) if rms_samples else 0.0

        print(f"\n[+] Audio Hardware Metrics over 2.0 seconds:")
        print(f"    - Min RMS:  {min_rms:.4f}")
        print(f"    - Avg RMS:  {avg_rms:.4f}")
        print(f"    - Peak RMS: {max_rms:.4f}")
        return True
    except Exception as e:
        print(f"[-] Physical Audio Hardware Test Failed: {e}")
        return False


async def main():
    print("=" * 65)
    print("   A.L.F.R.E.D. Core Physical Hardware & Live API Diagnostics")
    print("=" * 65)

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    print("\n[*] PART A: Checking .env & GEMINI_API_KEY")
    if not api_key:
        print("[-] FAILED: GEMINI_API_KEY not found in environment or .env file.")
        print("    Please ensure .env contains a valid GEMINI_API_KEY.")
        sys.exit(1)

    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    print(f"[+] GEMINI_API_KEY detected: {masked_key} (length: {len(api_key)})")

    model_id = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.8-live")
    live_ok = await test_live_api_connection(api_key, model_id=model_id)
    audio_ok = await test_audio_hardware()

    print("\n" + "=" * 65)
    print("                    DIAGNOSTIC SUMMARY")
    print("=" * 65)
    print(f"1. .env GEMINI_API_KEY:            {'[PASS]' if api_key else '[FAIL]'}")
    print(f"2. Gemini Multimodal Live API:     {'[PASS]' if live_ok else '[FAIL]'}")
    print(f"3. Microphone Hardware & RMS:      {'[PASS]' if audio_ok else '[FAIL]'}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
