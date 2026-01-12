import path from 'node:path'
import fs from 'node:fs'

import type { ShortLanguageCode } from '@/types'
import { GLOBAL_DATA_PATH } from '@/constants'

/**
 * Files
 */
export async function isFileEmpty(path: string): Promise<boolean> {
  return (await fs.promises.readFile(path)).length === 0
}

/**
 * Paths
 */
export function getGlobalEntitiesPath(lang: ShortLanguageCode): string {
  return path.join(GLOBAL_DATA_PATH, lang, 'global-entities')
}
export function getGlobalResolversPath(lang: ShortLanguageCode): string {
  return path.join(GLOBAL_DATA_PATH, lang, 'global-resolvers')
}

/**
 * Misc
 */
const TCP_SERVER_WARNINGS_TO_IGNORE = [
  'RuntimeWarning:',
  'FutureWarning:',
  'UserWarning:',
  '<00:00',
  '00:00<',
  'CUDNN_STATUS_NOT_SUPPORTED',
  'cls.seq_relationship.weight',
  'ALSA lib',
  'jack',
  'server request channel'
]
export function shouldIgnoreTCPServerError(error: string): boolean {
  return TCP_SERVER_WARNINGS_TO_IGNORE.some((warning) =>
    error.toLowerCase().includes(warning.toLowerCase())
  )
}
