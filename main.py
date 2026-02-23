import os
import requests
import json
import getpass
from dotenv import load_dotenv
load_dotenv()

# HKBU School API Configuration
hkbu_api_key = os.getenv("HKBU_API_KEY")
hkbu_base_url = os.getenv("HKBU_BASE_URL")
bluecart_api_key = os.getenv("BLUECART_API_KEY")

# 如果環境變數中沒有，則提示使用者手動輸入
if not hkbu_api_key:
    hkbu_api_key = getpass.getpass("請輸入您的 HKBU API 金鑰: ")

from langchain_openai import ChatOpenAI

# Use HKBU school API for both Gemini and ChatGPT through OpenAI-compatible endpoints
geminimodel = ChatOpenAI(
    model="gemini-2.5-pro",  # Using the model from your curl example
    temperature=0,
    openai_api_key=hkbu_api_key,
    openai_api_base=f"{hkbu_base_url}/deployments/gemini-2.5-pro/chat/completions?api-version=v1"
)

openAimodel = ChatOpenAI(
    model="gpt-4o",  # Standard GPT model available through HKBU
    temperature=0,
    openai_api_key=hkbu_api_key,
    openai_api_base=f"{hkbu_base_url}/deployments/gpt-4o/chat/completions?api-version=v1"
)

print("模型初始化成功！")

import requests
import json
import os  # 再次引入 os 以確保工具函式可以獨立運作


# 工具一：香港天文台天氣 API
def get_hko_weather_forecast():
    """
    從香港天文台獲取未來九天的天氣預報。
    這個 API 是公開的，不需要金鑰。
    """
    print("--- TOOL CALL: 正在呼叫香港天文台 API... ---")
    url = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=fnd&lang=tc"
    try:
        response = requests.get(url)
        response.raise_for_status()  # 如果請求失敗 (e.g., 404, 500)，會拋出異常
        data = response.json()
        # 簡化輸出，只提供未來兩天的天氣預報摘要
        forecast_summary = "未來兩天天氣預報：\n"
        for forecast in data['weatherForecast'][:2]:
            date = forecast['forecastDate']
            week = forecast['week']
            temp = f"{forecast['forecastMintemp']['value']} - {forecast['forecastMaxtemp']['value']} 度"
            weather = forecast['forecastWeather']
            forecast_summary += f"- {date} ({week}): {weather}，氣溫 {temp}\n"
        return forecast_summary
    except requests.exceptions.RequestException as e:
        print(f"錯誤：無法獲取天氣資訊: {e}")
        return "無法獲取天氣資訊，請稍後再試。"


# 工具二：BlueCart 商品搜尋 API
def search_products_with_bluecart(search_query: str, max_price: int):
    """
    使用 BlueCart API 根據關鍵字和最高價格搜尋商品。
    """
    print(f"--- TOOL CALL: 正在呼叫 BlueCart API (搜尋: '{search_query}', 價格 < {max_price})... ---")
    api_key = os.getenv("BLUECART_API_KEY")
    if not api_key:
        return "錯誤：BlueCart API 金鑰未設定。"

    params = {
        'api_key': api_key,
        'type': 'search',
        'search_term': search_query,
        'sort_by': 'price_low_to_high'  # 按價格從低到高排序
    }

    try:
        api_result = requests.get('https://api.bluecartapi.com/request', params)
        api_result.raise_for_status()
        search_results = api_result.json().get('search_results', [])

        # 篩選符合預算的商品
        filtered_items = []
        for item in search_results:
            product = item.get('product', {})
            offers = item.get('offers', {})
            primary_offer = offers.get('primary', {})

            title = product.get('title')
            price = primary_offer.get('price')

            if title and price and price <= max_price:
                filtered_items.append({
                    "name": title,
                    "price": price,
                    "currency": primary_offer.get('currency_symbol', '$'),
                    "seller": primary_offer.get('seller', {}).get('name', 'Unknown'),
                    "link": product.get('link', '')
                })
        print(f"--- TOOL RESULT: BlueCart API 找到 {len(filtered_items)} 件符合預算的商品 ---")
        return filtered_items[:5]  # 只返回前 5 個結果，避免資訊過多
    except requests.exceptions.RequestException as e:
        print(f"錯誤：BlueCart API 請求失敗: {e}")
        return []

from typing import List, TypedDict, Dict
import operator


