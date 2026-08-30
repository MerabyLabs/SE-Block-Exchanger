#version 330
in vec3 v_color;
in vec3 v_normal;
in vec3 v_world;
in vec2 v_uv;
in vec3 v_params;
in vec3 v_accent;
in float v_highlight;
uniform vec3 u_light_dir;
uniform vec3 u_fill_dir;
uniform vec3 u_camera_pos;
uniform float u_explode;
out vec4 f_color;
void main() {
    vec3 n = normalize(v_normal);
    if (!gl_FrontFacing) {
        n = -n;
    }
    vec3 key = normalize(-u_light_dir);
    vec3 fill = normalize(-u_fill_dir);
    vec3 view_dir = normalize(u_camera_pos - v_world);

    float metal = clamp(v_accent.x, 0.0, 1.0);
    float rim_boost = max(v_accent.y, 0.0);
    float armor = clamp(v_accent.z, 0.0, 1.0);
    float functional = 1.0 - armor;

    float ndotl = max(dot(n, key), 0.0);
    float wrap = max(dot(n, key) * 0.45 + 0.55, 0.0);
    float key_l = mix(wrap * 0.18, ndotl, mix(0.92, 0.88, armor));
    float fill_l = max(dot(n, fill), 0.0) * mix(0.22, 0.16, armor);

    float hemi = n.y * 0.5 + 0.5;
    float ambient = mix(mix(0.16, 0.36, hemi), mix(0.30, 0.52, hemi), armor);
    float down = (1.0 - hemi) * mix(0.06, 0.08, armor);

    vec3 half_v = normalize(key + view_dir);
    float spec_pow = mix(36.0, 58.0, metal);
    float spec = pow(max(dot(n, half_v), 0.0), spec_pow) * (0.08 + mix(0.26, 0.48, metal) * v_params.z);
    float rim = pow(1.0 - max(dot(n, view_dir), 0.0), 2.6) * (0.10 + rim_boost * 0.55);
    rim += functional * u_explode * 0.22 * rim_boost;

    float edge = min(min(v_uv.x, 1.0 - v_uv.x), min(v_uv.y, 1.0 - v_uv.y));
    float width = mix(0.022, 0.070, clamp(v_params.x, 0.0, 1.0));
    float crease = smoothstep(0.0, width, edge);
    float edge_mul = mix(mix(0.70, 0.82, armor), 1.0, crease);

    float jitter = 1.0 + (v_params.y - 0.5) * mix(0.10, 0.14, armor);
    vec3 albedo = v_color * jitter;
    vec3 n_bias = mix(vec3(0.04, 0.05, 0.08), vec3(0.07, 0.10, 0.05), armor);
    albedo *= vec3(1.0) + n * n_bias;

    vec3 light_tint = mix(vec3(0.86, 0.95, 1.10), vec3(1.03, 0.99, 0.92), armor);
    float light = clamp(ambient + 0.84 * key_l + fill_l - down, 0.40, 1.28);
    vec3 lit = albedo * light * edge_mul * light_tint;
    vec3 spec_col = mix(vec3(0.72, 0.82, 0.98), vec3(1.0), armor);
    lit += spec_col * spec;
    lit += albedo * rim;
    lit = min(lit, albedo * mix(1.18, 1.28, armor) + spec_col * spec);
    // Peeled armor stays visible but slightly quiet so systems read as a skeleton.
    float faint = armor * smoothstep(0.02, 0.40, u_explode);
    vec3 gray = vec3(dot(lit, vec3(0.30, 0.54, 0.16)));
    lit = mix(lit, mix(lit, gray, 0.38), faint);
    lit *= 1.0 - faint * 0.16;
    lit = mix(lit, lit * vec3(1.12, 1.28, 1.45) + vec3(0.04, 0.10, 0.16), clamp(v_highlight, 0.0, 1.0));
    f_color = vec4(lit, 1.0);
}
