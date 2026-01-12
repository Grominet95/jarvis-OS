/**
 * Contain common/shared types that are universal across the project
 * and cannot be placed in the respective core nodes
 */

/**
 * Language
 */

/**
 * ISO 639-1 (Language codes) - ISO 3166-1 (Country Codes)
 * @see https://www.iso.org/iso-639-language-codes.html
 * @see https://www.iso.org/iso-3166-country-codes.html
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { default: LANG_CONFIGS } = await import('@@/core/langs.json', {
  with: { type: 'json' }
})

export type Languages = typeof LANG_CONFIGS
export type LongLanguageCode = keyof Languages
export type Language = Languages[LongLanguageCode]
export type ShortLanguageCode = Language['short']

/**
 * System
 */

export enum OSTypes {
  Windows = 'windows',
  MacOS = 'macos',
  Linux = 'linux',
  Unknown = 'unknown'
}
export enum CPUArchitectures {
  X64 = 'x64',
  ARM64 = 'arm64'
}

/**
 * Logger
 */

export interface MessageLog {
  who: 'owner' | 'leon'
  sentAt: number
  message: string
}
