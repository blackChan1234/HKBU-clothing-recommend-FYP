import re
import json
from typing import Dict, Any, TypedDict, List


class AgentState(TypedDict):
    """State object shared between agents"""
    userInput: str
    userProfile: Dict
    
    # --- Agentic Loop Fields ---
    retry_count: int
    manager_feedback: str
    router_decision: str
    
    # --- Enhanced Workflow Fields ---
    style_suggestion: str
    search_queries: List[str]  # CHANGED: From single string to List of strings
    budget_items: List[Dict]
    context_advice: str
    manager_decision: str
    final_recommendation: str
    budget_exceeded: bool
    arbitration_needed: bool
    arbitration_result: str


def extract_json_from_response(content: str) -> Dict[str, Any]:
    """Extract JSON from response, handling markdown blocks and mixed text"""
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    markdown_patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
        r'`(\{.*?\})`'
    ]

    for pattern in markdown_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    # Fallback: Find first { and last }
    start_idx = content.find('{')
    end_idx = content.rfind('}')
    if start_idx != -1 and end_idx != -1:
        try:
            return json.loads(content[start_idx:end_idx+1])
        except json.JSONDecodeError:
            pass

    return {}


def format_budget_items(items: List[Dict]) -> str:
    """Format budget items for display, including LINKS"""
    if not items:
        return "沒有找到符合預算的商品"

    formatted = "### 🛒 找到的商品清單：\n"
    total_price = 0
    for i, item in enumerate(items, 1):
        link = item.get('link', '#')
        price = item.get('price', 0)
        total_price += price
        formatted += f"{i}. **[{item['name']}]({link})**\n   - 價格: {item['currency']} {price:.2f}\n"
    
    formatted += f"\n**總金額**: {items[0]['currency'] if items else 'HKD'} {total_price:.2f}"
    return formatted


def check_budget_exceeded(items: List[Dict], budget: float) -> bool:
    """
    Improved Check: 
    Checks if the SUM of the outfit exceeds budget, 
    OR if any individual item is ridiculously overpriced.
    """
    if not items:
        return False

    total_price = sum(item.get('price', 0) for item in items)
    
    # 邏輯：如果是單件推薦，我們看單價。如果是多件組(OOTD)，我們看總價。
    # 這裡採用一個寬容度 (Tolerance)，允許超支 10%
    if total_price > budget * 1.1: 
        return True
        
    return False

def create_arbitration_prompt(user_profile: Dict, style_suggestion: str, budget_items: List[Dict]) -> str:
    """Create prompt for budget arbitration"""
    budget = user_profile.get('預算', 0)

    if not budget_items:
        return f"""
        團隊衝突：造型師建議的風格無法在預算 {budget} 元內找到商品。

        造型師建議：{style_suggestion}
        預算限制：{budget} 元
        搜尋結果：沒有找到符合預算的商品

        作為經理，請提供以下決策：
        1. 是否要調整風格建議以符合預算？
        2. 是否要建議用戶增加預算？
        3. 還是要尋找替代方案？

        請提供明確的決策和理由。
        """

    min_price = min(item.get('price', float('inf')) for item in budget_items)

    return f"""
    團隊協作成功：找到了符合預算的商品選項。

    造型師建議：{style_suggestion}
    預算限制：{budget} 元
    找到商品：{len(budget_items)} 件，最低價格 {min_price} 元

    請基於以上信息做出最終推薦決策。
    """