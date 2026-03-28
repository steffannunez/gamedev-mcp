// ── Unreal Engine Types ─────────────────────────────────────

export type Vector3 = [number, number, number];
export type Rotator3 = [number, number, number]; // pitch, yaw, roll

export interface ActorInfo {
  name: string;
  class: string;
  path: string;
  location: Vector3;
  rotation: Rotator3;
  scale: Vector3;
  components: ComponentInfo[];
  tags: string[];
}

export interface ComponentInfo {
  name: string;
  class: string;
  properties: Record<string, unknown>;
}

export interface SceneInfo {
  level_name: string;
  actor_count: number;
  actors: ActorInfo[];
}

export interface RenderStats {
  fps: number;
  frame_time_ms: number;
  draw_calls: number;
  triangles: number;
  gpu_memory_mb: number;
  ram_usage_mb: number;
}

export interface BlueprintInfo {
  name: string;
  path: string;
  parent_class: string;
  compiled: boolean;
}

export interface AssetImportResult {
  success: boolean;
  asset_path: string;
  asset_type: string;
  warnings: string[];
}

export interface MaterialInfo {
  name: string;
  path: string;
  type: "material" | "material_instance";
  parent?: string;
  parameters: Record<string, unknown>;
}

// ── Blender Types ───────────────────────────────────────────

export type MeshPrimitive = "cube" | "sphere" | "cylinder" | "plane" | "cone" | "torus";

export interface BlenderObjectInfo {
  name: string;
  type: string;
  location: Vector3;
  rotation: Vector3;
  scale: Vector3;
  vertex_count: number;
  face_count: number;
  modifiers: string[];
  materials: string[];
}

export interface BlenderSceneInfo {
  objects: BlenderObjectInfo[];
  collections: string[];
  active_object: string | null;
}

export interface ExportResult {
  success: boolean;
  output_path: string;
  file_size_bytes: number;
}

export interface LODConfig {
  lod_level: number;
  ratio: number;
  screen_size: number;
}

export interface BlenderMaterialConfig {
  name: string;
  base_color?: Vector3;
  metallic?: number;
  roughness?: number;
  albedo_texture?: string;
  normal_texture?: string;
  orm_texture?: string;
}

// ── Bridge Communication ────────────────────────────────────

export interface BridgeRequest {
  command: string;
  params: Record<string, unknown>;
  request_id?: string;
}

export interface BridgeResponse {
  success: boolean;
  data: unknown;
  error?: string;
  request_id?: string;
}

// ── Performance Targets ─────────────────────────────────────

export const PERFORMANCE_TARGETS = {
  pc_target: {
    fps: 60,
    frame_time_ms: 16.6,
    draw_calls: 2000,
    gpu_memory_mb: 4096,
    ram_mb: 4096,
    load_time_s: 10,
  },
  pc_minimum: {
    fps: 30,
    frame_time_ms: 33,
    draw_calls: 3000,
    gpu_memory_mb: 2048,
    ram_mb: 2048,
    load_time_s: 30,
  },
} as const;

// ── Naming Conventions ──────────────────────────────────────

export const ASSET_PREFIXES = {
  static_mesh: "SM_",
  skeletal_mesh: "SK_",
  animation: "A_",
  texture: "T_",
  material: "M_",
  material_instance: "MI_",
  blueprint: "BP_",
  widget: "WBP_",
  niagara: "NS_",
  sound: "SFX_",
  data_asset: "DA_",
  gameplay_effect: "GE_",
  gameplay_ability: "GA_",
} as const;
