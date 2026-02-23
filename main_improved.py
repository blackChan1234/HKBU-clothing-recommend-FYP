import os
import sys
from dotenv import load_dotenv
import time
import concurrent.futures
# Load environment variables
load_dotenv()

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.helpers import AgentState
from agents.agents import (
    ManagerAgent,
    UserProfilerAgent,
    AestheticStylistAgent,
    BudgetPlannerAgent,
    ContextAdvisorAgent,
    RecommendationSynthesizerAgent
)
from langgraph.graph import StateGraph, END


def create_experts_node():
    """Create a combined experts node that runs experts in TRUE PARALLEL streams"""
    def experts_node(state: AgentState):
        print("--- Running expert team collaboration (Parallel Mode) ---")

        # Initialize agents
        stylist = AestheticStylistAgent()
        budget_planner = BudgetPlannerAgent()
        context_advisor = ContextAdvisorAgent()

        # --- 定義兩條賽道 ---

        # 賽道 1: 造型與預算 (必須按順序，因為 Budget 需要 Style 的關鍵字)
        def run_style_and_budget_stream():
            # 1. 先跑造型師
            print("   [Stream A] Stylist working...")
            style_result = stylist.process(state)
            
            # 2. 將造型結果傳給預算師
            temp_state = {**state, **style_result}
            
            # 3. 再跑預算師
            print("   [Stream A] Budget Planner searching...")
            budget_result = budget_planner.process(temp_state)
            
            # 合併這條賽道的結果
            return {**style_result, **budget_result}

        # 賽道 2: 天氣與環境 (完全獨立，可以同時跑)
        def run_context_stream():
            print("   [Stream B] Context Advisor checking weather...")
            return context_advisor.process(state)

        # --- 使用 ThreadPool 真正同時執行 ---
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # 同時發射兩條賽道
            future_sb = executor.submit(run_style_and_budget_stream)
            future_ctx = executor.submit(run_context_stream)

            # 等待兩者都完成
            style_budget_result = future_sb.result()
            context_result = future_ctx.result()

        # 合併所有結果
        print("--- Expert collaboration finished ---")
        return {
            **style_budget_result,
            **context_result,
        }

    return experts_node


def route_from_manager(state: AgentState) -> str:
    """Determine next node based on manager's state"""
    if state.get("manager_decision"):
        return "recommendation_synthesizer"
    else:
        return "experts"
    
def route_workflow(state: AgentState) -> str:
    """Decides whether to loop back or finish"""
    decision = state.get("router_decision", "FINISH")
    
    if decision == "CONTINUE":
       return "experts" # Loop back to start of expert chain
    else:
        return "synthesizer" # Go to end

def create_workflow():
    workflow = StateGraph(AgentState)

    # Initialize agents
    user_profiler = UserProfilerAgent()
    manager = ManagerAgent()
    synthesizer = RecommendationSynthesizerAgent()

    # --- Add Nodes ---
    workflow.add_node("user_profiler", user_profiler.process)
    
    # 加入並行處理的 Experts Node
    experts_node_func = create_experts_node()
    workflow.add_node("experts", experts_node_func) 
    
    workflow.add_node("manager", manager.process)
    workflow.add_node("synthesizer", synthesizer.process)

    # --- Define Edges (Correct Parallel Logic) ---
    workflow.set_entry_point("user_profiler")
    
    # 1. Profiler -> Experts (原本是 -> stylist，現在改為直接進並行節點)
    workflow.add_edge("user_profiler", "experts")
    
    # 2. Experts -> Manager (並行節點跑完後，交給經理審核)
    # (原本的中間過程 stylist->budget->context 全部由 experts 內部處理，不需在此定義 edge)
    workflow.add_edge("experts", "manager")

    # 3. Manager makes a decision (Loop back to Experts or Finish)
    workflow.add_conditional_edges(
        "manager",
        route_workflow,
        {
            "experts": "experts",          # 如果需要重試，回到 Experts
            "synthesizer": "synthesizer"   # 如果通過，進入 Synthesizer
        }
    )

    workflow.add_edge("synthesizer", END)

    return workflow.compile()


