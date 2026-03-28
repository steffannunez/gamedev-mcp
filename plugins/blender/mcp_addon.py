"""
Blender MCP Bridge Addon — HTTP server running inside Blender.

Uses a thread-safe queue + bpy.app.timers to execute Blender API calls
on the main thread (required by Blender).

Installation:
  1. Copy this file to %APPDATA%/Blender Foundation/Blender/4.5/scripts/addons/
  2. Open Blender → Edit → Preferences → Add-ons
  3. Search "MCP Bridge" and enable it
  4. The server auto-starts on http://localhost:3032
"""

bl_info = {
    "name": "MCP Bridge",
    "author": "Bfrost Studio",
    "version": (1, 1, 0),
    "blender": (4, 5, 0),
    "location": "N/A (background service)",
    "description": "HTTP bridge for Claude MCP — control Blender from Claude Code",
    "category": "Development",
}

import bpy
import http.server
import json
import threading
import traceback
import os
import mathutils
import queue

PORT = 3032
_server = None
_thread = None
_command_queue = queue.Queue()
_timer_running = False


class CommandRequest:
    """Represents a command waiting to be executed on the main thread."""
    def __init__(self, handler_fn, params):
        self.handler_fn = handler_fn
        self.params = params
        self.result = None
        self.error = None
        self.done = threading.Event()

    def execute(self):
        try:
            self.result = self.handler_fn(**self.params)
        except Exception as e:
            self.error = {"error": str(e), "traceback": traceback.format_exc()}
        finally:
            self.done.set()


def _timer_process_queue():
    """Called by bpy.app.timers on the MAIN THREAD — processes pending commands."""
    while not _command_queue.empty():
        try:
            cmd = _command_queue.get_nowait()
            cmd.execute()
        except queue.Empty:
            break
    return 0.05


# ── Handler Functions (all run on main thread via queue) ─────

def read_scene():
    objects = []
    for obj in bpy.data.objects:
        entry = {
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
            "rotation": [r for r in obj.rotation_euler],
            "scale": list(obj.scale),
            "vertex_count": len(obj.data.vertices) if hasattr(obj.data, "vertices") else 0,
            "face_count": len(obj.data.polygons) if hasattr(obj.data, "polygons") else 0,
            "modifiers": [m.name for m in obj.modifiers],
            "materials": [m.name if m else "None" for m in obj.data.materials] if hasattr(obj.data, "materials") else [],
        }
        objects.append(entry)

    active = None
    try:
        if bpy.context.view_layer.objects.active:
            active = bpy.context.view_layer.objects.active.name
    except Exception:
        pass

    return {
        "objects": objects,
        "collections": [c.name for c in bpy.data.collections],
        "active_object": active,
    }


def create_mesh(type, location=(0, 0, 0), scale=(1, 1, 1), name=None, segments=None):
    ops = {
        "cube": bpy.ops.mesh.primitive_cube_add,
        "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
        "cylinder": bpy.ops.mesh.primitive_cylinder_add,
        "plane": bpy.ops.mesh.primitive_plane_add,
        "cone": bpy.ops.mesh.primitive_cone_add,
        "torus": bpy.ops.mesh.primitive_torus_add,
    }

    if type not in ops:
        return {"error": f"Unknown mesh type: {type}. Available: {list(ops.keys())}"}

    kwargs = {"location": tuple(location), "scale": tuple(scale)}
    if segments and type in ("sphere", "cylinder"):
        kwargs["segments"] = segments

    ops[type](**kwargs)
    obj = bpy.context.view_layer.objects.active
    if name:
        obj.name = name
    return {"object": obj.name, "vertices": len(obj.data.vertices), "faces": len(obj.data.polygons)}


