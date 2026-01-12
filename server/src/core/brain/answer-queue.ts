import { LogHelper } from '@/helpers/log-helper'

/**
 * The answer queue is used to handle multiple answers in a row.
 * It helps to save the answers and process them one by one.
 * This queue became necessary because answers have more logic now and may need
 * more time to be processed. For instance, the LLM NLG model can take a few seconds to generate a text.
 * So, we need to wait for the previous answer to be processed before sending the next one.
 */
export class AnswerQueue<T> {
  public answers: T[]
  public isProcessing: boolean

  constructor() {
    this.answers = []
    this.isProcessing = false
  }

  public push(answer: T): void {
    this.answers.push(answer)
    LogHelper.title('Answer Queue')
    LogHelper.info(`New answer added to the queue: ${JSON.stringify(answer)}`)
  }

  public pop(): T | undefined {
    const nextAnswer = this.answers.shift()
    LogHelper.title('Answer Queue')
    LogHelper.info(
      `Answer popped from the queue: ${JSON.stringify(nextAnswer)}`
    )
    return nextAnswer
  }

  public clear(): void {
    this.answers = []
    LogHelper.title('Answer Queue')
    LogHelper.info('Answer queue has been cleared')
  }

  public isEmpty(): boolean {
    return this.answers.length === 0
  }
}
