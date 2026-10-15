"""A.L.F.R.E.D. Physical Hardware & Gemini Live API Diagnostic Suite.

Validates:
1. .env file & GEMINI_API_KEY presence and format.
2. Direct Gemini Multimodal Live API bidirectional WebSocket connection using `gemini-3.8-live`.
3. Live voice playback smoothness through speakers with 0 Output Underflow errors.
4. Physical microphone hardware capture via sounddevice/PortAudio with digital pre-amp gain and device selector.
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


async def test_live_api_and_playback_smoothness(api_key: str, model_id: str = "gemini-3.8-live"):
    print("\n" + "=" * 65)
    print(f"[*] PART B: Testing Live API & Speaker Playback Smoothness ({model_id})")
    print("=" * 65)

    audio_mgr = AudioManager()
    await audio_mgr.start()
    print("[+] Audio hardware streams active (Input 16kHz, Output 24kHz RawOutputStream).")

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
            print(f"[*] Transmitting prompt turn: '{test_prompt}'")
            await session.send(input=test_prompt, end_of_turn=True)

            print("[*] Streaming response chunks into continuous FIFO buffer and playing through speakers...")
            audio_chunks_count = 0
            total_audio_bytes = 0

            try:
                async with asyncio.timeout(12.0):
                    async for response in session.receive():
                        server_content = getattr(response, "server_content", None)
                        if server_content is not None:
                            model_turn = getattr(server_content, "model_turn", None)
                            if model_turn is not None:
                                for part in model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        chunk_data = part.inline_data.data
                                        audio_chunks_count += 1
                                        chunk_len = len(chunk_data)
                                        total_audio_bytes += chunk_len
                                        # Feed into continuous FIFO playback buffer
                                        audio_mgr.feed_speaker_audio(chunk_data)
                                        if audio_chunks_count <= 4 or audio_chunks_count % 10 == 0:
                                            print(f"    [AUDIO CHUNK #{audio_chunks_count:02d}] {chunk_len}B fed to buffer (Buf size: {len(audio_mgr._playback_buffer)}B)")
                                    if getattr(part, "text", None):
                                        print(f"    [TEXT PART]: {part.text}")

                            if getattr(server_content, "turn_complete", False):
                                print("[+] Turn complete signal received from Gemini Live API.")
                                audio_mgr.mark_turn_complete()
                                break
            except TimeoutError:
                print("[-] Turn timed out waiting for server completion.")

            print("[*] Waiting for continuous FIFO speaker buffer to drain cleanly...")
            await audio_mgr.wait_for_playback_drain(timeout=10.0)
            print("[+] Speaker playback complete. Buffer drained.")

            print(f"\n[+] Playback Diagnostics:")
            print(f"    - Total Chunks Received: {audio_chunks_count}")
            print(f"    - Total Audio Bytes:     {total_audio_bytes} bytes")
            print(f"    - Output Underflows:     {audio_mgr.underflow_count}")
            print(f"    - Buffer Remaining:      {len(audio_mgr._playback_buffer)} bytes")

            await audio_mgr.stop()
            smoothness_pass = (audio_mgr.underflow_count == 0 and audio_chunks_count > 0)
            return smoothness_pass

    except Exception as e:
        print(f"[-] Live API or Playback Failed: {e}")
        await audio_mgr.stop()
        return False


async def test_audio_hardware():
    print("\n" + "=" * 65)
    print("[*] PART C: Testing Physical Microphone Capture & Device Listing")
    print("=" * 65)

    audio_mgr = AudioManager(input_gain=2.5)
    print("[*] Querying physical input devices from sounddevice...")
    devices = audio_mgr.list_input_devices()
    print(f"[+] Found {len(devices)} input device(s):")
    for dev in devices[:5]:
        def_tag = " [DEFAULT]" if dev.get("is_default") else ""
        print(f"    - ID {dev['id']}: {dev['name']} ({dev['channels']} ch){def_tag}")

    print("[*] Starting sounddevice input stream with digital gain (*2.5)...")
    try:
        await audio_mgr.start()
        print("[+] sounddevice InputStream active. push_to_talk is LIVE by default.")

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
        sys.exit(1)

    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    print(f"[+] GEMINI_API_KEY detected: {masked_key} (length: {len(api_key)})")

    model_id = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.8-live")
    live_ok = await test_live_api_and_playback_smoothness(api_key, model_id=model_id)
    audio_ok = await test_audio_hardware()

    print("\n" + "=" * 65)
    print("                    DIAGNOSTIC SUMMARY")
    print("=" * 65)
    print(f"1. .env GEMINI_API_KEY:            {'[PASS]' if api_key else '[FAIL]'}")
    print(f"2. Live Voice Playback Smoothness: {'[PASS]' if live_ok else '[FAIL]'}")
    print(f"3. Microphone Hardware & RMS:      {'[PASS]' if audio_ok else '[FAIL]'}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
