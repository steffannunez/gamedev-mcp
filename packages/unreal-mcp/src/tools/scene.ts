import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { callBridge, jsonResponse, errorResponse, textResponse } from "@gamedev-mcp/shared";

export function registerSceneTools(server: McpServer, bridgeUrl: string) {
  server.tool(
    "ue_read_scene",
    "Get full scene hierarchy — all actors with their components, locations, and properties",
    {},
    async () => {
      const res = await callBridge(bridgeUrl, "read_scene");
      if (!res.success) return errorResponse(res.error!);
      return jsonResponse(res.data);
    }
  );

  server.tool(
    "ue_create_actor",
    "Spawn an actor in the current level at a given location",
    {
      class_path: z.string().describe("UE class path, e.g. /Script/Engine.StaticMeshActor"),
      name: z.string().describe("Label for the actor in the editor"),
      location: z.tuple([z.number(), z.number(), z.number()]).describe("[X, Y, Z] in cm"),
      rotation: z.tuple([z.number(), z.number(), z.number()]).optional().describe("[Pitch, Yaw, Roll] in degrees"),
      scale: z.tuple([z.number(), z.number(), z.number()]).optional().describe("[X, Y, Z] scale"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "create_actor", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Actor created: ${(res.data as any).name} → ${(res.data as any).id}`);
    }
  );

  server.tool(
    "ue_delete_actor",
    "Delete an actor from the current level by name or path",
    {
      actor_name: z.string().describe("Actor label or path to delete"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "delete_actor", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Deleted actor: ${params.actor_name}`);
    }
  );

  server.tool(
    "ue_set_property",
    "Set a property on an actor or component",
    {
      actor_name: z.string().describe("Actor label or path"),
      property_path: z.string().describe("Property path, e.g. 'StaticMeshComponent.StaticMesh'"),
      value: z.unknown().describe("Value to set"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "set_property", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Property set: ${params.actor_name}.${params.property_path}`);
    }
  );

  server.tool(
    "ue_add_component",
    "Add a component to an existing actor",
    {
      actor_name: z.string().describe("Target actor label or path"),
      component_class: z.string().describe("Component class, e.g. StaticMeshComponent, PointLightComponent"),
      component_name: z.string().optional().describe("Name for the new component"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "add_component", params);
      if (!res.success) return errorResponse(res.error!);
      return textResponse(`Component ${params.component_class} added to ${params.actor_name}`);
    }
  );

  server.tool(
    "ue_query_actors",
    "Search actors by class, tag, or name pattern",
    {
      class_filter: z.string().optional().describe("Filter by class name"),
      tag: z.string().optional().describe("Filter by actor tag"),
      name_pattern: z.string().optional().describe("Filter by name (supports * wildcards)"),
    },
    async (params) => {
      const res = await callBridge(bridgeUrl, "query_actors", params);
      if (!res.success) return errorResponse(res.error!);
      return jsonResponse(res.data);
    }
  );
}