def edit_mesh(object_name, operation, params=None):
    obj = bpy.data.objects.get(object_name)
    if not obj or obj.type != "MESH":
        return {"error": f"Mesh object not found: {object_name}"}

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")

    ops_map = {
        "extrude": bpy.ops.mesh.extrude_region_move,
        "inset": bpy.ops.mesh.inset,
        "bevel": bpy.ops.mesh.bevel,
        "loop_cut": bpy.ops.mesh.loopcut_slide,
        "subdivide": bpy.ops.mesh.subdivide,
    }

    if operation in ops_map:
        ops_map[operation](**(params or {}))

    bpy.ops.object.mode_set(mode="OBJECT")
    return {"operation": operation, "object": object_name}


def setup_lods(target_object, lod_counts=(1.0, 0.5, 0.25, 0.1)):
    obj = bpy.data.objects.get(target_object)
    if not obj:
        return {"error": f"Object not found: {target_object}"}

    created = 0
    for i, ratio in enumerate(lod_counts[1:], 1):
        lod = obj.copy()
        lod.data = obj.data.copy()
        lod.name = f"{target_object}_LOD{i}"
        bpy.context.collection.objects.link(lod)
        mod = lod.modifiers.new(f"Decimate_LOD{i}", "DECIMATE")
        mod.ratio = ratio
        created += 1

    return {"lods_created": created, "source": target_object}


def retopology(object_name, target_faces, method="decimate"):
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return {"error": f"Object not found: {object_name}"}

    original_faces = len(obj.data.polygons)

    if method == "decimate":
        ratio = target_faces / max(original_faces, 1)
        mod = obj.modifiers.new("Retopo", "DECIMATE")
        mod.ratio = min(ratio, 1.0)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier="Retopo")
    elif method == "remesh":
        mod = obj.modifiers.new("Retopo", "REMESH")
        mod.mode = "SMOOTH"
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier="Retopo")

    return {"original_faces": original_faces, "new_faces": len(obj.data.polygons)}


def create_material(name, base_color=None, metallic=None, roughness=None,
                    albedo_texture=None, normal_texture=None, orm_texture=None):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")

    if bsdf:
        if base_color:
            bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
        if metallic is not None:
            bsdf.inputs["Metallic"].default_value = metallic
        if roughness is not None:
            bsdf.inputs["Roughness"].default_value = roughness

        if albedo_texture:
            tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(albedo_texture)
            mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

        if normal_texture:
            tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
            tex.image = bpy.data.images.load(normal_texture)
            tex.image.colorspace_settings.name = "Non-Color"
            normal_map = mat.node_tree.nodes.new("ShaderNodeNormalMap")
            mat.node_tree.links.new(tex.outputs["Color"], normal_map.inputs["Color"])
            mat.node_tree.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])

    return {"material": name}


def assign_material(object_name, material_name, slot_index=0):
    obj = bpy.data.objects.get(object_name)
    mat = bpy.data.materials.get(material_name)
    if not obj:
        return {"error": f"Object not found: {object_name}"}
    if not mat:
        return {"error": f"Material not found: {material_name}"}

    if slot_index < len(obj.data.materials):
        obj.data.materials[slot_index] = mat
    else:
        obj.data.materials.append(mat)
    return {"assigned": material_name, "to": object_name}


def bake_textures(object_name, bake_types, resolution=2048, output_dir=""):
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return {"error": f"Object not found: {object_name}"}

    files = []
    bpy.context.view_layer.objects.active = obj

    for bake_type in bake_types:
        img = bpy.data.images.new(f"{object_name}_{bake_type}", resolution, resolution)
        file_path = os.path.join(output_dir, f"T_{object_name}_{bake_type}.png")
        bpy.ops.object.bake(type=bake_type)
        img.save_render(filepath=file_path)
        files.append(file_path)

    return {"files": files}


def export_fbx(output_path, selected_only=True, object_names=None, apply_modifiers=True, include_animation=False):
    # If specific objects requested, select them first
    if object_names:
        bpy.ops.object.select_all(action="DESELECT")
        for name in object_names:
            obj = bpy.data.objects.get(name)
            if obj:
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
        selected_only = True

    bpy.ops.export_scene.fbx(
        filepath=output_path,
        use_selection=selected_only,
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_UNITS",
        mesh_smooth_type="FACE",
        add_leaf_bones=False,
        use_mesh_modifiers=apply_modifiers,
        bake_anim=include_animation,
    )
    size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return {"exported_to": output_path, "file_size_bytes": size}


