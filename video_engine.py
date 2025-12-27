#!/usr/bin/env python3
"""
FFmpeg Timeline Video Engine (Fixed Lavfi Input)
Features: Unlimited Overlay Stacking, Audio Mixing, Auto-Duration.
"""
import argparse
import base64
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# --- UTILS ---

def get_media_duration(path: str) -> float:
    """Returns duration (seconds) using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[Warning] Could not measure duration of {path}: {e}")
        return 5.0

def get_asset_path(source: str) -> str:
    """Handles URL download, Base64 decode, or local path."""
    if source.startswith("data:"):
        try:
            header, encoded = source.split(",", 1)
            ext = "mp3"
            if "image" in header: ext = "png"
            if "video" in header: ext = "mp4"
            
            data = base64.b64decode(encoded)
            t = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
            t.write(data); t.close()
            return t.name
        except Exception:
            return source 

    elif source.startswith("http"):
        try:
            ext = Path(source).suffix.split("?")[0] or ".tmp"
            t = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            req = urllib.request.Request(source, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response, open(t.name, 'wb') as out_file:
                out_file.write(response.read())
            return t.name
        except Exception as e:
            print(f"[Error] Download failed: {source} ({e})")
            return source

    return source

# --- SCENE RENDERER ---

class SceneRenderer:
    def __init__(self, scene_spec: Dict, settings: Dict, index: int):
        self.spec = scene_spec
        self.settings = settings
        self.index = index
        self.w = settings.get("width", 1080)
        self.h = settings.get("height", 1920)
        self.temp_files = []

    def render(self, output_filename: str) -> Optional[str]:
        layers = self.spec.get("layers", [])
        
        # 1. Determine Scene Duration
        master_audio = next((l for l in layers if l.get("type") == "audio" and l.get("role") == "main"), None)
        if not master_audio:
            master_audio = next((l for l in layers if l.get("type") == "audio"), None)
            
        scene_duration = 0.0

        if master_audio:
            path = get_asset_path(master_audio["source"])
            self.temp_files.append(path)
            master_audio["_local_path"] = path 
            scene_duration = get_media_duration(path)
            print(f"[Scene {self.index}] Auto-duration: {scene_duration}s")
        else:
            scene_duration = float(self.spec.get("duration", 5.0))
            print(f"[Scene {self.index}] Manual duration: {scene_duration}s")

        # 2. Build Filter Graph
        inputs = []
        filter_chain = []
        
        # We handle the Canvas (Input 0) separately in the command build step
        # Input 0 is reserved for: color=c=black:s=WxH:d=DURATION
        canvas_source = f"color=c=black:s={self.w}x{self.h}:d={scene_duration}"
        filter_chain.append(f"[0:v]null[v_0]")
        
        current_v = "v_0"
        # Since Input 0 is the canvas, real files start at Input 1
        input_count = 1 
        
        audio_streams = []

        # 3. Iterate Layers
        for i, layer in enumerate(layers):
            l_type = layer.get("type")
            
            # --- VISUAL LAYERS ---
            if l_type in ["video", "image"]:
                path = layer.get("_local_path") or get_asset_path(layer["source"])
                if path not in self.temp_files: self.temp_files.append(path)
                inputs.append(path)
                
                dur_mode = layer.get("duration_mode", "trim")
                vid_ref = f"[{input_count}:v]"
                
                processed_v = f"v_in_{i}"
                
                loop_cmd = ""
                if dur_mode == "loop" or dur_mode == "freeze":
                    loop_cmd = "loop=loop=-1:size=32767:start=0,"
                
                width = layer.get("width", self.w)
                height = layer.get("height", self.h)
                x = layer.get("x", "(W-w)/2")
                y = layer.get("y", "(H-h)/2")
                opacity = layer.get("opacity", 1.0)
                
                scale_cmd = ""
                resize_mode = layer.get("resize_mode", "cover")
                
                if resize_mode == "cover":
                    scale_cmd = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
                elif resize_mode == "contain":
                    scale_cmd = f"scale={width}:{height}:force_original_aspect_ratio=decrease"
                else:
                    scale_cmd = f"scale={width}:{height}"
                    
                opacity_cmd = ""
                if opacity < 1.0:
                    opacity_cmd = f",colorchannelmixer=aa={opacity}"
                
                filter_chain.append(f"{vid_ref}{loop_cmd}setpts=N/FRAME_RATE/TB,{scale_cmd},trim=duration={scene_duration}{opacity_cmd}[{processed_v}]")
                
                next_v = f"v_{i+1}"
                filter_chain.append(f"[{current_v}][{processed_v}]overlay=x={x}:y={y}:eof_action=pass:shortest=1[{next_v}]")
                current_v = next_v
                input_count += 1

            # --- TEXT LAYER ---
            elif l_type == "text":
                content = layer["content"].replace("'", "").replace(":", "\\:")
                size = layer.get("size", 60)
                color = layer.get("color", "white")
                x = layer.get("x", "(w-text_w)/2")
                y = layer.get("y", "(h-text_h)/2")
                
                next_v = f"v_{i+1}"
                style = f"fontsize={size}:fontcolor={color}:borderw=2:bordercolor=black"
                filter_chain.append(f"[{current_v}]drawtext=text='{content}':{style}:x={x}:y={y}[{next_v}]")
                current_v = next_v

            # --- AUDIO LAYER ---
            elif l_type == "audio":
                path = layer.get("_local_path") or get_asset_path(layer["source"])
                if path not in self.temp_files: self.temp_files.append(path)
                inputs.append(path)
                
                vol = layer.get("volume", 1.0)
                a_lbl = f"a_raw_{i}"
                filter_chain.append(f"[{input_count}:a]atrim=duration={scene_duration},volume={vol}[{a_lbl}]")
                audio_streams.append(f"[{a_lbl}]")
                input_count += 1

        # 4. Final Audio Mix
        final_audio_node = "a_out"
        if len(audio_streams) > 0:
            filter_chain.append(f"{''.join(audio_streams)}amix=inputs={len(audio_streams)}:duration=first:dropout_transition=0[{final_audio_node}]")
        else:
            filter_chain.append(f"anullsrc=channel_layout=stereo:sample_rate=44100:d={scene_duration}[{final_audio_node}]")

        # 5. Build Final Command
        # CRITICAL FIX: Treat input 0 (canvas) as lavfi
        cmd = ["ffmpeg", "-y"]
        
        # Input 0: The Virtual Canvas
        cmd.extend(["-f", "lavfi", "-i", canvas_source])
        
        # Inputs 1..N: Real Files
        for inp in inputs:
            cmd.extend(["-i", inp])
        
        cmd.extend(["-filter_complex", ";".join(filter_chain)])
        cmd.extend(["-map", f"[{current_v}]", "-map", f"[{final_audio_node}]"])
        cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", output_filename])

        print(f"[Scene {self.index}] Rendering...")
        # Debug print to see exact command if needed
        # print(" ".join(cmd)) 
        subprocess.run(cmd, check=True)
        return self.temp_files

# --- MAIN ENGINE ---

def run_timeline(json_path: str):
    with open(json_path, 'r') as f:
        project = json.load(f)
    
    timeline = project.get("timeline", [])
    settings = project.get("settings", {})
    chunks = []
    all_temps = []

    for i, scene in enumerate(timeline):
        out_name = f"chunk_{i:03d}.mp4"
        renderer = SceneRenderer(scene, settings, i)
        try:
            temps = renderer.render(out_name)
            all_temps.extend(temps)
            chunks.append(out_name)
        except Exception as e:
            print(f"[Error] Scene {i} failed: {e}")
            raise # Raise error to stop CI pipeline

    if not chunks: return

    list_file = "files.txt"
    with open(list_file, "w") as f:
        for chunk in chunks: f.write(f"file '{chunk}'\n")

    final_out = "output/final.mp4"
    os.makedirs("output", exist_ok=True)
    
    bg_music = project.get("background_track")
    cmd = []
    
    if bg_music:
        bg_path = get_asset_path(bg_music["source"])
        all_temps.append(bg_path)
        vol = bg_music.get("volume", 0.15)
        
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
            "-stream_loop", "-1", "-i", bg_path,
            "-filter_complex", f"[1:a]volume={vol}[bg];[0:a][bg]amix=inputs=2:duration=first[a_final]",
            "-map", "0:v", "-map", "[a_final]",
            "-c:v", "copy", "-c:a", "aac", "-shortest", final_out
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
            "-c", "copy", final_out
        ]
        
    print("[Engine] Stitching final video...")
    subprocess.run(cmd, check=True)
    
    # Cleanup
    for p in all_temps: 
        if os.path.exists(p): os.remove(p)
    for c in chunks:
        if os.path.exists(c): os.remove(c)
    if os.path.exists(list_file): os.remove(list_file)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    args = parser.parse_args()
    run_timeline(args.spec)
