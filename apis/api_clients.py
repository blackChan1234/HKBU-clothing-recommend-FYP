import requests
import os
from typing import Dict, List, Any


class HKBUAPIClient:
    """API client for Official Google Gemini API and OpenAI ChatGPT"""

    def __init__(self):
        # Official Google Gemini API
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_base_url = "https://generativelanguage.googleapis.com/v1beta"

        # OpenAI API for ChatGPT
        self.openai_api_key = os.getenv("HKBU_API_KEY")
        self.openai_base_url = "https://genai.hkbu.edu.hk/api/v0/rest"

    def call_gemini(self, prompt: str, model: str = "gemini-3-pro-preview", temperature: float = 0.7) -> str:
        """Call Official Google Gemini API"""
        try:
            url = f"{self.gemini_base_url}/models/{model}:generateContent"
            headers = {
                "x-goog-api-key": self.gemini_api_key,
                "Content-Type": "application/json",
            }

            # Official Gemini API format
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": 2048,
                    "topP": 1,
                }
            }

            print(f"  [GEMINI API] Calling {model}...")
            response = requests.post(url, json=payload, headers=headers, timeout=300)
            print(f"  [GEMINI API] Response status: {response.status_code}")

            if response.status_code != 200:
                print(f"  [GEMINI API] Error: {response.text[:200]}")
                return self._fallback_gemini(prompt, temperature)

            response.raise_for_status()
            result = response.json()

            # Parse official Gemini response format
            if 'candidates' in result and len(result['candidates']) > 0:
                candidate = result['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content']:
                    parts = candidate['content']['parts']
                    if len(parts) > 0 and 'text' in parts[0]:
                        return parts[0]['text']

            print(f"  [GEMINI API] Unexpected response format: {str(result)[:200]}")
            return "Error: Unexpected response format from Gemini API"

        except Exception as e:
            try:
                print(f"  [GEMINI API] Error: {e}")
            except UnicodeEncodeError:
                print(f"  [GEMINI API] Error: {type(e).__name__}")
            return self._fallback_gemini(prompt, temperature)

    def call_chatgpt(self, messages: List[Dict], model: str = "qwen3-max", temperature: float = 0.7) -> str:
        """Call Official OpenAI ChatGPT API"""
        try:
            url = f"{self.openai_base_url}/deployments/{model}/chat/completions?api-version=v1"
            headers = {
                "api-key": self.openai_api_key,
                "Content-Type": "application/json",
            }

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1000,
            }

            print(f"  [OPENAI API] Calling {model}...")
            response = requests.post(url, json=payload, headers=headers, timeout=300)
            print(f"  [OPENAI API] Response status: {response.status_code}")

            if response.status_code != 200:
                print(f"  [OPENAI API] Error: {response.text[:200]}")
                return self._fallback_chatgpt(messages, temperature)

            response.raise_for_status()
            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            else:
                return "Error: No response from ChatGPT API"

        except Exception as e:
            try:
                print(f"  [OPENAI API] Error: {e}")
            except UnicodeEncodeError:
                print(f"  [OPENAI API] Error: {type(e).__name__}")
            return self._fallback_chatgpt(messages, temperature)

    def _fallback_gemini(self, prompt: str, temperature: float) -> str:
        """Fallback to LangChain Gemini"""
        try:
            print("  [GEMINI] Using LangChain fallback...")
            from langchain_google_genai import ChatGoogleGenerativeAI
            model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=temperature)
            response = model.invoke(prompt)
            return response.content
        except Exception as e:
            return f"Fallback Gemini Error: {e}"

    def _fallback_chatgpt(self, messages: List[Dict], temperature: float) -> str:
        """Fallback to LangChain OpenAI"""
        try:
            print("  [OPENAI] Using LangChain fallback...")
            from langchain_openai import ChatOpenAI
            model = ChatOpenAI(model="gpt-4o-mini", temperature=temperature)
            if len(messages) > 0:
                response = model.invoke(messages[-1]['content'])
                return response.content
            return "No messages provided"
        except Exception as e:
            return f"Fallback ChatGPT Error: {e}"


class WeatherAPI:
    """Hong Kong Observatory Weather API"""

    @staticmethod
    def get_hko_weather_forecast():
        """Get 9-day weather forecast from Hong Kong Observatory"""
        print("--- TOOL CALL: Calling Hong Kong Observatory API... ---")
        url = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=fnd&lang=tc"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            forecast_summary = "Weather forecast for next 2 days:\n"
            for forecast in data['weatherForecast'][:2]:
                date = forecast['forecastDate']
                week = forecast['week']
                temp = f"{forecast['forecastMintemp']['value']} - {forecast['forecastMaxtemp']['value']} C"
                weather = forecast['forecastWeather']
                forecast_summary += f"- {date} ({week}): {weather}, Temp {temp}\n"
            return forecast_summary
        except requests.exceptions.RequestException as e:
            print(f"Error: Failed to get weather info: {e}")
            return "Unable to get weather information. Please try again later."


