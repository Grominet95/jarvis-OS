import type { ActionFunction } from '@sdk/types'
import { leon } from '@sdk/leon'
import { Network } from '@sdk/network'

export const run: ActionFunction = async function (params) {
  const ownerMessage = params.new_utterance
  const network = new Network({
    baseURL: `${process.env['LEON_HOST']}:${process.env['LEON_PORT']}/api/v1`
  })

  /**
   * TODO: create SDK methods to handle request and response for every LLM duty
   */
  const response = await network.request({
    url: '/llm-inference',
    method: 'POST',
    data: {
      dutyType: 'conversation',
      input: ownerMessage,
      data: {
        // Load/follow the main conversation history
        useLoopHistory: false
      }
    }
  })

  await leon.answer({
    key: 'answer_message',
    data: {
      output: response.data.output
    }
  })
}
