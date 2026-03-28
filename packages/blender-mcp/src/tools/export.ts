import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse } from "@gamedev-mcp/shared";

export function registerExportTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "bl_export_fbx",
    "Export selection or scene as FBX for Unreal Engine import",
    {
      output_path: z.string().describe("Absolute path for the exported .fbx file"),
      selected_only: z.boolean().optional().describe("Export only selected objects (default true)"),
      apply_modifiers: z.boolean().optional().describe("Apply modifiers before export (default true)"),
      include_animation: z.boolean().optional().describe("Include animations (default false)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "export_fbx", params);
      if (!res.success) return errorResponse(res.error!);
      const data = res.data as any;
      return textResponse(`Exported FBX: ${data.exported_to} (${(data.file_size_bytes / 1024).toFixed(1)} KB)`);
    }
  );

  server.tool(
    "bl_export_gltf",
    "Export as GLTF/GLB format",
    {
      output_path: z.string().describe("Absolute path for the exported file (.gltf or .glb)"),
      format: z.enum(["GLTF_SEPARATE", "GLTF_EMBEDDED", "GLB"]).optional().describe("Export format (default GLB)"),
      selected_only: z.boolean().optional().describe("Export only selected objects (default true)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "export_gltf", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Exported: ${(res.data as any).exported_to}`);
    }
  );

  server.tool(
    "bl_import_file",
    "Import a 3D file into Blender (FBX, OBJ, GLTF, STL)",
    {
      file_path: z.string().describe("Absolute path to the file to import"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "import_file", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Imported: ${(res.data as any).objects_imported} objects from ${params.file_path}`);
    }
  );
}