def _print_agent_output(node_name: str, output: dict):
    """Pretty print each agent's output with clear formatting"""

    # Agent name mapping for better display
    agent_labels = {
        "user_profiler": "USER PROFILER AGENT",
        "stylist": "AESTHETIC STYLIST AGENT",
        "budget_planner": "BUDGET PLANNER AGENT",
        "context_advisor": "CONTEXT ADVISOR AGENT",
        "manager": "MANAGER AGENT (Arbitrator)",
        "synthesizer": "RECOMMENDATION SYNTHESIZER"
    }

    label = agent_labels.get(node_name, node_name.upper())

    print(f"\n{'>'*3} [{label}] {'<'*3}")
    print("-" * 40)

    if not isinstance(output, dict):
        print(f"  Output: {output}")
        return

    # Special formatting for different output types
    for key, value in output.items():
        if not value:  # Skip empty values
            continue

        if key == "userProfile":
            print("  [User Profile Analysis]")
            if isinstance(value, dict):
                for k, v in value.items():
                    print(f"    - {k}: {v}")
            else:
                print(f"    {value}")

        elif key == "style_suggestion":
            print(f"  [Style Suggestion]")
            print(f"    {value[:200]}..." if len(str(value)) > 200 else f"    {value}")

        elif key == "search_query":
            print(f"  [Search Query]: {value}")

        elif key == "budget_items":
            print(f"  [Products Found]: {len(value)} items")
            for i, item in enumerate(value[:3], 1):  # Show max 3 items
                name = item.get('name', 'Unknown')[:50]
                price = item.get('price', 'N/A')
                print(f"    {i}. {name} - ${price}")
            if len(value) > 3:
                print(f"    ... and {len(value) - 3} more items")

        elif key == "context_advice":
            print(f"  [Context/Weather Advice]")
            print(f"    {value[:300]}..." if len(str(value)) > 300 else f"    {value}")

        elif key == "router_decision":
            decision_icon = "LOOP BACK" if value == "CONTINUE" else "PROCEED"
            print(f"  [Decision]: {value} -> {decision_icon}")

        elif key == "manager_decision":
            print(f"  [Manager Decision]")
            print(f"    {value}")

        elif key == "manager_feedback":
            print(f"  [Feedback to Team]: {value}")

        elif key == "retry_count":
            print(f"  [Retry Count]: {value}")

        elif key == "final_recommendation":
            print(f"  [Final Recommendation]")
            # Truncate long recommendations for console
            rec_preview = str(value)[:500]
            print(f"    {rec_preview}..." if len(str(value)) > 500 else f"    {value}")

        else:
            print(f"  [{key}]: {value}")

    print("-" * 40)


def run_recommendation_system(user_input: str, verbose: bool = True, raise_on_error: bool = False):
    """Run the clothing recommendation system"""
    if verbose:
        print("\n" + "=" * 60)
        print("    MULTI-AGENT CLOTHING RECOMMENDATION SYSTEM")
        print("=" * 60)

    start_time = time.time()
    app = create_workflow()

    initial_state = {
        "userInput": user_input,
        "userProfile": {},
        "style_suggestion": "",
        "search_query": [],
        "budget_items": [],
        "context_advice": "",
        "manager_decision": "",
        "final_recommendation": "",
        "budget_exceeded": False,
        "arbitration_needed": False,
        "retry_count": 0,
        "manager_feedback": "",
        "arbitration_result": ""
    }

    try:
        if verbose:
            print(f"\n[INPUT] User Request: {user_input}")
            print("\n" + "-" * 60)
            print("    AGENT WORKFLOW EXECUTION")
            print("-" * 60)

        # for event in app.stream(initial_state, {"recursion_limit": 50}):
        #     if not verbose:
        #         continue
        #     for node_name, output in event.items():
        #         _print_agent_output(node_name, output)

        # Get final result
        final_state = app.invoke(initial_state, {"recursion_limit": 50})
        end_time = time.time()
        duration = end_time - start_time
        if verbose:
            print("\n" + "=" * 50)
            print("Final Recommendation")
            print("=" * 50)

            if final_state.get('arbitration_needed'):
                print("Manager Arbitration Result:")
                print(final_state.get('arbitration_result', 'No arbitration result'))
                print()

            print("Personalized Recommendation:")
            print(final_state.get('final_recommendation', 'Unable to generate recommendation'))
            print("\n" + "-" * 50)
            print(f"Total Execution Time: {duration:.2f} seconds")
            print("-" * 50)
        return final_state

    except Exception as e:
        if verbose:
            print(f"System execution error: {e}")
        if raise_on_error:
            raise
        return None


def main():
    """Main function with interactive mode and example"""
    print("Welcome to Smart Clothing Recommendation System")
    print("Features: Multi-agent collaboration + Budget arbitration + School API integration")

    # Check API configuration
    hkbu_key = os.getenv("HKBU_API_KEY")
    if not hkbu_key or hkbu_key == "YOUR_SCHOOL_API_KEY_HERE":
        print("\nNote: Please set your HKBU_API_KEY in .env file")
        print("   System will use fallback API as backup")

    # Example usage
    print("\nRunning example:")
    example_input = "我週末要去香港石澳海邊參加朋友的婚禮，預算3000港幣。"

    result = run_recommendation_system(example_input)

    # Interactive mode
    print("\n" + "=" * 50)
    print("Interactive Mode (type 'quit' to exit)")
    print("=" * 50)

    while True:
        try:
            user_input = input("\nDescribe your clothing needs: ").strip()

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Thank you for using Smart Clothing Recommendation System!")
                break

            if not user_input:
                print("Please enter your requirements")
                continue

            run_recommendation_system(user_input, verbose=False)

        except KeyboardInterrupt:
            print("\nProgram interrupted. Thank you for using!")
            break
        except Exception as e:
            print(f"Processing error: {e}")


if __name__ == "__main__":
    main()