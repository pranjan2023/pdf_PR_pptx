from langgraph.graph import StateGraph, END
from src.models import AgentState
from src.query_compiler import compile_query
from src.retrieval import retrieve
from src.planner import generate_slide_plan
from src.content import generate_content
from src.visual import plan_visuals      
from src.layout import plan_layout
from src.compression import compress_content
from src.style import resolve_style
from src.renderer import render_pptx
from src.utils import log, CONFIG
from src.strategy import generate_strategy, grade_strategy

# ── Node functions ────────────────────────────────────────────────────

def node_compile_query(state: AgentState) -> AgentState:
    log("agent", "S0 — compiling query")
    request = compile_query(state["raw_query"])
    return {**state, "request": request}


def node_retrieve(state: AgentState) -> AgentState:
    log("agent", "S3c — retrieving evidence")
    evidence = retrieve(
        state["request"].topic,
        top_k=CONFIG["retrieval"]["top_k"],
        doc_id=state["doc_id"],
    )
    total = sum([
        len(evidence.sections),
        len(evidence.concepts),
        len(evidence.tables),
        len(evidence.figures),
    ])
    log("agent", f"Retrieved {total} chunks")
    return {**state, "evidence": evidence}


def node_strategize(state: AgentState) -> AgentState:
    """S4 - Narrative Strategy Generation"""
    attempts = state.get("strategy_attempts", 0) + 1
    log("agent", f"S4 — generating presentation strategy (attempt {attempts})")
    strategy = generate_strategy(state["request"], state["evidence"])
    return {**state, "strategy": strategy, "strategy_attempts": attempts}


def node_grade_strategy(state: AgentState) -> AgentState:
    """S4c - Strategy Critic"""
    log("agent", "S4c — grading strategy")
    grade, reason = grade_strategy(state["strategy"])
    if grade == "good":
        log("agent", "Grade: good — Strategy looks solid")
    else:
        log("agent", f"Grade: retry — {reason}") 
    return {**state, "strategy_grade": grade, "strategy_reason": reason}


def node_plan(state: AgentState) -> AgentState:
    attempts = state.get("plan_attempts", 0) + 1
    log("agent", f"S5 — generating slide plan (attempt {attempts})")
    plan = generate_slide_plan(state["request"], state["evidence"])
    return {**state, "plan": plan, "plan_attempts": attempts}


def node_grade_plan(state: AgentState) -> AgentState:
    """
    S5c — deterministic plan critic.
    Checks: slide count, non-empty purposes, attempts cap.
    """
    log("agent", "S5c — grading plan")
    plan    = state["plan"]
    request = state["request"]

    if plan.total == 0:
        log("agent", "Grade: retry — empty plan")
        return {**state, "plan_grade": "retry", "plan_reason": "empty plan"}

    if abs(plan.total - request.slide_count) > 1:
        reason = f"got {plan.total} slides, expected {request.slide_count}"
        log("agent", f"Grade: retry — {reason}")
        return {**state, "plan_grade": "retry", "plan_reason": reason}

    empty_purposes = [s.slide_id for s in plan.slides if not s.purpose.strip()]
    if empty_purposes:
        reason = f"slides {empty_purposes} have empty purpose"
        log("agent", f"Grade: retry — {reason}")
        return {**state, "plan_grade": "retry", "plan_reason": reason}

    purposes = [s.purpose for s in plan.slides]
    if len(purposes) != len(set(purposes)):
        log("agent", "Grade: retry — duplicate slide purposes")
        return {**state, "plan_grade": "retry", "plan_reason": "duplicate purposes"}

    log("agent", f"Grade: good — {plan.total} slides, all valid")
    return {**state, "plan_grade": "good", "plan_reason": ""}

def node_generate_content(state: AgentState) -> AgentState:
    log("agent", "S6 — generating slide content")
    slides = generate_content(
        state["plan"],
        state["evidence"],
        audience=state["request"].audience,
    )
    return {**state, "slides": slides}

def node_visual_plan(state: AgentState) -> AgentState:
    slides_with_visuals = plan_visuals(state["slides"])
    return {**state, "slides": slides_with_visuals}

def node_layout_plan(state: AgentState) -> AgentState:
    log("agent", "S10 — planning layout coordinates")
    slides_with_layout = plan_layout(state["slides"])
    return {**state, "slides": slides_with_layout}

