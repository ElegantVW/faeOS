#version 330
in vec2 texcoord;

uniform sampler2D tex;
uniform float opacity;
uniform float time;

vec4 default_post_processing(vec4 c);

vec4 window_shader() {
    vec2 texsize = textureSize(tex, 0);
    vec2 uv = texcoord / texsize;
    vec2 center = uv - 0.5;
    float d2 = dot(center, center);

    /* barrel distortion (screen curvature) */
    vec2 curv = center * (1.0 + 0.22 * d2) + 0.5;

    /* outside the curved screen: black bezel, keep post-processing for corners */
    if (curv.x < 0.0 || curv.x > 1.0 || curv.y < 0.0 || curv.y > 1.0) {
        return default_post_processing(vec4(0.0, 0.0, 0.0, 1.0));
    }

    vec4 c = texture2D(tex, curv, 0);

    /* scanlines, 3px period */
    float row = curv.y * texsize.y;
    float scan = 1.0 - 0.38 * smoothstep(0.3, 0.7, abs(mod(row, 3.0) - 1.5));

    /* aperture grille */
    float col = curv.x * texsize.x;
    float grille = 1.0 - 0.14 * smoothstep(0.55, 1.0, abs(mod(col, 3.0) - 1.5));

    /* vignette */
    float vig = 1.0 - 0.5 * clamp(d2 * 3.5, 0.0, 1.0);

    /* phosphor glow: pink bloom on bright pixels */
    float lum = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    c.rgb += vec3(1.0, 0.55, 0.75) * lum * 0.18;

    /* subtle screen flicker ~2Hz */
    float flick = 1.0 + 0.015 * sin(time * 0.003);

    c.rgb *= scan * grille * vig * flick;
    return default_post_processing(c);
}
