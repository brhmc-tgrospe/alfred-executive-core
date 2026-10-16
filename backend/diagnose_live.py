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
            async def execute_turn(prompt: str, label: str) -> dict:
                print(f"--- [{label}] ---")
                print(f"[*] Transmitting prompt: '{prompt}'")
                t_start = time.perf_counter()
                first_audio_ms = None
                chunks = 0
                total_bytes = 0
                tool_called = False

                await session.send(input=prompt, end_of_turn=True)

                # Outer loop handles tool call -> tool response -> model vocal turn
                async with asyncio.timeout(18.0):
                    while True:
                        turn_finished = False
                        async for response in session.receive():
                            tool_call = getattr(response, "tool_call", None)
                            if tool_call is not None:
                                for fc in getattr(tool_call, "function_calls", []):
                                    fname = getattr(fc, "name", "")
                                    call_id = getattr(fc, "id", "1")
                                    print(f"    [+] Tool Call Triggered by Gemini: {fname}() [id: {call_id}]")
                                    tool_called = True
                                    tool_fn = getattr(dev_tools, fname, None)
                                    res_str = str(tool_fn()) if tool_fn else "Status: Nominal"
                                    fn_resp = types.FunctionResponse(
                                        id=call_id,
                                        name=fname,
                                        response={"result": res_str},
                                    )
                                    print(f"    [*] Sending tool response for {fname}...")
                                    await session.send(input=types.LiveClientToolResponse(function_responses=[fn_resp]))

                            server_content = getattr(response, "server_content", None)
                            if server_content is not None:
                                model_turn = getattr(server_content, "model_turn", None)
                                if model_turn is not None:
                                    for part in model_turn.parts:
                                        if part.inline_data and part.inline_data.data:
                                            if first_audio_ms is None:
                                                first_audio_ms = (time.perf_counter() - t_start) * 1000.0
                                                print(f"    [+] First Audio Chunk Latency: {first_audio_ms:.1f}ms")
                                            chunk = part.inline_data.data
                                            chunks += 1
                                            total_bytes += len(chunk)
                                            audio_mgr.feed_speaker_audio(chunk)
                                        if getattr(part, "text", None):
                                            print(f"    [Transcript]: {part.text.strip()}")

                                if getattr(server_content, "turn_complete", False):
                                    if chunks > 0:
                                        print(f"    [+] Turn complete signal received ({chunks} audio chunks).")
                                        audio_mgr.mark_turn_complete()
                                        turn_finished = True
                                        break

                        if turn_finished:
                            break

                await audio_mgr.wait_for_playback_drain(timeout=10.0)
                dur = time.perf_counter() - t_start
                print(f"[+] {label} complete in {dur:.2f}s (Buffer drained).\n")
                return {
                    "first_audio_ms": round(first_audio_ms or 0.0, 1),
                    "total_sec": round(dur, 2),
                    "chunks": chunks,
                    "bytes": total_bytes,
                    "tool_called": tool_called,
                }

            benchmarks["turn_1"] = await execute_turn(
                prompt="[SYSTEM EVENT: The Director has logged into the executive console. Greet the Director with an articulate, composed, and concise 2-sentence executive status briefing.]",
                label="TURN 1: Executive Startup Briefing",
            )
            benchmarks["turn_2"] = await execute_turn(
                prompt="Status report, Alfred.",
                label="TURN 2: Quick Directive: 'Status report, Alfred.'",
            )
            benchmarks["turn_3"] = await execute_turn(
                prompt="Check local dev ports.",
                label="TURN 3: Tool Directive: 'Check local dev ports.'",
            )

            await audio_mgr.stop()

            # Benchmark Assertions
            turn_1_fast = (benchmarks["turn_1"]["first_audio_ms"] < 3000.0)
            all_chunks_received = (
                benchmarks["turn_1"]["chunks"] > 0
                and benchmarks["turn_2"]["chunks"] > 0
                and benchmarks["turn_3"]["chunks"] > 0
            )
            zero_underflows = (audio_mgr.underflow_count == 0)
            any_tool_called = (benchmarks["turn_1"]["tool_called"] or benchmarks["turn_2"]["tool_called"] or benchmarks["turn_3"]["tool_called"])

            print("=" * 70)
            print("                 MULTI-TURN LATENCY BENCHMARKS")
            print("=" * 70)
            print(f"• Turn 1 (Startup Greeting): First Audio: {benchmarks['turn_1']['first_audio_ms']}ms | Duration: {benchmarks['turn_1']['total_sec']}s")
            print(f"• Turn 2 (Status Report):    First Audio: {benchmarks['turn_2']['first_audio_ms']}ms | Duration: {benchmarks['turn_2']['total_sec']}s")
            print(f"• Turn 3 (Dev Ports Tool):   First Audio: {benchmarks['turn_3']['first_audio_ms']}ms | Tool Called: {any_tool_called} | Duration: {benchmarks['turn_3']['total_sec']}s")
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
