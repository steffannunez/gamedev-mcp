import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse, jsonResponse } from "@gamedev-mcp/shared";

export function registerRigTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "bl_rig_character",
    "Set up a character rig using Rigify or basic armature",
    {
      object_name: z.string().describe("Character mesh object name"),
      rig_type: z.enum(["rigify_human", "rigify_quadruped", "basic_biped", "basic_armature"]).describe("Rig preset to use"),
      auto_weights: z.boolean().optional().describe("Automatically assign vertex weights (default true)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "rig_character", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Rig applied to ${params.object_name} using ${params.rig_type}`);
    }
  );

  server.tool(
    "bl_add_animation",
    "Create a new animation action or keyframe on the active armature",
    {
      armature_name: z.string().describe("Target armature"),
      action_name: z.string().describe("Animation action name"),
      frame_start: z.number().optional().describe("Start frame (default 1)"),
      frame_end: z.number().optional().describe("End frame (default 60)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "add_animation", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Animation '${params.action_name}' created on ${params.armature_name}`);
    }
  );

  server.tool(
    "bl_set_bone_transform",
    "Set position/rotation for a bone at a specific keyframe",
    {
      armature_name: z.string().describe("Target armature"),
      bone_name: z.string().describe("Bone name"),
      frame: z.number().describe("Frame number to keyframe"),
      location: z.tuple([z.number(), z.number(), z.number()]).optional(),
      rotation: z.tuple([z.number(), z.number(), z.number()]).optional().describe("Euler rotation in degrees"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "set_bone_transform", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Keyframe set: ${params.bone_name} @ frame ${params.frame}`);
    }
  );
}
