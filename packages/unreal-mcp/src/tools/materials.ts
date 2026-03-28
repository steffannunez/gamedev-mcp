import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse, jsonResponse } from "@gamedev-mcp/shared";

export function registerMaterialTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "ue_create_material",
    "Create a new Material or Material Instance",
    {
      name: z.string().describe("Material name (will add M_ or MI_ prefix)"),
      save_path: z.string().describe("Content path, e.g. /Game/Materials/"),
      type: z.enum(["material", "material_instance"]).describe("Material or Material Instance"),
      parent_material: z.string().optional().describe("Parent material path (required for instances)"),
      parameters: z.record(z.unknown()).optional().describe("Material parameters to set"),
    },
    async (params) => {
      const prefix = params.type === "material" ? "M_" : "MI_";
      const name = params.name.startsWith(prefix) ? params.name : `${prefix}${params.name}`;
      const res = await callBridge(bridgeUrl, "create_material", { ...params, name });
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Material created: ${(res.data as any).path}`);
    }
  );

  server.tool(
    "ue_set_material_param",
    "Set a parameter on a Material Instance (scalar, vector, or texture)",
    {
      material_path: z.string().describe("Path to the Material Instance"),
      param_name: z.string().describe("Parameter name"),
      param_type: z.enum(["scalar", "vector", "texture"]).describe("Parameter type"),
      value: z.unknown().describe("Parameter value: number for scalar, [R,G,B,A] for vector, texture path for texture"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "set_material_param", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Set ${params.param_name} = ${JSON.stringify(params.value)}`);
    }
  );

  server.tool(
    "ue_assign_material",
    "Assign a material to an actor's mesh component",
    {
      actor_name: z.string().describe("Target actor"),
      material_path: z.string().describe("Material or Material Instance path"),
      slot_index: z.number().optional().describe("Material slot index (default 0)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "assign_material", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Material assigned to ${params.actor_name} slot ${params.slot_index ?? 0}`);
    }
  );
}
