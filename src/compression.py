import sys
from src.models import SlideContent
from src.utils import call_llm, parse_json, log

_SYSTEM = """You are an expert editor for executive presentations.
Compress the provided text arrays into extremely concise, punchy statements.
Remove filler words. Keep items under 10 words each.
Return ONLY valid JSON matching the exact keys provided in the prompt."""

def compress_content(slides: list[SlideContent]) -> list[SlideContent]:
    """
    S7: Compression.
    Trims verbose text across ALL polymorphic layout fields.
    """
    log("compression", f"S7 — compressing {len(slides)} slides")
    
    for slide in slides:
        # Build a dynamic payload based on what text fields actually exist
        payload = {}
        if slide.bullets: payload["bullets"] = slide.bullets
        if slide.left_column: payload["left_column"] = slide.left_column
        if slide.right_column: payload["right_column"] = slide.right_column
        if slide.big_message: payload["big_message"] = slide.big_message
        
        # Skip if there's no text to compress (e.g., Title slide usually doesn't need it)
        if not payload or slide.layout_type == "Title":
            continue
            
        user_prompt = f"Layout: {slide.layout_type}\nText to compress: {payload}"
        
        raw = call_llm(_SYSTEM, user_prompt)
        compressed = parse_json(raw)
        
        # Map the compressed text back to the Pydantic object safely
        if compressed:
            if "bullets" in compressed: slide.bullets = compressed["bullets"]
            if "left_column" in compressed: slide.left_column = compressed["left_column"]
            if "right_column" in compressed: slide.right_column = compressed["right_column"]
            if "big_message" in compressed and isinstance(compressed["big_message"], str): 
                slide.big_message = compressed["big_message"]
            
    return slides

if __name__ == "__main__":
    from src.query_compiler import compile_query
    from src.retrieval import retrieve
    from src.strategy import generate_strategy
    from src.planner import generate_slide_plan
    from src.content import generate_content

    # 1. Run the standard pipeline
    req = compile_query("make a 4 slide presentation on RAG vs standard models")
    ev = retrieve(req.topic, top_k=10, doc_id="Rag")
    strat = generate_strategy(req, ev)
    plan = generate_slide_plan(req, ev, strategy=strat)
    
    print("\n" + "="*50)
    print("GENERATING ORIGINAL CONTENT...")
    print("="*50)
    original_slides = generate_content(plan, ev, audience=req.audience, strategy=strat)
    
    # Store a copy of the uncompressed text to print later
    uncompressed_data = {s.slide_id: s.model_dump() for s in original_slides}

    print("\n" + "="*50)
    print("RUNNING COMPRESSION S7...")
    print("="*50)
    compressed_slides = compress_content(original_slides)
    
    # 2. Print the Before & After Diff
    print("\n" + "="*50)
    print("COMPRESSION DIFF TEST")
    print("="*50)
    
    for s in compressed_slides:
        if s.layout_type == "Title": continue
        
        print(f"\nSlide {s.slide_id} [{s.layout_type}]")
        old = uncompressed_data[s.slide_id]
        
        if s.layout_type == "Two-Column":
            print(f"  Old Left  : {old['left_column']}")
            print(f"  New Left  : {s.left_column}")
        elif s.layout_type in ["Big-Message", "Assertion-Data"]:
            print(f"  Old Msg   : {old['big_message']}")
            print(f"  New Msg   : {s.big_message}")
        else:
            print(f"  Old Bullets: {old['bullets']}")
            print(f"  New Bullets: {s.bullets}")