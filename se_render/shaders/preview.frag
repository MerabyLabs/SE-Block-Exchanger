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
