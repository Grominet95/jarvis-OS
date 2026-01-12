import path from 'node:path'
import fs from 'node:fs'

import type { MessageLog } from '@/types'
import { LOGS_PATH } from '@/constants'
import { LogHelper } from '@/helpers/log-helper'

interface ConversationLoggerSettings {
  loggerName: string
  fileName: string
  nbOfLogsToKeep: number
  nbOfLogsToLoad: number
}

interface LoadParams {
  nbOfLogsToLoad?: number
}

/**
 * The goal of this class is to log the conversation data between the
 * owner and Leon.
 * This data is saved on the owner's machine.
 * This data can then be used to provide more context to the LLM to achieve
 * better results.
 */
export class ConversationLogger {
  private readonly settings: ConversationLoggerSettings
  private readonly conversationLogPath: string

  get loggerName(): string {
    return this.settings.loggerName
  }

  constructor(settings: ConversationLoggerSettings) {
    LogHelper.title(settings.loggerName)
    LogHelper.success('New instance')

    this.settings = settings
    this.conversationLogPath = path.join(LOGS_PATH, this.settings.fileName)
  }

  private async createConversationLogFile(): Promise<void> {
    try {
      if (!fs.existsSync(this.conversationLogPath)) {
        await fs.promises.writeFile(this.conversationLogPath, '[]', 'utf-8')
      }
    } catch (e) {
      LogHelper.title(this.settings.loggerName)
      LogHelper.error(`Failed to create conversation log file: ${e})`)
    }
  }

  private async getAllLogs(): Promise<MessageLog[]> {
    try {
      let conversationLog: MessageLog[] = []

      if (fs.existsSync(this.conversationLogPath)) {
        conversationLog = JSON.parse(
          await fs.promises.readFile(this.conversationLogPath, 'utf-8')
        )
      } else {
        await this.createConversationLogFile()
      }

      return conversationLog
    } catch (e) {
      LogHelper.title(this.settings.loggerName)
      LogHelper.error(`Failed to get conversation log: ${e})`)
    }

    return []
  }

  public async push(newRecord: Omit<MessageLog, 'sentAt'>): Promise<void> {
    try {
      const conversationLogs = await this.getAllLogs()

      if (conversationLogs.length >= this.settings.nbOfLogsToKeep) {
        conversationLogs.shift()
      }

      conversationLogs.push({
        ...newRecord,
        sentAt: Date.now()
      })

      await fs.promises.writeFile(
        this.conversationLogPath,
        JSON.stringify(conversationLogs, null, 2),
        'utf-8'
      )
    } catch (e) {
      LogHelper.title(this.settings.loggerName)
      LogHelper.error(`Failed to push new record: ${e})`)
    }
  }

  public async load(params?: LoadParams): Promise<MessageLog[]> {
    try {
      const conversationLog = await this.getAllLogs()
      const nbOfLogsToLoad =
        params?.nbOfLogsToLoad || this.settings.nbOfLogsToLoad

      return conversationLog.slice(-nbOfLogsToLoad)
    } catch (e) {
      LogHelper.title(this.settings.loggerName)
      LogHelper.error(`Failed to load conversation log: ${e})`)
    }

    return []
  }

  public async clear(): Promise<void> {
    try {
      await fs.promises.writeFile(this.conversationLogPath, '[]', 'utf-8')
    } catch (e) {
      LogHelper.title(this.settings.loggerName)
      LogHelper.error(`Failed to clear conversation log: ${e})`)
    }
  }
}
