export interface TrustedChat { id: string; mode: 'private' | 'group'; owner?: boolean }
export class LibraryError extends Error { code: string; outcome: string; causeCode?: string }
export const LIBRARY_TOOL_NAMES: readonly string[];
export interface MainLibraryAdapter {
  isOwner(chatId: string): boolean;
  call(chatId: string, operation: 'search' | 'read' | 'write' | 'edit', args: Record<string, unknown>, context?: { signal?: AbortSignal }): Promise<Record<string, unknown>>;
  health(chatId: string, context?: { signal?: AbortSignal }): Promise<Record<string, unknown>>;
}
export function createMainLibraryAdapter(options: {
  chats: TrustedChat[]; url?: string | null; probeIdentifier?: string;
  fetchImpl?: typeof fetch; timeoutMs?: number; maxResponseBytes?: number;
}): MainLibraryAdapter;
export function registerOwnerLibraryTools(options: {
  agentCtx: { tools: { register(tool: unknown): unknown } }; agent: unknown; chatId: string;
  adapter: MainLibraryAdapter; defineTool: (definition: any) => unknown;
  isActive: (chatId: string) => boolean;
}): string[];
