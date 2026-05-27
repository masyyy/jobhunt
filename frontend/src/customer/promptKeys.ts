/**
 * Customer-defined seed prompt keys.
 *
 * Each member identifies a backend seed prompt (markdown file under
 * backend/prompts/seeds/{value}.md) that the chat endpoint can inject as
 * the first user message of a new conversation.
 *
 * Pass the value via Chat's `seedPromptKey` prop. Must stay in sync with
 * backend/customer/prompt_keys.py — verified by check_customer_config.py.
 */

export const PromptKey = {} as const

export type PromptKey = (typeof PromptKey)[keyof typeof PromptKey]
