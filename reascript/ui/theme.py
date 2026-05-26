"""
ReaBot - ImGui Theme

Defines the visual style for the ReaBot chat window.
Applied once during context creation.
"""

import imgui


def apply_theme(ctx) -> None:
    """Apply the ReaBot dark theme to an ImGui context."""

    # --- Color palette ---
    # Background tiers
    imgui.PushStyleColor(ctx, imgui.Col_WindowBg(),         0xFF1A1A2E)  # deep navy
    imgui.PushStyleColor(ctx, imgui.Col_ChildBg(),          0xFF16213E)  # slightly lighter panel
    imgui.PushStyleColor(ctx, imgui.Col_PopupBg(),          0xFF1A1A2E)

    # Text
    imgui.PushStyleColor(ctx, imgui.Col_Text(),             0xFFE2E8F0)  # soft white
    imgui.PushStyleColor(ctx, imgui.Col_TextDisabled(),     0xFF64748B)

    # Header / Title bar
    imgui.PushStyleColor(ctx, imgui.Col_TitleBg(),          0xFF0F3460)
    imgui.PushStyleColor(ctx, imgui.Col_TitleBgActive(),    0xFF1A4A8A)
    imgui.PushStyleColor(ctx, imgui.Col_TitleBgCollapsed(), 0xFF0F3460)

    # Borders
    imgui.PushStyleColor(ctx, imgui.Col_Border(),           0xFF2D3748)
    imgui.PushStyleColor(ctx, imgui.Col_BorderShadow(),     0x00000000)

    # Buttons
    imgui.PushStyleColor(ctx, imgui.Col_Button(),           0xFF2563EB)  # blue
    imgui.PushStyleColor(ctx, imgui.Col_ButtonHovered(),    0xFF3B82F6)
    imgui.PushStyleColor(ctx, imgui.Col_ButtonActive(),     0xFF1D4ED8)

    # Input fields
    imgui.PushStyleColor(ctx, imgui.Col_FrameBg(),          0xFF1E293B)
    imgui.PushStyleColor(ctx, imgui.Col_FrameBgHovered(),   0xFF334155)
    imgui.PushStyleColor(ctx, imgui.Col_FrameBgActive(),    0xFF475569)

    # Scrollbar
    imgui.PushStyleColor(ctx, imgui.Col_ScrollbarBg(),      0xFF0F172A)
    imgui.PushStyleColor(ctx, imgui.Col_ScrollbarGrab(),    0xFF334155)
    imgui.PushStyleColor(ctx, imgui.Col_ScrollbarGrabHovered(), 0xFF475569)
    imgui.PushStyleColor(ctx, imgui.Col_ScrollbarGrabActive(),  0xFF64748B)

    # Separator
    imgui.PushStyleColor(ctx, imgui.Col_Separator(),        0xFF2D3748)

    # Checkbox / toggle
    imgui.PushStyleColor(ctx, imgui.Col_CheckMark(),        0xFF60A5FA)

    # --- Rounding and spacing ---
    imgui.PushStyleVar(ctx, imgui.StyleVar_WindowRounding(),    8.0)
    imgui.PushStyleVar(ctx, imgui.StyleVar_ChildRounding(),     6.0)
    imgui.PushStyleVar(ctx, imgui.StyleVar_FrameRounding(),     5.0)
    imgui.PushStyleVar(ctx, imgui.StyleVar_GrabRounding(),      4.0)
    imgui.PushStyleVar(ctx, imgui.StyleVar_ScrollbarRounding(), 4.0)
    imgui.PushStyleVar(ctx, imgui.StyleVar_WindowPadding(),     12.0, 12.0)
    imgui.PushStyleVar(ctx, imgui.StyleVar_FramePadding(),      8.0, 5.0)
    imgui.PushStyleVar(ctx, imgui.StyleVar_ItemSpacing(),       8.0, 6.0)
    imgui.PushStyleVar(ctx, imgui.StyleVar_ScrollbarSize(),     10.0)


# Color constants for use in the chat window directly
# (ABGR format as expected by ImGui_TextColored)
COLOR_USER_MSG   = 0xFF93C5FD   # light blue — user messages
COLOR_AI_MSG     = 0xFFE2E8F0   # soft white — AI responses
COLOR_STATUS_OK  = 0xFF4ADE80   # green — connected
COLOR_STATUS_ERR = 0xFFEF4444   # red — disconnected
COLOR_STATUS_BUSY = 0xFFFBBF24  # amber — analyzing/rendering
COLOR_MUTED      = 0xFF64748B   # grey — muted track indicator
COLOR_WARNING    = 0xFFFBBF24   # amber — warnings

# Number of PushStyleColor calls in apply_theme (must match for cleanup)
THEME_COLOR_COUNT = 23
THEME_VAR_COUNT   = 9