class RakutenAPI:
    """Rakuten Ichiba Product Search API (樂天市場商品搜尋 - HKD Version)"""

    # Rakuten API Endpoint (Version 20170706 is the standard stable version)
    BASE_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20170706"
    
    # Approximate Exchange Rates (Fixed for demo purposes)
    # In production, you might want to fetch live rates.
    # 1 JPY = ~0.051 HKD (as of late 2024/early 2025 estimation)
    JPY_TO_HKD_RATE = 0.051
    # 1 HKD = ~19.6 JPY
    HKD_TO_JPY_RATE = 19.6

    @staticmethod
    def search_products(search_query: str, max_price: int) -> List[Dict]:
        """
        Search products using Rakuten Ichiba API with HKD pricing.
        
        Args:
            search_query (str): The keyword to search (e.g., "dress", "kimono").
            max_price (int): Maximum price in HKD.
        """
        # Convert input max_price (HKD) to JPY for the API
        max_price_jpy = int(max_price * RakutenAPI.HKD_TO_JPY_RATE)
        
        print(f"--- TOOL CALL: Calling Rakuten API (search: '{search_query}', max price: {max_price} HKD -> approx. {max_price_jpy} JPY)... ---")
        
        # 1. Get Application ID (API Key)
        # Make sure to set this in your environment variables
        # Note: Rakuten Application ID is typically a ~19 digit number (e.g., 10192837465...)
        app_id = os.getenv("RAKUTEN_APP_ID")
        if not app_id:
            print("Error: RAKUTEN_APP_ID environment variable is missing.")
            return []

        # 2. Set Parameters
        # Documentation: https://webservice.rakuten.co.jp/documentation/ichiba-item-search
        params = {
            'applicationId': app_id,
            'keyword': search_query,      # Search keyword
            'maxPrice': max_price_jpy,    # API requires JPY
            'sort': '+itemPrice',         # Sort by price ascending (low to high)
            'format': 'json',             # Response format
            'hits': 5,                    # Number of results to return
            'imageFlag': 1                # Only return items with images
        }

        try:
            # 3. Make the Request
            response = requests.get(RakutenAPI.BASE_URL, params=params, timeout=15)
            
            # Improved Error Handling: Check for API error messages explicitly
            if response.status_code != 200:
                try:
                    error_data = response.json()
                    error_desc = error_data.get('error_description', 'Unknown API error')
                    error_code = error_data.get('error', str(response.status_code))
                    print(f"Error: Rakuten API returned error: {error_code} - {error_desc}")
                    print(f"Hint: Check if your App ID '{app_id[:4]}...' is correct and valid.")
                except ValueError:
                    # If response isn't JSON
                    print(f"Error: Rakuten API failed with status code: {response.status_code}")
                return []
            
            # 4. Parse the Response
            data = response.json()
            
            # Rakuten returns a list under 'Items'. 
            # Each element is a wrapper dict: {'Item': { ...product data... }}
            items_wrapper = data.get('Items', [])
            
            filtered_items = []
            
            for wrapper in items_wrapper:
                item = wrapper.get('Item', {})
                
                title = item.get('itemName')
                price_jpy = item.get('itemPrice')
                
                # Double check validity
                if title and price_jpy:
                    # Convert JPY price to HKD for display
                    price_hkd = round(price_jpy * RakutenAPI.JPY_TO_HKD_RATE, 2)
                    
                    # Construct clean item dictionary
                    filtered_items.append({
                        "name": title,
                        "price": price_hkd,
                        "currency": "HKD",     # Display as HKD
                        "original_price_jpy": price_jpy, # Keep original price for reference
                        "seller": item.get('shopName', 'Unknown Shop'),
                        "link": item.get('itemUrl', ''),
                        "image": item.get('mediumImageUrls', [{}])[0].get('imageUrl', '') # Get first image if available
                    })

            print(f"--- TOOL RESULT: Rakuten API found {len(filtered_items)} products ---")
            return filtered_items

        except requests.exceptions.RequestException as e:
            print(f"Error: Rakuten API connection failed: {e}")
            return []
        except ValueError as e:
            print(f"Error: JSON parsing failed: {e}")
            return []