import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse, jsonResponse } from "@gamedev-mcp/shared";

export function registerMeshTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "bl_create_mesh",
    "Create a primitive mesh (cube, sphere, cylinder, plane, cone, torus)",
    {
      type: z.enum(["cube", "sphere", "cylinder", "plane", "cone", "torus"]),
      location: z.tuple([z.number(), z.number(), z.number()]).optional().describe("[X, Y, Z] in meters"),
      scale: z.tuple([z.number(), z.number(), z.number()]).optional().describe("[X, Y, Z] scale"),
      name: z.string().optional().describe("Object name"),
      segments: z.number().optional().describe("Subdivision segments (for sphere/cylinder)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "create_mesh", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Created ${params.type}: ${(res.data as any).object}`);
    }
  );

  server.tool(
    "bl_edit_mesh",
    "Perform mesh edit operations: extrude, inset, bevel, loop cut, etc.",
    {
      object_name: z.string().describe("Target object"),
      operation: z.enum(["extrude", "inset", "bevel", "loop_cut", "subdivide", "merge", "separate"]),
      params: z.record(z.unknown()).optional().describe("Operation-specific parameters"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "edit_mesh", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Applied ${params.operation} to ${params.object_name}`);
    }
  );

  server.tool(
    "bl_setup_lods",
    "Generate LOD0-LOD3 using Decimate modifier for game-ready export",
    {
      object_name: z.string().describe("Source object (becomes LOD0)"),
      ratios: z.array(z.number()).optional().describe("Decimate ratios per LOD (default [1.0, 0.5, 0.25, 0.1])"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "setup_lods", {
        target_object: params.object_name,
        lod_counts: params.ratios ?? [1.0, 0.5, 0.25, 0.1],
      });
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`LODs created for ${params.object_name}: ${(res.data as any).lods_created} levels`);
    }
  );

  server.tool(
    "bl_retopology",
    "Run automatic retopology to reduce polygon count while preserving shape",
    {
      object_name: z.string().describe("Target high-poly object"),
      target_faces: z.number().describe("Target face count"),
      method: z.enum(["decimate", "remesh", "quadriflow"]).optional().describe("Retopo method (default decimate)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "retopology", params);
      if (!res.success) return errorResponse(res.error!);
      const data = res.data as any;
      return textResponse(`Retopo complete: ${data.original_faces} → ${data.new_faces} faces`);
    }
  );
}
