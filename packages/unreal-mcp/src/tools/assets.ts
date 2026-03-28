import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse, jsonResponse } from "@gamedev-mcp/shared";

export function registerAssetTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "ue_import_asset",
    "Import a .fbx, .obj, or .png file into the UE project content folder",
    {
      file_path: z.string().describe("Absolute path to the source file"),
      destination: z.string().describe("Content path, e.g. /Game/Assets/Characters/"),
      asset_name: z.string().optional().describe("Override name for the imported asset"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "import_asset", params);
      if (!res.success) return errorResponse(res.error!);
      const data = res.data as any;
      return textResponse(
        `Imported: ${data.asset_path}\nType: ${data.asset_type}` +
        (data.warnings?.length ? `\nWarnings: ${data.warnings.join(", ")}` : "")
      );
    }
  );

  server.tool(
    "ue_list_assets",
    "List assets in a content directory",
    {
      path: z.string().describe("Content path to list, e.g. /Game/Assets/"),
      recursive: z.boolean().optional().describe("Include subdirectories"),
      type_filter: z.string().optional().describe("Filter by asset type: StaticMesh, SkeletalMesh, Texture2D, Material, Blueprint, etc."),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "list_assets", params);
      if (!res.success) return errorResponse(res.error!);
      return jsonResponse(res.data);
    }
  );

  server.tool(
    "ue_delete_asset",
    "Delete an asset from the content browser (moves to trash)",
    {
      asset_path: z.string().describe("Full asset path, e.g. /Game/Assets/SM_Rock_01"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "delete_asset", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Deleted: ${params.asset_path}`);
    }
  );

  server.tool(
    "ue_duplicate_asset",
    "Duplicate an existing asset to a new path",
    {
      source_path: z.string().describe("Source asset path"),
      destination_path: z.string().describe("Destination path including new name"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "duplicate_asset", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Duplicated to: ${params.destination_path}`);
    }
  );
}
