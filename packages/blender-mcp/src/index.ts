import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { registerMeshTools } from "./tools/mesh.js";
import { registerMaterialTools } from "./tools/materials.js";
import { registerExportTools } from "./tools/export.js";
import { registerRigTools } from "./tools/rig.js";
import { registerSceneTools } from "./tools/scene.js";
import { registerModifierTools } from "./tools/modifiers.js";

const BLENDER_BRIDGE_URL = process.env.BLENDER_BRIDGE_URL ?? "http://localhost:3032";

const server = new McpServer({
  name: "blender-mcp",
  version: "1.0.0",
});

registerMeshTools(server, BLENDER_BRIDGE_URL);
registerMaterialTools(server, BLENDER_BRIDGE_URL);
registerExportTools(server, BLENDER_BRIDGE_URL);
registerRigTools(server, BLENDER_BRIDGE_URL);
registerSceneTools(server, BLENDER_BRIDGE_URL);
registerModifierTools(server, BLENDER_BRIDGE_URL);

const transport = new StdioServerTransport();
await server.connect(transport);
