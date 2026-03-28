import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, textResponse, errorResponse, jsonResponse } from "@gamedev-mcp/shared";
import { PERFORMANCE_TARGETS } from "@gamedev-mcp/shared";

export function registerDebugTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "ue_get_render_stats",
    "Get current FPS, frame time, draw calls, triangle count, and memory usage",
    {},
    async () => {
      const res = await callBridge(bridgeUrl, "get_stats");
      if (!res.success) return errorResponse(res.error!);
      const stats = res.data as any;
      const target = PERFORMANCE_TARGETS.pc_target;

      // Add status indicators
      const report = {
        ...stats,
        _targets: {
          fps: `${stats.fps}/${target.fps} ${stats.fps >= target.fps ? "OK" : "BELOW TARGET"}`,
          draw_calls: `${stats.draw_calls}/${target.draw_calls} ${stats.draw_calls <= target.draw_calls ? "OK" : "OVER BUDGET"}`,
          gpu_memory: `${stats.gpu_memory_mb}/${target.gpu_memory_mb}MB ${stats.gpu_memory_mb <= target.gpu_memory_mb ? "OK" : "OVER BUDGET"}`,
        },
      };
      return jsonResponse(report);
    }
  );

  server.tool(
    "ue_run_play",
    "Enter, exit, or pause Play-In-Editor mode",
    {
      action: z.enum(["play", "stop", "pause"]).describe("Play mode action"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "run_play_mode", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Play mode: ${params.action}`);
    }
  );

  server.tool(
    "ue_run_console_command",
    "Execute an Unreal console command (stat gpu, stat fps, etc.)",
    {
      command: z.string().describe("Console command to execute"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "run_console_command", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Executed: ${params.command}\n${(res.data as any).output ?? ""}`);
    }
  );

  server.tool(
    "ue_get_log",
    "Get recent lines from the Unreal output log, optionally filtered by category",
    {
      lines: z.number().optional().describe("Number of recent lines to fetch (default 50)"),
      category_filter: z.string().optional().describe("Filter by log category: LogTemp, LogBlueprintUserMessages, LogPhysics, etc."),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "get_log", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse((res.data as any).log);
    }
  );

  server.tool(
    "ue_take_screenshot",
    "Capture a screenshot of the current editor viewport",
    {
      output_path: z.string().optional().describe("Where to save the screenshot (default: project Saved/ folder)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "take_screenshot", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Screenshot saved: ${(res.data as any).path}`);
    }
  );
}
