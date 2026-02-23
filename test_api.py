#!/usr/bin/env python3
"""Test script for HKBU API integration"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_hkbu_gemini():
    """Test HKBU Gemini API"""
    api_key = os.getenv("HKBU_API_KEY")
    base_url = os.getenv("HKBU_BASE_URL")

    if not api_key or not base_url:
        print("❌ Missing HKBU_API_KEY or HKBU_BASE_URL in .env file")
        return False

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "Content-Type": "application/json"
    }

    url = f"{base_url}/gemini-3-pro-preview"
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "Hello, say hi back in 5 words or less."
            }
        ],
        "temperature": 0.7,
        "max_tokens": 50,
        "top_p": 1,
        "stream": False
    }

    try:
        print("🧪 Testing HKBU Gemini API...")
        print(f"URL: {url}")
        print(f"Headers: {headers}")
        print(f"Payload: {payload}")

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content']
                print(f"✅ HKBU Gemini API working! Response: {content}")
                return True
            else:
                print(f"❌ Unexpected response format: {result}")
                return False
        else:
            print(f"❌ API call failed with status {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Error calling HKBU Gemini API: {e}")
        return False

def test_hkbu_chatgpt():
    """Test HKBU ChatGPT API"""
    api_key = os.getenv("HKBU_API_KEY")
    base_url = os.getenv("HKBU_BASE_URL")

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "Content-Type": "application/json"
    }

    url = f"{base_url}/deployments/gpt-5/chat/completions?api-version=2024-12-01-preview"
    payload = {
        "messages": [
            {
                "role": "user",
                "content": "Hello, say hi back in 5 words or less."
            }
        ],
        "temperature": 1,
        "max_tokens": 50,
        "top_p": 1,
        "stream": False
    }

    try:
        print("🧪 Testing HKBU ChatGPT API...")
        print(f"URL: {url}")

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content']
                print(f"✅ HKBU ChatGPT API working! Response: {content}")
                return True
            else:
                print(f"❌ Unexpected response format: {result}")
                return False
        else:
            print(f"❌ API call failed with status {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Error calling HKBU ChatGPT API: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing HKBU School API integration")
    print("=" * 50)

    gemini_ok = test_hkbu_gemini()
    print()
    chatgpt_ok = test_hkbu_chatgpt()

    print()
    print("=" * 50)
    if gemini_ok and chatgpt_ok:
        print("✅ All APIs working correctly!")
    else:
        print("❌ Some APIs failed. Check the error messages above.")