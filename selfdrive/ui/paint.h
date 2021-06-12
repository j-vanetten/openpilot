#pragma once

#include "selfdrive/ui/ui.h"

void ui_draw(UIState *s, int w, int h);
void ui_draw_image(const UIState *s, const Rect &r, const char *name, float alpha);
void ui_draw_rect(NVGcontext *vg, const Rect &r, NVGcolor color, int width, float radius = 0);
void ui_fill_rect(NVGcontext *vg, const Rect &r, const NVGpaint &paint, float radius = 0);
void ui_fill_rect(NVGcontext *vg, const Rect &r, const NVGcolor &color, float radius = 0);
void ui_nvg_init(UIState *s);
void ui_resize(UIState *s, int width, int height);

const int v_edge_padding = 140;
const int h_edge_padding = 70;
const Rect authFollow_btn = {1920/2 - 475/2, 1080 - v_edge_padding - 130/2, 475, 130};
const Rect accEco_btn = {1920 - h_edge_padding - 350, 1080 - v_edge_padding - 130/2, 350, 130};
const Rect accEco_img = {1920 - h_edge_padding - 233, 1080 - v_edge_padding/2 - 233, 233, 233};