# 每個代理的輸出都會被添加到這個共享的狀態中
class AgentState(TypedDict):
    userInput: str  # 使用者原始輸入
    userProfile: Dict # 使用者輪廓分析結果
    style_suggestion: str # 造型師的風格建議
    search_query: str
    budget_items: List[Dict] # 預算師找到的商品
    context_advice: str # 情境顧問的建議
    manager_decision: str # 經理的最終決策
    final_recommendation: str # 最終生成給使用者的推薦文案


import re
import json


def extract_json_from_response(content: str) -> dict:
    """
    從回應中提取JSON，能處理markdown格式和混合文字
    """
    # Remove leading/trailing whitespace
    content = content.strip()

    # Try direct JSON parsing first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code blocks
    markdown_patterns = [
        r'``````',  # ``````
        r'``````',  # ``````
        r'`(\{.*?\})`'  # `{ }`
    ]

    for pattern in markdown_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    # Try to find the first complete JSON object
    brace_count = 0
    start_idx = content.find('{')

    if start_idx != -1:
        for i, char in enumerate(content[start_idx:], start_idx):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    try:
                        json_str = content[start_idx:i + 1]
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        break

    # If all else fails, return None
    return None


def user_profiler_agent(state: AgentState):
    """
    User Profiler Agent: 專門分析使用者初步需求。
    """
    print("--- AGENT: User Profiler Agent 運作中... ---")
    prompt = f"""
    你是一位使用者分析專家。請根據以下使用者輸入，解析出關鍵資訊。

    使用者輸入: "{state['userInput']}"

    請以JSON格式回傳分析結果，包含：場合、地點、預算、個人偏好
    """
    response = geminimodel.invoke(prompt)

    profile = extract_json_from_response(response.content)

    if profile is None:
        print("警告：無法解析JSON回應，使用預設值")
        print(f"原始回應: {response.content}")
        profile = {
            "場合": "休閒",
            "地點": "香港",
            "預算": 3000,
            "個人偏好": "舒適"
        }

    return {"userProfile": profile}
def manager_agent(state: AgentState):
    """
    Manager Agent: 團隊經理，負責解析需求、分派任務，並在最後整合方案。
    (在 LangGraph 中，"分派任務" 是透過定義工作流程的邊 (Edge) 來實現的，
    所以這個節點主要負責初步解析和最終整合)
    """
    print("--- AGENT: Manager Agent 運作中... ---")
    # 第一次被呼叫時，它進行任務解析
    if not state.get("style_suggestion"): # 檢查是否已進入協作階段
        print("--- Manager: 進行初步需求解析與任務規劃 ---")
        return {} # 在此階段不改變 state，僅作為流程的起點
    # 當所有專家都提供意見後，經理進行最終決策
    else:
        print("--- Manager: 整合所有專家意見，做出最終決策 ---")
        prompt = f"""
        你是一位專案經理。你的團隊成員提供了以下建議，請整合出一個最終的服裝方案。

        - 使用者輪廓: {state['userProfile']}
        - 造型師建議: {state['style_suggestion']}
        - 預算師找到的符合預算的商品: {state['budget_items']}
        - 情境顧問建議: {state['context_advice']}

        請基於以上所有資訊，決定最終推薦哪一件商品，並說明理由。
        你的決策應該聽起來像是對團隊說的，例如：「好的團隊，我們決定推薦...因為...」
        """
        response = geminimodel.invoke(prompt)
        return {"manager_decision": response.content}


def aesthetic_stylist_agent(state: AgentState):
    """
    Aesthetic Stylist Agent (GPT-4o): 提出風格建議，並生成用於商品搜尋的關鍵字。
    """
    print("--- AGENT: Aesthetic Stylist (GPT-4o) 運作中... ---")
    prompt = f"""
    你是一位頂尖的時尚造型師。根據以下使用者輪廓，為他推薦一個最適合的服裝風格，
    並提供一個用於電商網站搜尋的、精確的英文搜尋關鍵字 (search query)。

    使用者輪廓: {state['userProfile']}

    請以 JSON 格式回傳，包含 "style_suggestion" 和 "search_query" 兩個 key。
    例如:
    {{
      "style_suggestion": "波西米亞風飄逸長裙，搭配編織涼鞋",
      "search_query": "bohemian maxi dress for beach wedding"
    }}
    """
    response = openAimodel.invoke(prompt)
    suggestion = extract_json_from_response(response.content)
    return {
        "style_suggestion": suggestion['style_suggestion'],
        # 將搜尋關鍵字也加入狀態中，供下一個代理使用
        "search_query": suggestion['search_query']
    }

