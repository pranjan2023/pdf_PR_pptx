from langgraph.graph import StateGraph, END
from src.models import AgentState
from src.query_compiler import compile_query
from src.retrieval import retrieve
from src.planner import generate_slide_plan
from src.content import generate_content
from src.visual import process_visuals      # <-- UPDATED
from src.layout import plan_layout
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
    plan = generate_slide_plan(
        state["request"],
        state["evidence"],
        strategy=state.get("strategy"),   
    )
    return {**state, "plan": plan, "plan_attempts": attempts}


def node_grade_plan(state: AgentState) -> AgentState:
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

    evidence_sets = []
    for s in plan.slides[1:-1]:   # skip title and conclusion
        if s.evidence_ids:
            frozen = frozenset(s.evidence_ids)
            if frozen in evidence_sets:
                log("agent", "Grade: retry — duplicate evidence sets across slides")
                return {**state, "plan_grade": "retry",
                        "plan_reason": "duplicate evidence sets"}
            evidence_sets.append(frozen)

    log("agent", f"Grade: good — {plan.total} slides, all valid")
    return {**state, "plan_grade": "good", "plan_reason": ""}


def node_generate_content(state: AgentState) -> AgentState:
    log("agent", "S6 — generating slide content")
    slides = generate_content(
        state["plan"],
        state["evidence"],
        audience=state["request"].audience,
        strategy=state.get("strategy"),   
    )
    return {**state, "slides": slides}


def node_layout_plan(state: AgentState) -> AgentState:
    log("agent", "S10 — planning layout coordinates")
    slides_with_layout = plan_layout(state["slides"])
    return {**state, "slides": slides_with_layout}


def node_process_visuals(state: AgentState) -> AgentState:
    log("agent", "S11 — generating visual assets")
    slides_with_visuals = process_visuals(state["slides"], state["style"])
    return {**state, "slides": slides_with_visuals}


def node_resolve_style(state: AgentState) -> AgentState:
    log("agent", "S9 — resolving style")
    style = resolve_style(state["request"].style_desc)
    return {**state, "style": style}


def node_render(state: AgentState) -> AgentState:
    log("agent", "S12 — rendering PPTX")
    
    # Safely get output path from CONFIG, fallback to default
    out_path = CONFIG.get("output", {}).get("path", "final_output.pptx")
    
    output_path = render_pptx(
        state["slides"],
        state["style"],
        output_path=out_path,
    )
    return {**state, "output_path": output_path}


# ── Conditional edges ─────────────────────────────────────────────────

def route_after_strategy(state: AgentState) -> str:
    max_attempts = CONFIG.get("agent", {}).get("max_strategy_retries", 2)

    if state["strategy_grade"] == "good":
        return "plan"

    if state["strategy_attempts"] >= max_attempts:
        log("agent", f"Max strategy attempts ({max_attempts}) reached — proceeding to plan")
        return "plan"

    log("agent", f"Retrying strategy — reason: {state['strategy_reason']}")
    return "strategize"


def route_after_plan(state: AgentState) -> str:
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
    graph.add_node("strategize",         node_strategize)       
    graph.add_node("grade_strategy",     node_grade_strategy)   
    graph.add_node("plan",               node_plan)             
    graph.add_node("grade_plan",         node_grade_plan)       
    graph.add_node("generate_content",   node_generate_content) 
    graph.add_node("layout_plan",        node_layout_plan)
    graph.add_node("process_visuals",    node_process_visuals)
    graph.add_node("resolve_style",      node_resolve_style)    
    graph.add_node("render",             node_render)           

    graph.set_entry_point("compile_query")

    graph.add_edge("compile_query", "retrieve")
    graph.add_edge("retrieve", "strategize")
    graph.add_edge("strategize", "grade_strategy")
    
    graph.add_conditional_edges(
        "grade_strategy",
        route_after_strategy,
        {"plan": "plan", "strategize": "strategize"}
    )

    graph.add_edge("plan", "grade_plan")
    
    graph.add_conditional_edges(
        "grade_plan",
        route_after_plan,
        {"generate_content": "generate_content", "plan": "plan"}
    )

    # ── FIXED ORDER ───────────────────────────────────────────────────
    graph.add_edge("generate_content", "layout_plan")
    graph.add_edge("layout_plan",      "resolve_style")      # style first
    graph.add_edge("resolve_style",    "process_visuals")   # then visuals
    graph.add_edge("process_visuals",  "render")
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

if __name__ == "__main__":
    import sys
    raw_query = sys.argv[1] if len(sys.argv) > 1 else "make a 10 slide presentation"
    doc_id    = sys.argv[2] if len(sys.argv) > 2 else "Attention_is_all_you_Need"
    run_agent(raw_query, doc_id)