import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse } from "@gamedev-mcp/shared";

export function registerLightingTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "ue_build_lighting",
    "Build lighting for the current level",
    {
      quality: z.enum(["Preview", "Medium", "High", "Production"]).optional().describe("Build quality (default Preview)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "build_lighting", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Lighting build complete (${params.quality ?? "Preview"}): ${(res.data as any).duration_s}s`);
    }
  );

  server.tool(
    "ue_set_skylight",
    "Configure the Sky Light, Directional Light, and Sky Atmosphere in the level",
    {
      directional_light_intensity: z.number().optional().describe("Sun intensity (default 10.0 lux)"),
      directional_light_rotation: z.tuple([z.number(), z.number(), z.number()]).optional().describe("[Pitch, Yaw, Roll] for sun direction"),
      skylight_intensity: z.number().optional().describe("Sky Light intensity"),
      use_atmosphere: z.boolean().optional().describe("Enable Sky Atmosphere (default true)"),
      fog_density: z.number().optional().describe("Exponential Height Fog density"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "set_skylight", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse("Sky/Lighting configuration updated");
    }
  );
}
