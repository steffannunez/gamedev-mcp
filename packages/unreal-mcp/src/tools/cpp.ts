import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse } from "@gamedev-mcp/shared";

export function registerCppTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "ue_create_cpp_class",
    "Create a new C++ class using the Unreal class wizard",
    {
      class_name: z.string().describe("Class name without prefix (prefix is added by UE)"),
      parent_class: z.string().describe("Parent: Actor, Character, Pawn, ActorComponent, SceneComponent, Object, GameModeBase, PlayerController, AIController"),
      module_name: z.string().optional().describe("Module to add the class to (defaults to project module)"),
      public_header: z.boolean().optional().describe("Place in Public/ folder (default true)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "create_cpp_class", params);
      if (!res.success) return errorResponse(res.error!);
      const data = res.data as any;
      return textResponse(
        `C++ class created:\n  Header: ${data.header_path}\n  Source: ${data.source_path}\n\nRecompile needed — use ue_compile_project`
      );
    }
  );

  server.tool(
    "ue_compile_project",
    "Trigger a Hot Reload / Live Coding compile of the C++ project",
    {},
    async () => {
      const res = await callBridge(bridgeUrl, "compile_project");
      if (!res.success) return errorResponse(res.error!);
      const data = res.data as any;
      if (data.errors?.length > 0) {
        return textResponse(
          `Compilation failed with ${data.errors.length} errors:\n` +
          data.errors.map((e: string) => `  - ${e}`).join("\n")
        );
      }
      return textResponse(`Compilation successful (${data.duration_ms}ms)`);
    }
  );

  server.tool(
    "ue_read_cpp_file",
    "Read the contents of a C++ source or header file from the project",
    {
      file_path: z.string().describe("Relative path from Source/, e.g. MyProject/Public/Components/HealthComponent.h"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "read_cpp_file", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse((res.data as any).content);
    }
  );
}
