import fs from 'node:fs'

import { path as ffprobePath } from '@ffprobe-installer/ffprobe'

import { LogHelper } from '@/helpers/log-helper'

export default async () => {
  try {
    LogHelper.info('\nSetting ffprobe executable permissions...')

    await fs.promises.chmod(ffprobePath, 0o755)

    LogHelper.success(
      `ffprobe permissions set to 755 for path "${ffprobePath}"`
    )
  } catch (e) {
    LogHelper.warning(`Failed to set ffprobe permissions: ${e}`)
  }
}
