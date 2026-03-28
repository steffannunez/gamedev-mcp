import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse, jsonResponse } from "@gamedev-mcp/shared";

export function registerInputTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "ue_add_input_action",
    "Create an Input Action asset for the Enhanced Input System",
    {
      name: z.string().describe("Action name, e.g. IA_Jump, IA_Move, IA_Look"),
      value_type: z.enum(["Digital", "Axis1D", "Axis2D", "Axis3D"]).describe("Input value type"),
      save_path: z.string().optional().describe("Content path (default /Game/Input/Actions/)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "add_input_action", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Input Action created: ${(res.data as any).path}`);
    }
  );

  server.tool(
    "ue_add_input_mapping",
    "Add a key mapping to an Input Mapping Context",
    {
      mapping_context: z.string().describe("Path to the Input Mapping Context asset"),
      action: z.string().describe("Path to the Input Action asset"),
      key: z.string().describe("Key name: SpaceBar, W, A, S, D, MouseX, MouseY, Gamepad_LeftStick_X, etc."),
      modifiers: z.array(z.string()).optional().describe("Input modifiers: Negate, Swizzle, DeadZone, etc."),
      triggers: z.array(z.string()).optional().describe("Trigger types: Down, Pressed, Released, Hold, Tap"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "add_input_mapping", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Mapping added: ${params.key} → ${params.action}`);
    }
  );

  server.tool(
    "ue_list_input_actions",
    "List all Input Actions and Mapping Contexts in the project",
    {},
    async () => {
      const res = await callBridge(bridgeUrl, "list_input_actions");
      if (!res.success) return errorResponse(res.error!);
      return jsonResponse(res.data);
    }
  );
}
