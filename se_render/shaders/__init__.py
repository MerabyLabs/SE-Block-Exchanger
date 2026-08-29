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


VERTEX_SHADER = _load(
    "preview.vert",
    """
#version 330
in vec3 in_position;
in vec3 in_normal;
in vec3 in_instance_color;
in mat4 in_model;
uniform mat4 u_view;
uniform mat4 u_proj;
out vec3 v_color;
out vec3 v_normal;
out vec3 v_world;
void main() {
    vec4 world = in_model * vec4(in_position, 1.0);
    v_world = world.xyz;
    v_normal = mat3(in_model) * in_normal;
    v_color = in_instance_color;
    gl_Position = u_proj * u_view * world;
}
""",
)

FRAGMENT_SHADER = _load(
    "preview.frag",
    """
#version 330
in vec3 v_color;
in vec3 v_normal;
in vec3 v_world;
uniform vec3 u_light_dir;
uniform vec3 u_camera_pos;
out vec4 f_color;
void main() {
    vec3 n = normalize(v_normal);
    vec3 l = normalize(-u_light_dir);
    float ndotl = max(dot(n, l), 0.0);
    vec3 view_dir = normalize(u_camera_pos - v_world);
    vec3 half_v = normalize(l + view_dir);
    float spec = pow(max(dot(n, half_v), 0.0), 32.0) * 0.18;
    float ambient = 0.22;
    vec3 lit = v_color * (ambient + 0.78 * ndotl) + vec3(spec);
    f_color = vec4(lit, 1.0);
}
""",
)
