import type { ActionFunction } from '@sdk/types'
import { leon } from '@sdk/leon'
import { Network } from '@sdk/network'

export const run: ActionFunction = async function (params) {
  const targetLanguage = params.slots.target_language.resolution.value
  const textToTranslate = params.new_utterance
  const network = new Network({
    baseURL: `${process.env['LEON_HOST']}:${process.env['LEON_PORT']}/api/v1`
  })
  const systemPrompt = `You are an AI system that translates a given text to "${targetLanguage}" by auto-detecting the source language. You do not add any context to your response.`
  const prompt = `Text to translate: "${textToTranslate}"`

  /**
   * TODO: create SDK methods to handle request and response for every LLM duty
   */
  const response = await network.request({
    url: '/llm-inference',
    method: 'POST',
    data: {
      dutyType: 'custom',
      input: prompt,
      data: {
        systemPrompt
      }
    }
  })
  const translation = response.data.output

  await leon.answer({
    key: 'translate',
    data: {
      output: translation
    }
  })
}