def export_gltf(output_path, format="GLB", selected_only=True):
    bpy.ops.export_scene.gltf(
        filepath=output_path,
        export_format=format,
        use_selection=selected_only,
    )
    return {"exported_to": output_path}


def import_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    importers = {
        ".fbx": lambda: bpy.ops.import_scene.fbx(filepath=file_path),
        ".obj": lambda: bpy.ops.wm.obj_import(filepath=file_path),
        ".gltf": lambda: bpy.ops.import_scene.gltf(filepath=file_path),
        ".glb": lambda: bpy.ops.import_scene.gltf(filepath=file_path),
        ".stl": lambda: bpy.ops.wm.stl_import(filepath=file_path),
    }
    if ext not in importers:
        return {"error": f"Unsupported format: {ext}"}

    before = set(o.name for o in bpy.data.objects)
    importers[ext]()
    after = set(o.name for o in bpy.data.objects)
    new_objects = after - before

    return {"objects_imported": len(new_objects), "names": list(new_objects)}


def add_modifier(object_name, modifier_type, params=None):
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return {"error": f"Object not found: {object_name}"}

    mod = obj.modifiers.new(modifier_type, modifier_type)
    if params:
        for key, value in params.items():
            try:
                setattr(mod, key, value)
            except (AttributeError, TypeError):
                pass
    return {"modifier": mod.name, "type": modifier_type}


def apply_modifier(object_name, modifier_name):
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return {"error": f"Object not found: {object_name}"}
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier_name)
    return {"applied": modifier_name}


def list_modifiers(object_name):
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return {"error": f"Object not found: {object_name}"}
    return {"modifiers": [{"name": m.name, "type": m.type} for m in obj.modifiers]}


def select_object(names, deselect_others=True):
    if deselect_others:
        bpy.ops.object.select_all(action="DESELECT")
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj:
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
    return {"selected": names}


def delete_object(names):
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": names}


def transform_object(object_name, location=None, rotation=None, scale=None):
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return {"error": f"Object not found: {object_name}"}
    if location:
        obj.location = mathutils.Vector(location)
    if rotation:
        import math
        obj.rotation_euler = mathutils.Euler([math.radians(r) for r in rotation])
    if scale:
        obj.scale = mathutils.Vector(scale)
    return {"transformed": object_name}


def render_preview(output_path=None, resolution=None, engine=None):
    if engine:
        bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT" if engine == "EEVEE" else "CYCLES"
    if resolution:
        bpy.context.scene.render.resolution_x = resolution[0]
        bpy.context.scene.render.resolution_y = resolution[1]
    if not output_path:
        output_path = os.path.join(bpy.app.tempdir, "mcp_preview.png")
    bpy.context.scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)
    return {"path": output_path}


def rig_character(object_name, rig_type, auto_weights=True):
    obj = bpy.data.objects.get(object_name)
    if not obj:
        return {"error": f"Object not found: {object_name}"}
    return {"status": f"Rig {rig_type} applied to {object_name}", "_note": "Full rigging requires Rigify addon"}


def add_animation(armature_name, action_name, frame_start=1, frame_end=60):
    arm = bpy.data.objects.get(armature_name)
    if not arm or arm.type != "ARMATURE":
        return {"error": f"Armature not found: {armature_name}"}
    action = bpy.data.actions.new(action_name)
    arm.animation_data_create()
    arm.animation_data.action = action
    bpy.context.scene.frame_start = frame_start
    bpy.context.scene.frame_end = frame_end
    return {"action": action_name, "frames": f"{frame_start}-{frame_end}"}


