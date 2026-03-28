import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse, jsonResponse } from "@gamedev-mcp/shared";

export function registerModifierTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "bl_add_modifier",
    "Add a modifier to an object (Subdivision, Bevel, Boolean, Mirror, Array, Solidify, etc.)",
    {
      object_name: z.string().describe("Target object"),
      modifier_type: z.string().describe("Modifier type: SUBSURF, BEVEL, BOOLEAN, MIRROR, ARRAY, SOLIDIFY, DECIMATE, REMESH, SHRINKWRAP, SMOOTH"),
      params: z.record(z.unknown()).optional().describe("Modifier-specific parameters (e.g. levels, width, count)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "add_modifier", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Modifier ${params.modifier_type} added to ${params.object_name}`);
    }
  );

  server.tool(
    "bl_apply_modifier",
    "Apply (bake) a modifier to make its changes permanent",
    {
      object_name: z.string().describe("Target object"),
      modifier_name: z.string().describe("Name of the modifier to apply"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "apply_modifier", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Applied ${params.modifier_name} on ${params.object_name}`);
    }
  );

  server.tool(
    "bl_list_modifiers",
    "List all modifiers on an object",
    {
      object_name: z.string().describe("Target object"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "list_modifiers", params);
      if (!res.success) return errorResponse(res.error!);
      return jsonResponse(res.data);
    }
  );
}
