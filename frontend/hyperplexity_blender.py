import bpy

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# World background (black)
bpy.data.worlds["World"].use_nodes = True
bg = bpy.data.worlds["World"].node_tree.nodes["Background"]
bg.inputs[0].default_value = (0, 0, 0, 1)  # pure black
bg.inputs[1].default_value = 1.0

# --- Materials ---
def make_emission(name, color, strength=20):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    for n in nodes: nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*color, 1.0)
    emit.inputs["Strength"].default_value = strength
    mat.node_tree.links.new(emit.outputs[0], out.inputs[0])
    return mat

def make_diffuse(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    for n in nodes: nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    mat.node_tree.links.new(bsdf.outputs[0], out.inputs[0])
    return mat

mat_black = make_diffuse("Black", (0,0,0))
mat_white = make_diffuse("White", (1,1,1))
mat_green_emit = make_emission("GreenEmit", (0,1,0), 40)
mat_green_base = make_diffuse("GreenBase", (0,1,0))

# --- Geometry ---
# Outer black frame
bpy.ops.mesh.primitive_cube_add(size=2.8)
outer = bpy.context.active_object
outer.data.materials.append(mat_black)

# Inner cut (boolean)
bpy.ops.mesh.primitive_cube_add(size=2.2)
inner = bpy.context.active_object
mod = outer.modifiers.new("bool", "BOOLEAN")
mod.operation = 'DIFFERENCE'
mod.object = inner
bpy.context.view_layer.objects.active = outer
bpy.ops.object.modifier_apply(modifier="bool")
bpy.data.objects.remove(inner)

# White backplate
bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, -0.05, 0))
back = bpy.context.active_object
back.data.materials.append(mat_white)

# Green emission panel
bpy.ops.mesh.primitive_plane_add(size=1.5, location=(0, 0, 0))
green_emit = bpy.context.active_object
green_emit.data.materials.append(mat_green_emit)

# Green diffuse behind
bpy.ops.mesh.primitive_plane_add(size=1.5, location=(0, -0.01, 0))
green_diff = bpy.context.active_object
green_diff.data.materials.append(mat_green_base)

# Camera
bpy.ops.object.camera_add(location=(0, -5, 0))
cam = bpy.context.active_object
cam.rotation_euler = (1.5708, 0, 0)
bpy.context.scene.camera = cam

# Render settings
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = "C:/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/frontend/frames/logo.png"
scene.render.resolution_x = 512
scene.render.resolution_y = 512
scene.render.film_transparent = False

# Render
bpy.ops.render.render(write_still=True)
print("Render complete ->", scene.render.filepath)
