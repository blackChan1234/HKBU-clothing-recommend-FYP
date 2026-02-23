import base64
import io
import os
import re
import textwrap
from typing import Any, Dict, List, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image, ImageDraw, ImageFont


class NanoBananaClient:
    """Client for image generation using Nano Banana API (OpenAI-compatible format)."""

    def __init__(self):
        # Nano Banana API (OpenAI-compatible)
        self.api_key = os.getenv("NANO_BANANA_API_KEY")
        self.base_url = os.getenv("NANO_BANANA_BASE_URL", "https://newapi.pockgo.com")
        
        # Setup Session with Retry Logic (修復連線不穩問題)
        self.session = requests.Session()
        retries = Retry(
            total=3,                # 最多重試 3 次
            backoff_factor=1,       # 每次重試間隔 (1s, 2s, 4s...)
            status_forcelist=[500, 502, 503, 504], # 針對這些伺服器錯誤重試
            allowed_methods=["POST"],
            raise_on_status=False
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        
        # Use gemini-2.5-flash-image-preview for image generation
        self.model = "gemini-3-pro-image-preview"

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def generate_ootd_diagram(
        self,
        prompt: str,
        reference_style: Optional[str] = None,
        reference_image: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """Create an intermediate OOTD diagram using Gemini image generation."""

        style_context = reference_style or "Modern Streetwear"

        full_prompt = (
            f"Create a professional fashion **flat lay photography (knolling)** of a coordinated outfit. "
            f"Subject: {prompt}. "
            f"Style Aesthetic: {style_context}. "
            "Composition: **Top-down 90-degree view**, items are neatly arranged in a balanced **grid layout** on a clean, neutral background (light grey or white). "
            "Lighting: Soft, diffuse studio lighting to show fabric textures clearly. "
            "Constraints: **No human models**, no mannequins, no body parts. Just the clothing items and accessories laid out organized."
        )

        if self._is_remote_enabled:
            result = self._generate_image(full_prompt, reference_image)
            if result:
                return result
            print("--- Nano Banana: Remote API failed, using fallback stub ---")

        return self._generate_stub_diagram(prompt, reference_style)

    def blend_user_with_diagram(
        self,
        user_image: bytes,
        diagram_image_data: Optional[str],
        promo_prompt: str,
    ) -> Dict[str, Any]:
        """
        Task: Virtual Try-On.
        Takes the user (Image 1) and makes them wear the outfit from the diagram (Image 2).
        """

        base_instruction = (
            "**Virtual Try-On Task**: "
            "Generate a realistic photo of the person from the first image wearing the exact outfit shown in the second image. "
            "1. **Identity**: Preserve the person's face, body shape, and pose from Image 1 exactly. "
            "2. **Outfit**: Transfer all clothing items (jacket, top, pants, shoes, accessories) from Image 2 onto the person. "
            "3. **Style**: Outdoor street fashion photography, natural lighting, realistic fabric folds and fit. "
            "4. **Quality**: High resolution, photorealistic, cinematic depth of field."
        )

        final_prompt = f"{base_instruction} Additional Context: {promo_prompt}"

        if self._is_remote_enabled:
            # Pass both user image and diagram image
            input_images: List[Union[bytes, str]] = [user_image]
            if diagram_image_data:
                input_images.append(diagram_image_data)

            result = self._generate_image(final_prompt, input_images)
            if result:
                return result
            print("--- Nano Banana: Remote API failed, using fallback stub ---")

        return self._generate_stub_final(user_image, diagram_image_data)

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    @property
    def _is_remote_enabled(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _generate_image(
        self,
        prompt: str,
        reference_images: Optional[Union[bytes, List[Union[bytes, str]]]] = None
    ) -> Optional[Dict[str, Any]]:
        """Call Nano Banana API (OpenAI-compatible format) for image generation."""
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Build content array for OpenAI-compatible format
        content = [{"type": "text", "text": prompt}]

        # Handle reference images (can be single bytes or list of bytes/data URIs)
        if reference_images:
            images_list = reference_images if isinstance(reference_images, list) else [reference_images]

            for img in images_list:
                if isinstance(img, bytes):
                    img_base64 = base64.b64encode(img).decode()
                    img_url = f"data:image/jpeg;base64,{img_base64}"
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": img_url}
                    })
                elif isinstance(img, str) and img.startswith("data:"):
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": img}
                    })
                # If it's a remote URL (e.g. from previous step), pass it directly
                elif isinstance(img, str) and img.startswith("http"):
                     content.append({
                        "type": "image_url",
                        "image_url": {"url": img}
                    })

        # OpenAI-compatible payload
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.7
        }

        print(f"  [NANO BANANA API] Calling {url} with model {self.model}...")

        try:
            # Increased timeout to 240s for stability
            response = self.session.post(url, json=payload, headers=headers, timeout=240)
            
            if response.status_code != 200:
                print(f"  [NANO BANANA API] Error: Status {response.status_code} - {response.text[:300]}")
                return None

            result = response.json()

            # Parse OpenAI-compatible response format
            if 'choices' in result and len(result['choices']) > 0:
                choice = result['choices'][0]
                message = choice.get('message', {})
                msg_content = message.get('content', '')

                # Check if content is a string (could be base64 image or URL OR Markdown)
                if isinstance(msg_content, str):
                    # FIX: Handle Markdown image format ![alt](url)
                    markdown_match = re.search(r'!\[.*?\]\((.*?)\)', msg_content)
                    if markdown_match:
                        img_url = markdown_match.group(1)
                        print(f"  [NANO BANANA API] Image URL extracted from markdown: {img_url}")
                        return {
                            "image_data": None,
                            "image_url": img_url,
                            "prompt": prompt,
                        }
                    
                    if msg_content.startswith('data:image'):
                        print(f"  [NANO BANANA API] Image data received (base64)")
                        return {
                            "image_data": msg_content,
                            "image_url": None,
                            "prompt": prompt,
                        }
                    elif msg_content.startswith('http'):
                        print(f"  [NANO BANANA API] Image URL received")
                        return {
                            "image_data": None,
                            "image_url": msg_content,
                            "prompt": prompt,
                        }

                # Check if content is a list (multimodal response)
                if isinstance(msg_content, list):
                    for item in msg_content:
                        if isinstance(item, dict):
                            # Check for image type
                            if item.get('type') == 'image':
                                img_data = item.get('image', {}).get('data') or item.get('data')
                                if img_data:
                                    print(f"  [NANO BANANA API] Image generated successfully")
                                    return {
                                        "image_data": f"data:image/png;base64,{img_data}",
                                        "image_url": None,
                                        "prompt": prompt,
                                    }
                            # Check for image_url type
                            elif item.get('type') == 'image_url':
                                img_url = item.get('image_url', {}).get('url')
                                if img_url:
                                    print(f"  [NANO BANANA API] Image URL received")
                                    return {
                                        "image_data": img_url if img_url.startswith('data:') else None,
                                        "image_url": img_url if img_url.startswith('http') else None,
                                        "prompt": prompt,
                                    }

                # Log text response if no image found
                print(f"  [NANO BANANA API] Response (no image): {str(msg_content)[:200]}...")

            return None

        except requests.exceptions.RequestException as e:
            # 這是您遇到的錯誤類型
            print(f"  [NANO BANANA API] Connection Error (Retries failed): {e}")
            return None
        except Exception as e:
            print(f"  [NANO BANANA API] Unexpected Error: {type(e).__name__}: {e}")
            return None

    def _generate_stub_diagram(self, prompt: str, reference_style: Optional[str]) -> Dict[str, Any]:
        width, height = 768, 1024
        canvas = Image.new("RGB", (width, height), "#111827")
        draw = ImageDraw.Draw(canvas)

        title_font = self._load_font(42)
        body_font = self._load_font(24)

        draw.text((40, 40), "OOTD Diagram", fill="#fcd34d", font=title_font)
        if reference_style:
            draw.text((40, 110), f"Style: {reference_style}", fill="#fef3c7", font=body_font)

        wrapped = textwrap.fill(prompt, width=32)
        draw.multiline_text((40, 180), wrapped, fill="#d1d5db", font=body_font, spacing=6)

        encoded = self._encode_data_uri(canvas)
        return {
            "image_data": encoded,
            "image_url": None,
            "prompt": prompt,
        }

    def _generate_stub_final(self, user_image: bytes, diagram_image_data: Optional[str]) -> Dict[str, Any]:
        # Load or fallback to a gradient canvas
        try:
            base_img = Image.open(io.BytesIO(user_image)).convert("RGB")
        except Exception:
            base_img = Image.new("RGB", (768, 1024), "#1f2937")

        base_img = base_img.resize((768, 1024))
        overlay = Image.new("RGBA", base_img.size, (15, 23, 42, 140))
        composed = Image.alpha_composite(base_img.convert("RGBA"), overlay)

        draw = ImageDraw.Draw(composed)
        title_font = self._load_font(36)
        draw.text((32, 32), "Final OOTD Preview", fill="#fef3c7", font=title_font)

        if diagram_image_data:
            try:
                # Handle URL vs Base64 stub
                if diagram_image_data.startswith("http"):
                    # For stub purposes, just draw text "URL Image"
                    draw.text((480, 600), "Diagram URL\nLinked", fill="#fff", font=title_font)
                else:
                    header, b64 = diagram_image_data.split(",", 1)
                    diag_bytes = base64.b64decode(b64)
                    diag_img = Image.open(io.BytesIO(diag_bytes)).resize((256, 342))
                    composed.paste(diag_img, (480, 640))
            except Exception:
                pass

        encoded = self._encode_data_uri(composed.convert("RGB"))
        return {
            "image_data": encoded,
            "image_url": None,
        }

    @staticmethod
    def _encode_data_uri(image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{b64}"

    @staticmethod
    def _load_font(size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype("arial.ttf", size)
        except OSError:
            return ImageFont.load_default()