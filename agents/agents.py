from typing import Dict, List
import concurrent.futures
from utils.helpers import AgentState, extract_json_from_response, check_budget_exceeded, format_budget_items

# Import API Clients
from apis.api_clients import HKBUAPIClient

class ManagerAgent:
    """Manager Agent - Router & Arbitrator"""
    def __init__(self):
        self.api_client = HKBUAPIClient()

    def process(self, state: AgentState) -> Dict:
        print("\n" + "=" * 50)
        print("[MANAGER AGENT] Starting arbitration process...")
        print("=" * 50)

        items = state.get('budget_items', [])
        budget = state['userProfile'].get('預算', 0)
        retry_count = state.get('retry_count', 0)

        # 1. Safety Mechanism
        if retry_count >= 3:
            print("--- Manager: Too many retries, forcing completion ---")
            return {
                "router_decision": "FINISH",
                "manager_decision": "已達最大重試次數，將呈現目前找到的最佳組合。"
            }

        # 2. Check Constraints
        if not items:
            feedback = "找不到任何商品。請嘗試將搜尋關鍵字改為更常見的基礎款單品 (如 'T-shirt', 'Denim')。"
            return self._trigger_retry(feedback, retry_count)

        # 檢查總金額是否嚴重超支
        if check_budget_exceeded(items, budget):
            total_cost = sum(i['price'] for i in items)
            feedback = f"組合總價 ({total_cost}) 超出預算 ({budget})。請嘗試尋找更平價的替代品，或減少單品數量。"
            return self._trigger_retry(feedback, retry_count)

        # 3. Success Path
        print("--- Manager: Budget and style approved ---")
        return {
            "router_decision": "FINISH",
            "manager_decision": "團隊協作成功，已構建完整的預算內穿搭。"
        }

    def _trigger_retry(self, feedback: str, current_retry: int) -> Dict:
        print(f"--- Manager: Triggering retry loop -> {feedback} ---")
        return {
            "router_decision": "CONTINUE",
            "manager_feedback": feedback,
            "retry_count": current_retry + 1
        }


class UserProfilerAgent:
    """User Profiler Agent"""
    def __init__(self):
        self.api_client = HKBUAPIClient()

    def process(self, state: AgentState) -> Dict:
        print("\n" + "=" * 50)
        print("[USER PROFILER] Analyzing user requirements...")
        print("=" * 50)
        
        prompt = f"""
        你是一位使用者分析專家。請解析以下輸入。
        注意：輸入中可能包含 [SYSTEM_INJECTED_DATA] 區塊，該區塊內的資訊（預算、地點、風格）具有最高優先級。

        使用者輸入: "{state['userInput']}"

        請以JSON格式回傳分析結果：
        {{
            "場合": "string",
            "地點": "string (優先使用 SYSTEM_INJECTED_DATA)",
            "預算": number (優先使用 SYSTEM_INJECTED_DATA，純數字),
            "個人偏好": "string"
        }}
        """

        messages = [{"role": "user", "content": prompt}]
        response = self.api_client.call_chatgpt(messages)
        profile = extract_json_from_response(response)

        if not profile or not isinstance(profile, dict):
            profile = {
                "場合": "一般",
                "地點": "Hong Kong",
                "預算": 500,
                "個人偏好": "Casual"
            }

        print(f"  [USER PROFILER] Output: {profile}")
        return {"userProfile": profile}


class AestheticStylistAgent:
    """
    Aesthetic Stylist Agent - Decomposed Search Strategy
    Generates 3 parallel search queries for a complete outfit.
    """
    def __init__(self):
        self.api_client = HKBUAPIClient()

    def process(self, state: AgentState) -> Dict:
        print("\n" + "=" * 50)
        print("[AESTHETIC STYLIST] Generating outfit plan...")
        print("=" * 50)

        feedback = state.get('manager_feedback', "")
        context_instruction = f"注意：上一次失敗回饋：{feedback}。請簡化關鍵字。" if feedback else "請規劃一套完整的全身穿搭。"

        # Generate 3 specific Japanese keywords
        prompt = f"""
        你是一位日本潮流造型師。請為使用者規劃一套完整的 OOTD (Outfit of the Day)。
        
        使用者輪廓: {state['userProfile']}
        任務上下文: {context_instruction}

        【搜尋策略 - 針對 Rakuten Japan】
        我們需要將預算分配給 2-3 件單品來組成一套衣服。請生成 **3 個** 具體的日文搜尋關鍵字。
        
        1. **Top (上身)**: 如 "オーバーサイズ Tシャツ" (Oversized T-shirt)
        2. **Bottom (下身)**: 如 "ワイドパンツ" (Wide pants)
        3. **Shoes/Acc (鞋/配件)**: 如 "スニーカー" (Sneakers) 或 "キャップ" (Cap)

        請以 JSON 格式回傳 (List string):
        {{
          "style_suggestion": "給使用者的中文風格建議...",
          "search_queries": ["上身日文關鍵字", "下身日文關鍵字", "配件日文關鍵字"]
        }}
        """

        messages = [{"role": "user", "content": prompt}]
        response = self.api_client.call_chatgpt(messages)
        result = extract_json_from_response(response)

        style = result.get('style_suggestion', 'Fashion Style')
        queries = result.get('search_queries', ['トップス', 'パンツ', '小物'])
        
        if isinstance(queries, str):
            queries = [queries]

        print(f"  [STYLIST] Plan: {queries}")

        return {
            "style_suggestion": style,
            "search_queries": queries
        }

