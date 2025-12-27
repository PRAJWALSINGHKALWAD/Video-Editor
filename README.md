# 🎬 Video Automation Engine (JSON Specification)

This engine turns a structured **JSON Timeline** into a professional video using FFmpeg. It supports multi-layer composition (video-on-video), smart audio synchronization, and hybrid duration logic (Auto-TTS or Script-Fixed).

---

## 🚀 Key Features

* **Timeline Architecture:** Stitch multiple scenes together sequentially.
* **Hybrid Duration Logic:**
* **Auto Mode:** Scene length matches the Voiceover (TTS) automatically.
* **Script Mode:** Force a specific duration (e.g., 10s) regardless of audio length.


* **Multi-Layer Compositing:** Stack unlimited layers (Background -> Video Overlay -> Image Watermark -> Text).
* **Smart Assets:** Auto-looping, auto-cropping (`cover`/`contain`), and transparency support.
* **Audio Mixing:** Automatically mixes background music with voiceovers and SFX.

---

## 📜 The JSON Structure

The JSON file must follow this strict structure. **No comments (`//`) allowed in the actual file.**

### 1. Root Settings

Global settings for the video render.

```json
{
  "settings": {
    "width": 1080,
    "height": 1920
  },
  "background_track": {
    "source": "https://link.to/music.mp3",
    "volume": 0.15  // 0.0 to 1.0 (Keep low for background)
  }
}

```

### 2. The Timeline

An array of **Scenes**. Each scene plays one after the other.

```json
"timeline": [
  { "comment": "Scene 1", "layers": [...] },
  { "comment": "Scene 2", "layers": [...] }
]

```

---

## 🛠 Layer Properties

Every scene is built from **Layers**. Layers are processed from **Bottom to Top** (Layer 0 is the background).

### Common Properties (All Layers)

| Property | Type | Description |
| --- | --- | --- |
| `type` | String | `video`, `image`, `audio`, `text` |
| `source` | String | URL (`http`) or Base64 (`data:`) |

### 🎥 Video & Image Layers

| Property | Value | Description |
| --- | --- | --- |
| `resize_mode` | `"cover"` | **(Default)** Crops to fill screen (good for backgrounds). |
|  | `"contain"` | Fits inside black bars (good for charts/memes). |
|  | `"stretch"` | Distorts to fit exact size. |
| `duration_mode` | `"loop"` | **(Default for Images)** Repeats/Holds if scene is longer than asset. |
|  | `"trim"` | Cuts the video if it's too long. |
| `opacity` | `0.0 - 1.0` | Transparency (e.g., `0.5` for ghost effect). |
| `x` / `y` | Integer / String | Position. Supports math: `"(W-w)/2"` (Center), `"W-w-20"` (Right). |
| `width` / `height` | Integer | Force specific dimensions (e.g., `500`). |

### 🔊 Audio Layers

| Property | Value | Description |
| --- | --- | --- |
| `role` | `"main"` | **Crucial:** Sets this file as the "Master Clock" for **Auto Mode**. |
| `volume` | `0.0 - 1.0` | Volume level. |

### ✍️ Text Layers

| Property | Value | Description |
| --- | --- | --- |
| `content` | String | The text to display. |
| `size` | Integer | Font size (e.g., `60`). |
| `color` | String | Color name (`"white"`, `"yellow"`) or Hex. |
| `x` / `y` | String | Position logic (same as video). |

---

## ⏱️ Duration Logic (Auto vs. Manual)

You can mix these modes in the same video.

### 1. Auto Mode (Voice is King)

Use this when you want the video to end exactly when the TTS finishes.

* **How:** Do **NOT** set `duration` in the scene object.
* **Requirement:** One audio layer must have `"role": "main"`.
* **Behavior:** Video loops/cuts to match the MP3 length.

### 2. Script Mode (Fixed Time)

Use this for intros, outros, or visual pauses.

* **How:** Set `"duration": 5.0` (seconds) in the scene object.
* **Behavior:** The scene will be exactly 5.0s. If audio is shorter, it adds silence. If audio is longer, it cuts it.

---

## ⚠️ Do's and Don'ts

| ✅ DO | ❌ DO NOT |
| --- | --- |
| Use **Raw Links** for GitHub files (`raw.githubusercontent.com`). | Use Blob links (`github.com/.../blob/...`). |
| Use `"role": "main"` for TTS audio. | Forget to specify how scene duration is calculated. |
| Set `volume` to `0.1` for background music. | Set BG music to `1.0` (it will overpower the voice). |
| Use `duration_mode: "loop"` for short stock clips. | Expect a 2s video to fill a 10s scene without looping. |
| **Keep JSON Clean.** | **Add Comments (`//`) inside the JSON file.** |

---

## 📄 Example JSON (Copy Paste)

```json
{
  "settings": {
    "width": 1080,
    "height": 1920
  },
  "background_track": {
    "source": "https://commondatastorage.googleapis.com/codeskulptor-assets/Epoq-Lepidoptera.ogg",
    "volume": 0.1
  },
  "timeline": [
    {
      "comment": "SCENE 1: Auto Mode (Matches Voiceover)",
      "layers": [
        {
          "type": "audio",
          "role": "main",
          "source": "https://link.to/voiceover.mp3",
          "volume": 1.0
        },
        {
          "type": "video",
          "source": "https://link.to/background_video.mp4",
          "resize_mode": "cover",
          "duration_mode": "loop"
        },
        {
          "type": "text",
          "content": "Listening to Audio Length...",
          "y": 1200,
          "color": "yellow"
        }
      ]
    },
    {
      "comment": "SCENE 2: Script Mode (Fixed 3 Seconds)",
      "duration": 3.0,
      "layers": [
        {
          "type": "image",
          "source": "https://link.to/meme.png",
          "resize_mode": "contain"
        },
        {
          "type": "text",
          "content": "Forced 3s Pause",
          "y": 1500,
          "size": 50
        }
      ]
    }
  ]
}

```
