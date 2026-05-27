/**
 * Frontend renderers for ExternalToolset tools.
 *
 * Each entry maps a backend ``external_tools`` ToolDefinition.name to a React
 * component that renders the prompt UI (e.g. multi-choice picker) and supplies
 * the result back via ``addToolResult``. The tool name must match
 * ``backend/customer/tools/__init__.py`` ``TOOLBOX_AGENT_CONFIG[...]
 * .external_tools[i].name`` — verified by check_customer_config.py.
 *
 * Render component contract:
 *   - Receive ``input`` (the tool's structured args) and ``onResult`` callback.
 *   - When the user picks/answers, call ``onResult(output)``. The output is
 *     forwarded verbatim to the model as the tool's return value.
 */

import type { ComponentType } from 'react'

export interface ExternalToolRenderProps {
  toolCallId: string
  input: unknown
  onResult: (output: unknown) => void
}

export interface ExternalToolRenderer {
  toolName: string
  render: ComponentType<ExternalToolRenderProps>
}

export const externalToolRenderers: ExternalToolRenderer[] = []

export function findExternalToolRenderer(
  toolName: string
): ComponentType<ExternalToolRenderProps> | null {
  const entry = externalToolRenderers.find((r) => r.toolName === toolName)
  return entry ? entry.render : null
}
