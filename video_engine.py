#!/usr/bin/env python3
"""
Production FFmpeg Video Engine (GitHub Actions Optimized)
Fixes: Retries, Timeouts, Audio Padding, Fail-Fast Validation.
"""
import argparse
import base64
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

# --- CONFIGURATION ---

@dataclass
class RenderConfig:
    width: int = 1080
    height: int = 1920
    fps: int = 25
    codec: str = "libx264"
    preset: str = "veryfast"  # Optimized for CI/CD speed
    crf: int = 28             # Balanced quality/size for social media
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    max_download_threads: int = 4

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- UTILS ---

def get_media_duration(path: str) -> float:
    """Returns accurate duration using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"Could not measure duration of {path}: {e}")
        return 5.0

# --- ASSET MANAGEMENT ---

class AssetManager:
    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.cache: Dict[str, str] = {} # source_url -> local_path

    def resolve_all(self, timeline: List[Dict]) -> Dict[str, str]:
        """Identifies unique URLs and downloads them in parallel."""
        urls = set()
        for scene in timeline:
            for layer in scene.get("layers", []):
                src = layer.get("source")
                if src and src not in self.cache:
                    urls.add(src)
        
        # Parallel Download
        with ThreadPoolExecutor(max_workers=RenderConfig.max_download_threads) as executor:
            future_to_url = {executor.submit(self._download_asset, url): url for url in urls}
            for future in future_to_url:
                url = future_to_url[future]
                try:
                    path = future.result()
                    self.cache[url] = path
                    logger.info(f"Resolved: {url} -> {path}")
                except Exception as e:
                    logger.error(f"Failed to resolve {url}: {e}")
                    raise RuntimeError(f"Asset resolution failed: {e}")
        
        return self.cache

    def _download_asset(self, source: str) -> str:
        """Handles URL download or Base64 decoding."""
        try:
            if source.startswith("data:"):
                return self._save_base64(source)
            elif source.startswith("http"):
                return self._download_http(source)
            elif os.path.exists(source):
                return source
            else:
                raise ValueError(f"Unknown source type or file not found: {source}")
        except Exception as e:
            raise RuntimeError(f"Error processing asset: {e}")

    def _save_base64(self, source: str) -> str:
        header, encoded = source.split(",", 1)
        ext = "bin"
        if "image" in header: ext = "png"
        elif "video" in header: ext = "mp4"
        elif "audio" in header: ext = "mp3"
        
        data = base64.b64decode(encoded)
        path = os.path.join(self.temp_dir, f"asset_{hash(source)}.{ext}")
        with open(path, "wb") as f:
            f.write(data)
        return path

    def _download_http(self, url: str, max_retries: int = 3) -> str:
        ext = Path(url).suffix.split("?")[0] or ".tmp"
        path = os.path.join(self.temp_dir, f"dl_{hash(url)}{ext}")
        
        # Cache check
        if os.path.exists(path): return path

        # Retry Loop for Flaky GitHub Actions Network
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=30) as response, open(path, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
                return path
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == max_retries - 1:
                    raise e
                logger.warning(f"Download failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying...")
                time.sleep(2 ** attempt) # Exponential backoff (1s, 2s, 4s)
        return path

# --- FILTER GRAPH BUILDER ---

class FilterGraph:
    def __init__(self):
        self.chains = []
        self.node_counter = 0

    def add_node(self, inputs: List[str], filter_str: str, outputs: List[str]):
        inp_str = "".join([f"[{i}]" for i in inputs])
        out_str = "".join([f"[{o}]" for o in outputs])
        self.chains.append(f"{inp_str}{filter_str}{out_str}")

    def get_next_label(self, prefix="v") -> str:
        self.node_counter += 1
        return f"{prefix}_{self.node_counter}"

    def compile(self) -> str:
        return ";".join(self.chains)

# --- SCENE RENDERER ---

class SceneRenderer:
    def __init__(self, spec: Dict, config: RenderConfig, asset_cache: Dict[str, str], index: int):
        self.spec = spec
        self.config = config
        self.cache = asset_cache
        self.index = index
        
    def render(self, output_path: str):
        layers = self.spec.get("layers", [])
        if not layers:
            raise ValueError(f"Scene {self.index} has no layers")

        # 1. Determine Duration
        duration = self._calculate_duration(layers)
        logger.info(f"[Scene {self.index}] Final Duration: {duration}s")

        # 2. Setup Inputs
        input_args = ["-f", "lavfi", "-i", f"color=c=black:s={self.config.width}x{self.config.height}:d={duration}"]
        
        unique_paths = []
        path_to_input_idx = {}
        
        for layer in layers:
            src = layer.get("source")
            if not src: continue 
            
            path = self.cache.get(src)
            if path not in path_to_input_idx:
                path_to_input_idx[path] = len(unique_paths) + 1 # +1 for canvas
                unique_paths.append(path)
                
        for p in unique_paths:
            input_args.extend(["-i", p])

        # 3. Build Filter Graph
        fg = FilterGraph()
        curr_v = "v_0"
        fg.add_node(["0:v"], "null", [curr_v]) 
        
        audio_mix_pads = []
        
        for i, layer in enumerate(layers):
            l_type = layer.get("type")
            
            if l_type in ["video", "image"]:
                path = self.cache.get(layer["source"])
                inp_idx = path_to_input_idx[path]
                
                proc_v = fg.get_next_label("v_proc")
                
                scale_filter = self._get_scale_filter(layer)
                dur_mode = layer.get("duration_mode", "loop" if l_type == "image" else "trim")
                
                chain_filters = []
                
                if dur_mode in ["loop", "freeze"]:
                    chain_filters.append("loop=loop=-1:size=32767:start=0")
                
                chain_filters.append(scale_filter)
                chain_filters.append(f"trim=duration={duration},setpts=PTS-STARTPTS")
                
                opacity = layer.get("opacity", 1.0)
                if opacity < 1.0:
                    chain_filters.append(f"colorchannelmixer=aa={opacity}")

                fg.add_node([f"{inp_idx}:v"], ",".join(chain_filters), [proc_v])
                
                next_v = fg.get_next_label("v_stack")
                x = layer.get("x", "(W-w)/2")
                y = layer.get("y", "(H-h)/2")
                fg.add_node([curr_v, proc_v], f"overlay=x={x}:y={y}:eof_action=pass", [next_v])
                curr_v = next_v

            elif l_type == "text":
                next_v = fg.get_next_label("v_text")
                txt_filter = self._get_text_filter(layer)
                fg.add_node([curr_v], txt_filter, [next_v])
                curr_v = next_v

            elif l_type == "audio":
                path = self.cache.get(layer["source"])
                inp_idx = path_to_input_idx[path]
                a_pad = fg.get_next_label("a_pad")
                
                vol = layer.get("volume", 1.0)
                if not 0.0 <= vol <= 5.0: vol = 1.0 
                
                # FIXED AUDIO PADDING: apad (infinite) -> atrim (cut to size)
                # This guarantees audio is never shorter than video.
                af = f"apad,atrim=0:{duration},asetpts=PTS-STARTPTS,volume={vol}"
                
                fg.add_node([f"{inp_idx}:a"], af, [a_pad])
                audio_mix_pads.append(a_pad)

        # 4. Final Mix
        final_a = "a_out"
        if audio_mix_pads:
            fg.add_node(audio_mix_pads, f"amix=inputs={len(audio_mix_pads)}:duration=first:dropout_transition=0", [final_a])
        else:
            fg.add_node([], f"anullsrc=channel_layout=stereo:sample_rate=44100:d={duration}", [final_a])
            
        # 5. Execute FFmpeg
        cmd = ["ffmpeg", "-y"]
        cmd.extend(input_args)
        cmd.extend(["-filter_complex", fg.compile()])
        cmd.extend(["-map", f"[{curr_v}]", "-map", f"[{final_a}]"])
        
        cmd.extend([
            "-c:v", self.config.codec, "-preset", self.config.preset, "-crf", str(self.config.crf),
            "-c:a", self.config.audio_codec, "-b:a", self.config.audio_bitrate,
            output_path
        ])

        logger.debug(f"FFmpeg Command: {' '.join(cmd)}")
        # CAPTURE STDERR for debugging
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg Failed on Scene {self.index}")
            logger.error(e.stderr) # Print actual FFmpeg error
            raise e

    def _calculate_duration(self, layers: List[Dict]) -> float:
        explicit = self.spec.get("duration")
        if explicit and isinstance(explicit, (int, float)):
            return float(explicit)

        main_audio = next((l for l in layers if l.get("type") == "audio" and l.get("role") == "main"), None)
        
        if main_audio:
            path = self.cache.get(main_audio["source"])
            return get_media_duration(path)
        
        return 5.0 

    def _get_scale_filter(self, layer: Dict) -> str:
        w = layer.get("width", self.config.width)
        h = layer.get("height", self.config.height)
        mode = layer.get("resize_mode", "cover")
        
        if mode == "cover":
            return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        elif mode == "contain":
            return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        return f"scale={w}:{h}"

    def _get_text_filter(self, layer: Dict) -> str:
        content = layer["content"].replace("'", "").replace(":", "\\:")
        size = layer.get("size", 60)
        color = layer.get("color", "white")
        x = layer.get("x", "(w-text_w)/2")
        y = layer.get("y", "(h-text_h)/2")
        return f"drawtext=text='{content}':fontsize={size}:fontcolor={color}:borderw=2:bordercolor=black:x={x}:y={y}"


# --- PIPELINE ORCHESTRATOR ---

class VideoPipeline:
    def __init__(self, json_path: str):
        self.json_path = json_path
        self.config = RenderConfig()
        
    def run(self):
        # 1. Validation (Fail Fast)
        with open(self.json_path, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                sys.exit(1)

        self._validate_schema(data)
        
        settings = data.get("settings", {})
        self.config.width = settings.get("width", 1080)
        self.config.height = settings.get("height", 1920)

        # 2. Workspace Setup
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Workspace created at {temp_dir}")
            
            # 3. Resolve Assets
            manager = AssetManager(temp_dir)
            logger.info("Resolving assets...")
            try:
                asset_cache = manager.resolve_all(data["timeline"])
                
                # FIXED: Check if background track needs downloading
                bg_track = data.get("background_track")
                if bg_track:
                    src = bg_track["source"]
                    if src not in asset_cache:
                        asset_cache[src] = manager._download_asset(src)
            except Exception as e:
                logger.error(str(e))
                sys.exit(1)

            # 4. Render Scenes
            timeline = data["timeline"]
            chunks = []
            
            for i, scene in enumerate(timeline):
                out_name = os.path.join(temp_dir, f"chunk_{i:03d}.mp4")
                renderer = SceneRenderer(scene, self.config, asset_cache, i)
                try:
                    renderer.render(out_name)
                    chunks.append(out_name)
                except subprocess.CalledProcessError:
                    sys.exit(1) # Error already logged in render()

            # 5. Stitch & Background Music
            self._stitch_and_finalize(chunks, data.get("background_track"), asset_cache, "output/final.mp4")

    def _validate_schema(self, data: Dict):
        if "timeline" not in data or not isinstance(data["timeline"], list):
            raise ValueError("JSON must contain a 'timeline' list")
        if not data["timeline"]:
            raise ValueError("Timeline is empty")
        
        # Extended Validation
        for i, scene in enumerate(data["timeline"]):
            if "layers" not in scene:
                 raise ValueError(f"Scene {i} missing 'layers'")

    def _stitch_and_finalize(self, chunks: List[str], bg_track: Optional[Dict], cache: Dict, output_path: str):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        list_file = "concat_list.txt"
        with open(list_file, "w") as f:
            for c in chunks: f.write(f"file '{c}'\n")
            
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file]
        
        if bg_track:
            bg_path = cache[bg_track["source"]]
            bg_vol = bg_track.get("volume", 0.1)
            cmd.extend(["-stream_loop", "-1", "-i", bg_path])
            
            filter_str = f"[1:a]volume={bg_vol}[bg];[0:a][bg]amix=inputs=2:duration=first[a_out]"
            cmd.extend(["-filter_complex", filter_str, "-map", "0:v", "-map", "[a_out]"])
            cmd.extend(["-c:v", "copy", "-c:a", "aac", "-shortest", output_path])
        else:
            cmd.extend(["-c", "copy", output_path])

        logger.info("Stitching final video...")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error("Final Stitch Failed")
            logger.error(e.stderr)
            sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, help="Path to job.json")
    args = parser.parse_args()
    
    pipeline = VideoPipeline(args.spec)
    pipeline.run()
