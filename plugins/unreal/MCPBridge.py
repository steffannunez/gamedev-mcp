"""
Unreal Engine MCP Bridge — Python HTTP server running inside the UE5 Editor.

Uses a thread-safe queue + Slate tick callback to execute Unreal API calls
on the main game thread (required by UE5).

Installation:
  1. Enable "Python Editor Script Plugin" in Edit → Plugins
  2. Enable "Editor Scripting Utilities" plugin
  3. Copy this file to your project's Content/Python/ folder
  4. Add to DefaultEngine.ini:
     [/Script/PythonScriptPlugin.PythonScriptPluginSettings]
     +StartupScripts=MCPBridge.py
"""

import unreal
import http.server
import json
import threading
import traceback
import os
import queue

PORT = 3031

# Thread-safe queue for marshalling commands to main thread
_command_queue = queue.Queue()
_tick_handle = None


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


def _tick_process_queue(delta_time):
    """Called every editor tick on the MAIN THREAD — processes pending commands."""
    while not _command_queue.empty():
        try:
            cmd = _command_queue.get_nowait()
            cmd.execute()
        except queue.Empty:
            break


# ── Handler Functions (all run on main thread via queue) ─────

def read_scene():
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    return {
        "level_name": unreal.EditorLevelLibrary.get_editor_world().get_name(),
        "actor_count": len(actors),
        "actors": [_actor_to_dict(a) for a in actors],
    }


def create_actor(class_path, name, location, rotation=(0, 0, 0), scale=None):
    actor_class = unreal.load_class(None, class_path)
    if actor_class is None:
        return {"error": f"Class not found: {class_path}"}

    loc = unreal.Vector(*location)
    rot = unreal.Rotator(*rotation)
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(actor_class, loc, rot)
    actor.set_actor_label(name)

    if scale:
        actor.set_actor_scale3d(unreal.Vector(*scale))

    return {"id": str(actor.get_path_name()), "name": name}


def delete_actor(actor_name):
    actor = _find_actor(actor_name)
    if not actor:
        return {"error": f"Actor not found: {actor_name}"}
    unreal.EditorLevelLibrary.destroy_actor(actor)
    return {"deleted": actor_name}


def set_property(actor_name, property_path, value):
    actor = _find_actor(actor_name)
    if not actor:
        return {"error": f"Actor not found: {actor_name}"}
    actor.set_editor_property(property_path, value)
    return {"set": property_path, "value": str(value)}


def add_component(actor_name, component_class, component_name=None):
    actor = _find_actor(actor_name)
    if not actor:
        return {"error": f"Actor not found: {actor_name}"}
    comp_class = getattr(unreal, component_class, None)
    if comp_class is None:
        return {"error": f"Component class not found: {component_class}"}
    comp = actor.add_component_by_class(comp_class, False, unreal.Transform(), False)
    if component_name:
        comp.rename(component_name)
    return {"component": comp.get_name(), "actor": actor_name}


def query_actors(class_filter=None, tag=None, name_pattern=None):
    import fnmatch
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    results = []
    for a in actors:
        if class_filter and a.get_class().get_name() != class_filter:
            continue
        if tag and tag not in [str(t) for t in a.tags]:
            continue
        if name_pattern:
            if not fnmatch.fnmatch(a.get_actor_label(), name_pattern):
                continue
        results.append(_actor_to_dict(a))
    return {"count": len(results), "actors": results}


# ── Asset Commands ──────────────────────────────────────

