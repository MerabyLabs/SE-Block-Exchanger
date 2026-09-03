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
    // Functional blocks win tiny depth ties against coplanar armor.
    gl_Position.z -= (1.0 - armor) * 0.00018 * gl_Position.w;
    gl_Position = mix(gl_Position, vec4(2.0, 2.0, 2.0, 1.0), hide);
}