def node_resolve_style(state: AgentState) -> AgentState:
    log("agent", "S9 — resolving style")
    style = resolve_style(state["request"].style_desc)
    return {**state, "style": style}

def node_compress(state: AgentState) -> AgentState:
    log("agent", "S7 — compressing content")
    compressed_slides = compress_content(state["slides"])
    return {**state, "slides": compressed_slides}

def node_render(state: AgentState) -> AgentState:
    log("agent", "S11 — rendering PPTX")
    output_path = render_pptx(
        state["slides"],
        state["style"],
        output_path=CONFIG["output"]["path"],
    )
    return {**state, "output_path": output_path}


# ── Conditional edges ─────────────────────────────────────────────────

def route_after_strategy(state: AgentState) -> str:
    # Use config default, fallback to 2
    max_attempts = CONFIG.get("agent", {}).get("max_strategy_retries", 2)

    if state["strategy_grade"] == "good":
        return "plan"

    if state["strategy_attempts"] >= max_attempts:
        log("agent", f"Max strategy attempts ({max_attempts}) reached — proceeding to plan")
        return "plan"

    log("agent", f"Retrying strategy — reason: {state['strategy_reason']}")
    return "strategize"


def route_after_plan(state: AgentState) -> str:
    # Use config default, fallback to 3
    max_attempts = CONFIG.get("agent", {}).get("max_plan_retries", 3)

    if state["plan_grade"] == "good":
        return "generate_content"

    if state["plan_attempts"] >= max_attempts:
        log("agent", f"Max plan attempts ({max_attempts}) reached — proceeding with best plan")
        return "generate_content"

    log("agent", f"Retrying plan — reason: {state['plan_reason']}")
    return "plan"


# ── Build graph ───────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("compile_query",      node_compile_query)
    graph.add_node("retrieve",           node_retrieve)
    graph.add_node("strategize",         node_strategize)       # S4
    graph.add_node("grade_strategy",     node_grade_strategy)   # S4c
    graph.add_node("plan",               node_plan)             # S5
    graph.add_node("grade_plan",         node_grade_plan)       # S5c
    graph.add_node("generate_content",   node_generate_content) # S6
    graph.add_node("compress",           node_compress)         # S7
    graph.add_node("visual_plan",        node_visual_plan)      # S8
    graph.add_node("layout_plan",        node_layout_plan)      # S10
    graph.add_node("resolve_style",      node_resolve_style)    # S9
    graph.add_node("render",             node_render)           # S11

    graph.set_entry_point("compile_query")

    graph.add_edge("compile_query","retrieve")
    graph.add_edge("retrieve","strategize")
    graph.add_edge("strategize","grade_strategy")
    
    # Conditional route for Strategy
    graph.add_conditional_edges(
        "grade_strategy",
        route_after_strategy,
        {
            "plan": "plan",
            "strategize": "strategize",
        }
    )

    graph.add_edge("plan","grade_plan")
    # Conditional route for Plan
    graph.add_conditional_edges(
        "grade_plan",
        route_after_plan,
        {
            "generate_content": "generate_content",
            "plan": "plan",
        }
    )

    graph.add_edge("generate_content", "compress")              
    graph.add_edge("compress",         "visual_plan")
    graph.add_edge("visual_plan",      "layout_plan")
    graph.add_edge("layout_plan",      "resolve_style")
    graph.add_edge("resolve_style",    "render")
    graph.add_edge("render",           END)

    return graph.compile()


# ── Entry point ───────────────────────────────────────────────────────

def run_agent(raw_query: str, doc_id: str) -> str:
    graph = build_graph()

    initial_state: AgentState = {
        "raw_query":   raw_query,
        "doc_id":      doc_id,
        "request":     None,
        "evidence":    None,
        
        "strategy":          None,
        "strategy_grade":    "",
        "strategy_reason":   "",
        "strategy_attempts": 0,
        
        "plan":          None,
        "plan_grade":    "",
        "plan_reason":   "",
        "plan_attempts": 0,
        
        "slides":      None,
        "style":       None,
        "output_path": "",
    }

    print("[agent] Graph built, invoking dual-loop pipeline...")

    try:
        final_state = graph.invoke(initial_state)
        print(f"\n[agent] Pipeline complete. Output saved to: {final_state.get('output_path')}")
        return final_state["output_path"]
    except Exception as e:
        import traceback
        print(f"[agent] CRITICAL EXCEPTION: {e}")
        traceback.print_exc()
        return ""