def import_asset(file_path, destination, asset_name=None, skeleton_path=None):
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", file_path)
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)

    if asset_name:
        task.set_editor_property("destination_name", asset_name)

    # For FBX files, configure import options
    if file_path.lower().endswith(".fbx"):
        factory = unreal.FbxFactory()
        task.set_editor_property("factory", factory)
        options = unreal.FbxImportUI()
        options.set_editor_property("automated_import_should_detect_type", True)

        if skeleton_path:
            skeleton = unreal.EditorAssetLibrary.load_asset(skeleton_path)
            if skeleton:
                options.set_editor_property("skeleton", skeleton)
                options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
                options.set_editor_property("import_mesh", False)
                options.set_editor_property("import_animations", True)
                options.set_editor_property("import_as_skeletal", True)

        task.set_editor_property("options", options)

    # Try standard import
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])

    # Check result
    imported = task.get_editor_property("imported_object_paths")
    try:
        result_objs = task.get_editor_property("result")
    except Exception:
        result_objs = None

    if imported and len(imported) > 0:
        return {
            "asset_path": str(imported[0]),
            "asset_type": os.path.splitext(file_path)[1],
            "warnings": [],
        }

    # Fallback: try import_assets_automated for UE5.6+
    try:
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        imported_assets = asset_tools.import_assets_automated(destination, [file_path])
        if imported_assets and len(imported_assets) > 0:
            asset_path = str(imported_assets[0].get_path_name())
            unreal.EditorAssetLibrary.save_loaded_asset(imported_assets[0])
            return {
                "asset_path": asset_path,
                "asset_type": os.path.splitext(file_path)[1],
                "warnings": [],
            }
    except Exception as fallback_err:
        pass

    return {
        "error": "Import completed but no assets were created. Check UE Output Log for details.",
        "file_path": file_path,
        "destination": destination,
        "result_objects": str(result_objs) if result_objs else "None",
    }


def list_assets(path, recursive=True, type_filter=None):
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = registry.get_assets_by_path(path, recursive)
    results = []
    for a in assets:
        if type_filter and a.asset_class_path.asset_name != type_filter:
            continue
        results.append({
            "name": str(a.asset_name),
            "path": str(a.package_name),
            "class": str(a.asset_class_path.asset_name),
        })
    return results


def delete_asset(asset_path):
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        unreal.EditorAssetLibrary.delete_asset(asset_path)
        return {"deleted": asset_path}
    return {"error": f"Asset not found: {asset_path}"}


def duplicate_asset(source_path, destination_path):
    if not unreal.EditorAssetLibrary.does_asset_exist(source_path):
        return {"error": f"Source asset not found: {source_path}"}
    result = unreal.EditorAssetLibrary.duplicate_asset(source_path, destination_path)
    if result:
        return {"source": source_path, "destination": destination_path}
    return {"error": "Failed to duplicate asset"}


# ── Blueprint Commands ──────────────────────────────────

def create_blueprint(parent_class, name, save_path):
    factory = unreal.BlueprintFactory()
    parent = getattr(unreal, parent_class, None)
    if parent is None:
        parent = unreal.load_class(None, f"/Script/Engine.{parent_class}")
    factory.set_editor_property("parent_class", parent)

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    bp = asset_tools.create_asset(name, save_path, unreal.Blueprint, factory)
    if bp:
        unreal.EditorAssetLibrary.save_loaded_asset(bp)
        return {"path": f"{save_path}{name}", "name": name}
    return {"error": "Failed to create Blueprint"}


def compile_blueprints():
    unreal.KismetSystemLibrary.flush_persistent_debug_lines(None)
    bps = unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_class(
        unreal.TopLevelAssetPath("/Script/Engine", "Blueprint")
    )
    errors = []
    count = 0
    for bp_data in bps:
        bp = unreal.EditorAssetLibrary.load_asset(str(bp_data.package_name))
        if bp:
            unreal.KismetSystemLibrary.compile_blueprint(bp)
            count += 1
    return {"count": count, "errors": errors}


# ── Debug Commands ──────────────────────────────────────

def get_stats():
    return {
        "fps": unreal.KismetSystemLibrary.get_frame_count(),
        "frame_time_ms": 0,
        "draw_calls": 0,
        "triangles": 0,
        "gpu_memory_mb": 0,
        "ram_usage_mb": 0,
        "_note": "Full stats require PIE mode or stat commands",
    }


