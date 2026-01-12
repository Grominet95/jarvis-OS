import type { LlamaChatSession } from 'node-llama-cpp'

import {
  type LLMDutyParams,
  type LLMDutyInitParams,
  type LLMDutyResult,
  LLMDuty,
  DEFAULT_INIT_PARAMS
} from '@/core/llm-manager/llm-duty'
import { LogHelper } from '@/helpers/log-helper'
import { CONVERSATION_LOGGER, LLM_MANAGER, LLM_PROVIDER } from '@/core'
import { LLMProviders, LLMDuties } from '@/core/llm-manager/types'
import { LLM_PROVIDER as LLM_PROVIDER_NAME } from '@/constants'

export interface ActionRecognitionLLMDutyParams extends LLMDutyParams {
  data: {
    existingContextName: string | null
  }
}

const JSON_KEY_RESPONSE = 'intent_name'

export class ActionRecognitionLLMDuty extends LLMDuty {
  private static instance: ActionRecognitionLLMDuty
  private static session: LlamaChatSession = null as unknown as LlamaChatSession
  protected readonly systemPrompt: LLMDutyParams['systemPrompt'] = null
  protected readonly name = 'Action Recognition LLM Duty'
  protected input: LLMDutyParams['input'] = null
  protected data = {
    existingContextName: null
  } as ActionRecognitionLLMDutyParams['data']

  constructor(params: ActionRecognitionLLMDutyParams) {
    super()

    if (!ActionRecognitionLLMDuty.instance) {
      LogHelper.title(this.name)
      LogHelper.success('New instance')

      ActionRecognitionLLMDuty.instance = this
    }

    this.input = params.input
    this.data = params.data

    this.systemPrompt = `INTENT MATCHING PROMPT:
You are tasked with matching user utterances to their corresponding intents. Your goal is to identify the most probable intent from a given utterance, considering the context of the conversation when necessary.
Once you have identified the intent, you must check again according to the sample whether the intent is correct or not.
It is better to not match any intent than to match the wrong intent.

INTENT FORMAT:
The intent format is "{domain}.{skill}.{action}", for example, "food_drink.advisor.suggest".
The intent format should always contain the domain, skill, and action.

INTENT LIST:
The valid intents are listed below. You must only respond with one of the intents from this list. Do not generate new intents.

${LLM_MANAGER.llmActionsClassifierContent}

RESPONSE GUIDELINES:
* If the utterance matches one of the intents, respond with the corresponding intent in the format "{domain}.{skill}.{action}".
* If the utterance does not match any of the intents, respond with { "${JSON_KEY_RESPONSE}": "not_found" }. Do not make up new intents by yourself.`
  }

  public async init(
    params: LLMDutyInitParams = DEFAULT_INIT_PARAMS
  ): Promise<void> {
    if (LLM_PROVIDER_NAME === LLMProviders.Local) {
      if (!ActionRecognitionLLMDuty.session || params.force) {
        LogHelper.title(this.name)
        LogHelper.info('Initializing...')

        try {
          const { LlamaChatSession } = await Function(
            'return import("node-llama-cpp")'
          )()

          /**
           * Dispose the previous session and sequence
           * to give space for the new one
           */
          if (params.force) {
            ActionRecognitionLLMDuty.session.dispose({ disposeSequence: true })
            LogHelper.info('Session disposed')
          }

          ActionRecognitionLLMDuty.session = new LlamaChatSession({
            contextSequence: LLM_MANAGER.context.getSequence(),
            autoDisposeSequence: true,
            systemPrompt: this.systemPrompt
          }) as LlamaChatSession

          LogHelper.success('Initialized')
        } catch (e) {
          LogHelper.title(this.name)
          LogHelper.error(`Failed to initialize: ${e}`)
        }
      }
    }
  }

  public async execute(): Promise<LLMDutyResult | null> {
    LogHelper.title(this.name)
    LogHelper.info('Executing...')

    try {
      let prompt = `Utterance: "${this.input}"`

      if (this.data.existingContextName) {
        prompt += `\nPrevious intent context: "${this.data.existingContextName}"`
      } else {
        prompt += '\nPrevious intent context: no context provided.'
      }

      const completionParams = {
        dutyType: LLMDuties.ActionRecognition,
        systemPrompt: this.systemPrompt as string,
        data: {
          [JSON_KEY_RESPONSE]: {
            type: 'string'
          }
        }
      }
      let completionResult

      if (LLM_PROVIDER_NAME === LLMProviders.Local) {
        const history = await LLM_MANAGER.loadHistory(
          CONVERSATION_LOGGER,
          ActionRecognitionLLMDuty.session,
          { nbOfLogsToLoad: 8 }
        )

        ActionRecognitionLLMDuty.session.setChatHistory(history)

        completionResult = await LLM_PROVIDER.prompt(prompt, {
          ...completionParams,
          session: ActionRecognitionLLMDuty.session,
          maxTokens: LLM_MANAGER.context.contextSize
        })
      } else {
        completionResult = await LLM_PROVIDER.prompt(prompt, completionParams)
      }

      if (
        completionResult?.output &&
        typeof completionResult.output === 'object' &&
        completionResult.output[JSON_KEY_RESPONSE]
      ) {
        let intent = completionResult.output[JSON_KEY_RESPONSE] as string
        intent = intent.toLowerCase().replace(/\s/g, '')
        ;(completionResult.output[JSON_KEY_RESPONSE] as string) = intent
      }

      LogHelper.title(this.name)
      LogHelper.success('Duty executed')
      LogHelper.success(`Prompt — ${prompt}`)
      LogHelper.success(`Output — ${JSON.stringify(completionResult?.output)}
usedInputTokens: ${completionResult?.usedInputTokens}
usedOutputTokens: ${completionResult?.usedOutputTokens}`)

      return completionResult as unknown as LLMDutyResult
    } catch (e) {
      LogHelper.title(this.name)
      LogHelper.error(`Failed to execute: ${e}`)
    }

    return null
  }
}
