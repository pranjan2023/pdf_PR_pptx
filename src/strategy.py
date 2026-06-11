from src.models import PresentationRequest, EvidencePack, PresentationStrategy
from src.utils import call_llm, parse_json, log

def generate_strategy(request: PresentationRequest, evidence: EvidencePack) -> PresentationStrategy:
    """
    S4: Analyzes the request and evidence to formulate a narrative strategy.
    """
    
    # Flatten evidence into a quick summary preview to save tokens
    all_chunks = evidence.sections + evidence.concepts + evidence.tables + evidence.figures
    evidence_preview = "\n".join([f"- {c.text[:150]}..." for c in all_chunks[:10]]) # Preview top 10 chunks
    
    system_prompt = (
        "You are an expert presentation strategist. "
        "Analyze the user's request and the available evidence. "
        "Define the core message, how to adapt the tone for the audience, and an outline of recommended sections. "
        "Return ONLY valid JSON matching this schema: "
        "{'core_message': 'str', 'audience_adaptation': 'str', 'recommended_sections': ['str']}"
    )
    
    user_prompt = (
        f"Topic: {request.topic}\n"
        f"Audience: {request.audience}\n"
        f"Objective: {request.objective}\n\n"
        f"Available Evidence Preview:\n{evidence_preview}"
    )
    
    response_text = call_llm(system_prompt, user_prompt)
    strategy_dict = parse_json(response_text)
    
    # Fallback if parsing fails
    if not strategy_dict:
        return PresentationStrategy(
            core_message=f"A presentation about {request.topic}",
            audience_adaptation=f"Tailored for {request.audience}",
            recommended_sections=["Introduction", "Key Findings", "Conclusion"]
        )
        
    return PresentationStrategy(**strategy_dict)


def grade_strategy(strategy: PresentationStrategy) -> tuple[str, str]:
    """
    S4c: Deterministic Strategy Critic.
    Returns (grade, reason).
    """
    if not strategy.core_message.strip():
        return "retry", "Core message is empty."
        
    if len(strategy.recommended_sections) < 3:
        return "retry", "Too few sections recommended (need at least 3 for a standard narrative flow)."
        
    return "good", ""