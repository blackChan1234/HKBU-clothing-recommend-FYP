#!/usr/bin/env python3
"""
Test script to verify the improved image upload workflow
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main_improved import run_recommendation_system

def test_workflow():
    """Test the image workflow with sample data"""
    print("=" * 60)
    print("Testing Image Upload Workflow")
    print("=" * 60)

    # Sample test data (simulating frontend input)
    test_requirements = "我需要參加朋友的海邊婚禮，想要一套優雅但不搶新娘風頭的outfit"
    test_style = "優雅休閒"
    test_user_prompt = "希望顏色不要太亮，適合下午的戶外婚禮"

    # Create dummy image bytes (in real scenario, this comes from uploaded file)
    dummy_image_bytes = b"dummy_image_data_for_testing"

    print(f"User Requirements: {test_requirements}")
    print(f"Selected Style: {test_style}")
    print(f"User Prompt: {test_user_prompt}")
    print(f"Image Data Size: {len(dummy_image_bytes)} bytes")
    print("\n" + "-" * 60)

    try:
        # Run the recommendation system
        result = run_recommendation_system(
            user_input=test_requirements,  # Fallback for backward compatibility
            user_image_bytes=dummy_image_bytes,
            user_requirements=test_requirements,
            selected_style=test_style,
            user_prompt=test_user_prompt,
            verbose=True,
            raise_on_error=False
        )

        if result:
            print("\n" + "=" * 60)
            print("WORKFLOW TEST SUCCESSFUL")
            print("=" * 60)
            print("Agent workflow processed user image and requirements successfully!")
            print(f"Final recommendation generated: {len(result.get('final_recommendation', ''))} characters")

            # Print some key results
            print(f"\nUser Profile: {result.get('userProfile', {})}")
            print(f"Style Suggestion: {result.get('style_suggestion', 'N/A')}")
            print(f"Budget Items Found: {len(result.get('budget_items', []))}")

        else:
            print("\n" + "!" * 60)
            print("WORKFLOW TEST FAILED")
            print("!" * 60)
            print("Agent workflow returned None - check system configuration")

    except Exception as e:
        print(f"\n❌ WORKFLOW TEST ERROR: {e}")
        print("Check your API keys and system configuration")

def test_appearance_service():
    """Test the full appearance generation service"""
    print("\n" + "=" * 60)
    print("Testing Appearance Service Integration")
    print("=" * 60)

    try:
        from services.appearance_service import AppearanceGenerationService

        service = AppearanceGenerationService()

        # Test data
        test_image = b"dummy_image_bytes_for_service_test"
        test_requirements = "需要一套適合商務會議的professional outfit"
        test_style = "現代商務"
        test_prompt = "希望看起來專業但不會太嚴肅"

        print(f"Testing with requirements: {test_requirements}")

        result = service.generate(
            user_image_bytes=test_image,
            requirements=test_requirements,
            selected_style=test_style,
            user_prompt=test_prompt
        )

        print("\n✅ APPEARANCE SERVICE TEST SUCCESSFUL")
        print(f"Generated diagram: {bool(result.get('diagram', {}).get('image_data'))}")
        print(f"Generated final image: {bool(result.get('final_image', {}).get('image_data'))}")
        print(f"Agent summary: {len(str(result.get('agent_summary', {})))} chars")

    except Exception as e:
        print(f"\n❌ APPEARANCE SERVICE TEST ERROR: {e}")

if __name__ == "__main__":
    print("🚀 Starting Image Upload Workflow Tests")

    # Test 1: Basic agent workflow
    test_workflow()

    # Test 2: Full appearance service
    test_appearance_service()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)