class BudgetPlannerAgent:
    """
    Budget Planner Agent - Parallel Execution
    Uses ThreadPoolExecutor to call Rakuten API in parallel for faster results.
    """

    def __init__(self):
        from apis.api_clients import RakutenAPI 
        self.rakuten_api = RakutenAPI()

    def process(self, state: AgentState) -> Dict:
        print("\n" + "=" * 50)
        print("[BUDGET PLANNER] Executing parallel decomposed search...")
        print("=" * 50)

        total_budget = state['userProfile'].get('預算', 999999)
        queries = state.get('search_queries', [])
        
        if not queries:
            queries = ['dress']

        # Budget Allocation: 40% Top, 30% Bottom, 30% Acc (approx)
        # Using 60% as a loose upper bound for each item to find good candidates
        item_budget_limit = int(total_budget * 0.6) 

        print(f"  Total Budget: ${total_budget} HKD | Queries: {queries}")

        collected_items = []

        # Helper for parallel execution
        def search_single_item(query):
            try:
                # print(f"    -> Searching: '{query}'")
                results = self.rakuten_api.search_products(query, item_budget_limit)
                if results:
                    return results[0] # Pick the best match
            except Exception as e:
                print(f"    -> Error searching '{query}': {e}")
            return None

        # PARALLEL EXECUTION starts here
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_query = {executor.submit(search_single_item, q): q for q in queries}
            for future in concurrent.futures.as_completed(future_to_query):
                item = future.result()
                if item:
                    collected_items.append(item)
        
        print(f"  [BUDGET] Successfully gathered {len(collected_items)} items.")
        
        return {"budget_items": collected_items}


class ContextAdvisorAgent:
    """Context Advisor Agent"""
    def __init__(self):
        self.api_client = HKBUAPIClient()
        from apis.api_clients import WeatherAPI
        self.weather_api = WeatherAPI()

    def process(self, state: AgentState) -> Dict:
        print("\n" + "=" * 50)
        print("[CONTEXT ADVISOR] Fetching weather & context data...")
        print("=" * 50)

        weather = self.weather_api.get_hko_weather_forecast()
        
        prompt = f"""
        你是一位情境顧問。
        使用者輪廓: {state['userProfile']}
        當地天氣: {weather}
        
        請提供簡短的材質或穿搭建議。
        """

        messages = [{"role": "user", "content": prompt}]
        advice = self.api_client.call_chatgpt(messages)
        
        print(f"  [CONTEXT] Advice: {advice.strip()[:50]}...")
        return {"context_advice": advice.strip()}


class RecommendationSynthesizerAgent:
    """Synthesizer Agent"""
    def __init__(self):
        self.api_client = HKBUAPIClient()

    def process(self, state: AgentState) -> Dict:
        print("\n" + "=" * 50)
        print("[SYNTHESIZER] Generating final recommendation...")
        print("=" * 50)

        items_info = format_budget_items(state.get('budget_items', []))
        
        prompt = f"""
        你是一位專業的個人購物助理。請為使用者生成一份結構清晰的穿搭提案。
        
        【輸入資訊】
        1. 造型師建議: {state.get('style_suggestion', '')}
        2. 商品清單 (這是一整套穿搭): {items_info}
        3. 天氣建議: {state.get('context_advice', '')}
        
        【輸出格式要求】
        請使用 Markdown 格式，嚴格遵守以下結構：
        
        ### 🌤️ 天氣與情境分析
        (簡短說明為何這樣搭配適合當前天氣)

        ### 👕 全身穿搭推薦 (OOTD)
        (請將商品清單中的單品組合成一套故事，例如："上身穿著...搭配...")
        - **[商品名稱](商品連結)**：單品亮點介紹。
        
        ### 💡 搭配技巧
        (如何將這幾件單品穿得更好看)

        注意：請將長網址格式化為 `[商品名稱](URL)` 的超連結形式。
        """

        messages = [{"role": "user", "content": prompt}]
        recommendation = self.api_client.call_chatgpt(messages)
        
        print(f"  [SYNTHESIZER] Done. Length: {len(recommendation)}")
        return {"final_recommendation": recommendation}