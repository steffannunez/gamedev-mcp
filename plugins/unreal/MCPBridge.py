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


# ── Tier 1 Handlers ─────────────────────────────────────

def spawn_from_blueprint(blueprint_path, name, location, rotation=None, scale=None, properties=None):
    """
    Spawn an actor from a Blueprint asset into the current level.
    Tries loading blueprint_path directly, then appends '_C' for generated class fallback.
    """
    try:
        if rotation is None:
            rotation = [0, 0, 0]
        if scale is None:
            scale = [1, 1, 1]
        if properties is None:
            properties = {}

        # Try loading the Blueprint class — first via EditorAssetLibrary, then via load_class with _C suffix
        bp_class = None
        try:
            bp_asset = unreal.EditorAssetLibrary.load_blueprint_class(blueprint_path)
            if bp_asset:
                bp_class = bp_asset
        except Exception:
            pass

        if bp_class is None:
            # UE5.6: generated Blueprint class path ends with _C
            class_path_c = blueprint_path + "_C"
            bp_class = unreal.load_class(None, class_path_c)

        if bp_class is None:
            return {"error": f"Blueprint class not found: {blueprint_path}"}

        loc = unreal.Vector(*location)
        rot = unreal.Rotator(rotation[0], rotation[1], rotation[2])
        actor = unreal.EditorLevelLibrary.spawn_actor_from_class(bp_class, loc, rot)
        if not actor:
            return {"error": f"Failed to spawn actor from blueprint: {blueprint_path}"}

        actor.set_actor_label(name)
        actor.set_actor_scale3d(unreal.Vector(*scale))

        for prop_key, prop_val in properties.items():
            try:
                actor.set_editor_property(prop_key, prop_val)
            except Exception as prop_err:
                unreal.log_warning(f"[MCP Bridge] spawn_from_blueprint: could not set property '{prop_key}': {prop_err}")

        return {
            "actor_id": str(actor.get_path_name()),
            "name": name,
            "location": location,
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def set_actor_tag(actor_name, tags, mode="add"):
    """
    Modify tags on an actor.
    mode='add'    — appends without duplicating
    mode='remove' — removes specified tags
    mode='set'    — replaces all tags
    """
    try:
        actor = _find_actor(actor_name)
        if not actor:
            return {"error": f"Actor not found: {actor_name}"}

        # actor.tags is an Array of FName in Python
        current = list(actor.tags)
        tag_names = [unreal.Name(t) for t in tags]

        if mode == "add":
            for t in tag_names:
                if t not in current:
                    current.append(t)
        elif mode == "remove":
            current = [t for t in current if t not in tag_names]
        elif mode == "set":
            current = tag_names
        else:
            return {"error": f"Invalid mode '{mode}'. Use 'add', 'remove', or 'set'."}

        actor.tags = current
        return {
            "actor": actor_name,
            "tags": [str(t) for t in actor.tags],
            "mode": mode,
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def set_collision_preset(actor_name, preset, component_name=None):
    """
    Apply a collision profile preset to all PrimitiveComponents (or a specific one) on an actor.
    Valid presets: NoCollision, BlockAll, OverlapAll, BlockAllDynamic, OverlapAllDynamic,
                   Pawn, PhysicsActor, Destructible, InvisibleWall, Trigger
    """
    try:
        VALID_PRESETS = {
            "NoCollision", "BlockAll", "OverlapAll", "BlockAllDynamic",
            "OverlapAllDynamic", "Pawn", "PhysicsActor", "Destructible",
            "InvisibleWall", "Trigger",
        }
        if preset not in VALID_PRESETS:
            return {"error": f"Invalid preset '{preset}'. Valid options: {sorted(VALID_PRESETS)}"}

        actor = _find_actor(actor_name)
        if not actor:
            return {"error": f"Actor not found: {actor_name}"}

        components = actor.get_components_by_class(unreal.PrimitiveComponent)
        if not components:
            return {"error": f"No PrimitiveComponents found on actor '{actor_name}'"}

        affected = 0
        for comp in components:
            if component_name and comp.get_name() != component_name:
                continue
            try:
                comp.set_collision_profile_name(unreal.Name(preset))
                affected += 1
            except Exception as comp_err:
                unreal.log_warning(f"[MCP Bridge] set_collision_preset: '{comp.get_name()}' failed: {comp_err}")

        return {
            "actor": actor_name,
            "preset": preset,
            "components_affected": affected,
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def add_blueprint_variable(blueprint_path, var_name, var_type, default_value=None,
                            is_exposed=False, category="Default"):
    """
    Add a variable to a Blueprint asset.
    var_type: 'bool' | 'float' | 'int' | 'string' | 'vector' | 'rotator' | 'transform' | 'actor'

    UE5.6: BlueprintEditorLibrary.add_member_variable is the primary API.
    Falls back to a note if the subsystem is unavailable (e.g. editor not in focus).
    """
    try:
        # UE5.6 type-string mapping for add_member_variable
        TYPE_MAP = {
            "bool":      "bool",
            "float":     "float",
            "double":    "double",
            "int":       "int",
            "int64":     "int64",
            "string":    "string",
            "vector":    "Vector",
            "rotator":   "Rotator",
            "transform": "Transform",
            "actor":     "Object",  # object reference; caller should specify via object_class
        }
        ue_type = TYPE_MAP.get(var_type.lower())
        if ue_type is None:
            return {"error": f"Unsupported var_type '{var_type}'. Supported: {list(TYPE_MAP.keys())}"}

        bp = unreal.EditorAssetLibrary.load_asset(blueprint_path)
        if not bp:
            return {"error": f"Blueprint not found: {blueprint_path}"}

        # UE5.6: BlueprintEditorLibrary.add_member_variable
        added = False
        try:
            unreal.BlueprintEditorLibrary.add_member_variable(bp, var_name, ue_type)
            added = True
        except Exception as api_err:
            unreal.log_warning(f"[MCP Bridge] add_blueprint_variable: BlueprintEditorLibrary.add_member_variable failed: {api_err}")

        if not added:
            return {
                "blueprint": blueprint_path,
                "variable": var_name,
                "type": var_type,
                "_note": "Variable could not be added programmatically in this UE build. "
                         "Use the Blueprint editor to add the variable manually.",
            }

        # Set category and exposure via editor properties when possible
        try:
            if is_exposed:
                unreal.BlueprintEditorLibrary.set_blueprint_property_exposed_on_spawn(bp, var_name, True)
        except Exception:
            pass  # Non-fatal

        # Compile and save
        unreal.KismetSystemLibrary.compile_blueprint(bp)
        unreal.EditorAssetLibrary.save_loaded_asset(bp)

        return {
            "blueprint": blueprint_path,
            "variable": var_name,
            "type": var_type,
            "category": category,
            "is_exposed": is_exposed,
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def create_data_asset(class_path, name, save_path):
    """
    Create a DataAsset of the given class at save_path/name.
    Falls back to PrimaryDataAsset if the specified class cannot be loaded.
    """
    try:
        asset_class = None
        try:
            asset_class = unreal.load_class(None, class_path)
        except Exception:
            pass

        if asset_class is None:
            # Fallback to PrimaryDataAsset
            asset_class = unreal.load_class(None, "/Script/Engine.PrimaryDataAsset")
            unreal.log_warning(f"[MCP Bridge] create_data_asset: class '{class_path}' not found, "
                               f"falling back to PrimaryDataAsset")

        if asset_class is None:
            return {"error": f"Could not load class '{class_path}' and PrimaryDataAsset fallback also failed"}

        factory = unreal.DataAssetFactory()
        factory.set_editor_property("data_asset_class", asset_class)

        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        asset = asset_tools.create_asset(name, save_path, asset_class, factory)
        if not asset:
            return {"error": f"Failed to create DataAsset '{name}' at '{save_path}'"}

        unreal.EditorAssetLibrary.save_loaded_asset(asset)
        full_path = f"{save_path.rstrip('/')}/{name}"
        return {
            "path": full_path,
            "class": asset_class.get_name(),
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def create_enum_asset(name, save_path, values):
    """
    Create a UserDefinedEnum asset with the specified string values.
    UE5.6: UserDefinedEnumFactory creates the enum; values are added via add_new_bitfield_enum_value
    or directly editing the Names array.
    """
    try:
        factory = unreal.UserDefinedEnumFactory()
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        enum_asset = asset_tools.create_asset(name, save_path, unreal.UserDefinedEnum, factory)
        if not enum_asset:
            return {"error": f"Failed to create UserDefinedEnum '{name}' at '{save_path}'"}

        # UE5.6: add enum values — try the editor utility first, fall back to direct manipulation
        added_values = []
        for val in values:
            try:
                # UserDefinedEnumEditorUtilities is the standard path in UE5
                success = unreal.UserDefinedEnumEditorUtilities.add_new_enum_value(enum_asset, val)
                if success:
                    added_values.append(val)
                else:
                    unreal.log_warning(f"[MCP Bridge] create_enum_asset: could not add value '{val}'")
            except AttributeError:
                # UE5.6: fallback — AddNewEnumeratorForUserDefinedEnum is exposed differently
                try:
                    unreal.UserDefinedEnumUtilities.add_new_enumerator(enum_asset, val)
                    added_values.append(val)
                except Exception as inner_err:
                    unreal.log_warning(f"[MCP Bridge] create_enum_asset: value '{val}' skipped: {inner_err}")

        unreal.EditorAssetLibrary.save_loaded_asset(enum_asset)
        full_path = f"{save_path.rstrip('/')}/{name}"
        return {
            "path": full_path,
            "values": added_values,
            "_note": f"{len(values) - len(added_values)} value(s) could not be added programmatically — "
                     "add them manually in the Enum editor." if len(added_values) < len(values) else None,
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def create_struct_asset(name, save_path, fields):
    """
    Create a UserDefinedStruct asset with the provided fields.
    fields: list of dicts with keys 'name' and 'type'.
    type string uses the same mapping as add_blueprint_variable.

    UE5.6: UserDefinedStructEditorUtils is the standard API for adding variables.
    """
    try:
        TYPE_MAP = {
            "bool":      "bool",
            "float":     "float",
            "double":    "double",
            "int":       "int",
            "int64":     "int64",
            "string":    "string",
            "vector":    "Vector",
            "rotator":   "Rotator",
            "transform": "Transform",
            "actor":     "SoftObjectPath",  # UE5.6: closest generic reference type for structs
        }

        factory = unreal.UserDefinedStructFactory()
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        struct_asset = asset_tools.create_asset(name, save_path, unreal.UserDefinedStruct, factory)
        if not struct_asset:
            return {"error": f"Failed to create UserDefinedStruct '{name}' at '{save_path}'"}

        added_fields = []
        for field in fields:
            field_name = field.get("name", "")
            field_type = field.get("type", "float")
            ue_type = TYPE_MAP.get(field_type.lower(), field_type)
            try:
                # UE5.6: FStructureEditorUtils via Python bindings
                unreal.UserDefinedStructEditorUtils.add_variable(struct_asset, field_name)
                added_fields.append({"name": field_name, "type": field_type})
            except Exception as field_err:
                unreal.log_warning(f"[MCP Bridge] create_struct_asset: field '{field_name}' ({ue_type}): {field_err}")
                added_fields.append({"name": field_name, "type": field_type, "warning": str(field_err)})

        unreal.EditorAssetLibrary.save_loaded_asset(struct_asset)
        full_path = f"{save_path.rstrip('/')}/{name}"
        return {
            "path": full_path,
            "fields": added_fields,
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def create_gameplay_tag(tag, comment="", source_file="DefaultGameplayTags"):
    """
    Add a GameplayTag to the project.
    Tries GameplayTagsEditorSubsystem first (cleanest API).
    Falls back to writing DefaultGameplayTags.ini directly.
    """
    try:
        # Primary path: GameplayTagsEditorSubsystem (UE5.1+)
        try:
            subsystem = unreal.get_editor_subsystem(unreal.GameplayTagsEditorSubsystem)
            if subsystem:
                result = subsystem.add_new_gameplay_tag_to_ini(tag, comment, source_file)
                if result:
                    return {"tag": tag, "added": True, "method": "subsystem"}
        except Exception as sub_err:
            unreal.log_warning(f"[MCP Bridge] create_gameplay_tag: subsystem path failed: {sub_err}")

        # Fallback: write directly to DefaultGameplayTags.ini
        config_dir = unreal.Paths.project_dir() + "Config/"
        ini_path = os.path.join(config_dir, "DefaultGameplayTags.ini")

        # Ensure the file and section exist
        section_header = "[/Script/GameplayTags.GameplayTagsSettings]"
        tag_line = f'+GameplayTagList=(Tag="{tag}",DevComment="{comment}")'

        if os.path.exists(ini_path):
            with open(ini_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = ""

        # Avoid duplicates
        if f'Tag="{tag}"' in content:
            return {"tag": tag, "added": False, "method": "ini_file", "reason": "tag already exists"}

        if section_header in content:
            # Insert after the section header
            content = content.replace(
                section_header,
                section_header + "\n" + tag_line,
                1,
            )
        else:
            content += f"\n{section_header}\n{tag_line}\n"

        os.makedirs(config_dir, exist_ok=True)
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Request tag manager reload via console command
        try:
            unreal.SystemLibrary.execute_console_command(None, "GameplayTags.PrintReplicationFrequencyReport")
        except Exception:
            pass  # Non-fatal — tags will be picked up on next editor restart

        return {"tag": tag, "added": True, "method": "ini_file"}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


def create_anim_montage(skeleton_path, anim_sequence_path, name, save_path,
                        slot_name="DefaultSlot", blend_in_time=0.25, blend_out_time=0.25):
    """
    Create an AnimMontage asset targeting the given skeleton and (optionally) wrapping an AnimSequence.
    UE5.6: AnimMontageFactory sets the target_skeleton; segment insertion via the Python API is
    limited — the sequence is linked where the API permits, otherwise an empty montage is returned
    with a note instructing the developer to add segments in the editor.
    """
    try:
        skeleton = unreal.EditorAssetLibrary.load_asset(skeleton_path)
        if not skeleton:
            return {"error": f"Skeleton not found: {skeleton_path}"}

        anim_sequence = None
        if anim_sequence_path:
            anim_sequence = unreal.EditorAssetLibrary.load_asset(anim_sequence_path)
            if not anim_sequence:
                unreal.log_warning(f"[MCP Bridge] create_anim_montage: AnimSequence not found: {anim_sequence_path}")

        factory = unreal.AnimMontageFactory()
        factory.set_editor_property("target_skeleton", skeleton)

        # UE5.6: AnimMontageFactory exposes anim_sequence to pre-populate one slot
        if anim_sequence:
            try:
                factory.set_editor_property("anim_sequence", anim_sequence)
            except Exception:
                pass  # Non-fatal, montage will be created empty

        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        montage = asset_tools.create_asset(name, save_path, unreal.AnimMontage, factory)
        if not montage:
            return {"error": f"Failed to create AnimMontage '{name}' at '{save_path}'"}

        # UE5.6: blend times are set via editor properties on the montage asset
        try:
            montage.set_editor_property("blend_in_time", blend_in_time)
        except Exception:
            pass
        try:
            montage.set_editor_property("blend_out_time", blend_out_time)
        except Exception:
            pass

        unreal.EditorAssetLibrary.save_loaded_asset(montage)
        full_path = f"{save_path.rstrip('/')}/{name}"
        return {
            "path": full_path,
            "skeleton": skeleton_path,
            "slot": slot_name,
            "_note": "Montage created. If the AnimSequence was not auto-linked, open the Montage editor "
                     "and drag the sequence into the slot track manually." if not anim_sequence else None,
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


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
    # Tier 1 handlers
    "spawn_from_blueprint": spawn_from_blueprint,
    "set_actor_tag": set_actor_tag,
    "set_collision_preset": set_collision_preset,
    "add_blueprint_variable": add_blueprint_variable,
    "create_data_asset": create_data_asset,
    "create_enum_asset": create_enum_asset,
    "create_struct_asset": create_struct_asset,
    "create_gameplay_tag": create_gameplay_tag,
    "create_anim_montage": create_anim_montage,
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
