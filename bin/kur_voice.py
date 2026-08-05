import os
import subprocess
import socket
import json
import sys
import time

class KurVoice:
    def __init__(self, socket_path=None):
        self.socket_path = socket_path or os.environ.get("SIREN_SOCK", "/tmp/siren-mpv.sock")
        self.model_path = os.path.expanduser("~/.config/siren/voices/en_US-danny-low.onnx")
        self.output_wav = "/tmp/kur_voice_output.wav"
        
    def speak(self, text):
        if not os.path.exists(self.model_path):
            sys.__stderr__.write(f"[Kur Voice Error]: Model file missing at {self.model_path}\n")
            return False

        try:
            # Clean up old audio artifact to ensure fresh generation tracking
            if os.path.exists(self.output_wav):
                os.remove(self.output_wav)

            # 1. Direct Pipeline execution: Pipe text input directly to Piper binary safely with deliberate narrator pacing (Morgan Freeman style)
            piper_proc = subprocess.Popen(
                ["piper", "--model", self.model_path, "--output_file", self.output_wav, "--length-scale", "1.25"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )
            
            _, stderr_data = piper_proc.communicate(input=text)

            if piper_proc.returncode != 0:
                sys.__stderr__.write(f"[Piper Engine Error Output]: {stderr_data}\n")
                return False

            # Verify the audio asset was actually constructed and contains real content
            if not os.path.exists(self.output_wav) or os.path.getsize(self.output_wav) == 0:
                sys.__stderr__.write("[Kur Voice Error]: Piper generated a dead 0-byte audio file.\n")
                return False
            
            # 2. Command Handoff to MPV IPC
            if not os.path.exists(self.socket_path):
                try:
                    subprocess.Popen(
                        ["mpv", "--idle=yes", f"--input-ipc-server={self.socket_path}", "--no-video"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    time.sleep(0.4)
                except Exception:
                    pass

            if os.path.exists(self.socket_path):
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.connect(self.socket_path)
                
                # Using 'replace' to instantly grab control of the playback core
                command = ["loadfile", self.output_wav, "replace"]
                payload = json.dumps({"command": command}) + "\n"
                
                client.sendall(payload.encode("utf-8"))
                client.recv(1024)

                # Ensure playback is unpaused so speech is heard
                unpause_cmd = ["set_property", "pause", False]
                client.sendall((json.dumps({"command": unpause_cmd}) + "\n").encode("utf-8"))
                client.recv(1024)

                client.close()
                return True
            else:
                sys.__stderr__.write(f"[Kur Voice Error]: MPV socket missing at {self.socket_path}\n")
                return False
                
        except Exception as e:
            sys.__stderr__.write(f"[Kur Voice Engine Exception]: {e}\n")
            return False
