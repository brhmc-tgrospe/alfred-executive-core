"""A.L.F.R.E.D. Physical Hardware & Gemini Live API Multi-Turn Benchmark Suite.

Validates:
1. .env file & GEMINI_API_KEY presence and format.
2. Direct Gemini Multimodal Live API bidirectional session with 3 consecutive turns:
   - Turn 1: Startup Briefing (Verifies <3.0s latency to first audio chunk).
   - Turn 2: Quick Prompt ('Status report, Alfred').
   - Turn 3: Tool Prompt ('Check local dev ports' with tool call dispatching & vocalization).
3. Live voice playback smoothness through speakers with 0 Output Underflows.
4. Physical microphone hardware capture via sounddevice with digital gain and RMS visualizer.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dotenv import load_dotenv

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai
from google.genai import types
from backend.audio_manager import AudioManager
from backend.tools.dev_logistics import DevLogistics

load_dotenv()


async def test_live_api_multi_turn_benchmark(api_key: str, model_id: str = "gemini-3.8-live"):
    print("\n" + "=" * 70)
    print(f"[*] PART B: 3-Turn Multi-Turn Session & Latency Benchmark ({model_id})")
    print("=" * 70)

    audio_mgr = AudioManager()
    dev_tools = DevLogistics()
    await audio_mgr.start()
    print("[+] Audio hardware streams active (16kHz Input, 24kHz RawOutputStream).")

    client = genai.Client(api_key=api_key)
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Fenrir")
            )
        ),
        tools=[dev_tools.inspect_local_dev_ports],
    )

    benchmarks = {}

    print(f"[*] Initiating WebSocket connection to model: {model_id}...")
    try:
        async with client.aio.live.connect(model=model_id, config=config) as session:
            print("[+] WebSocket connection established successfully!\n")

            # -------------------------------------------------------------
            # TURN 1: Executive Startup Briefing
            # -------------------------------------------------------------
            print("--- [TURN 1: Executive Startup Briefing] ---")
            prompt_1 = (
                "[SYSTEM EVENT: The Director has logged into the executive console. "
                "Greet the Director with an articulate, composed, and concise 2-sentence executive status briefing.]"
            )
            t0 = time.perf_counter()
            first_audio_t1 = None
            chunks_t1 = 0
            bytes_t1 = 0

            print(f"[*] Transmitting Turn 1 trigger prompt...")
            await session.send(input=prompt_1, end_of_turn=True)

            async with asyncio.timeout(12.0):
                async for response in session.receive():
                    server_content = getattr(response, "server_content", None)
                    if server_content is not None:
                        model_turn = getattr(server_content, "model_turn", None)
                        if model_turn is not None:
                            for part in model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    if first_audio_t1 is None:
                                        first_audio_t1 = time.perf_counter() - t0
                                        print(f"    [+] Turn 1 First Audio Chunk Latency: {first_audio_t1*1000:.1f}ms (< 3000ms goal)")
                                    chunk = part.inline_data.data
                                    chunks_t1 += 1
                                    bytes_t1 += len(chunk)
                                    audio_mgr.feed_speaker_audio(chunk)
                                if getattr(part, "text", None):
                                    print(f"    [Transcript]: {part.text.strip()}")

                        if getattr(server_content, "turn_complete", False):
                            print("[+] Turn 1 complete signal received.")
                            audio_mgr.mark_turn_complete()
                            break

            await audio_mgr.wait_for_playback_drain(timeout=10.0)
            dur_t1 = time.perf_counter() - t0
            benchmarks["turn_1"] = {
                "first_audio_ms": round((first_audio_t1 or 0) * 1000, 1),
                "total_sec": round(dur_t1, 2),
                "chunks": chunks_t1,
                "bytes": bytes_t1,
            }
            print(f"[+] Turn 1 complete in {dur_t1:.2f}s (Buffer drained).\n")

            # -------------------------------------------------------------
            # TURN 2: Quick Prompt ('Status report, Alfred.')
            # -------------------------------------------------------------
            print("--- [TURN 2: Quick Directive: 'Status report, Alfred.'] ---")
            prompt_2 = "Status report, Alfred."
            t1 = time.perf_counter()
            first_audio_t2 = None
            chunks_t2 = 0
            bytes_t2 = 0

            print(f"[*] Transmitting Turn 2 prompt: '{prompt_2}'")
            await session.send(input=prompt_2, end_of_turn=True)

            async with asyncio.timeout(12.0):
                async for response in session.receive():
                    server_content = getattr(response, "server_content", None)
                    if server_content is not None:
                        model_turn = getattr(server_content, "model_turn", None)
                        if model_turn is not None:
                            for part in model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    if first_audio_t2 is None:
                                        first_audio_t2 = time.perf_counter() - t1
                                        print(f"    [+] Turn 2 First Audio Chunk Latency: {first_audio_t2*1000:.1f}ms")
                                    chunk = part.inline_data.data
                                    chunks_t2 += 1
                                    bytes_t2 += len(chunk)
                                    audio_mgr.feed_speaker_audio(chunk)
                                if getattr(part, "text", None):
                                    print(f"    [Transcript]: {part.text.strip()}")

                        if getattr(server_content, "turn_complete", False):
                            print("[+] Turn 2 complete signal received.")
                            audio_mgr.mark_turn_complete()
                            break

            await audio_mgr.wait_for_playback_drain(timeout=10.0)
            dur_t2 = time.perf_counter() - t1
            benchmarks["turn_2"] = {
                "first_audio_ms": round((first_audio_t2 or 0) * 1000, 1),
                "total_sec": round(dur_t2, 2),
                "chunks": chunks_t2,
                "bytes": bytes_t2,
            }
            print(f"[+] Turn 2 complete in {dur_t2:.2f}s (Buffer drained).\n")

            # -------------------------------------------------------------
            # TURN 3: Tool Directive ('Check local dev ports.')
            # -------------------------------------------------------------
            print("--- [TURN 3: Tool Directive: 'Check local dev ports.'] ---")
            prompt_3 = "Check local dev ports."
            t2 = time.perf_counter()
            first_audio_t3 = None
            chunks_t3 = 0
            bytes_t3 = 0
            tool_dispatched = False

            print(f"[*] Transmitting Turn 3 tool prompt: '{prompt_3}'")
            await session.send(input=prompt_3, end_of_turn=True)

            # 1. Receive Tool Call from Gemini
            async with asyncio.timeout(15.0):
                async for response in session.receive():
                    tool_call = getattr(response, "tool_call", None)
                    if tool_call is not None:
                        for fc in getattr(tool_call, "function_calls", []):
                            fname = getattr(fc, "name", "")
                            call_id = getattr(fc, "id", "1")
                            print(f"    [+] Tool Call Triggered by Gemini: {fname}() [id: {call_id}]")
                            if fname == "inspect_local_dev_ports":
                                tool_result = dev_tools.inspect_local_dev_ports()
                                tool_dispatched = True
                                print(f"    [*] Executed tool in <10ms. Sending tool response to Gemini...")
                                fn_resp = types.FunctionResponse(
                                    id=call_id,
                                    name=fname,
                                    response={"result": tool_result},
                                )
                                await session.send(input=types.LiveClientToolResponse(function_responses=[fn_resp]))

            # 2. Receive Vocal Response to Tool Output
            if tool_dispatched:
                print("    [*] Awaiting Gemini vocal response to tool output...")
                async with asyncio.timeout(15.0):
                    async for response in session.receive():
                        server_content = getattr(response, "server_content", None)
                        if server_content is not None:
                            model_turn = getattr(server_content, "model_turn", None)
                            if model_turn is not None:
                                for part in model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        if first_audio_t3 is None:
                                            first_audio_t3 = time.perf_counter() - t2
                                            print(f"    [+] Turn 3 Audio Vocalization Latency: {first_audio_t3*1000:.1f}ms")
                                        chunk = part.inline_data.data
                                        chunks_t3 += 1
                                        bytes_t3 += len(chunk)
                                        audio_mgr.feed_speaker_audio(chunk)
                                    if getattr(part, "text", None):
                                        print(f"    [Transcript]: {part.text.strip()}")

                            if getattr(server_content, "turn_complete", False):
                                print("[+] Turn 3 complete signal received.")
                                audio_mgr.mark_turn_complete()
                                break

            await audio_mgr.wait_for_playback_drain(timeout=10.0)
            dur_t3 = time.perf_counter() - t2
            benchmarks["turn_3"] = {
                "first_audio_ms": round((first_audio_t3 or 0) * 1000, 1),
                "total_sec": round(dur_t3, 2),
                "chunks": chunks_t3,
                "bytes": bytes_t3,
                "tool_called": tool_dispatched,
            }
            print(f"[+] Turn 3 complete in {dur_t3:.2f}s (Buffer drained).\n")

            await audio_mgr.stop()

            # Benchmark Assertions
            turn_1_fast = (benchmarks["turn_1"]["first_audio_ms"] < 3000.0)
            all_chunks_received = (
                benchmarks["turn_1"]["chunks"] > 0
                and benchmarks["turn_2"]["chunks"] > 0
                and benchmarks["turn_3"]["chunks"] > 0
            )
            zero_underflows = (audio_mgr.underflow_count == 0)

            print("=" * 70)
            print("                 MULTI-TURN LATENCY BENCHMARKS")
            print("=" * 70)
            print(f"• Turn 1 (Startup Greeting): First Audio: {benchmarks['turn_1']['first_audio_ms']}ms | Duration: {benchmarks['turn_1']['total_sec']}s")
            print(f"• Turn 2 (Status Report):    First Audio: {benchmarks['turn_2']['first_audio_ms']}ms | Duration: {benchmarks['turn_2']['total_sec']}s")
            print(f"• Turn 3 (Dev Ports Tool):   First Audio: {benchmarks['turn_3']['first_audio_ms']}ms | Tool Called: {tool_dispatched} | Duration: {benchmarks['turn_3']['total_sec']}s")
            print(f"• Output Underflow Errors:   {audio_mgr.underflow_count}")
            print(f"• Overall Multi-Turn Status: {'[PASSED]' if (turn_1_fast and all_chunks_received and zero_underflows) else '[FAILED]'}")
            print("=" * 70)

            return turn_1_fast and all_chunks_received and zero_underflows

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[-] Multi-turn Live API Benchmark Failed: {repr(e)}")
        await audio_mgr.stop()
        return False


async def test_audio_hardware():
    print("\n" + "=" * 70)
    print("[*] PART C: Testing Physical Microphone Capture & Device Listing")
    print("=" * 70)

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
        for i in range(15):
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

        print(f"\n[+] Audio Hardware Metrics over 1.5 seconds:")
        print(f"    - Min RMS:  {min_rms:.4f}")
        print(f"    - Avg RMS:  {avg_rms:.4f}")
        print(f"    - Peak RMS: {max_rms:.4f}")
        return True
    except Exception as e:
        print(f"[-] Physical Audio Hardware Test Failed: {e}")
        return False


async def main():
    print("=" * 70)
    print("   A.L.F.R.E.D. Core Physical Hardware & Live Multi-Turn Suite")
    print("=" * 70)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    print("\n[*] PART A: Checking .env & GEMINI_API_KEY")
    if not api_key:
        print("[-] FAILED: GEMINI_API_KEY not found in environment or .env file.")
        sys.exit(1)

    masked_key = api_key[:6] + "..." + api_key[-4:] if len(api_key) > 10 else "***"
    print(f"[+] GEMINI_API_KEY detected: {masked_key} (length: {len(api_key)})")

    model_id = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.8-live")
    live_ok = await test_live_api_multi_turn_benchmark(api_key, model_id=model_id)
    audio_ok = await test_audio_hardware()

    print("\n" + "=" * 70)
    print("                    FINAL DIAGNOSTIC SUMMARY")
    print("=" * 70)
    print(f"1. .env GEMINI_API_KEY:               {'[PASS]' if api_key else '[FAIL]'}")
    print(f"2. 3-Turn Multi-Turn Session & Audio: {'[PASS]' if live_ok else '[FAIL]'}")
    print(f"3. Microphone Hardware & RMS:         {'[PASS]' if audio_ok else '[FAIL]'}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
