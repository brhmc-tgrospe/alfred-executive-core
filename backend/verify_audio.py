"""A.L.F.R.E.D. Audio Device Hardware Enumeration & Verification Script.

Verifies default microphone (16kHz PCM) and speaker (24kHz PCM) capabilities.
"""

import sys
import json

def verify_audio_hardware():
    print("=" * 60)
    print(" [A.L.F.R.E.D. TELEMETRY] Initializing Audio Hardware Audit...")
    print("=" * 60)

    try:
        import sounddevice as sd
        import numpy as np
    except ImportError as e:
        print(f"[ERROR] Required audio packages not found in environment: {e}")
        sys.exit(1)

    print(f"sounddevice version: {sd.__version__}")
    print(f"numpy version:       {np.__version__}")
    print("-" * 60)

    # 1. Enumerate all audio devices
    try:
        devices = sd.query_devices()
        print(f"Total Audio Devices Detected: {len(devices)}\n")
    except Exception as e:
        print(f"[ERROR] Failed to query audio devices: {e}")
        sys.exit(1)

    # 2. Query default host API and devices
    try:
        default_input_idx, default_output_idx = sd.default.device
        default_input = sd.query_devices(default_input_idx, "input") if default_input_idx is not None else None
        default_output = sd.query_devices(default_output_idx, "output") if default_output_idx is not None else None
    except Exception as e:
        print(f"[WARNING] Could not determine default devices via index: {e}")
        default_input = None
        default_output = None

    print(f"Default Input Device (Mic):    {default_input['name'] if default_input else 'None'}")
    print(f"Default Output Device (Spk):   {default_output['name'] if default_output else 'None'}")
    print("-" * 60)

    # 3. Check 16kHz 1-channel mono input compatibility (Gemini Live Requirement)
    print("Testing 16,000 Hz Mono Input (Microphone)...")
    input_supported = False
    try:
        sd.check_input_settings(
            device=default_input_idx,
            channels=1,
            dtype="int16",
            samplerate=16000
        )
        print("  --> [SUCCESS] 16kHz 1-channel 16-bit PCM Input Supported.")
        input_supported = True
    except Exception as e:
        print(f"  --> [FAIL] 16kHz Input Check: {e}")

    # 4. Check 24kHz 1-channel output compatibility (Gemini Live Audio Out Requirement)
    print("Testing 24,000 Hz Output (Speaker/Playback)...")
    output_supported = False
    try:
        sd.check_output_settings(
            device=default_output_idx,
            channels=1,
            dtype="int16",
            samplerate=24000
        )
        print("  --> [SUCCESS] 24kHz 1-channel 16-bit PCM Output Supported.")
        output_supported = True
    except Exception as e:
        # Fallback test 2 channels
        try:
            sd.check_output_settings(
                device=default_output_idx,
                channels=2,
                dtype="int16",
                samplerate=24000
            )
            print("  --> [SUCCESS] 24kHz 2-channel 16-bit PCM Output Supported (stereo playback mode).")
            output_supported = True
        except Exception as e2:
            print(f"  --> [FAIL] 24kHz Output Check: {e2}")

    print("-" * 60)
    audit_summary = {
        "status": "PASS" if (input_supported and output_supported) else "PARTIAL_OR_FAIL",
        "default_input": default_input['name'] if default_input else None,
        "default_output": default_output['name'] if default_output else None,
        "input_16khz_supported": input_supported,
        "output_24khz_supported": output_supported
    }
    print("Audit Result Summary:")
    print(json.dumps(audit_summary, indent=2))
    print("=" * 60)

    return 0 if (input_supported and output_supported) else 1

if __name__ == "__main__":
    sys.exit(verify_audio_hardware())
