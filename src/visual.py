import os
import matplotlib.pyplot as plt
from src.models import SlideContent, StyleConfig
from src.utils import log

def process_visuals(slides: list[SlideContent], style: StyleConfig, output_dir: str = "temp_assets") -> list[SlideContent]:
    """
    S11: Asset Engine. Generates transparent charts that match the theme's color palette.
    """
    log("visual", f"S11 — Processing visual assets for {len(slides)} slides")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for slide in slides:
        hint = getattr(slide, "visual_hint", "text-only")
        
        if hint == "chart":
            chart_path = os.path.join(output_dir, f"chart_slide_{slide.slide_id}.png")
            
            # --- Draw the Chart ---
            fig, ax = plt.subplots(figsize=(5, 4))
            
            # Set transparency for seamless integration
            fig.patch.set_alpha(0.0)
            ax.patch.set_alpha(0.0)
            
            # Mock data
            categories = ['Baseline', 'Standard', 'RAG']
            values = [10, 25, 68] 
            
            # Use the theme's accent color for the primary bar, neutral for others
            colors = ['#888888', '#888888', style.accent_color]
            ax.bar(categories, values, color=colors)
            
            # Style text based on theme text_color
            text_color_rgb = style.text_color
            ax.tick_params(colors=text_color_rgb, labelsize=10)
            ax.set_title("Performance Metrics", color=text_color_rgb, fontsize=12, pad=10)
            
            # Remove borders for a modern, clean look
            for spine in ax.spines.values():
                spine.set_visible(False)
                
            plt.tight_layout()
            # Save with transparent background
            plt.savefig(chart_path, dpi=150, transparent=True, edgecolor='none')
            plt.close()
            
    return slides