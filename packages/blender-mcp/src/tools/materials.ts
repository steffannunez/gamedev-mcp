import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse } from "@gamedev-mcp/shared";

export function registerMaterialTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "bl_create_material",
    "Create a PBR material with Principled BSDF shader",
    {
      name: z.string().describe("Material name"),
      base_color: z.tuple([z.number(), z.number(), z.number()]).optional().describe("[R, G, B] 0-1 range"),
      metallic: z.number().optional().describe("Metallic value 0-1"),
      roughness: z.number().optional().describe("Roughness value 0-1"),
      albedo_texture: z.string().optional().describe("Path to albedo/base color texture"),
      normal_texture: z.string().optional().describe("Path to normal map"),
      orm_texture: z.string().optional().describe("Path to ORM (Occlusion/Roughness/Metallic) packed texture"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "create_material", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Material created: ${params.name}`);
    }
  );

  server.tool(
    "bl_assign_material",
    "Assign a material to an object",
    {
      object_name: z.string().describe("Target object"),
      material_name: z.string().describe("Material to assign"),
      slot_index: z.number().optional().describe("Material slot (default 0)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "assign_material", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Material '${params.material_name}' assigned to ${params.object_name}`);
    }
  );

  server.tool(
    "bl_bake_textures",
    "Bake textures (albedo, normal, AO) from materials/sculpt to UV map",
    {
      object_name: z.string().describe("Object to bake from"),
      bake_types: z.array(z.enum(["DIFFUSE", "NORMAL", "AO", "ROUGHNESS", "EMIT", "COMBINED"])).describe("Types to bake"),
      resolution: z.number().optional().describe("Texture resolution (default 2048)"),
      output_dir: z.string().describe("Directory to save baked textures"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "bake_textures", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Textures baked for ${params.object_name}: ${(res.data as any).files.join(", ")}`);
    }
  );
}