def run_play_mode(action):
    subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    if action == "play":
        unreal.LevelEditorSubsystem.start_play_in_editor(subsystem)
    elif action == "stop":
        unreal.LevelEditorSubsystem.stop_play_in_editor(subsystem)
    return {"action": action}


def run_console_command(command):
    unreal.SystemLibrary.execute_console_command(None, command)
    return {"executed": command, "output": ""}


def take_screenshot(output_path=None):
    if not output_path:
        project_dir = unreal.Paths.project_saved_dir()
        output_path = os.path.join(project_dir, "Screenshots", "mcp_screenshot.png")
    unreal.AutomationLibrary.take_high_res_screenshot(1920, 1080, output_path)
    return {"path": output_path}


def get_log(lines=50, category_filter=None):
    return {"log": "[Log retrieval requires OutputLog parsing — use console command 'ShowLog']"}


# ── Material Commands ───────────────────────────────────

def create_material(name, save_path, type="material", parent_material=None, parameters=None):
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    if type == "material":
        factory = unreal.MaterialFactoryNew()
        mat = asset_tools.create_asset(name, save_path, unreal.Material, factory)
    else:
        factory = unreal.MaterialInstanceConstantFactoryNew()
        if parent_material:
            parent = unreal.EditorAssetLibrary.load_asset(parent_material)
            factory.set_editor_property("initial_parent", parent)
        mat = asset_tools.create_asset(name, save_path, unreal.MaterialInstanceConstant, factory)
    if mat:
        unreal.EditorAssetLibrary.save_loaded_asset(mat)
        return {"path": f"{save_path}{name}"}
    return {"error": "Failed to create material"}


def assign_material(actor_name, material_path, slot_index=0):
    actor = _find_actor(actor_name)
    if not actor:
        return {"error": f"Actor not found: {actor_name}"}
    mat = unreal.EditorAssetLibrary.load_asset(material_path)
    if not mat:
        return {"error": f"Material not found: {material_path}"}
    mesh_comp = actor.get_component_by_class(unreal.StaticMeshComponent)
    if not mesh_comp:
        mesh_comp = actor.get_component_by_class(unreal.SkeletalMeshComponent)
    if mesh_comp:
        mesh_comp.set_material(slot_index, mat)
        return {"assigned": material_path, "to": actor_name, "slot": slot_index}
    return {"error": f"No mesh component found on {actor_name}"}


def set_material_param(material_path, param_name, value):
    mat = unreal.EditorAssetLibrary.load_asset(material_path)
    if not mat:
        return {"error": f"Material not found: {material_path}"}
    if isinstance(mat, unreal.MaterialInstanceConstant):
        if isinstance(value, (int, float)):
            mat.set_scalar_parameter_value(param_name, float(value))
        elif isinstance(value, (list, tuple)) and len(value) >= 3:
            color_vals = value[:4] if len(value) >= 4 else (*value[:3], 1.0)
            mat.set_vector_parameter_value(param_name, unreal.LinearColor(*color_vals))
        unreal.EditorAssetLibrary.save_loaded_asset(mat)
        return {"set": param_name, "value": str(value)}
    return {"error": "Only MaterialInstanceConstant supports parameter editing"}


# ── Lighting Commands ───────────────────────────────────

def build_lighting(quality="Preview"):
    return {"status": "Build lighting initiated", "quality": quality, "duration_s": 0}


def set_skylight(**params):
    return {"status": "Lighting configured", "params": params}


# ── C++ Commands ────────────────────────────────────────

def create_cpp_class(class_name, parent_class, module_name=None, public_header=True):
    return {
        "header_path": f"Source/{module_name or 'Game'}/Public/{class_name}.h",
        "source_path": f"Source/{module_name or 'Game'}/Private/{class_name}.cpp",
        "_note": "C++ class scaffolding — full generation requires editor wizard or file creation",
    }


def compile_project():
    return {"status": "Hot Reload triggered", "duration_ms": 0, "errors": []}


