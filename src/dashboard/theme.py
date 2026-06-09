"""
Dashboard UI Theme Configuration
Centralizes color palettes and visual styles for the Streamlit executive interface.
"""

# Premium executive style palette (Minimalist & High-End)
UI_COLORS = {
    "primary": "#8B0000",        # Crimson/Wine accent representing Peru
    "secondary": "#1E293B",      # Deep Slate Blue for text hierarchy and headers
    "background_card": "#F8FAFC", # Ultra-clean light gray/blue for metric cards
    "border": "#E2E8F0",          # Soft dividers
    "success": "#10B981",         # Emerald green for healthy budget execution (>75%)
    "warning": "#F59E0B",         # Amber for warning/moderate execution (40% - 75%)
    "danger": "#EF4444",          # Light red for stagnant budget execution (<40%)
}

# Typography adjustments if needed by components
FONT_FAMILY = "'Outfit', sans-serif"
