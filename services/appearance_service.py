from __future__ import annotations

from typing import Any, Dict, Optional
from apis.nano_banana_client import NanoBananaClient
from main_improved import run_recommendation_system

PROMOTION_PROMPT = (
    "The goal is to select the person in Figure 1 and have them wear all the clothing "
    "and accessories from Figure 2. Take a series of realistic OOTD-style photos outdoors, "
    "using natural light, a trendy street style, and clear full-body shots. Maintain the "
    "person's identity and pose from Figure 1, but showcase the complete clothing and "
    "accessories from Figure 2 in a coherent and fashionable way."
)

class AppearanceGenerationService:
    """Coordinates agent reasoning, Nano Banana diagramming, and image fusion."""

    def __init__(self):
        self.nano_client = NanoBananaClient()

    def generate_plan_only(
        self,
        requirements: str,
        selected_style: Optional[str] = None,
        user_prompt: Optional[str] = None,
        budget: int = 500,
        location: str = "Hong Kong",
        gender: str = "Men",
        age: str = "Young Adult (20-35)"
    ) -> Dict[str, Any]:
        
        normalized_requirements = requirements.strip() or "General outfit assistance request."
        
        planner_prompt = self._compose_planner_prompt(
            normalized_requirements,
            selected_style,
            user_prompt,
            budget,
            location,
            gender,
            age
        )

        # 執行 Agent Workflow (這裡比較快)
        agent_state = run_recommendation_system(
            planner_prompt,
            verbose=True,
            raise_on_error=True,
        ) or {}

        # 回傳 Agent 結果，不跑 Nano Banana
        return {
            "requirements": normalized_requirements,
            "promotion_prompt": PROMOTION_PROMPT,
            "agent_summary": {
                "style_suggestion": agent_state.get("style_suggestion"),
                "final_recommendation": agent_state.get("final_recommendation"),
                "context_advice": agent_state.get("context_advice"),
                "budget_items": agent_state.get("budget_items", []),
            },
            # 這裡回傳 prompt 資訊給前端，讓前端在第二步傳回來
            "internal_context": {
                "style_suggestion": agent_state.get("style_suggestion"),
                "context_advice": agent_state.get("context_advice"),
                "requirements": normalized_requirements,
                "selected_style": selected_style
            }
        }

    # --- 修改 2: 只負責產生圖片 (慢速) ---
    def generate_visuals_only(
        self,
        user_image_bytes: bytes,
        internal_context: str, # 接收 JSON string
    ) -> Dict[str, Any]:
        
        import json
        ctx = json.loads(internal_context)
        
        # 重建 Agent State dict 以供 compose prompt 使用
        agent_state_mock = {
            "style_suggestion": ctx.get("style_suggestion"),
            "context_advice": ctx.get("context_advice")
        }

        print("\n[NANO BANANA] Step 1: Generating OOTD Diagram...")
        diagram_prompt = self._compose_diagram_prompt(
            ctx.get("requirements"),
            ctx.get("selected_style"),
            agent_state_mock,
        )
        
        diagram_result = self.nano_client.generate_ootd_diagram(
            prompt=diagram_prompt,
            reference_style=ctx.get("selected_style"),
        )

        print("\n[NANO BANANA] Step 2: Generating Virtual Try-On...")
        final_prompt = self._compose_final_prompt(
            ctx.get("requirements"),
            diagram_prompt,
            agent_state_mock,
        )

        final_result = self.nano_client.blend_user_with_diagram(
            user_image=user_image_bytes,
            diagram_image_data=diagram_result.get("image_data"),
            promo_prompt=final_prompt,
        )

        return {
            "diagram": {
                "prompt": diagram_prompt,
                "image_url": diagram_result.get("image_url"),
                "image_data": diagram_result.get("image_data"),
            },
            "final_image": final_result,
        }

    @staticmethod
    def _compose_planner_prompt(
        requirements: str,
        selected_style: Optional[str],
        user_prompt: Optional[str],
        budget: int,
        location: str,
        gender: str,
        age: str,
    ) -> str:
        base = f"""
        [SYSTEM_INJECTED_DATA]
        BUDGET: {budget}
        LOCATION: {location}
        STYLE_PREF: {selected_style if selected_style else "Not specified"}
        TARGET_GENDER: {gender} (Strictly enforce this gender for clothing selection)
        TARGET_AGE_GROUP: {age} (Ensure the style is age-appropriate)
        [/SYSTEM_INJECTED_DATA]
        
        使用者需求描述：{requirements}
        """
        if user_prompt:
            base += f"\n額外說明：{user_prompt}"
        return base

    @staticmethod
    def _compose_diagram_prompt(
        requirements: str,
        selected_style: Optional[str],
        agent_state: Dict[str, Any],
    ) -> str:
        style = selected_style or agent_state.get("style_suggestion") or "Streetwear"
        context = agent_state.get("context_advice") or ""
        # Improved Prompt: 強調一致性 (Consistency)
        return (
            f"Professional fashion **knolling photography (flat lay)**. "
            f"Style: {style}. "
            f"User request: {requirements}. "
            f"Context: {context}. "
            "Layout: Neatly arranged grid on a clean white background. "
            "Items: clearly visible top, bottom, shoes, and accessories. "
            "Ensure color consistency and realistic fabric textures."
        )

    @staticmethod
    def _compose_final_prompt(
        requirements: str,
        diagram_prompt: str,
        agent_state: Dict[str, Any],
    ) -> str:
        # Improved Prompt: 強制要求穿著圖表中的衣物
        return (
            f"{PROMOTION_PROMPT}\n"
            f"**IMPORTANT**: The person MUST wear the EXACT outfit described below.\n"
            f"Outfit Description: {diagram_prompt}\n"
            f"User Context: {requirements}\n"
            "Maintain the exact colors, style, and textures from the description. "
            "High fidelity, cinematic lighting, photorealistic 8k."
        )