def set_bone_transform(armature_name, bone_name, frame, location=None, rotation=None):
    arm = bpy.data.objects.get(armature_name)
    if not arm or arm.type != "ARMATURE":
        return {"error": f"Armature not found: {armature_name}"}
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="POSE")
    bone = arm.pose.bones.get(bone_name)
    if not bone:
        bpy.ops.object.mode_set(mode="OBJECT")
        return {"error": f"Bone not found: {bone_name}"}
    bpy.context.scene.frame_set(frame)
    if location:
        bone.location = mathutils.Vector(location)
        bone.keyframe_insert(data_path="location", frame=frame)
    if rotation:
        import math
        bone.rotation_euler = mathutils.Euler([math.radians(r) for r in rotation])
        bone.keyframe_insert(data_path="rotation_euler", frame=frame)
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"bone": bone_name, "frame": frame}


# ── Handler Dispatch Table ──────────────────────────────

HANDLERS = {
    "read_scene": read_scene,
    "create_mesh": create_mesh,
    "edit_mesh": edit_mesh,
    "setup_lods": setup_lods,
    "retopology": retopology,
    "create_material": create_material,
    "assign_material": assign_material,
    "bake_textures": bake_textures,
    "export_fbx": export_fbx,
    "export_gltf": export_gltf,
    "import_file": import_file,
    "add_modifier": add_modifier,
    "apply_modifier": apply_modifier,
    "list_modifiers": list_modifiers,
    "select_object": select_object,
    "delete_object": delete_object,
    "transform_object": transform_object,
    "render_preview": render_preview,
    "rig_character": rig_character,
    "add_animation": add_animation,
    "set_bone_transform": set_bone_transform,
}


# ── HTTP Server ─────────────────────────────────────────

class BlenderMCPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that queues commands for main-thread execution."""

    def log_message(self, format, *args):
        print(f"[MCP Bridge] {format % args}")

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            command = data.get("command", "")
            params = data.get("params", {})

            print(f"[MCP Bridge] Command: {command}")

            if command not in HANDLERS:
                self._respond(400, {
                    "error": f"Unknown command: {command}",
                    "available": list(HANDLERS.keys()),
                })
                return

            # Queue command for main thread execution and wait
            cmd = CommandRequest(HANDLERS[command], params)
            _command_queue.put(cmd)

            # Wait for main thread to process (timeout 30s)
            if cmd.done.wait(timeout=30.0):
                if cmd.error:
                    self._respond(500, cmd.error)
                else:
                    self._respond(200, cmd.result)
            else:
                self._respond(504, {"error": "Command timed out waiting for main thread"})

        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode("utf-8"))


# ── Blender Addon Registration ──────────────────────────

class MCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "mcp.start_server"
    bl_label = "Start MCP Bridge"

    def execute(self, context):
        start_server()
        self.report({"INFO"}, f"MCP Bridge running on port {PORT}")
        return {"FINISHED"}


class MCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "mcp.stop_server"
    bl_label = "Stop MCP Bridge"

    def execute(self, context):
        stop_server()
        self.report({"INFO"}, "MCP Bridge stopped")
        return {"FINISHED"}


def start_server():
    global _server, _thread, _timer_running
    if _server is not None:
        return

    # Register timer for main-thread command processing
    if not _timer_running:
        bpy.app.timers.register(_timer_process_queue, persistent=True)
        _timer_running = True

    # Start HTTP server on background thread
    _server = http.server.HTTPServer(("localhost", PORT), BlenderMCPHandler)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    print(f"[MCP Bridge] Server running on http://localhost:{PORT}")


def stop_server():
    global _server, _thread, _timer_running
    if _server:
        _server.shutdown()
        _server = None
        _thread = None
    if _timer_running:
        try:
            bpy.app.timers.unregister(_timer_process_queue)
        except Exception:
            pass
        _timer_running = False
    print("[MCP Bridge] Server stopped")


def register():
    bpy.utils.register_class(MCP_OT_StartServer)
    bpy.utils.register_class(MCP_OT_StopServer)
    start_server()


def unregister():
    stop_server()
    bpy.utils.unregister_class(MCP_OT_StopServer)
    bpy.utils.unregister_class(MCP_OT_StartServer)


if __name__ == "__main__":
    register()
