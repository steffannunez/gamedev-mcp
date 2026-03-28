import type { BridgeRequest, BridgeResponse } from "./types.js";

/**
 * Send a command to a local Python bridge (Unreal or Blender).
 */
export async function callBridge(
  bridgeUrl: string,
  command: string,
  params: Record<string, unknown> = {}
): Promise<BridgeResponse> {
  const request: BridgeRequest = {
    command,
    params,
    request_id: crypto.randomUUID(),
  };

  try {
    const res = await fetch(bridgeUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });

    if (!res.ok) {
      return {
        success: false,
        data: null,
        error: `Bridge returned HTTP ${res.status}: ${res.statusText}`,
        request_id: request.request_id,
      };
    }

    const data = await res.json();
    return {
      success: true,
      data,
      request_id: request.request_id,
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      success: false,
      data: null,
      error: `Bridge connection failed: ${message}. Is the editor running with the MCP bridge plugin?`,
      request_id: request.request_id,
    };
  }
}

/**
 * Format MCP tool response content.
 */
export function textResponse(text: string) {
  return { content: [{ type: "text" as const, text }] };
}

/**
 * Format a successful JSON response.
 */
export function jsonResponse(data: unknown) {
  return textResponse(JSON.stringify(data, null, 2));
}

/**
 * Format an error response.
 */
export function errorResponse(message: string) {
  return textResponse(`ERROR: ${message}`);
}

/**
 * Validate that a name follows UE naming conventions.
 */
export function validateAssetName(name: string, expectedPrefix?: string): string | null {
  if (!name || name.trim().length === 0) {
    return "Asset name cannot be empty";
  }
  if (/[^a-zA-Z0-9_]/.test(name)) {
    return "Asset name can only contain letters, numbers, and underscores";
  }
  if (expectedPrefix && !name.startsWith(expectedPrefix)) {
    return `Asset name should start with '${expectedPrefix}' (e.g., ${expectedPrefix}${name})`;
  }
  return null;
}