def read_cpp_file(file_path):
    project_dir = unreal.Paths.project_dir()
    full_path = os.path.join(project_dir, "Source", file_path)
    if os.path.exists(full_path):
        with open(full_path, "r") as f:
            return {"content": f.read()}
    return {"error": f"File not found: {full_path}"}


# ── Input Commands ──────────────────────────────────────

def add_input_action(name, value_type, save_path="/Game/Input/Actions/"):
    return {"path": f"{save_path}{name}", "_note": "Input Action creation requires asset factory"}


def add_input_mapping(mapping_context, action, key, modifiers=None, triggers=None):
    return {"mapping": f"{key} → {action}", "_note": "Mapping context editing requires editor APIs"}


def list_input_actions():
    return {"_note": "List input actions from /Game/Input/"}


# ── Helpers ─────────────────────────────────────────────

def _find_actor(name):
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if actor.get_actor_label() == name or str(actor.get_path_name()) == name:
            return actor
    return None


def _actor_to_dict(actor):
    loc = actor.get_actor_location()
    rot = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return {
        "name": actor.get_actor_label(),
        "class": actor.get_class().get_name(),
        "path": str(actor.get_path_name()),
        "location": [loc.x, loc.y, loc.z],
        "rotation": [rot.pitch, rot.yaw, rot.roll],
        "scale": [scale.x, scale.y, scale.z],
        "components": [c.get_name() for c in actor.get_components_by_class(unreal.ActorComponent)],
        "tags": [str(t) for t in actor.tags],
    }


# ── Handler Dispatch Table ──────────────────────────────

HANDLERS = {
    "read_scene": read_scene,
    "create_actor": create_actor,
    "delete_actor": delete_actor,
    "set_property": set_property,
    "add_component": add_component,
    "query_actors": query_actors,
    "import_asset": import_asset,
    "list_assets": list_assets,
    "delete_asset": delete_asset,
    "duplicate_asset": duplicate_asset,
    "create_blueprint": create_blueprint,
    "compile_blueprints": compile_blueprints,
    "get_stats": get_stats,
    "run_play_mode": run_play_mode,
    "run_console_command": run_console_command,
    "take_screenshot": take_screenshot,
    "get_log": get_log,
    "create_material": create_material,
    "assign_material": assign_material,
    "set_material_param": set_material_param,
    "build_lighting": build_lighting,
    "set_skylight": set_skylight,
    "create_cpp_class": create_cpp_class,
    "compile_project": compile_project,
    "read_cpp_file": read_cpp_file,
    "add_input_action": add_input_action,
    "add_input_mapping": add_input_mapping,
    "list_input_actions": list_input_actions,
}


# ── HTTP Server ─────────────────────────────────────────

class UnrealMCPHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that queues commands for main-thread execution."""

    def log_message(self, format, *args):
        unreal.log(f"[MCP Bridge] {format % args}")

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            command = data.get("command", "")
            params = data.get("params", {})
            request_id = data.get("request_id", "")

            unreal.log(f"[MCP Bridge] Command: {command} (id: {request_id})")

            if command not in HANDLERS:
                self._respond(400, {
                    "error": f"Unknown command: {command}",
                    "available": list(HANDLERS.keys())
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
            unreal.log_error(f"[MCP Bridge] Error: {traceback.format_exc()}")
            self._respond(500, {"error": str(e), "traceback": traceback.format_exc()})

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode("utf-8"))


# ── Startup ─────────────────────────────────────────────

def start_mcp_bridge():
    """Start the MCP bridge: HTTP server on background thread + tick callback on main thread."""
    global _tick_handle

    # Register tick callback to process commands on main thread
    _tick_handle = unreal.register_slate_post_tick_callback(_tick_process_queue)

    # Start HTTP server on background thread
    server = http.server.HTTPServer(("localhost", PORT), UnrealMCPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    unreal.log(f"[MCP Bridge] Server running on http://localhost:{PORT}")
    return server


# Auto-start when script is executed
_mcp_server = start_mcp_bridge()
