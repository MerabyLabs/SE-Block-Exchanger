"""GLSL used by the Subgrids preview. On-disk copies live next to this file."""

from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name: str, fallback: str) -> str:
    path = _DIR / name
    try:
        text = path.read_text(encoding="utf-8")
        if text.strip():
            return text
    except OSError:
        pass
    return fallback


_VERTEX_FALLBACK = """
#version 330
in vec3 in_position;
in vec3 in_normal;
in vec2 in_uv;
in vec3 in_instance_color;
in vec3 in_instance_params;
in vec3 in_instance_accent;
in vec3 in_explode_peel;
in vec3 in_explode_decks;
in vec3 in_explode_radial;
in vec3 in_inspect;
in float in_instance_id;
in mat4 in_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform float u_explode;
uniform float u_selected_id;
uniform float u_pull;
uniform float u_dissect_mode;
uniform float u_hide_armor;
uniform float u_isolate_id;
uniform float u_hide_layers;
uniform float u_category_mask;
out vec3 v_color;
out vec3 v_normal;
out vec3 v_world;
out vec2 v_uv;
out vec3 v_params;
out vec3 v_accent;
out float v_highlight;
void main() {
    float armor = in_instance_accent.z;
    float isolated = step(0.0, u_isolate_id);
    float is_iso = step(abs(in_instance_id - u_isolate_id), 0.5);
    float layer = in_inspect.x;
    float cat = in_inspect.y;
    float user_hide = in_inspect.z;
    float cat_bit = mod(floor(u_category_mask / pow(2.0, cat) + 0.001), 2.0);
    float hide = isolated * (1.0 - is_iso)
        + (1.0 - isolated) * step(0.5, u_hide_armor) * step(0.5, armor)
        + (1.0 - isolated) * step(layer + 0.5, u_hide_layers)
        + (1.0 - isolated) * step(0.5, cat_bit)
        + step(0.5, user_hide);
    vec3 explode_off = in_explode_peel;
    explode_off = mix(explode_off, in_explode_decks, step(0.5, u_dissect_mode) * step(u_dissect_mode, 1.5));
    explode_off = mix(explode_off, in_explode_radial, step(1.5, u_dissect_mode));
    vec4 world = in_model * vec4(in_position, 1.0);
    float selected = step(abs(in_instance_id - u_selected_id), 0.5);
    world.xyz += explode_off * (u_explode + selected * u_pull);
    v_world = world.xyz;
    v_normal = transpose(inverse(mat3(in_model))) * in_normal;
    v_color = in_instance_color;
    v_uv = in_uv;
    v_params = in_instance_params;
    v_accent = in_instance_accent;
    v_highlight = selected;
    gl_Position = u_proj * u_view * world;
    gl_Position.z -= (1.0 - armor) * 0.00018 * gl_Position.w;
    gl_Position = mix(gl_Position, vec4(2.0, 2.0, 2.0, 1.0), hide);
}
"""

_FRAGMENT_FALLBACK = """
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
    float faint = armor * smoothstep(0.02, 0.40, u_explode);
    vec3 gray = vec3(dot(lit, vec3(0.30, 0.54, 0.16)));
    lit = mix(lit, mix(lit, gray, 0.38), faint);
    lit *= 1.0 - faint * 0.16;
    lit = mix(lit, lit * vec3(1.12, 1.28, 1.45) + vec3(0.04, 0.10, 0.16), clamp(v_highlight, 0.0, 1.0));
    f_color = vec4(lit, 1.0);
}
"""

VERTEX_SHADER = _load("preview.vert", _VERTEX_FALLBACK)
FRAGMENT_SHADER = _load("preview.frag", _FRAGMENT_FALLBACK)
