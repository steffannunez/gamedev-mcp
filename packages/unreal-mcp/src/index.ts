import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { registerSceneTools } from "./tools/scene.js";
import { registerAssetTools } from "./tools/assets.js";
import { registerBlueprintTools } from "./tools/blueprint.js";
import { registerDebugTools } from "./tools/debug.js";
import { registerMaterialTools } from "./tools/materials.js";
import { registerCppTools } from "./tools/cpp.js";
import { registerInputTools } from "./tools/input.js";
import { registerLightingTools } from "./tools/lighting.js";

const UNREAL_BRIDGE_URL = process.env.UNREAL_BRIDGE_URL ?? "http://localhost:3031";

const server = new McpServer({
  name: "unreal-engine-mcp",
  version: "1.0.0",
});

// Register all tool groups
registerSceneTools(server, UNREAL_BRIDGE_URL);
registerAssetTools(server, UNREAL_BRIDGE_URL);
registerBlueprintTools(server, UNREAL_BRIDGE_URL);
registerDebugTools(server, UNREAL_BRIDGE_URL);
registerMaterialTools(server, UNREAL_BRIDGE_URL);
registerCppTools(server, UNREAL_BRIDGE_URL);
registerInputTools(server, UNREAL_BRIDGE_URL);
registerLightingTools(server, UNREAL_BRIDGE_URL);

const transport = new StdioServerTransport();
await server.connect(transport);
