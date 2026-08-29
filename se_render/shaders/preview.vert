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
