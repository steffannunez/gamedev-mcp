import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse, jsonResponse } from "@gamedev-mcp/shared";

export function registerBlueprintTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "ue_create_blueprint",
    "Create a new Blueprint class from a parent class",
    {
      parent_class: z.string().describe("Parent class: Actor, Character, Pawn, PlayerController, GameModeBase, ActorComponent, etc."),
      name: z.string().describe("Blueprint name (will add BP_ prefix if missing)"),
      save_path: z.string().describe("Content path, e.g. /Game/Blueprints/"),
    },
    async (params) => {
      const name = params.name.startsWith("BP_") ? params.name : `BP_${params.name}`;
      const res = await callBridge(bridgeUrl, "create_blueprint", { ...params, name });
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Blueprint created: ${(res.data as any).path}`);
    }
  );

  server.tool(
    "ue_compile_blueprints",
    "Compile all Blueprints in the project and report errors",
    {},
    async () => {
      const res = await callBridge(bridgeUrl, "compile_blueprints");
      if (!res.success) return errorResponse(res.error!);
      const data = res.data as any;
      if (data.errors?.length > 0) {
        return textResponse(
          `Compiled with ${data.errors.length} errors:\n` +
          data.errors.map((e: any) => `  - ${e.blueprint}: ${e.message}`).join("\n")
        );
      }
      return textResponse(`All Blueprints compiled successfully (${data.count} total)`);
    }
  );

  server.tool(
    "ue_add_bp_variable",
    "Add a variable to a Blueprint",
    {
      blueprint_path: z.string().describe("Path to the Blueprint asset"),
      var_name: z.string().describe("Variable name"),
      var_type: z.string().describe("Type: Boolean, Integer, Float, String, Vector, Rotator, Transform, or class/struct path"),
      default_value: z.unknown().optional().describe("Default value"),
      expose_on_spawn: z.boolean().optional().describe("Expose as spawn parameter"),
      replicated: z.boolean().optional().describe("Enable replication"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "add_bp_variable", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Variable '${params.var_name}' (${params.var_type}) added to Blueprint`);
    }
  );

  server.tool(
    "ue_list_blueprints",
    "List all Blueprints in a directory with their parent class and compile status",
    {
      path: z.string().optional().describe("Content path to search, defaults to /Game/"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "list_blueprints", params);
      if (!res.success) return errorResponse(res.error!);
      return jsonResponse(res.data);
    }
  );
}
