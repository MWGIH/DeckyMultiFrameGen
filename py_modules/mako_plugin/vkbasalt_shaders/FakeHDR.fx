/**
 * HDR
 * by Christian Cann Schuldt Jensen ~ CeeJay.dk
 *
 * Not actual HDR - It just tries to mimic an HDR look (relatively high performance cost)
 */
uniform float HDRPower < ui_type = "slider";
	ui_min = 0.0; ui_max = 8.0;
	ui_label = "Power";
> = 1.30;
uniform float radius1 < ui_type = "slider";
	ui_min = 0.0; ui_max = 8.0;
	ui_label = "Radius 1";
> = 0.793;
uniform float radius2 < ui_type = "slider";
	ui_min = 0.0; ui_max = 8.0;
	ui_label = "Radius 2";
	ui_tooltip = "Raising this seems to make the effect stronger and also brighter.";
> = 0.87;

#include "ReShade.fxh"

float3 HDRRing(float2 texcoord, float radius)
{
    float2 pixel = radius * BUFFER_PIXEL_SIZE;
    float3 sum = tex2D(ReShade::BackBuffer, texcoord + float2( 1.5, -1.5) * pixel).rgb;
    sum += tex2D(ReShade::BackBuffer, texcoord + float2(-1.5, -1.5) * pixel).rgb;
    sum += tex2D(ReShade::BackBuffer, texcoord + float2( 1.5,  1.5) * pixel).rgb;
    sum += tex2D(ReShade::BackBuffer, texcoord + float2(-1.5,  1.5) * pixel).rgb;
    sum += tex2D(ReShade::BackBuffer, texcoord + float2( 0.0, -2.5) * pixel).rgb;
    sum += tex2D(ReShade::BackBuffer, texcoord + float2( 0.0,  2.5) * pixel).rgb;
    sum += tex2D(ReShade::BackBuffer, texcoord + float2(-2.5,  0.0) * pixel).rgb;
    sum += tex2D(ReShade::BackBuffer, texcoord + float2( 2.5,  0.0) * pixel).rgb;
    return sum;
}

float3 HDRPass(float4 vpos : SV_Position, float2 texcoord : TexCoord) : SV_Target
{
    float3 color = tex2D(ReShade::BackBuffer, texcoord).rgb;
    float dist = radius2 - radius1;
    float3 bloomDelta;
    if (abs(dist) <= 0.1 && (2.0 * radius2 - radius1) >= 0.0)
    {
        // First-order equivalent of 0.010 * ring(radius2) - 0.005 * ring(radius1).
        // The default radii differ by only 0.077, so one ring is sufficient.
        bloomDelta = 0.005 * HDRRing(texcoord, 2.0 * radius2 - radius1);
    }
    else
    {
        bloomDelta = 0.010 * HDRRing(texcoord, radius2)
                   - 0.005 * HDRRing(texcoord, radius1);
    }
    float3 HDR = (color + bloomDelta) * dist;
    float3 blend = HDR + color;
    color = pow(abs(blend), abs(HDRPower)) + HDR;
    return saturate(color);
}

technique HDR
{
	pass
	{
		VertexShader = PostProcessVS;
		PixelShader = HDRPass;
	}
}
