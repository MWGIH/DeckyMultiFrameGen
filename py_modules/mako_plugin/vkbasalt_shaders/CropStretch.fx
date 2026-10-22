/* SPDX-License-Identifier: GPL-3.0-or-later */
// Original MAKO shader. Crop the source image, then stretch it to the full output.

#include "ReShade.fxh"

uniform float CropLeft <
    ui_type = "slider"; ui_label = "Left crop (%)";
    ui_min = 0.0; ui_max = 49.0; ui_step = 0.1;
    ui_tooltip = "Remove this percentage from the left edge and stretch the remaining image to fill the screen. 0 keeps the edge unchanged.";
> = 0.0;
uniform float CropRight <
    ui_type = "slider"; ui_label = "Right crop (%)";
    ui_min = 0.0; ui_max = 49.0; ui_step = 0.1;
    ui_tooltip = "Remove this percentage from the right edge and stretch the remaining image to fill the screen. 0 keeps the edge unchanged.";
> = 0.0;
uniform float CropTop <
    ui_type = "slider"; ui_label = "Top crop (%)";
    ui_min = 0.0; ui_max = 49.0; ui_step = 0.1;
    ui_tooltip = "Remove this percentage from the top edge. Increase Top and Bottom equally to remove horizontal black bars and stretch vertically.";
> = 0.0;
uniform float CropBottom <
    ui_type = "slider"; ui_label = "Bottom crop (%)";
    ui_min = 0.0; ui_max = 49.0; ui_step = 0.1;
    ui_tooltip = "Remove this percentage from the bottom edge. Each edge is independent. Cropping also affects HUD elements and subtitles.";
> = 0.0;

sampler CropStretchSampler
{
    Texture = ReShade::BackBufferTex;
    MinFilter = LINEAR;
    MagFilter = LINEAR;
    MipFilter = POINT;
    AddressU = CLAMP;
    AddressV = CLAMP;
};

float4 CropStretchPass(float4 position : SV_Position, float2 texcoord : TexCoord) : SV_Target
{
    // Guard advanced config edits too: opposing edges must never cross or flip.
    float2 first = clamp(float2(CropLeft, CropTop), 0.0, 49.0) * 0.01;
    float2 last = 1.0 - clamp(float2(CropRight, CropBottom), 0.0, 49.0) * 0.01;
    float2 uv = lerp(first, last, texcoord);

    // Keep bilinear taps inside the cropped image, avoiding a dark border from
    // discarded letterbox pixels. Sub-pixel crops on tiny images use the centre.
    float2 middle = (first + last) * 0.5;
    float2 low = min(first + BUFFER_PIXEL_SIZE * 0.5, middle);
    float2 high = max(last - BUFFER_PIXEL_SIZE * 0.5, middle);
    return tex2D(CropStretchSampler, clamp(uv, low, high));
}

technique CropStretch
{
    pass
    {
        VertexShader = PostProcessVS;
        PixelShader = CropStretchPass;
    }
}
