import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse, jsonResponse } from "@gamedev-mcp/shared";

export function registerSceneTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "bl_read_scene",
    "Get all objects in the current Blender scene with their properties",
    {},
    async () => {
      const res = await callBridge(bridgeUrl, "read_scene");
      if (!res.success) return errorResponse(res.error!);
      return jsonResponse(res.data);
    }
  );

  server.tool(
    "bl_select_object",
    "Select one or more objects by name",
    {
      names: z.array(z.string()).describe("Object names to select"),
      deselect_others: z.boolean().optional().describe("Deselect all others first (default true)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "select_object", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Selected: ${params.names.join(", ")}`);
    }
  );

  server.tool(
    "bl_delete_object",
    "Delete objects from the scene",
    {
      names: z.array(z.string()).describe("Object names to delete"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "delete_object", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Deleted: ${params.names.join(", ")}`);
    }
  );

  server.tool(
    "bl_transform_object",
    "Move, rotate, or scale an object",
    {
      object_name: z.string().describe("Target object"),
      location: z.tuple([z.number(), z.number(), z.number()]).optional(),
      rotation: z.tuple([z.number(), z.number(), z.number()]).optional().describe("Euler degrees"),
      scale: z.tuple([z.number(), z.number(), z.number()]).optional(),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "transform_object", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Transformed ${params.object_name}`);
    }
  );

  server.tool(
    "bl_render_preview",
    "Render a preview image of the current viewport and return the file path",
    {
      output_path: z.string().optional().describe("Where to save the render"),
      resolution: z.tuple([z.number(), z.number()]).optional().describe("[width, height] in pixels (default [1280, 720])"),
      engine: z.enum(["EEVEE", "CYCLES"]).optional().describe("Render engine (default EEVEE for speed)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "render_preview", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Render saved: ${(res.data as any).path}`);
    }
  );
}