def budget_planner_agent(state: AgentState):
    """
    Budget Planner Agent: 使用 BlueCart API 進行真實商品搜尋。
    """
    print("--- AGENT: Budget Planner Agent 運作中... ---")
    budget = state['userProfile'].get('預算', 99999)
    query = state.get('search_query', 'dress') # 從 state 中獲取搜尋關鍵字
    items = search_products_with_bluecart(query, budget)
    return {"budget_items": items}

def context_advisor_agent(state: AgentState):
    """
    Context Advisor Agent: 根據香港天文台的真實天氣提供建議。
    """
    print("--- AGENT: Context Advisor Agent 運作中... ---")
    weather = get_hko_weather_forecast()
    prompt = f"""
    你是一位情境顧問。根據以下資訊，提供材質或設計上的建議。
    - 使用者輪廓: {state['userProfile']}
    - 香港天氣預報: {weather}
    你的建議要簡潔有力，並結合天氣情況。
    """
    response = geminimodel.invoke(prompt) # 使用 Gemini
    return {"context_advice": response.content.strip()}

def recommendation_synthesizer_agent(state: AgentState):
    """
    Recommendation Synthesizer Agent: 最終的推薦文案產生器。
    """
    print("--- AGENT: Recommendation Synthesizer Agent 運作中... ---")
    prompt = f"""
    你是一位親切的個人購物助理。請根據以下經理的最終決策，為使用者生成一段有說服力且溫暖的推薦文案。
    你需要解釋為什麼推薦這套服裝，並巧妙地結合風格、預算和情境考量。

    經理的決策摘要: {state['manager_decision']}
    """
    response = geminimodel.invoke(prompt)
    return {"final_recommendation": response.content}

def experts_node(state: AgentState):
    """
    這個節點會同時呼叫三個專家代理，並將他們的結果合併。
    """
    # 呼叫各個專家
    style_result = aesthetic_stylist_agent(state)
    budget_result = budget_planner_agent(state)
    context_result = context_advisor_agent(state)

    # 合併所有專家的結果
    return {
        **style_result,
        **budget_result,
        **context_result,
    }

from langgraph.graph import StateGraph, END

workflow = StateGraph(AgentState)

# 1. 添加節點
workflow.add_node("user_profiler", user_profiler_agent)
workflow.add_node("manager", manager_agent)
workflow.add_node("experts", experts_node)
workflow.add_node("recommendation_synthesizer", recommendation_synthesizer_agent)

# 2. 定義邊 (流程不變)
workflow.set_entry_point("user_profiler")
workflow.add_edge("user_profiler", "manager")
workflow.add_edge("manager", "experts")
workflow.add_edge("experts", "manager")
# helper: after each Manager run decide next node
def route_from_manager(state: AgentState) -> str:
    # Second pass: we already have the final decision
    if state.get("manager_decision"):
        return "recommendation_synthesizer"
    # First pass (no style_suggestion yet) → go gather expert opinions
    else:
        return "experts"

workflow.add_conditional_edges(
    "manager",
    route_from_manager,                         # decision fn
    {                                           # label → target
        "experts": "experts",
        "recommendation_synthesizer": "recommendation_synthesizer",
    }
)

workflow.add_edge("recommendation_synthesizer", END)

# 3. 編譯圖
app = workflow.compile()

print("Graph 編譯成功！系統準備就緒。")

# --- 如何執行 ---
user_input = {"userInput": "我週末要去香港石澳海邊參加朋友的婚禮，預算3000港幣。"}

# 使用 stream 可以看到每一步的詳細輸出
print("--- 系統開始運作 ---")
for event in app.stream(user_input, {"recursion_limit": 5}):
    for key, value in event.items():
        print(f"\n--- 節點 '{key}' 的輸出 ---")
        print(value)
print("\n" + "="*40 + "\n")

# 使用 invoke 只獲取最終結果
print("--- 正在獲取最終推薦... ---")
final_state = app.invoke(user_input, {"recursion_limit": 5})
print("\n✨ --- 最終推薦文案 --- ✨")
print(final_state.get('final_recommendation'))