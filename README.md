# 🎬 Automated Video Engine (JSON Timeline)

**A professional, FFmpeg-based engine that turns structured JSON timelines into high-quality video edits.**

This engine is designed for **AI Automation Agencies** and **Python Developers** who need to generate complex videos programmatically. It moves beyond simple concatenation, offering a full **Timeline & Layering System** similar to professional video editing software (Adobe Premiere, CapCut), but controlled entirely via code.

---

## ❓ Why use this?

Most video automation scripts only handle one video and one audio file. This engine allows you to:

1. **Layer Media:** Put a watermark over a video, or a "Ghost" video on top of another.
2. **Mix Audio:** Automatically lower background music volume while a Voiceover plays.
3. **Hybrid Control:** Let the **Audio** decide the scene length (great for TTS), OR force a specific **Script** duration (great for memes/pauses).
4. **Handle Unpredictability:** Automatically **Loops** stock footage if it's too short, or **Trims** it if it's too long.

---

## ⚡ Key Features

* **Timeline Architecture:** Sequence multiple scenes seamlessly.
* **Smart "Auto-Looping":** Never worry about stock footage being shorter than your audio. The engine fixes it.
* **Multi-Layer Compositing:** Stack Video, Images, Text, and Audio on top of each other.
* **Resolution Agnostic:** Built for 1080x1920 (Vertical) but adaptable to any aspect ratio.
* **Performance:** Optimized FFmpeg filter chains for fast rendering.

---

## 📖 How to Use

The engine accepts a single `job.json` file. This file describes the entire video project.

### 1. The Structure

The JSON is divided into **Settings** (Global) and **Timeline** (The Sequence).

```json
{
  "settings": {
    "width": 1080,
    "height": 1920
  },
  "background_track": {
    "source": "https://link.to/lofi_beat.mp3",
    "volume": 0.15
  },
  "timeline": [
    { ...Scene 1... },
    { ...Scene 2... }
  ]
}

```

### 2. Hybrid Duration Logic (The Core Concept)

This is the most powerful feature. You can control time in two ways:

#### 🅰️ Auto Mode (Voice-Driven)

* **Use Case:** Explainer videos, News, Storytelling.
* **How it works:** The scene lasts exactly as long as the TTS audio.
* **Configuration:**
* Do **NOT** set a `duration` value.
* Add `"role": "main"` to your Audio layer.



#### 🅱️ Script Mode (Fixed Duration)

* **Use Case:** Intros, Outros, Visual Pauses, Memes.
* **How it works:** The scene is forced to a specific time (e.g., 5 seconds).
* **Configuration:**
* Set `"duration": 5.0` in the scene object.
* If audio is shorter, silence is added. If longer, it is cut.



---

## 🛠 Layer Properties Reference

Every scene is a stack of layers. Layers are rendered from **Bottom (0) to Top**.

### 🎥 Visual Layers (Video / Image)

| Property | Type | Description |
| --- | --- | --- |
| `type` | String | `"video"` or `"image"` |
| `source` | String | Direct URL (`http`) or Base64 string (`data:`). |
| `resize_mode` | String | `"cover"` (Fill screen), `"contain"` (Fit inside), `"stretch"`. |
| `duration_mode` | String | `"loop"` (Repeat to fit), `"trim"` (Cut to fit), `"freeze"` (Hold last frame). |
| `opacity` | Float | `0.0` (Invisible) to `1.0` (Visible). |
| `x` / `y` | String | Position logic. E.g., `"(W-w)/2"` for center. |

### 🔊 Audio Layers

| Property | Type | Description |
| --- | --- | --- |
| `type` | String | `"audio"` |
| `role` | String | Set to `"main"` to make this file dictate the scene length (Auto Mode). |
| `volume` | Float | `1.0` is 100%. |

### ✍️ Text Layers

| Property | Type | Description |
| --- | --- | --- |
| `type` | String | `"text"` |
| `content` | String | The text string to display. |
| `size` | Integer | Font size (e.g., `60`). |
| `color` | String | Color name (`yellow`, `white`, `black`) or Hex code. |

---

## 📄 Example JSON Payload

Copy this to test the engine capabilities.

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
      "comment": "SCENE 1: Auto Mode. The video loops until the Voiceover finishes.",
      "layers": [
        {
          "type": "audio",
          "role": "main",
          "source": "https://www2.cs.uic.edu/~i101/SoundFiles/BabyElephantWalk60.wav",
          "volume": 1.0
        },
        {
          "type": "video",
          "source": "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4",
          "resize_mode": "cover",
          "duration_mode": "loop"
        },
        {
          "type": "text",
          "content": "Mode: Auto-Sync",
          "y": 1200,
          "color": "yellow"
        }
      ]
    },
    {
      "comment": "SCENE 2: Script Mode. Forced to 3 seconds regardless of audio.",
      "duration": 3.0,
      "layers": [
        {
          "type": "image",
          "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/200px-Python-logo-notext.svg.png",
          "resize_mode": "contain"
        },
        {
          "type": "text",
          "content": "Fixed 3s Pause",
          "y": 1500,
          "size": 50
        }
      ]
    }
  ]
}

```

## ⚠️ Important Notes

1. **Direct Links Only:** When using URLs, ensure they point directly to the file (ending in .mp4, .mp3, .png). Do not use webpage links (like Dropbox landing pages).
2. **JSON Syntax:** Standard JSON does not support comments (`//`). Remove them before processing.
3. **Order Matters:** Layers are stacked in order. The first item in the `layers` list is the background. The last item is the top-most overlay.
